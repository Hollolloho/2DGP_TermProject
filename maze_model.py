"""Grid rules for the hybrid-view prototype; independent of drawing and SDL."""
from collections import deque
from dataclasses import dataclass
import math
import random
from transitions import Machine

COLS, ROWS = 31, 23
DIRECTIONS = ((0, 1), (-1, 0), (1, 0), (0, -1))  # down, left, right, up
PHASES = ('낮', '밤', '새벽')
TRAP_LENGTH, TRAP_HALF_WIDTH, TRAP_HEIGHT = 9.0, 1.6, 3.0
TRAP_LATERAL, BLADE_RADIUS, PLAYER_RADIUS = 1.1, .34, .20
TRAP_PLANES = (.30, .58, .82)


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


class Game:
    def __init__(self, seed=117, run_number=0):
        self.seed, self.run_number = seed, run_number
        self.grid = make_maze(seed)
        self.exit = (COLS//2, ROWS//2)
        paths = distances(self.grid, self.exit)
        candidates = [cell for cell, distance in paths.items() if distance > 25 and
                      (cell[0] in (1, COLS-2) or cell[1] in (1, ROWS-2))]
        self.spawn = random.Random(seed+run_number*31).choice(candidates)
        # A shortest path supplies usable demonstration objects near the spawn.
        path, cell = [self.spawn], self.spawn
        while cell != self.exit:
            x, y = cell
            cell = next((x+dx, y+dy) for dx, dy in DIRECTIONS
                        if paths.get((x+dx, y+dy)) == paths[(x, y)]-1)
            path.append(cell)
        self.path = path
        self.player = Player(self.spawn[0]+.5, self.spawn[1]+.5)
        delta = path[1][0]-path[0][0], path[1][1]-path[0][1]
        self.player.direction = DIRECTIONS.index(delta)
        self.torch_cell, self.trap_cell = path[1], path[5]
        self.trap_exit, self.fountain = path[min(24,len(path)-12)], path[15]
        self.shortcut_distance = distances(self.grid,self.trap_cell)[self.trap_exit]
        self.trap_discovered, self.trap_completed = False, False
        self.landing_until = 0.0
        protected=(self.spawn,self.torch_cell,self.trap_cell,self.trap_exit,self.fountain,self.exit)
        self.guard = guard_position(self.grid,path,protected,seed)
        gx,gy=self.guard
        def open_length(direction):
            dx,dy=DIRECTIONS[direction]
            return next((n for n in range(1,6) if self.solid(gx+dx*n,gy+dy*n)),6)
        self.guard_direction=max(range(4),key=open_length)
        self.guard_alert_until=0.0
        self.guard_hp, self.fountain_used = 3, False
        self.phase = run_number % 3
        self.phase_time = self.time = 0.0
        self.attack_time = 10.0
        self.visible, self.visited = set(), set()
        self.map_open, self.reveal_all = False, False
        self.banner, self.banner_until = '횃불에 접근해 F를 눌러 보세요', 5.0
        self.trap_progress, self.trap_x, self.trap_cooldown = 0.0, 0.0, 0.0
        self.trap_return = None
        self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
        self.trap_hit_at = -10.0
        self.machine = Machine(model=self, states=['explore', 'trap', 'clear'],
            initial='explore', auto_transitions=False,
            transitions=[['enter_room', 'explore', 'trap'], ['leave_room', 'trap', 'explore'],
                         ['escape', 'explore', 'clear']])
        self.player_machine = Machine(model=self.player, states=['idle', 'walk', 'sprint', 'attack'],
            initial='idle', auto_transitions=False,
            transitions=[['rest', '*', 'idle'], ['walk_now', '*', 'walk'],
                         ['sprint_now', '*', 'sprint'], ['swing', '*', 'attack']])
        self.update_visibility()

    def message(self, text, seconds=3):
        self.banner, self.banner_until = text, self.time+seconds

    def solid(self, x, y):
        return not (0 <= x < COLS and 0 <= y < ROWS) or self.grid[y][x] == 1

    def can_stand(self, x, y):
        return all(not self.solid(math.floor(x+dx), math.floor(y+dy))
                   for dx in (-.21, .21) for dy in (-.21, .21))

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
        fx, fy = DIRECTIONS[player.direction]
        reach = 7 if player.torch else 5.5
        for y in range(max(0, int(player.y-reach)), min(ROWS, math.ceil(player.y+reach))):
            for x in range(max(0, int(player.x-reach)), min(COLS, math.ceil(player.x+reach))):
                dx, dy = x+.5-player.x, y+.5-player.y
                distance = math.hypot(dx, dy)
                cone = distance < 1.6 or player.torch or (dx*fx+dy*fy)/max(.01, distance) > .48
                if distance <= reach and cone and self.line_of_sight(x, y):
                    visible.add((x, y))
        self.visible = visible
        self.visited |= visible
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
            self.trap_progress = self.trap_x = self.trap_cooldown = 0.0
            self.trap_velocity = self.trap_side_velocity = self.trap_stride = 0.0
            self.trap_discovered = True
            self.map_open = False
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
            self.escape()
        self.update_visibility()

    def return_from_trap(self, completed=False):
        if self.state != 'trap':
            return
        self.player.x, self.player.y = ((self.trap_exit[0]+.5, self.trap_exit[1]+.5)
                                      if completed else self.trap_return)
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
        if self.state != 'explore' or self.map_open or self.attack_time < .75:
            return
        self.attack_time = 0
        self.player.swing()
        if self.guard_hp > 0 and self.close_to(self.guard, 1.8):
            self.guard_hp -= 1
            self.guard_alert_until=self.time+2.5
            self.message('수호자 타격' if self.guard_hp else '수호자 처치 · 추적 AI는 다음 단계')

    def update(self, dt, dx=0, dy=0, sprint=False):
        dt = min(.05, max(0, dt))
        self.time += dt
        self.attack_time += dt
        if self.state == 'clear':
            return
        self.phase_time += dt
        if self.phase_time >= 60:
            self.phase_time -= 60
            self.phase = (self.phase+1) % 3
            if self.state == 'trap':
                self.return_from_trap()
                self.message(f'{PHASES[self.phase]} 전환 · A 입구로 복귀')
                return
            self.message(f'{PHASES[self.phase]} 조명으로 전환 · 지형 변형은 다음 단계')
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
                    self.trap_progress = max(0,plane-.06)
                    self.trap_velocity = -.5
                    self.trap_cooldown = 1.0
                    self.trap_hit_at = self.time
                    self.message('칼날 피격 · 좌우로 피해서 통과하세요')
            if self.trap_progress >= 1:
                self.return_from_trap(completed=True)
            if self.player.hp <= 0:
                self.player.hp = 100
                self.return_from_trap()
                self.message('시제품: 쓰러져 입구로 복귀 · 체력 초기화')
            return
        if self.map_open:
            dx = dy = 0
        magnitude = math.hypot(dx, dy)
        if magnitude:
            if abs(dx) > abs(dy):
                self.player.direction = 2 if dx > 0 else 1
            elif dy:
                self.player.direction = 0 if dy > 0 else 3
            running = sprint and self.player.stamina > 0
            speed = 4.1 if running else 2.5
            vx, vy = dx/magnitude*dt*speed, dy/magnitude*dt*speed
            if self.can_stand(self.player.x+vx, self.player.y):
                self.player.x += vx
            if self.can_stand(self.player.x, self.player.y+vy):
                self.player.y += vy
            if running:
                self.player.stamina = max(0, self.player.stamina-dt*18)
                self.player.sprint_now()
            else:
                self.player.walk_now()
        elif self.attack_time >= .75:
            self.player.rest()
        self.update_visibility()
