"""실제 새 판의 해·분기 지표, 순서/되짚기, 60초 안의 예약·다음 시간대 통과."""
from collections import deque
from math import ceil
from SourceCode.mouse_maze import BOARD, MAZE, START_CELL, GOAL_CELL, WAYPOINTS, MouseMaze, cell_center
from SourceCode.maze_model import Game, PHASE_SECONDS

SOLUTION_CORNERS = ((3,1),(3,3),(1,3),(1,5),(5,5),(5,1),(9,1),(9,3),(7,3),(7,5),(11,5),(11,1))
EXIT_SHORTCUT = ((3,1),(3,3),(11,3),(11,1))
SECOND_FIRST = ((3,1),(3,3),(5,3),(5,1),(9,1))


def topology():
    floor = {(x,y) for y,row in enumerate(MAZE) for x,tile in enumerate(row) if tile != '#'}
    def neighbors(cell):
        x,y = cell
        return [p for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)) if p in floor]
    reached = {START_CELL}
    pending = deque([START_CELL])
    while pending:
        for node in neighbors(pending.popleft()):
            if node not in reached:
                reached.add(node);pending.append(node)
    assert reached == floor, 'hand-authored board has an unreachable region'
    routes,valid = [],[]
    def search(cell,path):
        if cell == GOAL_CELL:
            routes.append(len(path)-1)
            if [node for node in path if node in WAYPOINTS] == list(WAYPOINTS):valid.append(len(path)-1)
            return
        for node in neighbors(cell):
            if node not in path:search(node,path+[node])
    search(START_CELL,[START_CELL])
    junctions = sum(len(neighbors(cell)) >= 3 for cell in floor)
    dead_ends = sum(len(neighbors(cell)) == 1 for cell in floor if cell not in (START_CELL,GOAL_CELL))
    assert valid and len(routes) > len(valid)+8
    assert junctions >= 8 and dead_ends >= 3
    assert min(valid) >= 30 and min(valid) >= min(routes)+12
    assert all(MAZE[y][x] == str(index+1) for index,(x,y) in enumerate(WAYPOINTS))
    assert MAZE[START_CELL[1]][START_CELL[0]] == 'S' and MAZE[GOAL_CELL[1]][GOAL_CELL[0]] == 'G'
    print(f'PASS: actual {len(MAZE[0])}x{len(MAZE)} board, {len(floor)} floor cells, {junctions} junctions, {dead_ends} dead ends; {len(routes)} goal routes/{len(valid)} ordered solutions; shortest {min(routes)} vs ordered {min(valid)} edges.')


def trace(maze,corners):
    results = [maze.move(cell_center(*cell)) for cell in corners]
    assert not any(results[:-1])
    return results[-1]


def check_order_and_rewind():
    for route in (EXIT_SHORTCUT,SECOND_FIRST):
        maze = MouseMaze();maze.press(cell_center(*START_CELL))
        assert not trace(maze,route) and not maze.completed and maze.progress == 0
        if route == SECOND_FIRST:
            assert maze.sequence_error and WAYPOINTS[1] in maze.path
            trace(maze,((5,1),(5,3),(3,3)))
            assert not maze.sequence_error
        else:
            assert maze.cell == GOAL_CELL
            trace(maze,((11,3),(3,3)))
        assert trace(maze,SOLUTION_CORNERS[2:]) and maze.completed and maze.progress == 3

    maze = MouseMaze();maze.press(cell_center(*START_CELL))
    assert not trace(maze,SOLUTION_CORNERS[:7]) and maze.progress == 2
    assert not maze.move(cell_center(*WAYPOINTS[1]))
    x,y = cell_center(*WAYPOINTS[1])
    assert not maze.move((x-3,y)) and maze.progress == 1
    assert maze.cell == WAYPOINTS[1] and maze.retained_path[-1] != WAYPOINTS[1]
    saved = maze.path[:],maze.cursor,maze.preview_cell,maze.progress
    maze.release();maze.press(maze.cursor)
    assert (maze.path,maze.cursor,maze.preview_cell,maze.progress) == saved
    assert not maze.move((x,y)) and maze.progress == 2
    trace(maze,((5,1),(5,5),(1,5)))
    assert maze.progress == 1
    x,y = cell_center(*WAYPOINTS[0])
    assert not maze.move((x,y-3)) and maze.progress == 0
    assert not maze.move((x,y)) and maze.progress == 1
    maze.reset()
    assert maze.progress == 0 and not maze.sequence_error and maze.path == [START_CELL]

    # 새 셀 크기에서도 첫 직선과 둥글게 돌아 내려가는 입력을 그대로 스냅한다.
    maze.press(cell_center(*START_CELL));maze.move(cell_center(2,1))
    cx,cy = cell_center(3,1)
    for ox,oy in ((-10,0),(-6,1),(-4,3),(-2,8),(-2,9),(-2,11),(-2,16),(-2,22),(-2,27)):
        assert not maze.move((cx+ox,cy+oy)) and not maze.hit_wall,(ox,oy)
    assert maze.cursor == (cx,cy+27) and maze.cell == (3,2)
    print('PASS: exit-only/second-first rejected, multi-cell marker order, full/partial rewind, resume/reset and new-board rounded first corner.')


def check_game():
    assert PHASE_SECONDS == 60
    times = []
    for phase in range(3):
        game = Game(117,phase)
        wall,near,far = game.puzzle_gate
        game.player.x,game.player.y = near[0]+.5,near[1]+.5
        game.guard_hp = 0;game.update_visibility();game.interact()
        assert game.state == 'puzzle'
        game.puzzle.press(cell_center(*START_CELL))
        for cell in EXIT_SHORTCUT:game.drag_puzzle(cell_center(*cell))
        assert game.state == 'puzzle' and game.puzzle_reserved_phase is None and game.solid(*wall)
        game.puzzle.reset();game.puzzle.press(cell_center(*START_CELL))
        for cell in SOLUTION_CORNERS[:4]:game.drag_puzzle(cell_center(*cell))
        assert game.puzzle.progress == 1
        saved = game.puzzle.path[:],game.puzzle.cursor
        game.take_guard_hit()
        assert game.state == 'explore' and game.puzzle.progress == 1
        game.interact();game.puzzle.press(game.puzzle.cursor)
        assert (game.puzzle.path,game.puzzle.cursor) == saved
        game.phase_time = PHASE_SECONDS-.01;game.update(.02)
        assert game.puzzle.progress == 0 and game.puzzle.path == [START_CELL]
        while game.state == 'shifting':game.update(.05)
        assert game.solid(*wall) and game.puzzle_reserved_phase is None
        game.interact();game.puzzle.press(cell_center(*START_CELL))
        for _ in range(300):game.update(.05)  # 판 읽기 15초를 포함한 시뮬레이션 예산.
        previous = START_CELL
        started = game.time-15
        for cell in SOLUTION_CORNERS:
            duration = .3*(abs(cell[0]-previous[0])+abs(cell[1]-previous[1]))
            ticks = ceil(duration/.05)
            for _ in range(ticks):game.update(duration/ticks)
            game.drag_puzzle(cell_center(*cell));previous=cell
        times.append(game.time-started)
        assert game.state == 'explore' and game.puzzle_reserved_phase == game.next_phase
        assert game.phase_time < 40 and game.solid(*wall)
        game.phase_time = PHASE_SECONDS-.01;game.update(.02)
        while game.state == 'shifting':game.update(.05)
        assert game.puzzle_open and not game.solid(*wall)
        for _ in range(40):game.update(.02,0,1)
        assert abs(game.player.y-far[1]-.5) < 1e-6
    print(f'PASS: new board, 3 phases, rejected exit, real hit resume/phase reset/reservation/door crossing; scripted read+trace {max(times):.2f}s of 60s (not human play timing).')


def run():
    topology();check_order_and_rewind();check_game()


if __name__ == '__main__':
    run()
