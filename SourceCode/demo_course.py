"""검수 코스의 고정 지형과 지점. 일반 시드 생성에서는 사용하지 않는다."""
SEED = 117
GUARD_HOME = (24, 13)
FIRST_VARIABLE_ROW = 13
SPAWN, BLADE_ENTRY, BLADE_EXIT = (3, 1), (8, 1), (5, 3)
BOULDER_ENTRY, BOULDER_EXIT = (2, 3), (26, 5)
MOUSE_GATE = ((23, 6), (23, 5), (23, 7))
SLAB_ENTRY, SLAB_EXIT = (20, 7), (19, 9)
CHOICE_ENTRY, CHOICE_EXIT = (22, 9), (18, 17)
CHOICE_GATES = ((24, 10), (26, 10))


def build_grid(base, distances):
    # 위쪽 함정/퍼즐 코스와 아래쪽 두 갈래는 시간대마다 같은 모양이다.
    # 남서쪽 원본 미로에서 기존 시간대별 변형을 계속 사용한다.
    grid = [row[:] for row in base]
    for y in range(len(grid)):
        for x in range(len(grid[y])):
            if y < FIRST_VARIABLE_ROW or x >= 14:
                grid[y][x] = 1
    for y in (1, 3, 5, 7, 9):
        for x in range(2, 29):
            grid[y][x] = 0
        if y < 9:
            grid[y+1][28 if y % 4 == 1 else 2] = 0
    # 상시 우회는 동쪽 끝으로, 짧은 문은 수호자 앞을 통과한다.
    floors = [
        *((28, y) for y in range(10, 14)),
        *((26, y) for y in range(11, 18)),
        *((x, 13) for x in range(26, 29)),
        *((x, 17) for x in range(15, 27)),
        *((24, y) for y in range(11, 16)),
        *((x, 15) for x in range(18, 25)),
        (18, 16),
        *((15, y) for y in range(11, 18)),
        *((x, 11) for x in range(9, 16)),
        (9, 12),
    ]
    for x, y in floors:
        grid[y][x] = 0
    reachable = distances(grid, SPAWN)
    for y in range(len(grid)):
        for x in range(len(grid[y])):
            if (x, y) not in reachable:
                grid[y][x] = 1
    return grid
