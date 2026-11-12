"""Grid rules for the hybrid-view prototype; independent of drawing and SDL."""
from collections import deque
from dataclasses import dataclass
import math
import random
from transitions import Machine

COLS, ROWS = 31, 23
# 쿼터뷰 지면의 반쪽 타일 크기. 렌더링과 이동 속도 계산이 같은 투영을 사용한다.
HALF_TILE_W, HALF_TILE_H = 32, 16
# 64×64 원본·pivot(32,54)의 지지 발 후보를 수동 비교한 근사 보폭(px/주기).
# 걷기 2프레임에 약 5~7px, 달리기 2프레임에 약 8~10px의 후방 이동을 기준으로 한다.
# 발 식별·접지 메타데이터가 없어 완전한 발 고정값은 아니다.
WALK_CYCLE_PX, RUN_CYCLE_PX = 24., 40.
# 기존 대각선 통로의 이동 속도를 복구한다. 보행 주기는 각 클립의 보폭 메타로 조절한다.
WALK_SPEED = 2.5 * math.hypot(HALF_TILE_W, HALF_TILE_H)
RUN_SPEED = 4.1 * math.hypot(HALF_TILE_W, HALF_TILE_H)
PLAYER_HALF_SIZE = .21  # 미로 충돌 상자의 반폭(격자 단위). 함정방 반지름과 별개다.
MOVE_EPSILON = 1e-7  # 벽 면과 겹치지 않도록 남기는 격자 단위의 미세한 간격.
BASE_SIGHT_RADIUS, TORCH_SIGHT_RADIUS = 5.5, 7
DIRECTIONS = ((0, 1), (-1, 0), (1, 0), (0, -1))  # down, left, right, up
DIAGONAL_FACINGS = ('sw', 'nw', 'se', 'ne')
ATTACK_COOLDOWN, DEFAULT_ATTACK_HIT = .75, .233
PHASES = ('낮', '밤', '새벽')
# 플레이테스트용 기본값. 최종 시간·연출 강도는 조정할 수 있다.
PHASE_SECONDS, PHASE_WARNING_SECONDS = 60.0, 5.0
SHIFT_SECONDS, SHIFT_SWAP_AT = .6, .3
TRAP_LENGTH, TRAP_HALF_WIDTH, TRAP_HEIGHT = 9.0, 1.6, 3.0
TRAP_LATERAL, BLADE_RADIUS, PLAYER_RADIUS = 1.1, .34, .20
TRAP_PLANES = (.30, .58, .82)


def project(x, y):
    """카메라와 확대를 제외한 논리 화면의 지면 좌표로 바꾼다."""
    return HALF_TILE_W*(x-y), HALF_TILE_H*(x+y)


ATTACK_FORWARD = {facing: project(*direction) for facing, direction in zip(DIAGONAL_FACINGS, DIRECTIONS)}
ATTACK_FORWARD.update(n=(0, -1), s=(0, 1), w=(-1, 0), e=(1, 0))


def blade_position(time, index):
    return math.sin(time*2.1+index*2)*.85


def make_maze(seed):
    rng = random.Random(seed)
    grid = [[1] * COLS for _ in range(ROWS)]
    grid[1][1] = 0
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        choices = [(x+dx*2, y+dy*2, dx, dy) for dx, dy in DIRECTIONS
                   if 0 < x+dx*2 < COLS-1 and 0 < y+dy*2 < ROWS-1
                   and grid[y+dy*2][x+dx*2]]
        if not choices:
            stack.pop()
            continue
        nx, ny, dx, dy = rng.choice(choices)
        grid[y+dy][x+dx] = grid[ny][nx] = 0
        stack.append((nx, ny))
    # Add loops without carving outside the intended maze boundaries.
    walls = [(x, y) for y in range(1, ROWS-1) for x in range(1, COLS-1)
             if grid[y][x] and ((grid[y-1][x] == grid[y+1][x] == 0)
                               != (grid[y][x-1] == grid[y][x+1] == 0))]
    for x, y in rng.sample(walls, min(18, len(walls))):
        grid[y][x] = 0
    return grid


def distances(grid, start):
    result, queue = {start: 0}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRECTIONS:
            cell = x+dx, y+dy
            if 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS and not grid[cell[1]][cell[0]] and cell not in result:
                result[cell] = result[(x, y)] + 1
                queue.append(cell)
    return result


def shortest_path(grid, start, goal):
    """도착점까지의 거리표를 따라 최단 경로를 만든다."""
    remaining = distances(grid, goal)
    path = [start]
    while path[-1] != goal:
        x, y = path[-1]
        for dx, dy in DIRECTIONS:
            next_cell = (x + dx, y + dy)
            if remaining.get(next_cell) == remaining[(x, y)] - 1:
                path.append(next_cell)
                break
    return path


def choose_torch_mount(grid, path, reserved):
    """초반 진행 경로에서 보이는 벽을 우선하고, 없으면 가까운 통로를 찾는다."""
    for x, y in [*path[1:4], *distances(grid, path[0])]:
        if (x, y) in reserved:
            continue
        for wx, wy in ((x, y-1), (x-1, y)):
            if wx >= 0 and wy >= 0 and grid[wy][wx]:
                return (x, y), (wx, wy)
    return path[1], None


class MazeLayouts:
    """한 판에서 반복해서 사용할 낮·밤·새벽 지형을 준비한다.

    grid[y][x]의 0은 통로, 1은 벽이다.
    지형 생성과 검사는 게임 시작 때만 실행한다.
    """

    CHANGES_PER_PHASE = 3  # 테스트값: 통로 3칸 폐쇄, 다른 벽 3칸 개방.

    def __init__(self, base_grid, seed, landmarks):
        self.landmarks = landmarks
        self.protected_cells = set()
        for x, y in landmarks.values():
            # 테스트 보존 범위: 주요 지점과 함정 복귀 위치 주변 3×3.
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    self.protected_cells.add((x + dx, y + dy))

        self.grids = [[row[:] for row in base_grid]]
        used_cells = set()
        for phase in (1, 2):
            grid = self.make_variant(base_grid, seed + phase * 997, used_cells)
            self.grids.append(grid)
            # 밤에서 바꾼 칸은 새벽에서 고르지 않아 세 배치를 구별한다.
            for y in range(ROWS):
                for x in range(COLS):
                    if grid[y][x] != base_grid[y][x]:
                        used_cells.add((x, y))

    def copy_for_phase(self, phase):
        """실제 플레이용 복사본을 반환해 저장된 원본을 보호한다."""
        return [row[:] for row in self.grids[phase]]

    def is_valid(self, grid):
        """일반 탈출 경로, 숏컷 이득, 수호자와의 간격을 검사한다."""
        points = self.landmarks
        exit_distances = distances(grid, points['exit'])
        floor_count = sum(row.count(0) for row in grid)
        if len(exit_distances) != floor_count:
            return False
        if exit_distances[points['spawn']] <= 25:
            return False
        if exit_distances[points['trap_exit']] < 10:
            return False

        trap_distances = distances(grid, points['trap_entry'])
        if trap_distances[points['trap_exit']] < 15:
            return False

        guard_distances = distances(grid, points['guardian'])
        return all(guard_distances[cell] >= 4 for name, cell in points.items()
                   if name != 'guardian')

    def make_variant(self, base_grid, seed, used_cells):
        grid = [row[:] for row in base_grid]
        candidates = []
        for y in range(1, ROWS - 1):
            for x in range(1, COLS - 1):
                cell = (x, y)
                # 홀수 좌표의 방 사이를 잇는 칸만 바꾼다.
                # 닫히는 칸 양옆에는 모든 시간대에 남는 통로가 있다.
                if (x + y) % 2 == 1 and cell not in self.protected_cells and cell not in used_cells:
                    candidates.append(cell)

        rng = random.Random(seed)
        rng.shuffle(candidates)
        passages = [(x, y) for x, y in candidates if grid[y][x] == 0]
        walls = [(x, y) for x, y in candidates if grid[y][x] == 1]
        change_count = 0
        for close_x, close_y in passages:
            grid[close_y][close_x] = 1
            if not self.is_valid(grid):
                grid[close_y][close_x] = 0
                continue

            opened = False
            for open_x, open_y in walls:
                if grid[open_y][open_x] == 0:
                    continue
                grid[open_y][open_x] = 0
                if self.is_valid(grid):
                    opened = True
                    break
                grid[open_y][open_x] = 1

            if not opened:
                grid[close_y][close_x] = 0
                continue
            change_count += 1
            if change_count == self.CHANGES_PER_PHASE:
                return grid

        raise RuntimeError(f'시간대별 미로 생성 실패 · seed={seed}')


def guard_position(grid, path, protected, seed):
    """Prefer a junction off the route, separated from service/arrival cells."""
    spawn_distance=distances(grid,path[0])
    target_distance=distances(grid,path[min(26,len(path)-2)])
    clearance=[distances(grid,cell) for cell in protected]
    candidates=[cell for cell,d in spawn_distance.items() if d>=12 and
                all(field.get(cell,0)>=4 for field in clearance)]
    if not candidates:
        candidates=[cell for cell,d in spawn_distance.items() if d>=4 and cell not in protected]
    nearby=[cell for cell in candidates if target_distance.get(cell,999)<=9]
    rng=random.Random(seed+911)
    def rank(cell):
        x,y=cell
        degree=sum(not grid[y+dy][x+dx] for dx,dy in DIRECTIONS)
        return degree>=3,cell not in path,-target_distance[cell],rng.random()
    return max(nearby or candidates,key=rank)


@dataclass
class Player:
    x: float
    y: float
    direction: int = 0
    hp: int = 100
    stamina: float = 100
    torch: bool = False
    gait_distance: float = 0.  # 충돌 처리 후 실제 걸은 논리 지면 거리. 순간이동은 제외한다.
    gait_phase: float = 0.  # 걷기·달리기·방향이 바뀌어도 유지하는 0~1 주기 위치.
    screen_facing: str = ''  # 실제 지면 이동으로 정한 8방향. 멈춘 뒤에도 유지한다.


class Game:
    def __init__(self, seed=117, run_number=0, player_clips=None):
        self.seed, self.run_number = seed, run_number
        self.player_clips = player_clips if player_clips is not None else {}
        self.grid = make_maze(seed)
        self.exit = (COLS//2, ROWS//2)
        paths = distances(self.grid, self.exit)
        # 보관된 구현의 테스트값: 숏컷 뒤에도 탐색할 거리가 남도록 31칸 이상 이격한다.
        candidates = [cell for cell, distance in paths.items() if distance >= 31 and
                      (cell[0] in (1, COLS-2) or cell[1] in (1, ROWS-2))]
        self.spawn = random.Random(seed+run_number*31).choice(candidates)
        path = shortest_path(self.grid, self.spawn, self.exit)
        self.trap_cell = path[5]
        self.trap_exit, self.fountain = path[min(24,len(path)-12)], path[15]
        reserved = {self.spawn, self.trap_cell, self.trap_exit, self.fountain, self.exit}
        # 획득은 통로에서, 그림은 벽과 통로의 경계에서 처리한다.
        self.torch_cell, self.torch_wall = choose_torch_mount(self.grid, path, reserved)
        self.torch_wall_contact = (tuple((floor+wall+1)/2 for floor, wall in zip(self.torch_cell, self.torch_wall))
                                   if self.torch_wall is not None else None)
        self.trap_discovered, self.trap_completed = False, False
        self.landing_until = 0.0
        protected=(self.spawn,self.torch_cell,self.trap_cell,self.trap_exit,self.fountain,self.exit)
        self.guard = guard_position(self.grid,path,protected,seed)
        landmarks = {
            'spawn': self.spawn, 'exit': self.exit, 'torch': self.torch_cell,
            'trap_entry': self.trap_cell, 'trap_exit': self.trap_exit,
            'fountain': self.fountain, 'guardian': self.guard,
        }
        self.maze_layouts = MazeLayouts(self.grid, seed, landmarks)
        self.phase = self.layout_phase = run_number % 3
        self.grid = self.maze_layouts.copy_for_phase(self.phase)
        self.path = shortest_path(self.grid, self.spawn, self.exit)
        self.shortcut_distance = distances(self.grid, self.trap_cell)[self.trap_exit]
        self.player = Player(self.spawn[0]+.5, self.spawn[1]+.5)
        delta = (self.path[1][0]-self.path[0][0], self.path[1][1]-self.path[0][1])
        self.player.direction = DIRECTIONS.index(delta)
        gx,gy=self.guard
        def open_length(direction):
            dx,dy=DIRECTIONS[direction]
            return next((n for n in range(1,6) if self.solid(gx+dx*n,gy+dy*n)),6)
        self.guard_direction=max(range(4),key=open_length)
        self.guard_alert_until=0.0
        self.guard_hp, self.fountain_used = 3, False
        self.phase_time = self.time = 0.0
        # UI·변형 연출 시계만 계속 움직이고, 변형 중 게임 세계 시계는 멈춘다.
        self.ui_time = self.shift_elapsed = 0.0
        self.phase_warning = self.shift_applied = False
        self.shift_cells = set()
        self.layout_revision = 0
        self.attack_time = 10.0
        self.attack_facing = self.attack_clip = None
        self.attack_hit_at = DEFAULT_ATTACK_HIT
        self.observed_by_phase = [set() for _ in PHASES]
        self.visited_by_phase = [set() for _ in PHASES]
        self.observed = self.observed_by_phase[self.phase]
        self.visited = self.visited_by_phase[self.phase]
        self.visible = set()
        self.map_open, self.reveal_all = False, False
        self.banner, self.banner_until = '횃불에 접근해 F를 눌러 보세요', 5.0
        self.trap_progress, self.trap_x, self.trap_cooldown = 0.0, 0.0, 0.0
        self.trap_return = None
        self.trap_return_direction = self.player.direction
        self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
        self.trap_hit_at = -10.0
        self.machine = Machine(model=self, states=['explore', 'trap', 'shifting', 'clear', 'failed'],
            initial='explore', auto_transitions=False,
            transitions=[['enter_room', 'explore', 'trap'], ['leave_room', 'trap', 'explore'],
                         ['escape', 'explore', 'clear'], ['fail', 'trap', 'failed'],
                         ['begin_transform', 'explore', 'shifting'],
                         ['finish_transform', 'shifting', 'explore']])
        self.player_machine = Machine(model=self.player, states=['idle', 'walk', 'sprint', 'attack'],
            initial='idle', auto_transitions=False,
            transitions=[['rest', '*', 'idle'], ['walk_now', '*', 'walk'],
                         ['sprint_now', '*', 'sprint'], ['swing', '*', 'attack']])
        self.update_visibility()

    def message(self, text, seconds=3):
        self.banner, self.banner_until = text, self.time+seconds

    def locomotion_clip_name(self, state):
        """모델의 보폭과 뷰의 프레임이 같은 클립을 사용한다. 구 에셋은 4방향으로 대체한다."""
        name = state+'-'+self.player.screen_facing
        return name if name in self.player_clips else state+'-'+DIAGONAL_FACINGS[self.player.direction]

    def solid(self, x, y, grid=None):
        grid = self.grid if grid is None else grid
        return not (0 <= x < COLS and 0 <= y < ROWS) or grid[y][x] == 1

    def can_stand(self, x, y, grid=None):
        return all(not self.solid(math.floor(x+dx), math.floor(y+dy), grid)
                   for dx in (-PLAYER_HALF_SIZE, PLAYER_HALF_SIZE)
                   for dy in (-PLAYER_HALF_SIZE, PLAYER_HALF_SIZE))

    def move_straight(self, dx, dy):
        """입력 선을 따라 벽 직전까지만 이동하고, 실제 이동량을 돌려준다."""
        if dx == 0 and dy == 0:
            return 0., 0.
        x, y = self.player.x, self.player.y
        radius = PLAYER_HALF_SIZE
        fraction = 1.0
        # 지나갈 영역의 벽만 확인한다. 끝점이 비어 있어도 중간 모퉁이는 통과할 수 없다.
        for wall_y in range(math.floor(min(y, y+dy)-radius), math.floor(max(y, y+dy)+radius)+1):
            for wall_x in range(math.floor(min(x, x+dx)-radius), math.floor(max(x, x+dx)+radius)+1):
                if not self.solid(wall_x, wall_y):
                    continue
                # 벽을 몸 반폭만큼 넓히면 플레이어 중심을 점으로 계산할 수 있다.
                enter, leave = -math.inf, math.inf
                for position, delta, low, high in (
                        (x, dx, wall_x-radius, wall_x+1+radius),
                        (y, dy, wall_y-radius, wall_y+1+radius)):
                    if delta == 0:
                        if position <= low or position >= high:
                            break
                    else:
                        first, last = (low-position)/delta, (high-position)/delta
                        enter = max(enter, min(first, last))
                        leave = min(leave, max(first, last))
                else:
                    if enter <= leave and leave > 0 and enter <= fraction:
                        gap = MOVE_EPSILON / max(abs(dx), abs(dy))
                        fraction = max(0., enter-gap)
        moved_x, moved_y = dx*fraction, dy*fraction
        if max(abs(moved_x), abs(moved_y)) < MOVE_EPSILON:
            return 0., 0.
        self.player.x += moved_x
        self.player.y += moved_y
        return moved_x, moved_y

    def safe_position(self, next_grid):
        """몸 전체가 들어가면 유지하고, 아니면 이전 통로를 따라 공통 통로를 찾는다."""
        player = self.player
        if self.can_stand(player.x, player.y, next_grid):
            return player.x, player.y
        start = math.floor(player.x), math.floor(player.y)
        # distances는 가까운 순서의 BFS다. 벽 너머 칸으로 바로 밀어내지 않는다.
        for x, y in distances(self.grid, start):
            if all(self.can_stand(x+.5, y+.5, grid) for grid in self.maze_layouts.grids):
                return x+.5, y+.5
        raise RuntimeError('변형 후 복귀할 공통 통로가 없습니다.')

    def start_shift(self):
        """시간대 경계에서 함정방을 빠져나오고 변형 상태에 들어간다."""
        if self.state == 'trap':
            self.return_from_trap()
        next_grid = self.maze_layouts.grids[(self.phase+1) % len(PHASES)]
        self.shift_cells = {(x, y) for y in range(ROWS) for x in range(COLS)
                            if self.grid[y][x] != next_grid[y][x]}
        self.shift_elapsed = 0.0
        self.shift_applied = False
        self.begin_transform()
        self.message('미로 변형 중 · 잠시 멈춥니다')

    def apply_next_layout(self):
        """중간 시점에 좌표·지형·충돌·관찰 기록을 한 번에 교체한다."""
        next_phase = (self.phase+1) % len(PHASES)
        next_grid = self.maze_layouts.copy_for_phase(next_phase)
        self.player.x, self.player.y = self.safe_position(next_grid)
        self.grid = next_grid
        self.phase = self.layout_phase = next_phase
        self.layout_revision += 1
        self.observed = self.observed_by_phase[next_phase]
        self.visited = self.visited_by_phase[next_phase]
        self.path = shortest_path(self.grid, self.spawn, self.exit)
        self.shortcut_distance = distances(self.grid, self.trap_cell)[self.trap_exit]
        self.update_visibility()

    def update_shift(self, dt):
        """변형 중에는 이 시계만 갱신하며, 교체 이후 프레임에는 다시 적용하지 않는다."""
        self.shift_elapsed = min(SHIFT_SECONDS, self.shift_elapsed+dt)
        if not self.shift_applied and self.shift_elapsed >= SHIFT_SWAP_AT:
            self.apply_next_layout()
            self.shift_applied = True
        if self.shift_elapsed >= SHIFT_SECONDS:
            self.finish_transform()
            self.phase_time = 0.0
            self.phase_warning = False
            self.shift_cells.clear()
            self.message(f'{PHASES[self.phase]} · 미로의 길이 바뀌었습니다')

    def close_to(self, cell, radius=1.25):
        return math.hypot(self.player.x-cell[0]-.5, self.player.y-cell[1]-.5) <= radius and self.line_of_sight(*cell)

    def line_of_sight(self, x, y):
        px, py = self.player.x, self.player.y
        steps = max(1, math.ceil(math.hypot(x+.5-px, y+.5-py)*5))
        for i in range(1, steps):
            t = i/steps
            cell = math.floor(px+(x+.5-px)*t), math.floor(py+(y+.5-py)*t)
            if cell != (x,y) and self.solid(*cell):
                return False
        return True

    def update_visibility(self):
        player, visible = self.player, set()
        reach = TORCH_SIGHT_RADIUS if player.torch else BASE_SIGHT_RADIUS
        for y in range(max(0, int(player.y-reach)), min(ROWS, math.ceil(player.y+reach))):
            for x in range(max(0, int(player.x-reach)), min(COLS, math.ceil(player.x+reach))):
                dx, dy = x+.5-player.x, y+.5-player.y
                distance = math.hypot(dx, dy)
                if distance <= reach and self.line_of_sight(x, y):
                    visible.add((x, y))
        self.visible = visible
        self.observed.update(visible)
        self.visited.add((math.floor(player.x), math.floor(player.y)))
        if self.trap_cell in visible:
            self.trap_discovered = True

    def interact(self):
        if self.state != 'explore' or self.map_open:
            return
        if not self.player.torch and self.close_to(self.torch_cell):
            self.player.torch = True
            self.message('횃불 획득 · 원형 시야 확대')
        elif self.close_to(self.trap_cell):
            self.trap_return = self.player.x, self.player.y
            self.trap_return_direction = self.player.direction
            self.trap_progress = self.trap_x = self.trap_cooldown = 0.0
            self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
            self.trap_discovered = True
            self.map_open = False
            self.attack_facing = self.attack_clip = None
            self.enter_room()
            self.message(f'A 입구 → B 출구 · 일반 통로 {self.shortcut_distance}칸을 우회', 5)
        elif self.close_to(self.fountain):
            if self.fountain_used:
                self.message('이미 사용한 샘물입니다')
            else:
                self.fountain_used = True
                self.player.hp = min(100, self.player.hp+35)
                self.message('샘물 사용 · 체력 회복')
        elif self.close_to(self.exit):
            self.attack_facing = self.attack_clip = None
            self.escape()
        self.update_visibility()

    def return_from_trap(self, completed=False):
        if self.state != 'trap':
            return
        self.player.x, self.player.y = ((self.trap_exit[0]+.5, self.trap_exit[1]+.5)
                                      if completed else self.trap_return)
        self.player.direction = self.trap_return_direction
        self.leave_room()
        if completed:
            self.trap_completed = self.trap_discovered = True
            self.landing_until = self.time+10
            self.message(f'B 출구 도착 · 일반 통로 {self.shortcut_distance}칸 우회 · M 지도 확인',8)
        else:
            self.message('A 입구 · 입장 전 위치로 복귀')
        self.trap_velocity = self.trap_side_velocity = 0.0
        self.update_visibility()

    def attack(self):
        if self.state != 'explore' or self.map_open or self.attack_time < ATTACK_COOLDOWN:
            return
        diagonal = DIAGONAL_FACINGS[self.player.direction]
        self.attack_facing = self.player.screen_facing or diagonal
        clip = 'attack-'+self.attack_facing
        self.attack_clip = clip if clip in self.player_clips else 'attack-'+diagonal
        events = self.player_clips.get(self.attack_clip, {}).get('events', ())
        self.attack_hit_at = next((event['at_ms']/1000 for event in events if event['name'] == 'hit'),
                                  DEFAULT_ATTACK_HIT)
        self.attack_time = 0
        self.player.swing()

    def hit_guard(self):
        if self.guard_hp <= 0 or not self.close_to(self.guard, 1.8):
            return
        gx, gy = self.guard
        dx, dy = project(gx+.5-self.player.x, gy+.5-self.player.y)
        fx, fy = ATTACK_FORWARD[self.attack_facing]
        if dx*fx + dy*fy > 0:
            self.guard_hp -= 1
            self.guard_alert_until=self.time+2.5
            self.message('수호자 타격' if self.guard_hp else '수호자 처치 · 추적 AI는 다음 단계')

    def update(self, dt, dx=0, dy=0, sprint=False):
        dt = min(.05, max(0, dt))
        self.ui_time += dt
        if self.state in ('clear', 'failed'):
            return
        if self.state == 'shifting':
            self.update_shift(dt)
            return
        self.phase_time = min(PHASE_SECONDS, self.phase_time+dt)
        if not self.phase_warning and self.phase_time >= PHASE_SECONDS-PHASE_WARNING_SECONDS:
            self.phase_warning = True
            self.message('곧 미로가 변합니다', PHASE_WARNING_SECONDS)
        if self.phase_time >= PHASE_SECONDS:
            self.start_shift()
            return
        self.time += dt
        previous_attack_time = self.attack_time
        self.attack_time += dt
        if self.phase == 2:
            self.player.stamina = min(100, self.player.stamina+dt*8)
        if self.state == 'trap':
            running = sprint and self.player.stamina>0
            target_speed = -dy*(2.7 if running else 1.8)
            self.trap_velocity += max(-10*dt,min(10*dt,target_speed-self.trap_velocity))
            self.trap_side_velocity += max(-12*dt,min(12*dt,dx*1.8-self.trap_side_velocity))
            self.trap_x = max(-1,min(1,self.trap_x+self.trap_side_velocity*dt))
            change = self.trap_velocity*dt
            old_progress = self.trap_progress
            self.trap_progress = max(0,self.trap_progress+change/TRAP_LENGTH)
            self.trap_stride += abs(self.trap_progress-old_progress)*TRAP_LENGTH
            if running and dy:
                self.player.stamina = max(0,self.player.stamina-dt*18)
            self.trap_cooldown = max(0, self.trap_cooldown-dt)
            for index, plane in enumerate(TRAP_PLANES):
                blade_x = blade_position(self.time,index)
                dz=abs((plane-self.trap_progress)*TRAP_LENGTH)
                dx_metres=abs(self.trap_x-blade_x)*TRAP_LATERAL
                if dz<.24 and dx_metres<BLADE_RADIUS+PLAYER_RADIUS and not self.trap_cooldown:
                    self.player.hp = max(0, self.player.hp-20)
                    if self.player.hp == 0:
                        self.fail()
                        return
                    self.trap_progress = max(0,plane-.06)
                    self.trap_velocity = -.5
                    self.trap_cooldown = 1.0
                    self.trap_hit_at = self.time
                    self.message('칼날 피격 · 좌우로 피해서 통과하세요')
            if self.trap_progress >= 1:
                self.return_from_trap(completed=True)
            return
        if self.map_open:
            dx = dy = 0
        # 격자 거리 대신 투영된 지면 거리로 정규화한다. 대각선의 2:1 방향은 유지한다.
        magnitude = math.hypot(*project(dx, dy))
        running = sprint and self.player.stamina > 0
        vx = vy = 0.
        if magnitude:
            speed = RUN_SPEED if running else WALK_SPEED
            vx, vy = self.move_straight(dx/magnitude*dt*speed, dy/magnitude*dt*speed)
            if running:
                self.player.stamina = max(0, self.player.stamina-dt*18)
        if vx or vy:
            # A screen-axis move ties two clips. Keep the current one if it fits.
            alignment = [vx*x+vy*y for x, y in DIRECTIONS]
            best = max(alignment)
            if alignment[self.player.direction] < best:
                self.player.direction = alignment.index(best)
            sx, sy = project(vx, vy)
            self.player.screen_facing = (('s' if sy > 1e-8 else 'n' if sy < -1e-8 else '')
                                         + ('e' if sx > 1e-8 else 'w' if sx < -1e-8 else ''))
            distance = math.hypot(sx, sy)
            self.player.gait_distance += distance
            clip = self.player_clips.get(self.locomotion_clip_name('run' if running else 'walk'), {})
            cycle = clip.get('cycle_distance_px', RUN_CYCLE_PX if running else WALK_CYCLE_PX)
            phase = (self.player.gait_phase + distance/cycle) % 1.
            # dt 분할에 따른 부동소수점 오차가 주기 경계의 프레임을 바꾸지 않게 한다.
            self.player.gait_phase = 0. if min(phase, 1.-phase) < 1e-10 else phase
            if running:
                self.player.sprint_now()
            else:
                self.player.walk_now()
        elif self.player.state in ('walk', 'sprint') or self.attack_time >= ATTACK_COOLDOWN:
            self.player.rest()
        if (self.attack_facing and not self.map_open
                and previous_attack_time < self.attack_hit_at <= self.attack_time):
            self.hit_guard()
        self.update_visibility()
