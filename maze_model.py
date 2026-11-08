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
