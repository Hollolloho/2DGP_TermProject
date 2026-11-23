"""두 퍼즐의 공유 문 예약·중단 보존·시간대 초기화. SDL 없이 실행한다."""
from SourceCode.maze_model import Game, PHASE_SECONDS, GUARD_DAMAGE
from SourceCode.mouse_maze import START_CELL, cell_center
from SourceCode.path_connection import N, E, S, W
from .checks_phase_changes import finish_shift


SOLUTION = ((0,(0,1),(W,E)),(1,(1,1),(W,E)),(3,(2,1),(W,S)),
            (4,(2,2),(N,E)),(2,(3,2),(W,E)))


def opened(run=0):
    game = Game(117,run)
    cell = game.puzzle_gate[1]
    game.player.x,game.player.y = cell[0]+.5,cell[1]+.5
    game.player.torch,game.guard_hp = True,0
    game.update_visibility()
    game.interact()
    assert game.state == 'puzzle' and game.puzzle_tab == 'maze'
    assert game.switch_puzzle_tab('connection')
    return game


def put(game, index, cell, ports):
    assert game.connection.pick(index)
    for _ in range(4):
        if game.connection.pieces[index].ports == frozenset(ports):
            break
        assert not game.rotate_connection()
    return game.drop_connection(cell)


def run():
    for run_number in range(3):
        game = opened(run_number)
        wall = game.puzzle_gate[0]
        assert not put(game,*SOLUTION[0])
        saved = game.connection.pieces[0].rotation
        assert game.connection.pick(0)
        game.rotate_connection()
        game.close_puzzle()
        assert game.connection.pieces[0].cell == (0,1) and game.connection.pieces[0].rotation == saved
        assert not game.connection.dragging and game.state == 'explore'
        assert not game.rotate_connection() and not game.drop_connection((1,1))
        game.interact()
        assert game.puzzle_tab == 'connection'
        assert game.connection.pieces[0].cell == (0,1)
        game.switch_puzzle_tab('maze')
        game.puzzle.press(cell_center(*START_CELL))
        game.drag_puzzle(cell_center(3,1))
        assert game.switch_puzzle_tab('connection') and not game.puzzle.dragging
        assert game.puzzle.cell == (3,1)
        assert game.connection.pick(0)
        game.cancel_puzzle_drag()
        assert game.connection.pieces[0].cell == (0,1) and not game.connection.dragging
        assert game.connection.pick(0)
        hp = game.player.hp
        game.take_guard_hit()
        assert game.player.hp == hp-GUARD_DAMAGE and game.state == 'explore'
        assert game.connection.pieces[0].cell == (0,1) and not game.connection.dragging
        game.interact()
        assert game.puzzle_tab == 'connection'
        game.switch_puzzle_tab('connection')
        for position,item in enumerate(SOLUTION[1:],1):
            assert put(game,*item) == (position == len(SOLUTION)-1)
        reserved = game.puzzle_reserved_phase
        assert reserved == game.next_phase and game.state == 'explore' and game.solid(*wall)
        assert not game._complete_puzzle() and not game.drop_connection() and not game.rotate_connection()
        assert game.puzzle_reserved_phase == reserved
        game.interact()
        assert game.state == 'explore'
        game.phase_time = PHASE_SECONDS-.01
        game.update(.02)
        finish_shift(game)
        assert game.puzzle_open and game.puzzle_reserved_phase is None and not game.solid(*wall)

    game = opened()
    put(game,*SOLUTION[0])
    assert game.connection.pick(0)
    game.phase_time = PHASE_SECONDS-.01
    game.update(.02)
    assert not game.connection.dragging and all(piece.cell is None for piece in game.connection.pieces)
    assert game.puzzle_tab == 'maze' and game.puzzle_reserved_phase is None
    finish_shift(game)
    assert not game.puzzle_open and game.solid(*game.puzzle_gate[0])

    game = opened()
    put(game,*SOLUTION[0])
    game.switch_puzzle_tab('maze')
    game.puzzle.press(cell_center(*START_CELL))
    for cell in ((3,1),(3,3),(5,3),(5,1),(7,1)):
        game.drag_puzzle(cell_center(*cell))
    assert game.state == 'explore' and game.puzzle_reserved_phase == game.next_phase
    assert all(piece.cell is None for piece in game.connection.pieces)
    assert game.puzzle.cell == START_CELL
    print('PASS: both puzzle tabs share one reservation; three phases, Esc/hit/focus-style cancel preserve commits; shift resets unfinished edits; mouse maze still completes.')


if __name__ == '__main__':
    run()
