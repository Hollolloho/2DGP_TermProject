"""시간대 변형의 연결성·충돌·안전 복귀·기록·자원 유지 검사. SDL 창 없이 실행한다."""
import math
from SourceCode.maze_model import (Game, COLS, ROWS, DIRECTIONS, PHASE_SECONDS,
                                   PHASE_WARNING_SECONDS, SHIFT_SWAP_AT, GUARD_DAMAGE, RETURN_REASON_SECONDS, distances)
from SourceCode.mouse_maze import BOARD, MAZE, START_CELL, GOAL_CELL, MouseMaze, cell_at, cell_center
from .mouse_maze_fixture import legacy_mouse_maze


def finish_shift(game):
    for _ in range(20):
        if game.state != 'shifting':
            return
        game.update(.05, 1, -1, True)
    raise AssertionError('변형 상태가 종료되지 않음')


def start_shift(game):
    game.phase_time = PHASE_SECONDS-.01
    game.update(.02)
    assert game.state == 'shifting'


def check_phase_changes():
    for seed in range(32):
        for run in range(3):
            game = Game(seed, run)
            layouts = game.maze_layouts
            assert game.puzzle_gate is not None, (seed, run)
            assert game.phase == game.layout_phase == run
            assert game.grid == layouts.grids[run] and game.grid is not layouts.grids[run]
            copied = layouts.copy_for_phase(run)
            copied[game.spawn[1]][game.spawn[0]] = 1
            assert layouts.grids[run][game.spawn[1]][game.spawn[0]] == 0
            base = layouts.grids[0]
            for phase, grid in enumerate(layouts.grids):
                assert layouts.is_valid(grid)
                assert all(grid[0]) and all(grid[-1]) and all(row[0] and row[-1] for row in grid)
                changes = {(x, y) for y in range(ROWS) for x in range(COLS) if grid[y][x] != base[y][x]}
                assert len(changes) == (0 if phase == 0 else 6)
                assert not changes & layouts.protected_cells
                tx, ty = game.torch_cell
                wx, wy = game.torch_wall
                assert (wx-tx, wy-ty) in ((-1, 0), (0, -1))
                assert grid[ty][tx] == 0 and grid[wy][wx] == 1
                assert (tx, ty) in distances(grid, game.spawn)
                assert game.torch_wall_contact == ((tx+wx+1)/2, (ty+wy+1)/2)

            # 모든 시작 시간대에서 한 바퀴 돈다. 이전 시간대 기록으로 새 지형을 공개하지 않는다.
            game.player.hp, game.player.stamina = 61, 37.
            game.fountain_used = game.player.torch = True
            game.observed = game.observed_by_phase[run]
            game.observed.update((x, y) for y in range(ROWS) for x in range(COLS))
            game.visited.update(distances(game.grid, game.spawn))
            saved_observed, saved_visited = set(game.observed), set(game.visited)
            game.attack()
            locked_facing = game.attack_facing
            for index in range(3):
                old_phase = game.phase
                old_grid = game.grid
                previous_time = game.time
                previous_position = game.player.x, game.player.y
                old_resources = game.player.hp, game.player.stamina, game.fountain_used, game.player.torch
                start_shift(game)
                assert game.grid is old_grid and game.phase == old_phase
                assert game.time == previous_time
                assert game.attack_time == 0 and game.attack_facing == locked_facing
                for _ in range(4):
                    game.update(.05, 1, 1, True)
                assert game.shift_elapsed < SHIFT_SWAP_AT and game.grid is old_grid
                game.attack()
                game.interact()
                assert (game.player.x, game.player.y) == previous_position
                finish_shift(game)
                assert game.phase == game.layout_phase == (old_phase+1) % 3
                assert game.layout_revision == index+1
                assert game.phase_time == 0 and not game.phase_warning
                assert game.grid == layouts.grids[game.phase]
                assert game.grid != old_grid
                assert game.time == previous_time
                assert (game.player.hp, game.player.stamina, game.fountain_used, game.player.torch) == old_resources
                assert game.can_stand(game.player.x, game.player.y)
                assert len(distances(game.grid, game.exit)) == sum(row.count(0) for row in game.grid)
                for y in range(ROWS):
                    for x in range(COLS):
                        assert game.can_stand(x+.5, y+.5) == (game.grid[y][x] == 0)
                if index < 2:
                    assert game.observed == game.visible
                    assert game.visited == {game.spawn}
                else:
                    assert saved_observed <= game.observed and saved_visited <= game.visited

            # 각 시작 시간대에서 닫히는 모든 칸과 몸 일부가 걸치는 경계도 확인한다.
            next_grid = layouts.grids[(game.phase+1) % 3]
            for y in range(1, ROWS-1):
                for x in range(1, COLS-1):
                    if game.grid[y][x] or not next_grid[y][x]:
                        continue
                    positions = [(x+.5, y+.5)]
                    for dx, dy in DIRECTIONS:
                        if not game.solid(x+dx, y+dy):
                            positions.append((x+.5+dx*.6, y+.5+dy*.6))
                    for px, py in positions:
                        game.player.x, game.player.y = px, py
                        assert game.can_stand(px, py) and not game.can_stand(px, py, next_grid)
                        safe = game.safe_position(next_grid)
                        assert game.can_stand(*safe) and game.can_stand(*safe, next_grid)
                        route = distances(game.grid, (math.floor(px), math.floor(py)))
                        assert (math.floor(safe[0]), math.floor(safe[1])) in route
            # 실제 교체에서도 좌표가 보정되는지 확인한다.
            closed = next((x, y) for y in range(ROWS) for x in range(COLS)
                          if not game.grid[y][x] and next_grid[y][x])
            game.player.x, game.player.y = closed[0]+.5, closed[1]+.5
            start_shift(game)
            finish_shift(game)
            assert game.can_stand(game.player.x, game.player.y)
            assert (math.floor(game.player.x), math.floor(game.player.y)) != closed

            # 보호된 입구 주변에서 정확한 소수 좌표·방향으로 복귀한다.
            x, y = game.trap_cell
            game.player.x, game.player.y = x+.4, y+.6
            game.player.direction = 2
            saved = game.player.x, game.player.y, game.player.direction
            before = game.grid
            game.interact()
            assert game.state == 'trap'
            game.trap_velocity, game.trap_side_velocity = 1.5, .8
            game.trap_progress = .4
            start_shift(game)
            assert (game.player.x, game.player.y, game.player.direction) == saved
            finish_shift(game)
            assert (game.player.x, game.player.y, game.player.direction) == saved
            assert game.trap_velocity == game.trap_side_velocity == 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    assert before[y+dy][x+dx] == game.grid[y+dy][x+dx]

    game = Game()
    game.phase_time = PHASE_SECONDS-PHASE_WARNING_SECONDS-.01
    game.update(.02)
    assert game.phase_warning and game.state == 'explore'
    for phase in range(3):
        game = Game(117, phase)
        game.player.stamina = 20.
        game.update(.05)
        assert math.isclose(game.player.stamina, 20.4 if phase == 2 else 20.)
    print('PASS: 96 starts, 288 layouts, 480 transitions; routes, one swap, frozen world, safe relocation, exact trap return, phase maps and resources.')
    check_return_guidance()


def check_return_guidance():
    reason = '시간대 전환으로 입장 위치 복귀'
    for course in (False,True):
        for room in ('blade','boulder','path-entering','path-active'):
            game = Game(117,test_course=course)
            cell = (game.trap_cell if room == 'blade' else game.boulder_entry if room == 'boulder' else game.path_entry)
            game.player.x,game.player.y = cell[0]+.45,cell[1]+.55
            game.player.direction = 2
            game.guard_hp = 0
            game.update_visibility()
            game.puzzle_reserved_phase = game.next_phase
            saved = game.player.x,game.player.y,game.player.direction
            game.interact()
            if room.startswith('path'):
                assert game.state == 'path_room'
                for _ in range(21 if room == 'path-active' else 4):game.update(.05)
                assert game.world_path.stage == ('active' if room == 'path-active' else 'entering')
            else:
                assert game.state == 'trap' and game.trap_kind == room
            resources = game.player.hp,game.player.stamina
            before = game.time
            start_shift(game)
            assert game.shift_returned_from_room and game.state == 'shifting'
            assert (game.player.x,game.player.y,game.player.direction) == saved
            finish_shift(game)
            assert game.state == 'explore' and (game.player.x,game.player.y,game.player.direction) == saved
            assert (game.player.hp,game.player.stamina) == resources and game.time == before
            assert game.banner == reason and math.isclose(game.banner_until-game.time,RETURN_REASON_SECONDS)
            assert not game.shift_returned_from_room and game.puzzle_open
            assert not game.solid(*game.puzzle_gate[0])
            # 다음 일반 전환에 지난 복귀 이유를 다시 표시하지 않는다.
            start_shift(game);finish_shift(game)
            assert game.banner != reason and '미로의 길이 바뀌었습니다' in game.banner
            assert not Game(117,test_course=course).shift_returned_from_room
    print('PASS: general/course blade, boulder and entering/active slab rooms show the 5s phase-return reason after transformation; exact position/facing, resources and P opening preserved; no stale reason on normal shift/new run.')


@legacy_mouse_maze
def check_first_puzzle():
    left, top, size = BOARD
    center = cell_center
    start, corner, goal = center(*START_CELL), center(3, 1), center(*GOAL_CELL)
    route = (corner, center(3, 3), center(5, 3), center(5, 1), goal)
    assert cell_at((left, top)) == (0, 0)
    assert cell_at((left-.001, top)) is None
    assert cell_at((left+len(MAZE[0])*size, top)) is None
    assert cell_at((left, top+len(MAZE)*size)) is None
    assert cell_at((left+2*size-.001, start[1])) == START_CELL
    assert cell_at((left+2*size, start[1])) == (2, 1)

    maze = MouseMaze()
    assert maze.path == [START_CELL] and maze.cursor == start and not maze.dragging
    maze.press(start)
    halfway = (start[0]+size//2+3, start[1])
    assert not maze.move((halfway[0], halfway[1]+4))
    assert maze.path == [START_CELL] and maze.cursor == halfway
    assert maze.preview_cell == (2, 1)
    maze.release()
    assert not maze.move(corner) and maze.path == [START_CELL]
    assert maze.cursor == halfway and maze.preview_cell == (2, 1)
    maze.press(goal)
    assert not maze.dragging
    maze.press(halfway)
    assert maze.dragging and maze.cursor == halfway
    for point in ((167, 207), center(3, 2)):  # 벽 내부와 한 번에 꺾는 대각선 이동
        assert not maze.move(point) and maze.hit_wall
        assert maze.path == [START_CELL] and maze.cursor == halfway
    assert not maze.move(corner)
    assert maze.path == [START_CELL, (2, 1), (3, 1)]
    assert maze.cursor == corner and maze.preview_cell is None
    for invalid in (goal, center(5, 3), (left-1, corner[1])):
        assert not maze.move(invalid)
        assert maze.hit_wall and maze.dragging
        assert maze.path == [START_CELL, (2, 1), (3, 1)] and maze.cursor == corner
    retreat = (corner[0]-size//2, corner[1])
    assert not maze.move(retreat) and not maze.hit_wall
    assert maze.cell == (3, 1) and maze.preview_cell == (2, 1) and maze.cursor == retreat
    assert not maze.move(center(2, 1))
    assert maze.path == [START_CELL, (2, 1)] and maze.preview_cell is None
    assert not maze.move(start)
    assert maze.path == [START_CELL]
    assert not maze.move(corner)
    for point in route[1:-1]:
        assert not maze.move(point) and maze.cell == cell_at(point)
    assert not maze.move(center(8, 1))  # 도착 칸을 가로질러 벽에 들어가면 실패한다.
    assert maze.hit_wall and maze.cell == (5, 1) and maze.dragging
    assert maze.cursor == center(5, 1)
    assert maze.move(goal) and maze.cell == GOAL_CELL

    for offset in (-10, -6, -3, 3, 6, 10):
        maze.reset()
        maze.press(start)
        assert not maze.move(center(2, 1))
        assert not maze.move((163, 185+offset))
        assert maze.cursor == (163, 185) and not maze.hit_wall
        assert not maze.move(corner)
        assert not maze.move((185+offset, 207))
        assert maze.cursor == (185, 207) and not maze.hit_wall

    maze.reset()
    maze.press(start)
    assert not maze.move(center(2, 1))
    rounded = ((170, 185), (175, 186), (179, 190), (182, 197), (182, 199),
               (182, 202), (182, 209), (182, 219), (182, 226))
    previous = sum(maze.cursor)
    for point in rounded:
        assert not maze.move(point) and not maze.hit_wall, point
        x, y = maze.cursor
        assert (151 <= x <= 185 and y == 185) or (x == 185 and 185 <= y <= 226)
        assert sum(maze.cursor) > previous, (point, maze.cursor)
        previous = sum(maze.cursor)
    assert maze.path == [START_CELL, (2, 1), (3, 1), (3, 2)]
    assert maze.cursor == (185, 226) and maze.preview_cell == (3, 3)

    maze.reset()
    maze.press(start)
    for point in (center(2, 1), (170, 185), (171, 189), (173, 190), (174, 192)):
        assert not maze.move(point) and not maze.hit_wall, point
        if point[1] > corner[1]:
            assert maze.cursor == (corner[0], point[1]) and maze.preview_cell == (3, 2)
    assert not maze.move((167, 193)) and maze.hit_wall
    assert maze.cursor == (185, 192) and maze.preview_cell == (3, 2)
    for point in ((176, 191), (178, 188), (178, 185)):
        assert not maze.move(point) and not maze.hit_wall, point
        assert maze.cursor == (corner[0], point[1])
    assert maze.cursor == corner and maze.preview_cell is None
    assert not maze.move((175, 185)) and maze.cursor == (175, 185) and maze.preview_cell == (2, 1)
    assert not maze.move(center(2, 1)) and maze.path == [START_CELL, (2, 1)]

    for goal_x in (304, 319):
        maze.reset()
        maze.press(start)
        for point in (corner, center(3, 3), center(5, 3), (253, 250), (246, 247)):
            assert not maze.move(point) and not maze.hit_wall, point
        assert maze.cursor == (253, 247) and maze.preview_cell == (5, 2)
        for invalid in ((270, 204), center(6, 1)):
            assert not maze.move(invalid) and maze.hit_wall
            assert maze.cursor == (253, 247) and maze.preview_cell == (5, 2)
        assert not maze.move((264, 192)) and not maze.hit_wall
        assert maze.cell == (5, 1) and maze.cursor == (264, 185) and maze.preview_cell == (6, 1)
        assert not maze.move((264, 194)) and not maze.hit_wall
        assert maze.cursor == (264, 185) and maze.preview_cell == (6, 1)
        assert maze.move((goal_x, goal[1])) and not maze.hit_wall
        assert maze.cell == GOAL_CELL

    maze.reset()
    maze.press(start)
    for point, projected in (
            (corner, corner), ((185, 247), (185, 247)), ((190, 254), (190, 253)),
            ((247, 253), (247, 253)), ((253, 259), (253, 253)), ((269, 244), (253, 244)),
            ((253, 198), (253, 198)), ((236, 184), (253, 185)), ((252, 181), (253, 185)),
            ((264, 192), (264, 185))):
        assert not maze.move(point) and not maze.hit_wall, point
        assert maze.cursor == projected, (point, maze.cursor)
        if point in ((190, 254), (253, 259), (269, 244)):
            saved_path, saved_preview = maze.path[:], maze.preview_cell
            for invalid in ((point[0], 270), center(6, 1)):
                assert not maze.move(invalid) and maze.hit_wall, invalid
                assert maze.path == saved_path and maze.cursor == projected
                assert maze.preview_cell == saved_preview
    assert maze.move((304, goal[1])) and maze.cell == GOAL_CELL

    for run in range(3):
        game = Game(117, run)
        wall, near, far = game.puzzle_gate
        assert (wall, near, far) == ((17, 6), (17, 5), (17, 7))
        game.interact()
        assert game.state == 'explore'
        game.player.x, game.player.y = near[0]+.5, near[1]+.5
        game.update_visibility()
        game.interact()
        assert game.state == 'puzzle'
        game.puzzle.press(start)
        game.drag_puzzle(corner)
        game.close_puzzle()
        assert game.puzzle.cell == (3, 1) and not game.puzzle.dragging
        assert game.puzzle.path == [START_CELL, (2, 1), (3, 1)] and game.puzzle.cursor == corner
        game.interact()
        assert game.state == 'puzzle'
        position = game.player.x, game.player.y
        game.update(.05, 0, 2)
        game.attack()
        assert (game.player.x, game.player.y) == position and game.phase_time > 0
        assert not game.attack_hits_ms and game.player.hp == 100
        start_shift(game)
        game.drag_puzzle(goal)
        assert game.puzzle.cell == START_CELL and not game.puzzle.dragging
        assert game.puzzle.path == [START_CELL] and game.puzzle.cursor == start
        assert game.puzzle_reserved_phase is None
        finish_shift(game)
        assert game.solid(*wall)
        game.interact()
        game.puzzle.press(start)
        for point in route:
            game.drag_puzzle(point)
        reserved = (game.phase+1) % 3
        assert game.state == 'explore' and game.puzzle_reserved_phase == reserved and game.solid(*wall)
        assert game.puzzle.path == [START_CELL] and not game.puzzle.dragging
        game.interact()
        assert game.state == 'explore'
        start_shift(game)
        assert wall in game.shift_cells and game.solid(*wall)
        while not game.shift_applied:
            game.update(.05)
        assert game.phase == reserved and game.puzzle_open and game.puzzle_reserved_phase is None
        assert not game.solid(*wall) and game.maze_layouts.is_valid(game.grid)
        finish_shift(game)
        for _ in range(32):
            game.update(.025, 0, 1)
        assert math.isclose(game.player.y, far[1]+.5, abs_tol=1e-8)
        for _ in range(16):
            game.update(.025, 0, -1)
        on_gate = game.player.x, game.player.y
        assert (int(on_gate[0]), int(on_gate[1])) == wall
        for _ in range(3):
            start_shift(game)
            finish_shift(game)
            assert not game.solid(*wall) and (game.player.x, game.player.y) == on_gate
        fresh = Game(game.seed, run+1)
        assert fresh.solid(*fresh.puzzle_gate[0]) and not fresh.puzzle_open
        assert fresh.puzzle.cell == START_CELL and not fresh.puzzle.dragging
        assert all(grid[wall[1]][wall[0]] for grid in game.maze_layouts.grids)
    print('PASS: projected edges, intermediate nodes, backtracking, invalid-move rejection, resume, phase cancellation and delayed traversal.')
    check_puzzle_both_sides()


@legacy_mouse_maze
def check_puzzle_both_sides():
    def stand(game, point):
        assert game.can_stand(*point)
        game.player.x, game.player.y = point
        game.update_visibility()

    def center(cell):
        return cell[0]+.5, cell[1]+.5

    for seed, run in [(117, phase) for phase in range(3)]+[(0, 0)]:
        game = Game(seed, run)
        wall, near, far = game.puzzle_gate
        assert (near[1] == far[1]) == (seed == 0)
        positions = [center(near), center(far)]
        if seed == 117:
            positions.append((17.28, 7.21))
        for position in positions:
            stand(game, position)
            assert wall in game.visible and game.puzzle_available(), (seed, run, position)
            game.interact()
            assert game.state == 'puzzle'
            game.close_puzzle()

    game = Game(117, 2)
    wall, near, far = game.puzzle_gate
    stand(game, (16.5, 7.5))
    assert wall in game.visible and not game.puzzle_available()
    game.interact()
    assert game.state == 'explore'
    stand(game, (19.5, 5.5))
    assert not game.line_of_sight(*wall) and not game.puzzle_available()
    stand(game, (17.28, 7.21))
    game.visible.discard(wall)
    assert not game.puzzle_available()

    stand(game, center(far))
    game.interact()
    assert game.state == 'puzzle' and game.phase == 2
    game.puzzle.press(cell_center(*START_CELL))
    for cell in ((3, 1), (3, 3), (5, 3), (5, 1), GOAL_CELL):
        game.drag_puzzle(cell_center(*cell))
    assert game.state == 'explore' and game.puzzle_reserved_phase == 0 and game.solid(*wall)
    for position in (center(near), center(far)):
        stand(game, position)
        assert wall in game.visible and not game.puzzle_available()
        game.interact()
        assert game.state == 'explore' and game.puzzle_reserved_phase == 0
    start_shift(game)
    finish_shift(game)
    assert game.phase == 0 and game.puzzle_open and not game.solid(*wall)
    for _ in range(32):
        game.update(.025, dy=-1)
    assert all(math.isclose(actual, expected)
               for actual, expected in zip((game.player.x, game.player.y), center(near)))
    for position in (center(near), center(far)):
        stand(game, position)
        assert not game.puzzle_available()
        game.interact()
        assert game.state == 'explore'
    print('PASS: both sides of vertical and horizontal puzzle gates, range/visibility and dawn-to-day traversal.')


def guardian_interrupts_puzzle():
    game = Game()
    wall, near, _ = game.puzzle_gate
    player = game.player
    player.x, player.y = near[0]+.5, near[1]+.5
    game.guard = near[0], near[1]-2
    game.update_visibility()
    game.interact()
    assert game.state == 'puzzle'
    start, corner = cell_center(*START_CELL), cell_center(3, 1)
    game.puzzle.press(start)
    game.drag_puzzle(corner)
    game.drag_puzzle((corner[0], corner[1]+10))
    path = game.puzzle.path[:]
    cursor, preview = game.puzzle.cursor, game.puzzle.preview_cell
    hp = player.hp
    windup = False
    for _ in range(80):
        game.update(.025)
        if game.state != 'puzzle':
            break
        windup |= game.guard_attack_at is not None
        assert player.hp == hp and game.puzzle.dragging
    assert windup and game.state == 'explore' and player.hp == hp-GUARD_DAMAGE
    assert not game.puzzle.dragging and game.puzzle.path == path
    assert (game.puzzle.cursor, game.puzzle.preview_cell) == (cursor, preview)
    assert game.puzzle_reserved_phase is None and game.solid(*wall)
    return game


@legacy_mouse_maze
def check_guardian_puzzle():
    interrupted = guardian_interrupts_puzzle()
    start_shift(interrupted)
    finish_shift(interrupted)
    assert interrupted.puzzle.path == [START_CELL] and not interrupted.puzzle.dragging
    assert interrupted.puzzle.cursor == cell_center(*START_CELL) and interrupted.puzzle.preview_cell is None
    assert interrupted.puzzle_reserved_phase is None and interrupted.solid(*interrupted.puzzle_gate[0])

    # Resume while the same guardian has to wait for its next attack.
    game = guardian_interrupts_puzzle()
    wall = game.puzzle_gate[0]
    hp = game.player.hp
    game.interact()
    assert game.state == 'puzzle'
    game.puzzle.press(game.puzzle.cursor)
    game.update(.025)
    assert game.puzzle.dragging and game.player.hp == hp
    for cell in ((3, 3), (5, 3), (5, 1), GOAL_CELL):
        game.drag_puzzle(cell_center(*cell))
    assert game.state == 'explore' and game.puzzle_reserved_phase == game.next_phase
    start_shift(game)
    finish_shift(game)
    assert game.puzzle_open and not game.solid(*wall)
    assert game.player.hp == hp
    print('PASS: live guardian damage interrupts puzzle; shift clears an unfinished path or opens a reserved gate.')


if __name__ == '__main__':
    check_phase_changes()
    check_first_puzzle()
    check_guardian_puzzle()
