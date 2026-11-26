"""Grid rules for the hybrid-view prototype; independent of drawing and SDL."""
from collections import deque
from dataclasses import dataclass
import math
import random
from transitions import Machine
from .mouse_maze import MouseMaze
from .world_path_room import WorldPathRoom, ENTER_SECONDS, START, REVERSE_START, TRAVERSE_CELLS
from .shortcut_choice import ShortcutChoice, ROUTE_OPTIONS, CHOICE_START, CHOICE_GOAL

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
ATTACK_COOLDOWN, DEFAULT_ATTACK_HIT_MS = .75, 233
GUARD_SPEED, GUARD_NOTICE_RADIUS, GUARD_CHASE_MEMORY = 2., 6., 6.
GUARD_REACH, GUARD_WINDUP, GUARD_COOLDOWN, GUARD_DAMAGE = 1.25, .45, 1.1, 15
PHASES = ('낮', '밤', '새벽')
# 플레이테스트용 기본값. 최종 시간·연출 강도는 조정할 수 있다.
PHASE_SECONDS, PHASE_WARNING_SECONDS = 60.0, 5.0
SHIFT_SECONDS, SHIFT_SWAP_AT = .6, .3
TRAP_LENGTH, TRAP_HALF_WIDTH, TRAP_HEIGHT = 9.0, 1.6, 3.0
TRAP_LATERAL, BLADE_RADIUS, PLAYER_RADIUS = 1.1, .34, .20
TRAP_PLANES = (.30, .58, .82)
SPRINT_STAMINA_COST = 18.0  # ST/s, 일반 미로와 두 함정방의 공통 소모량.
# 외부 격자 통로 칸 수. 기존 함정의 최소 우회·도착 후 탐색 조건을 재사용한다.
BOULDER_MIN_BYPASS_CELLS, BOULDER_MIN_REMAINING_CELLS = 15, 10


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


def landmark_area(points):
    """주요 지점과 복귀 위치의 주변 3×3 격자를 반환한다."""
    return {(x+dx, y+dy) for x,y in points for dx in (-1,0,1) for dy in (-1,0,1)}


class MazeLayouts:
    """한 판에서 반복해서 사용할 낮·밤·새벽 지형을 준비한다.

    grid[y][x]의 0은 통로, 1은 벽이다.
    지형 생성과 검사는 게임 시작 때만 실행한다.
    """

    CHANGES_PER_PHASE = 3  # 테스트값: 통로 3칸 폐쇄, 다른 벽 3칸 개방.

    def __init__(self, base_grid, seed, landmarks):
        self.landmarks = landmarks
        self.protected_cells = landmark_area(landmarks.values())

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
        self.landing_cell = None
        protected=(self.spawn,self.torch_cell,self.trap_cell,self.trap_exit,self.fountain,self.exit)
        self.guard_home = guard_position(self.grid,path,protected,seed)
        self.guard = self.guard_home
        landmarks = {
            'spawn': self.spawn, 'exit': self.exit, 'torch': self.torch_cell,
            'trap_entry': self.trap_cell, 'trap_exit': self.trap_exit,
            'fountain': self.fountain, 'guardian': self.guard,
        }
        self.maze_layouts = MazeLayouts(self.grid, seed, landmarks)
        self.puzzle_gate = self.choose_puzzle_gate()
        self.boulder_entry, self.boulder_exit = self.choose_boulder_shortcut() or (None, None)
        if self.boulder_entry is not None:
            self.maze_layouts.landmarks.update(boulder_entry=self.boulder_entry, boulder_exit=self.boulder_exit)
            self.maze_layouts.protected_cells.update(landmark_area((self.boulder_entry, self.boulder_exit)))
        self.puzzle = MouseMaze()
        self.path_entry,self.path_exit = self.choose_world_path() or (None,None)
        if self.path_entry is not None:
            self.maze_layouts.landmarks.update(path_entry=self.path_entry,path_exit=self.path_exit)
            self.maze_layouts.protected_cells.update(landmark_area((self.path_entry,self.path_exit)))
        self.world_path = WorldPathRoom()
        self.route_options = self.choose_shortcut_routes()
        self.shortcut_choice = ShortcutChoice()
        self.choice_confirm_requested = False
        self.connection = self.world_path.puzzle
        self.path_completed = self.path_discovered = False
        self.path_return = None
        self.puzzle_tab = 'maze'
        self.puzzle_reserved_phase = None
        self.puzzle_open = False
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
        self.guard_seen_until = self.guard_ready_at = 0.
        self.guard_attack_at = None
        self.guard_hp, self.fountain_used = 3, False
        self.phase_time = self.time = 0.0
        # UI·변형 연출 시계만 계속 움직이고, 변형 중 게임 세계 시계는 멈춘다.
        self.ui_time = self.shift_elapsed = 0.0
        self.phase_warning = self.shift_applied = False
        self.shift_cells = set()
        self.layout_revision = 0
        self.attack_time = 10.0
        self.attack_facing = self.attack_clip = None
        self.attack_hits_ms = ()
        self.observed_by_phase = [set() for _ in PHASES]
        self.visited_by_phase = [set() for _ in PHASES]
        self.observed = self.observed_by_phase[self.phase]
        self.visited = self.visited_by_phase[self.phase]
        self.visible = set()
        self.map_open, self.reveal_all = False, False
        self.banner, self.banner_until = '횃불에 접근해 F를 눌러 보세요', 5.0
        self.trap_kind = 'blade'
        self.boulder_room = None
        self.boulder_discovered = self.boulder_completed = False
        self.boulder_return_requested = self.boulder_exit_requested = False
        self.trap_progress, self.trap_x, self.trap_cooldown = 0.0, 0.0, 0.0
        self.trap_return = None
        self.trap_return_direction = self.player.direction
        self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
        self.trap_hit_at = -10.0
        self.machine = Machine(model=self, states=['explore', 'puzzle', 'trap', 'path_room', 'shifting', 'clear', 'failed'],
            initial='explore', auto_transitions=False,
            transitions=[['enter_room', 'explore', 'trap'], ['leave_room', 'trap', 'explore'],
                         ['escape', 'explore', 'clear'], ['fail', ['explore', 'trap'], 'failed'],
                         ['enter_puzzle', 'explore', 'puzzle'], ['leave_puzzle', 'puzzle', 'explore'],
                         ['enter_path', 'explore', 'path_room'], ['leave_path', 'path_room', 'explore'],
                         {'trigger':'fail','source':'path_room','dest':'failed','before':'_restore_path'},
                         ['begin_transform', 'explore', 'shifting'],
                         ['finish_transform', 'shifting', 'explore']])
        self.player_machine = Machine(model=self.player, states=['idle', 'walk', 'sprint', 'attack'],
            initial='idle', auto_transitions=False,
            transitions=[['rest', '*', 'idle'], ['walk_now', '*', 'walk'],
                         ['sprint_now', '*', 'sprint'], ['swing', '*', 'attack']])
        self.update_visibility()

    def choose_shortcut_routes(self):
        """기획에서 실측한 117 첫 회차의 두 길을 여섯 지형 조건에서 검증한다."""
        if (self.seed,self.run_number) != (117,0):
            return ()
        protected = self.maze_layouts.protected_cells | set(self.puzzle_gate or ()) | {self.torch_wall}
        if any(option.gate in protected for option in ROUTE_OPTIONS):
            return ()
        for base in self.maze_layouts.grids:
            for p_open in (False,True):
                original = [row[:] for row in base]
                if self.puzzle_gate:
                    x,y = self.puzzle_gate[0];original[y][x] = int(not p_open)
                ordinary = distances(original,CHOICE_START).get(CHOICE_GOAL,0)
                for option in ROUTE_OPTIONS:
                    x,y = option.gate
                    if not original[y][x]:return ()
                    grid = [row[:] for row in original];grid[y][x] = 0
                    if (any(grid[y][x] for x,y in option.path)
                            or not self.maze_layouts.is_valid(grid)
                            or not option.distance < ordinary
                            or distances(grid,CHOICE_START).get(CHOICE_GOAL) != option.distance
                            or distances(grid,self.exit).get(CHOICE_GOAL,0) < 8):
                        return ()
        return ROUTE_OPTIONS

    def choose_boulder_shortcut(self):
        """검증된 117 첫 회차 후보만 선택하고, 안전하지 않으면 생략한다."""
        if (self.seed, self.run_number) != (117, 0):
            return None
        entry, arrival = (9, 6), (11, 13)
        return (entry, arrival) if self.valid_boulder_shortcut(entry, arrival) else None

    def valid_boulder_shortcut(self, entry, arrival):
        """지형을 바꾸지 않고 세 시간대×퍼즐 문 개폐의 경로·복귀 안전을 검사한다."""
        if any(not (1 <= x < COLS-1 and 1 <= y < ROWS-1) for x,y in (entry, arrival)):
            return False
        entry_area, arrival_area = landmark_area((entry,)), landmark_area((arrival,))
        if entry_area & arrival_area:
            return False
        area = entry_area | arrival_area
        layouts = self.maze_layouts
        existing = [cell for name,cell in layouts.landmarks.items()
                    if name not in ('boulder_entry', 'boulder_exit')]
        if area & landmark_area(existing) or (self.puzzle_gate and area & set(self.puzzle_gate)):
            return False
        for base in layouts.grids:
            if any(base[y][x] != layouts.grids[0][y][x] for x,y in area):
                return False
            for opened in (False, True):
                grid = [row[:] for row in base]
                if self.puzzle_gate:
                    x,y = self.puzzle_gate[0]
                    grid[y][x] = int(not opened)
                if any(self.solid(x,y,grid) for x,y in existing):
                    return False
                if not all(self.can_stand(x+.5,y+.5,grid) for x,y in (entry, arrival)):
                    return False
                if not layouts.is_valid(grid):
                    return False
                remaining = distances(grid, self.exit)
                if remaining[arrival] < BOULDER_MIN_REMAINING_CELLS:
                    return False
                if distances(grid, entry)[arrival] < BOULDER_MIN_BYPASS_CELLS:
                    return False
                if distances(grid, self.spawn)[entry]+remaining[arrival] >= remaining[self.spawn]:
                    return False
                guard = distances(grid, self.guard_home)
                if any(guard[cell] < 4 for cell in (entry, arrival)):
                    return False
        return True

    def choose_world_path(self):
        """여섯 지형 조건에서 안전·왕복 착지·실제 보행 이득을 보장하는 후보만 고른다."""
        layouts = self.maze_layouts
        base = layouts.grids[0]
        ds,de = distances(base,self.spawn),distances(base,self.exit)
        landmarks = set(layouts.landmarks.values()) | set(self.puzzle_gate or ())
        if self.torch_wall is not None:
            landmarks.add(self.torch_wall)
        fields = []
        for original in layouts.grids:
            for opened in (False,True):
                grid = [row[:] for row in original]
                if self.puzzle_gate:
                    x,y = self.puzzle_gate[0];grid[y][x] = int(not opened)
                fields.append((distances(grid,self.spawn),distances(grid,self.exit),distances(grid,self.guard_home)))
        def usable(cell):
            area = landmark_area((cell,))
            return (all(math.dist(cell,other) > 1.5 for other in landmarks)
                    and all(0 <= x < COLS and 0 <= y < ROWS
                            and all(grid[y][x] == base[y][x] for grid in layouts.grids) for x,y in area)
                    and any(base[cell[1]+dy][cell[0]+dx] for dx,dy in ((0,-1),(-1,0)))
                    and all(guard.get(cell,0) >= 4 for _,_,guard in fields))
        entries = sorted((cell for cell,distance in ds.items() if 2 <= distance <= 18 and usable(cell)),
                         key=lambda cell:(ds[cell],cell))
        arrivals = sorted((cell for cell,distance in de.items() if 8 <= distance <= 24 and usable(cell)),
                          key=lambda cell:(ds[cell]+de[cell] != ds[self.exit],abs(de[cell]-18),cell))
        pairs = [(entry,arrival) for entry in entries for arrival in arrivals if math.dist(entry,arrival) >= 4]
        def beneficial(pair, cost, from_spawn=True):
            entry,arrival = pair
            return all(goal[arrival] >= 8 and
                       ((goal[self.spawn]-spawn[entry]) if from_spawn else goal[entry]) > cost+goal[arrival]
                       for spawn,goal,_ in fields)
        previous = next((pair for pair in pairs if beneficial(pair,10)),None)
        if previous is not None and beneficial(previous,TRAVERSE_CELLS):return previous
        primary = next((pair for pair in pairs if beneficial(pair,TRAVERSE_CELLS)),None)
        if primary is not None:return primary
        # 입구를 이미 만난 경우의 선택도 실제 방 보행보다 빨라야 한다. 시작점 이득은 검사에서 별도 공개한다.
        if previous is not None and beneficial(previous,TRAVERSE_CELLS,False):return previous
        return next((pair for pair in pairs if beneficial(pair,TRAVERSE_CELLS,False)),None)

    def choose_puzzle_gate(self):
        layouts = self.maze_layouts
        protected = layouts.protected_cells | {self.torch_wall}

        def valid(wall, near, far):
            x, y = wall
            if wall in protected or near in protected or far in protected:
                return False
            for grid in layouts.grids:
                if not grid[y][x] or grid[near[1]][near[0]] or grid[far[1]][far[0]]:
                    return False
                opened = [row[:] for row in grid]
                opened[y][x] = 0
                if not layouts.is_valid(opened):
                    return False
            return True

        preferred = ((17, 6), (17, 5), (17, 7))
        if self.seed == 117 and valid(*preferred):
            return preferred
        for y in range(1, ROWS-1):
            for x in range(1, COLS-1):
                wall = (x, y)
                for near, far in (((x-1, y), (x+1, y)), ((x, y-1), (x, y+1))):
                    if valid(wall, near, far):
                        return wall, near, far
        return None

    @property
    def next_phase(self):
        return (self.phase+1) % len(PHASES)

    @property
    def guard(self):
        return math.floor(self.guard_x), math.floor(self.guard_y)

    @guard.setter
    def guard(self, cell):
        self.guard_x, self.guard_y = cell[0]+.5, cell[1]+.5
        self.guard_step = None

    def puzzle_available(self):
        if self.puzzle_gate is None or self.puzzle_open or self.puzzle_reserved_phase is not None:
            return False
        wall, near, far = self.puzzle_gate
        return wall in self.visible and (self.close_to(near, .75) or self.close_to(far, .75))

    def shortcut_available(self):
        return (self.state == 'explore' and not self.map_open and bool(self.route_options)
                and self.shortcut_choice.selected is None and CHOICE_START in self.visible
                and self.close_to(CHOICE_START,.75))

    def select_shortcut(self, index):
        return (self.state == 'puzzle' and self.puzzle_tab == 'choice'
                and not self.choice_confirm_requested
                and self.shortcut_choice.select(index))

    def request_shortcut_confirmation(self):
        if (self.state != 'puzzle' or self.puzzle_tab != 'choice' or self.player.hp <= 0
                or self.shortcut_choice.preview is None or self.shortcut_choice.selected is not None):
            return False
        self.choice_confirm_requested = True
        return True

    def _confirm_shortcut(self):
        if (self.state != 'puzzle' or self.puzzle_tab != 'choice' or self.player.hp <= 0
                or self.phase_time >= PHASE_SECONDS or not self.shortcut_choice.confirm(self.next_phase)):
            return False
        option = self.route_options[self.shortcut_choice.selected]
        self.close_puzzle()
        self.message(f'{option.label} 확정 · 다음 {PHASES[self.next_phase]}에 선택한 문만 개방',5)
        return True

    def close_puzzle(self):
        self.choice_confirm_requested = False
        if self.state == 'puzzle':
            self.cancel_puzzle_drag()
            self.leave_puzzle()
            self.puzzle_tab = 'maze'

    def cancel_puzzle_drag(self):
        self.puzzle.release()
        self.connection.cancel()

    def switch_puzzle_tab(self, tab):
        if self.state != 'puzzle' or tab != 'maze':
            return False
        self.cancel_puzzle_drag()
        self.puzzle_tab = tab
        return True

    def drag_puzzle(self, point):
        if self.state != 'puzzle' or self.puzzle_tab != 'maze' or not self.puzzle.move(point):
            return False
        return self._complete_puzzle()

    def rotate_connection(self):
        if self.state != 'path_room' or self.world_path.stage != 'active':
            return False
        return self.connection.rotate()

    def drop_connection(self, cell=None, *, shelf=False):
        if self.state != 'path_room' or self.world_path.stage != 'active':
            return False
        return self.connection.drop(cell,shelf=shelf)

    def pick_connection(self, index):
        return (self.state == 'path_room' and self.world_path.stage == 'active'
                and self.connection.pick(index))

    def _complete_puzzle(self):
        if (self.state != 'puzzle' or self.puzzle_tab != 'maze'
                or self.puzzle_reserved_phase is not None or self.puzzle_open):
            return False
        self.puzzle_reserved_phase = self.next_phase
        self.puzzle.reset()
        self.close_puzzle()
        self.message(f'퍼즐 완료 · 다음 {PHASES[self.next_phase]}에 통로가 열립니다', 5)
        return True

    def layout_for_phase(self, phase):
        grid = self.maze_layouts.copy_for_phase(phase)
        if self.puzzle_gate and (self.puzzle_open or self.puzzle_reserved_phase == phase):
            x, y = self.puzzle_gate[0]
            grid[y][x] = 0
        route = self.shortcut_choice.route_for_phase(phase)
        if route is not None and self.route_options:
            x,y = self.route_options[route].gate
            grid[y][x] = 0
        return grid

    def message(self, text, seconds=3):
        self.banner, self.banner_until = text, self.time+seconds

    def locomotion_clip_name(self, state):
        """모델의 보폭과 뷰의 프레임이 같은 클립을 사용한다. 구 에셋은 4방향으로 대체한다."""
        name = state+'-'+self.player.screen_facing
        return name if name in self.player_clips else state+'-'+DIAGONAL_FACINGS[self.player.direction]

    def animate_movement(self, vx, vy, running=False, sprint_cost=0.):
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
                self.player.stamina -= sprint_cost
                self.player.sprint_now()
            else:
                self.player.walk_now()
        elif self.player.state in ('walk', 'sprint') or self.attack_time >= ATTACK_COOLDOWN:
            self.player.rest()

    def solid(self, x, y, grid=None):
        if (grid is None and getattr(self,'state',None) == 'path_room'
                and self.world_path.stage == 'active'):
            return self.world_path.solid(x,y)
        grid = self.grid if grid is None else grid
        return not (0 <= x < COLS and 0 <= y < ROWS) or grid[y][x] == 1

    def can_stand(self, x, y, grid=None):
        clear = all(not self.solid(math.floor(x+dx), math.floor(y+dy), grid)
                    for dx in (-PLAYER_HALF_SIZE, PLAYER_HALF_SIZE)
                    for dy in (-PLAYER_HALF_SIZE, PLAYER_HALF_SIZE))
        if clear and grid is None and getattr(self,'state',None) == 'path_room' and self.world_path.stage == 'active':
            return self.world_path.clear_at(x,y,PLAYER_HALF_SIZE)
        return clear

    def move_straight(self, dx, dy):
        """입력 선을 따라 벽 직전까지만 이동하고, 실제 이동량을 돌려준다."""
        if dx == 0 and dy == 0:
            return 0., 0.
        x, y = self.player.x, self.player.y
        radius = PLAYER_HALF_SIZE
        fraction = 1.0
        walls = []
        for wall_y in range(math.floor(min(y,y+dy)-radius),math.floor(max(y,y+dy)+radius)+1):
            for wall_x in range(math.floor(min(x,x+dx)-radius),math.floor(max(x,x+dx)+radius)+1):
                if self.solid(wall_x,wall_y):walls.append((wall_x,wall_y,wall_x+1,wall_y+1))
        if self.state == 'path_room' and self.world_path.stage == 'active':
            walls.extend(self.world_path.barriers)
        for left,top,right,bottom in walls:
            enter,leave = -math.inf,math.inf
            for position,delta,low,high in ((x,dx,left-radius,right+radius),(y,dy,top-radius,bottom+radius)):
                if delta == 0:
                    if position <= low or position >= high:break
                else:
                    first,last = (low-position)/delta,(high-position)/delta
                    enter = max(enter,min(first,last));leave = min(leave,max(first,last))
            else:
                if enter <= leave and leave > 0 and enter <= fraction:
                    gap = MOVE_EPSILON/max(abs(dx),abs(dy))
                    fraction = max(0.,enter-gap)
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
            if (self.can_stand(x+.5, y+.5, next_grid) and
                    all(self.can_stand(x+.5, y+.5, grid) for grid in self.maze_layouts.grids)):
                return x+.5, y+.5
        raise RuntimeError('변형 후 복귀할 공통 통로가 없습니다.')

    def start_shift(self):
        """시간대 경계에서 함정방을 빠져나오고 변형 상태에 들어간다."""
        if self.state == 'trap':
            self.return_from_trap()
        if self.state == 'path_room':
            self.return_from_path()
        self.close_puzzle()
        self.shortcut_choice.cancel()
        self.puzzle.reset()
        if not self.path_completed:
            self.world_path.reset()
        self.puzzle_tab = 'maze'
        self.guard_attack_at = None
        self.guard_seen_until = 0.
        next_grid = self.layout_for_phase(self.next_phase)
        self.shift_cells = {(x, y) for y in range(ROWS) for x in range(COLS)
                            if self.grid[y][x] != next_grid[y][x]}
        self.shift_elapsed = 0.0
        self.shift_applied = False
        self.begin_transform()
        self.message('미로 변형 중 · 잠시 멈춥니다')

    def apply_next_layout(self):
        """중간 시점에 좌표·지형·충돌·관찰 기록을 한 번에 교체한다."""
        next_phase = self.next_phase
        next_grid = self.layout_for_phase(next_phase)
        if self.puzzle_reserved_phase == next_phase:
            self.puzzle_open = True
            self.puzzle_reserved_phase = None
        self.shortcut_choice.apply_phase(next_phase)
        self.player.x, self.player.y = self.safe_position(next_grid)
        self.grid = next_grid
        if self.guard_hp and (
                not self.can_stand(self.guard_x, self.guard_y)
                or (self.guard_step is not None and self.solid(*self.guard_step))):
            # The home cell is protected across phases. Use a nearby floor cell
            # if the player is standing within immediate melee reach of home.
            self.guard = next(cell for cell in distances(self.grid, self.guard_home)
                              if math.hypot(cell[0]+.5-self.player.x,
                                            cell[1]+.5-self.player.y) > GUARD_REACH)
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
        return self.clear_line_to(x+.5, y+.5)

    def clear_line_to(self, tx, ty):
        px, py = self.player.x, self.player.y
        cx, cy = math.floor(px), math.floor(py)
        x, y = math.floor(tx), math.floor(ty)
        dx, dy = tx-px, ty-py
        step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        stride_x = 1/abs(dx) if dx else math.inf
        stride_y = 1/abs(dy) if dy else math.inf
        next_x = (cx+(step_x > 0)-px)/dx if dx else math.inf
        next_y = (cy+(step_y > 0)-py)/dy if dy else math.inf
        while (cx, cy) != (x, y):
            if cx == x:
                next_x = math.inf
            if cy == y:
                next_y = math.inf
            # Visit every crossed cell, even when the ray clips only a corner.
            if math.isclose(next_x, next_y, rel_tol=0., abs_tol=1e-12):
                # A corner shared by two solid cells leaves no opening.
                if self.solid(cx+step_x, cy) and self.solid(cx, cy+step_y):
                    return False
                cx, cy = cx+step_x, cy+step_y
                next_x, next_y = next_x+stride_x, next_y+stride_y
            elif next_x < next_y:
                cx += step_x
                next_x += stride_x
            else:
                cy += step_y
                next_y += stride_y
            # The first blocking wall itself is visible.
            if (cx, cy) != (x, y) and self.solid(cx, cy):
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
        if self.boulder_entry in visible:
            self.boulder_discovered = True
        if self.path_entry in visible:
            self.path_discovered = True

    def path_available(self):
        return (self.state == 'explore' and not self.map_open and self.path_entry is not None
                and (self.close_to(self.path_entry) or (self.path_completed and self.close_to(self.path_exit))))

    def enter_path_room(self):
        if not self.path_available():
            return False
        reverse = self.path_completed and self.close_to(self.path_exit)
        cell = self.path_exit if reverse else self.path_entry
        self.path_return = self.player.x,self.player.y
        self.path_return_direction,self.path_return_facing = self.player.direction,self.player.screen_facing
        step = next((step for step in ((0,-1),(-1,0),(1,0),(0,1))
                     if self.solid(cell[0]+step[0],cell[1]+step[1])),(0,-1))
        self.path_walk_target = cell[0]+.5+step[0]*.85,cell[1]+.5+step[1]*.85
        self.world_path.start(reverse)
        self.map_open = False
        self.attack_facing = self.attack_clip = None
        self.attack_hits_ms = ()
        self.guard_attack_at = None
        self.player.rest()
        self.enter_path()
        return True

    def _restore_path(self):
        self.connection.cancel()
        self.world_path.stage = 'idle'
        self.player.x,self.player.y = self.path_return
        self.player.direction,self.player.screen_facing = self.path_return_direction,self.path_return_facing
        self.player.rest()
        self.update_visibility()

    def return_from_path(self, completed=False):
        if self.state != 'path_room':
            return False
        if completed and (self.world_path.stage != 'active' or not self.connection.completed
                          or self.world_path.endpoint(self.player.x,self.player.y)
                          != ('entry' if self.world_path.reverse else 'exit')):
            return False
        target = self.path_entry if self.world_path.reverse else self.path_exit
        self._restore_path()
        self.leave_path()
        if completed:
            self.path_completed = self.path_discovered = True
            self.player.x,self.player.y = target[0]+.5,target[1]+.5
            self.landing_cell,self.landing_until = target,self.time+10
            self.message('길의 방 통과 · 이번 회차에 바로 왕복할 수 있습니다',5)
        else:
            self.message('길의 방 입구로 복귀 · 같은 시간대에는 배치가 유지됩니다')
        self.update_visibility()
        return True

    def update_path_room(self, dt, dx, dy):
        room = self.world_path
        room.elapsed += dt
        if room.stage == 'entering':
            t = min(1.,room.elapsed/ENTER_SECONDS)
            old = self.player.x,self.player.y
            self.player.x,self.player.y = (self.path_return[0]+(self.path_walk_target[0]-self.path_return[0])*t,
                                          self.path_return[1]+(self.path_walk_target[1]-self.path_return[1])*t)
            self.animate_movement(self.player.x-old[0],self.player.y-old[1])
            if t >= 1:
                self.player.x,self.player.y = REVERSE_START if room.reverse else START
                room.stage,room.elapsed = 'active',0.
                self.player.rest()
            return
        vx = vy = 0.
        magnitude = math.hypot(*project(dx,dy))
        if magnitude and not self.connection.dragging:
            vx,vy = self.move_straight(dx/magnitude*dt*WALK_SPEED,dy/magnitude*dt*WALK_SPEED)
        self.animate_movement(vx,vy)
        end = room.endpoint(self.player.x,self.player.y)
        if end is not None:
            forward = end == ('entry' if room.reverse else 'exit')
            if not forward or self.connection.completed:
                self.return_from_path(completed=forward)

    def _enter_trap(self, kind):
        self.trap_kind = kind
        self.trap_return = self.player.x, self.player.y
        self.trap_return_direction = self.player.direction
        self.trap_progress = self.trap_x = self.trap_cooldown = 0.0
        self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
        self.boulder_return_requested = self.boulder_exit_requested = False
        self.map_open = False
        self.attack_facing = self.attack_clip = None
        self.attack_hits_ms = ()
        self.guard_attack_at = None
        self.guard_seen_until = 0.
        self.enter_room()

    def boulder_available(self):
        return (self.state == 'explore' and not self.map_open and self.boulder_entry is not None
                and self.close_to(self.boulder_entry))

    def enter_boulder(self):
        """C 앞에서 모델에 진입한다. 판 시간과 공유 플레이어 자원은 유지한다."""
        if not self.boulder_available():
            return False
        if self.boulder_room is None:
            from BoulderPractice.boulder_practice import Practice
            self.boulder_room = Practice(self.player)
        else:
            self.boulder_room.reset()
        self._enter_trap('boulder')
        self.player.rest()
        self.boulder_discovered = True
        self.message('돌 출발까지 5초 · 지금 이동할 수 있습니다', 5)
        return True

    def request_boulder_return(self):
        if self.state == 'trap' and self.trap_kind == 'boulder':
            self.boulder_return_requested = True

    def request_boulder_exit(self):
        if self.state == 'trap' and self.trap_kind == 'boulder':
            self.boulder_exit_requested = True

    def update_boulder(self, dt, dx, dy, running, look_back):
        """시간대 경계 뒤 Esc, 돌 충돌, F/자동 출구 순으로 결과를 확정한다."""
        returning, exiting = self.boulder_return_requested, self.boulder_exit_requested
        self.boulder_return_requested = self.boulder_exit_requested = False
        if returning:
            self.return_from_trap()
            return
        room = self.boulder_room
        previous_stride = room.stride
        room.advance(dt, dx, -dy, float(running), look_back)
        moved = room.stride > previous_stride
        if moved and room.running:
            self.player.stamina = max(0., self.player.stamina-dt*SPRINT_STAMINA_COST)
            self.player.sprint_now()
        elif moved:
            self.player.walk_now()
        else:
            self.player.rest()
        if room.ball_touching:
            self.player.hp = 0
            room.vx = room.vz = 0.
            room.running = False
            self.player.rest()
            self.fail()
            self.message('돌에 깔렸습니다 · R로 새 회차', 8)
            return
        if exiting:
            room.use_exit()
        room.automatic_exit()
        if room.state == 'clear':
            self.return_from_trap(completed=True)

    def interact(self):
        if self.state == 'trap' and self.trap_kind == 'boulder':
            self.request_boulder_exit()
            return
        if self.state != 'explore' or self.map_open:
            return
        if not self.player.torch and self.close_to(self.torch_cell):
            self.player.torch = True
            self.message('횃불 획득 · 원형 시야 확대')
        elif self.close_to(self.trap_cell):
            self._enter_trap('blade')
            self.trap_discovered = True
            self.message(f'A 입구 → B 출구 · 일반 통로 {self.shortcut_distance}칸을 우회', 5)
        elif self.boulder_available():
            self.enter_boulder()
        elif self.path_available():
            self.enter_path_room()
        elif self.close_to(self.fountain):
            if self.fountain_used:
                self.message('이미 사용한 샘물입니다')
            else:
                self.fountain_used = True
                self.player.hp = min(100, self.player.hp+35)
                self.message('샘물 사용 · 체력 회복')
        elif self.close_to(self.exit):
            self.attack_facing = self.attack_clip = None
            self.attack_hits_ms = ()
            self.guard_attack_at = None
            self.escape()
        elif self.shortcut_available():
            self.attack_facing = self.attack_clip = None
            self.attack_hits_ms = ()
            self.player.rest()
            self.puzzle_tab = 'choice'
            self.enter_puzzle()
        elif self.puzzle_available():
            self.attack_facing = self.attack_clip = None
            self.attack_hits_ms = ()
            self.player.rest()
            self.puzzle_tab = 'maze'
            self.enter_puzzle()
        self.update_visibility()

    def return_from_trap(self, completed=False):
        if self.state != 'trap':
            return
        boulder = self.trap_kind == 'boulder'
        target = self.boulder_exit if boulder else self.trap_exit
        self.player.x, self.player.y = ((target[0]+.5, target[1]+.5)
                                      if completed else self.trap_return)
        self.player.direction = self.trap_return_direction
        self.leave_room()
        self.boulder_return_requested = self.boulder_exit_requested = False
        if boulder and self.boulder_room is not None:
            self.boulder_room.vx = self.boulder_room.vz = 0.
            self.boulder_room.running = self.boulder_room.look_back = False
            self.player.rest()
        if completed:
            if boulder:
                self.boulder_completed = self.boulder_discovered = True
                self.message('D 도착 · M 지도에서 현재 위치 확인', 8)
            else:
                self.trap_completed = self.trap_discovered = True
                self.message(f'B 출구 도착 · 일반 통로 {self.shortcut_distance}칸 우회 · M 지도 확인',8)
            self.landing_until = self.time+10
            self.landing_cell = target
        else:
            self.message(f'{"C" if boulder else "A"} 입구 · 입장 전 위치로 복귀')
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
        self.attack_hits_ms = tuple(event['at_ms'] for event in events if event['name'] == 'hit')
        if not self.attack_hits_ms:
            self.attack_hits_ms = (DEFAULT_ATTACK_HIT_MS,)
        self.attack_time = 0
        self.player.swing()

    def hit_guard(self):
        gx, gy = self.guard_x-self.player.x, self.guard_y-self.player.y
        if (not self.guard_hp or math.hypot(gx, gy) > 1.8
                or not self.clear_line_to(self.guard_x, self.guard_y)):
            return
        dx, dy = project(gx, gy)
        fx, fy = ATTACK_FORWARD[self.attack_facing]
        if dx*fx + dy*fy > 0:
            self.guard_hp -= 1
            self.guard_alert_until=self.time+2.5
            if not self.guard_hp:
                self.guard_attack_at = None
            self.message('수호자 타격' if self.guard_hp else '수호자 처치')

    def update_guard(self, dt):
        if not self.guard_hp or self.state not in ('explore', 'puzzle'):
            return
        dx, dy = self.player.x-self.guard_x, self.player.y-self.guard_y
        distance = math.hypot(dx, dy)
        sees_player = (distance <= GUARD_NOTICE_RADIUS
                       and self.clear_line_to(self.guard_x, self.guard_y))
        if sees_player:
            self.guard_seen_until = self.time+GUARD_CHASE_MEMORY
        in_reach = sees_player and distance <= GUARD_REACH
        if self.guard_attack_at is not None:
            if self.time >= self.guard_attack_at:
                self.guard_attack_at = None
                self.guard_ready_at = self.time+GUARD_COOLDOWN
                if in_reach:
                    self.take_guard_hit()
            return
        if in_reach:
            if self.time >= self.guard_ready_at:
                facing = max(DIRECTIONS, key=lambda step: dx*step[0]+dy*step[1])
                self.guard_direction = DIRECTIONS.index(facing)
                self.guard_attack_at = self.time+GUARD_WINDUP
            return
        if self.guard_step is None:
            if self.time >= self.guard_seen_until:
                return
            player_cell = math.floor(self.player.x), math.floor(self.player.y)
            remaining = distances(self.grid, player_cell)
            x, y = self.guard
            next_distance = remaining[x, y]-1
            for dx, dy in DIRECTIONS:
                cell = x+dx, y+dy
                if remaining.get(cell) == next_distance:
                    self.guard_step = cell
                    break
            else:
                return
        # Commit to a cardinal step so retargeting never cuts through a corner.
        tx, ty = self.guard_step[0]+.5, self.guard_step[1]+.5
        dx, dy = tx-self.guard_x, ty-self.guard_y
        step_left = abs(dx)+abs(dy)
        facing = max(DIRECTIONS, key=lambda step: dx*step[0]+dy*step[1])
        self.guard_direction = DIRECTIONS.index(facing)
        if step_left <= GUARD_SPEED*dt+MOVE_EPSILON:
            self.guard_x, self.guard_y = tx, ty
            self.guard_step = None
        else:
            fraction = GUARD_SPEED*dt/step_left
            self.guard_x += dx*fraction
            self.guard_y += dy*fraction

    def take_guard_hit(self):
        was_puzzling = self.state == 'puzzle'
        if self.state == 'path_room':
            self.return_from_path()
        self.player.hp = max(0, self.player.hp-GUARD_DAMAGE)
        self.close_puzzle()
        self.map_open = False
        if self.player.hp == 0:
            self.fail()
        else:
            self.message('수호자 피격 · F로 이어 풀기' if was_puzzling else '수호자 피격')

    def update(self, dt, dx=0, dy=0, sprint=False, *, look_back=False):
        dt = min(.05, max(0, dt))
        self.ui_time += dt
        if self.state in ('clear', 'failed'):
            return
        if self.state == 'puzzle' and self.puzzle_tab == 'choice' and self.player.hp <= 0:
            self.close_puzzle()
            self.fail()
            return
        if self.state == 'path_room' and self.player.hp <= 0:
            self.fail()
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
        sprint_cost = dt*SPRINT_STAMINA_COST
        # A sprint tick must be funded before this tick's dawn recovery.
        running = sprint and self.player.stamina >= sprint_cost
        if self.phase == 2:
            self.player.stamina = min(100, self.player.stamina+dt*8)
        if self.state == 'path_room':
            self.update_path_room(dt,dx,dy)
            return
        if self.state == 'puzzle':
            self.update_guard(dt)
            if self.choice_confirm_requested:
                self._confirm_shortcut()
            self.choice_confirm_requested = False
            return
        if self.state == 'trap':
            if self.trap_kind == 'boulder':
                self.update_boulder(dt, dx, dy, running, look_back)
                return
            target_speed = -dy*(2.7 if running else 1.8)
            self.trap_velocity += max(-10*dt,min(10*dt,target_speed-self.trap_velocity))
            self.trap_side_velocity += max(-12*dt,min(12*dt,dx*1.8-self.trap_side_velocity))
            self.trap_x = max(-1,min(1,self.trap_x+self.trap_side_velocity*dt))
            change = self.trap_velocity*dt
            old_progress = self.trap_progress
            self.trap_progress = max(0,self.trap_progress+change/TRAP_LENGTH)
            self.trap_stride += abs(self.trap_progress-old_progress)*TRAP_LENGTH
            if running and dy:
                self.player.stamina -= sprint_cost
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
        vx = vy = 0.
        if magnitude:
            speed = RUN_SPEED if running else WALK_SPEED
            vx, vy = self.move_straight(dx/magnitude*dt*speed, dy/magnitude*dt*speed)
        self.animate_movement(vx,vy,running,sprint_cost)
        if self.attack_facing and not self.map_open:
            for hit_ms in self.attack_hits_ms:
                if previous_attack_time < hit_ms/1000 <= self.attack_time:
                    self.hit_guard()
        self.update_guard(dt)
        self.update_visibility()
