"""실제 통로 방의 진입·보행·포트 충돌·복귀·즉시 통과. SDL 없이 실행한다."""
from SourceCode.maze_model import Game, PHASE_SECONDS, distances
from SourceCode.mouse_maze import START_CELL, cell_center
from SourceCode.path_connection import N, E, S, W
from .checks_phase_changes import finish_shift
from .check_waypoint_maze import SOLUTION_CORNERS

SOLUTION = ((0,(0,1),(W,E)),(1,(1,1),(W,E)),(3,(2,1),(W,S)),
            (4,(2,2),(N,E)),(2,(3,2),(W,E)))


def opened(game=None):
    game = game or Game(117)
    x,y = game.path_entry
    game.player.x,game.player.y = x+.55,y+.45
    game.guard_hp = 0
    game.update_visibility()
    saved = game.player.x,game.player.y
    game.interact()
    assert game.state == 'path_room' and game.world_path.stage == 'entering'
    before = game.player.gait_distance
    for _ in range(21):game.update(.05)
    assert game.world_path.stage == 'active' and game.player.gait_distance > before
    assert game.can_stand(game.player.x,game.player.y)
    return game,saved


def put(game, item):
    index,cell,ports = item
    assert game.pick_connection(index)
    for _ in range(4):
        if game.connection.pieces[index].ports == frozenset(ports):break
        assert game.rotate_connection()
    assert game.drop_connection(cell)


def solve(game):
    for item in SOLUTION:put(game,item)
    assert game.connection.completed and game.state == 'path_room'
    assert not game.path_completed and game.puzzle_reserved_phase is None


def walk(game, target):
    for _ in range(400):
        if game.state != 'path_room':return
        dx,dy = target[0]-game.player.x,target[1]-game.player.y
        if max(abs(dx),abs(dy)) < 1e-6:return
        if abs(dx) > 1e-6:
            axis = (1 if dx > 0 else -1,0);distance = abs(dx)
        else:
            axis = (0,1 if dy > 0 else -1);distance = abs(dy)
        game.update(min(.02,distance/2.5),*axis)
    raise AssertionError(('blocked route',target,game.player.x,game.player.y))


def check_placements():
    maximum = 0
    for seed in (*range(32),117):
        for run_number in range(3):
            game = Game(seed,run_number)
            assert game.path_entry is not None and game.path_exit is not None,(seed,run_number)
            for base in game.maze_layouts.grids:
                for opened_gate in (False,True):
                    grid = [row[:] for row in base]
                    x,y = game.puzzle_gate[0];grid[y][x] = int(not opened_gate)
                    assert game.maze_layouts.is_valid(grid),(seed,run_number)
                    spawn,goal,guard = (distances(grid,cell) for cell in (game.spawn,game.exit,game.guard_home))
                    assert all(guard[cell] >= 4 for cell in (game.path_entry,game.path_exit))
                    assert spawn[game.path_entry]+goal[game.path_exit]+10 < goal[game.spawn]
                    maximum = max(maximum,spawn[game.path_entry])
    print(f'PASS: 99 maps / 594 layouts provide a safe, beneficial room; guard gap >=4; entry distance <= {maximum} cells including fallback.')


def run():
    check_placements()
    game = Game(117)
    assert (game.path_entry,game.path_exit) == ((8,1),(19,9))
    assert distances(game.grid,game.spawn)[game.path_entry] == 2
    assert distances(game.grid,game.exit)[game.path_exit] == 18
    for base in game.maze_layouts.grids:
        for opened_gate in (False,True):
            grid = [row[:] for row in base]
            x,y = game.puzzle_gate[0];grid[y][x] = int(not opened_gate)
            assert all(game.can_stand(x+.5,y+.5,grid) for x,y in (game.path_entry,game.path_exit))
            assert game.maze_layouts.is_valid(grid)
    game,saved = opened(game)
    assert not game.return_from_path(completed=True) and game.state == 'path_room'
    for _ in range(50):game.update(.02,1,0)
    assert game.player.x < -.2 and not game.path_completed
    game.move_straight(20,1)
    assert game.player.x < 0 and game.can_stand(game.player.x,game.player.y)
    put(game,SOLUTION[0]);rotation = game.connection.pieces[0].rotation
    assert game.pick_connection(0) and game.rotate_connection()
    game.return_from_path()
    assert (game.player.x,game.player.y) == saved and game.can_stand(*saved)
    assert game.connection.pieces[0].cell == (0,1) and game.connection.pieces[0].rotation == rotation
    game,saved = opened(game)
    solve(game)
    assert not game.return_from_path(completed=True) and not game.path_completed
    game.player.x,game.player.y = 1.5,1.5
    game.move_straight(1,1)
    assert game.player.x < 1.8 and game.player.y < 1.8, 'cut an unsupported inside corner'
    game.player.x,game.player.y = -2.3,1.5
    for point in ((-.5,1.5),(.5,1.5),(1.5,1.5),(2.5,1.5),(2.5,2.5),(3.5,2.5),(4.5,2.5)):
        walk(game,point)
        assert game.state == 'path_room' and not game.path_completed
    walk(game,(5.6,2.5))
    assert game.state == 'explore' and game.path_completed
    assert (game.player.x,game.player.y) == (19.5,9.5)
    assert game.landing_cell == game.path_exit and game.path_exit in game.visited
    assert game.puzzle_reserved_phase is None and not game.puzzle_open
    game.phase_time = PHASE_SECONDS-.01;game.update(.02);finish_shift(game)
    assert game.connection.completed and game.path_completed and game.path_available()
    game.interact()
    for _ in range(21):game.update(.05)
    assert game.world_path.reverse
    for point in ((4.5,2.5),(3.5,2.5),(2.5,2.5),(2.5,1.5),(.5,1.5),(-1.5,1.5),(-2.8,1.5)):
        walk(game,point)
    assert game.state == 'explore' and (game.player.x,game.player.y) == (8.5,1.5)

    for cause in ('phase','failure','hit'):
        game,saved = opened()
        solve(game)
        game.player.x,game.player.y = 5.54,2.5
        if cause == 'phase':game.phase_time = PHASE_SECONDS-.01
        elif cause == 'failure':game.player.hp = 0
        else:game.take_guard_hit()
        if cause != 'hit':game.update(.02,1,0)
        assert not game.path_completed and (game.player.x,game.player.y) == saved
        assert game.can_stand(*saved) and not game.connection.dragging
        assert game.state == {'phase':'shifting','failure':'failed','hit':'explore'}[cause]
        if cause == 'phase':
            assert not game.connection.completed and all(piece.cell is None for piece in game.connection.pieces)
    game = Game(117)
    game.player.x,game.player.y = 9.5,1.5;game.update_visibility();game.interact()
    game.update(.2)
    assert game.world_path.stage == 'entering' and (game.player.x,game.player.y) != (9.5,1.5)
    game.return_from_path()
    assert (game.player.x,game.player.y) == (9.5,1.5) and not game.path_completed

    game,saved = opened()
    put(game,SOLUTION[0]);game.return_from_path()
    near = game.puzzle_gate[1]
    game.player.x,game.player.y = near[0]+.5,near[1]+.5;game.update_visibility();game.interact()
    assert game.state == 'puzzle' and not game.switch_puzzle_tab('connection')
    game.puzzle.press(cell_center(*START_CELL))
    for cell in SOLUTION_CORNERS:game.drag_puzzle(cell_center(*cell))
    assert game.state == 'explore' and game.puzzle_reserved_phase == game.next_phase
    assert game.connection.pieces[0].cell == (0,1) and not game.path_completed
    print('PASS: early separate doorway, six safe layouts, continuous entry/retreat, no empty/diagonal shortcut; physical exit alone lands across immediately; reverse reuse and phase/failure/hit priority; old mouse-maze reservation retained.')


if __name__ == '__main__':
    run()
