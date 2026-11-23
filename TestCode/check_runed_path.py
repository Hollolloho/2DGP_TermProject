"""두 무순서 문양을 지나는 실제 포트 경로와 조작/진행도 판정. SDL 없이 실행한다."""
from SourceCode.path_connection import PathConnection,RUNES,DIRECTIONS,ENTRY,EXIT,N,E,S,W
from .runed_path_fixtures import ROUTES,placement,put


def enumerate_routes():
    solutions = []
    def visit(path):
        cell = path[-1]
        if cell == EXIT[0]:
            try:items = placement(path)
            except StopIteration:return
            if set(RUNES) <= set(path):solutions.append(tuple(path))
            return
        if len(path) == 9:return
        for dx,dy in DIRECTIONS:
            other = cell[0]+dx,cell[1]+dy
            if 0 <= other[0] < 4 and 0 <= other[1] < 4 and other not in path:visit(path+[other])
    visit([ENTRY[0]])
    assert set(solutions) == set(ROUTES) and len(solutions) == 5
    assert min(map(len,solutions)) == 9
    orders = {tuple(cell for cell in route if cell in RUNES) for route in solutions}
    assert orders == {RUNES,tuple(reversed(RUNES))}
    for route in solutions:
        puzzle = PathConnection()
        assert len(puzzle.pieces) == 9
        for index,item in enumerate(placement(route)):
            put(puzzle,item)
            assert puzzle.completed == (index == 8)
        assert puzzle.route() == route and puzzle.reached_runes == frozenset(RUNES)
    print('PASS: exhaustive 4x4 search yields 5 solutions, minimum 9 tiles/6 corners; A->B and B->A both solve through actual pick/rotate/drop.')


def check_rejections():
    routes = (
        ((0,1),(0,2),(1,2),(2,2),(3,2)),
        ((0,1),(0,2),(0,3),(1,3),(2,3),(3,3),(3,2)),
        ((0,1),(1,1),(2,1),(2,2),(3,2)),
    )
    for route,expected in zip(routes,(set(),{RUNES[0]},{RUNES[1]})):
        puzzle = PathConnection()
        for item in placement(route):put(puzzle,item)
        assert puzzle.exit_connected and puzzle.reached_runes == expected
        assert not puzzle.is_connected() and not puzzle.completed and not puzzle.route()
        if not expected:
            for item in ((5,RUNES[0],frozenset((N,E))),(6,RUNES[1],frozenset((S,W)))):put(puzzle,item)
            assert not puzzle.reached_runes and not puzzle.completed, 'occupied but detached runes counted'
    puzzle = PathConnection()
    for item in ((0,(1,2),frozenset((N,S))),(3,(1,3),frozenset((N,E))),
                 (4,(1,1),frozenset((S,E))),(5,(2,1),frozenset((W,S)))):put(puzzle,item)
    assert not puzzle.connected_cells and not puzzle.reached_runes and not puzzle.completed
    print('PASS: exit with 0/1 runes, two occupied/detached runes and an isolated rune component never activate the floor.')


def check_progress_and_rotation():
    puzzle = PathConnection()
    items = placement(ROUTES[0])
    for item in items[:6]:put(puzzle,item)
    assert puzzle.reached_runes == frozenset(RUNES) and not puzzle.completed
    assert puzzle.pick(items[0][0])
    assert not puzzle.reached_runes
    assert puzzle.rotate() and puzzle.cancel() and puzzle.reached_runes == frozenset(RUNES)
    assert puzzle.pick(items[0][0])
    assert not puzzle.drop((1,1)) and puzzle.reached_runes == frozenset(RUNES)
    for item in items[6:-1]:put(puzzle,item)
    index,cell,ports = items[-1]
    wrong = frozenset((port-1)%4 for port in ports)
    put(puzzle,(index,cell,wrong))
    assert not puzzle.completed
    assert puzzle.pick(index) and puzzle.rotate() and not puzzle.completed
    assert not puzzle.drop((1,1)) and not puzzle.completed
    assert puzzle.rotate() and puzzle.completed and puzzle.route() == ROUTES[0]
    puzzle.reset()
    assert not puzzle.reached_runes and not puzzle.completed and not puzzle.dragging
    print('PASS: entry-connected progress retracts on disconnection, cancel/invalid drops restore it; held rotation cannot win and last-selected committed rotation can.')


def run():
    enumerate_routes();check_rejections();check_progress_and_rotation()


if __name__ == '__main__':
    run()
