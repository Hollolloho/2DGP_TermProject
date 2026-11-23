"""통로 조각 이동·회전의 확정/복구와 포트 연결 판정. SDL 없이 실행한다."""
from itertools import product

from SourceCode.path_connection import PathConnection, COLS, ROWS, ENTRY, EXIT, N, E, S, W
from .path_connection_fixture import legacy_path_connection


def snapshot(puzzle):
    return [(piece.kind,piece.rotation,piece.cell) for piece in puzzle.pieces]


def place(puzzle, index, cell, ports):
    assert puzzle.pick(index)
    for _ in range(4):
        if puzzle.pieces[index].ports == frozenset(ports):
            break
        assert puzzle.rotate()
    assert puzzle.pieces[index].ports == frozenset(ports)
    assert not puzzle.completed, 'held rotations must not complete the puzzle'
    assert puzzle.drop(cell)


def check_moves():
    puzzle = PathConnection()
    initial = snapshot(puzzle)
    assert (COLS,ROWS,ENTRY,EXIT) == (4,4,((0,1),W),((3,2),E))
    assert [piece.kind for piece in puzzle.pieces].count('straight') == 3
    assert [piece.kind for piece in puzzle.pieces].count('corner') == 6
    assert all(piece.cell is None for piece in puzzle.pieces)
    assert not puzzle.completed and not puzzle.is_connected() and not puzzle.dragging
    assert not puzzle.rotate() and not puzzle.drop() and not puzzle.cancel()
    for index in (-1,9,None,1.5,True):
        assert not puzzle.pick(index) and snapshot(puzzle) == initial

    assert puzzle.pick(0) and puzzle.dragging and puzzle.held == puzzle.selected == 0
    ports = puzzle.pieces[0].ports
    assert puzzle.rotate() and puzzle.pieces[0].ports == frozenset((port+1)%4 for port in ports)
    for _ in range(3):
        assert puzzle.rotate()
    assert snapshot(puzzle) == initial
    assert not puzzle.pick(1) and puzzle.held == 0
    assert puzzle.drop((0,1)) and puzzle.piece_at((0,1)) == 0
    assert puzzle.pick(0) and puzzle.piece_at((0,1)) is None
    assert puzzle.rotate() and puzzle.drop((1,1)) and puzzle.piece_at((1,1)) == 0
    assert puzzle.piece_at((0,1)) is None

    for target in ((-1,0),(4,0),(0,-1),(0,4),None,(1.0,1),[1,1],(True,1)):
        before = snapshot(puzzle)
        assert puzzle.pick(0) and puzzle.rotate()
        assert not puzzle.drop(target) and not puzzle.dragging
        assert snapshot(puzzle) == before, target
    assert puzzle.pick(1) and puzzle.drop((2,1))
    before = snapshot(puzzle)
    for index in (0,2):
        assert puzzle.pick(index) and puzzle.rotate()
        assert not puzzle.drop((2,1)) and snapshot(puzzle) == before
    assert puzzle.pick(0) and puzzle.rotate() and puzzle.cancel()
    assert snapshot(puzzle) == before and not puzzle.cancel()
    assert puzzle.pick(0) and puzzle.rotate() and puzzle.drop(shelf=True)
    assert puzzle.pieces[0].cell is None and puzzle.selected == 0
    assert puzzle.rotate() and not puzzle.completed
    assert puzzle.pick(0) and puzzle.rotate() and puzzle.cancel()
    assert puzzle.pieces[0].cell is None
    assert puzzle.pick(1) and puzzle.rotate()
    puzzle.reset()
    assert snapshot(puzzle) == initial and not puzzle.completed and not puzzle.dragging
    assert puzzle.selected is None and puzzle.origin is None
    other = PathConnection()
    puzzle.pieces[0].rotation = 0
    assert snapshot(other) == initial
    print('PASS: inventory, clockwise rotation, relocation, shelf return, invalid drops and full cancel/reset rollback.')


@legacy_path_connection
def check_solutions():
    # 아래로 꺾이는 열이 0~3인 네 경로를 실제 잡기·회전·드롭으로 완성한다.
    for turn in range(4):
        puzzle = PathConnection()
        route = [(x,1) for x in range(turn+1)]+[(x,2) for x in range(turn,4)]
        straight,corner = iter((0,1,2)),iter((3,4))
        for index,cell in enumerate(route):
            if cell == (turn,1):
                piece,ports = next(corner),(W,S)
            elif cell == (turn,2):
                piece,ports = next(corner),(N,E)
            else:
                piece,ports = next(straight),(W,E)
            place(puzzle,piece,cell,ports)
            assert puzzle.completed == (index == len(route)-1)
        assert puzzle.is_connected() and not puzzle.dragging
        solved = snapshot(puzzle)
        assert not puzzle.pick(0) and not puzzle.rotate() and not puzzle.drop(shelf=True)
        assert snapshot(puzzle) == solved
        puzzle.reset()
        assert not puzzle.completed and not puzzle.dragging and puzzle.selected is None
        assert all(piece.cell is None for piece in puzzle.pieces)
    print('PASS: four valid routes finish only on a committed drop, freeze on completion and reset cleanly.')


@legacy_path_connection
def check_rotation_commit():
    puzzle = PathConnection()
    for index,cell,ports in ((0,(0,1),(W,E)),(1,(1,1),(W,E)),(2,(3,2),(W,E)),
                             (3,(2,1),(W,S)),(4,(2,2),(N,W))):
        place(puzzle,index,cell,ports)
    assert not puzzle.completed and not puzzle.is_connected() and puzzle.selected == 4
    before = snapshot(puzzle)
    for target in ((0,1),None):
        assert puzzle.pick(4) and puzzle.rotate() and not puzzle.completed
        assert not puzzle.drop(target) and snapshot(puzzle) == before
    assert puzzle.pick(4) and puzzle.rotate() and puzzle.cancel()
    assert snapshot(puzzle) == before and not puzzle.completed
    assert puzzle.rotate() and puzzle.completed and puzzle.is_connected()
    print('PASS: held rotations stay provisional; canceled winning rotations do not complete; last-selected board rotation commits.')


@legacy_path_connection
def check_ports():
    puzzle = PathConnection()
    cells = ((0,1),(1,1),(3,2),(2,1),(2,2))
    for piece,cell in zip(puzzle.pieces,cells):
        piece.cell = cell
    for rotations in product(range(4),repeat=5):
        for piece,rotation in zip(puzzle.pieces,rotations):
            piece.rotation = rotation
        expected = all(rotation%2 == 0 for rotation in rotations[:3]) and rotations[3:] == (2,0)
        assert puzzle.is_connected() == expected,rotations
        assert not puzzle.completed, 'querying connectivity must not commit completion'
    for piece,rotation in zip(puzzle.pieces,(0,0,0,2,0)):
        piece.rotation = rotation
    assert puzzle.is_connected()
    puzzle.pieces[3].cell = (2,0)
    assert not puzzle.is_connected(), 'diagonal contact or a missing cell is not a connection'
    # 출구 칸에 닿아도 바깥 E 포트가 없으면 실패한다.
    for piece,cell,rotation in zip(puzzle.pieces,((0,1),(1,1),(2,1),(3,1),(3,2)),(0,0,0,2,3)):
        piece.cell,piece.rotation = cell,rotation
    assert not puzzle.is_connected()
    puzzle.pieces[4].rotation = 0
    assert puzzle.is_connected()
    print('PASS: all 1024 orientations, reciprocal ports, endpoint direction and missing/diagonal cells; queries never commit.')


def run():
    check_moves()
    check_solutions()
    check_rotation_commit()
    check_ports()


if __name__ == '__main__':
    run()
