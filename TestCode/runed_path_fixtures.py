"""실제 9개 석판 판의 독립 경로와 조작 데이터. 런타임에는 정답을 넣지 않는다."""
from SourceCode.path_connection import N,E,S,W,DIRECTIONS

ROUTES = (
    ((0,1),(1,1),(2,1),(2,2),(1,2),(1,3),(2,3),(3,3),(3,2)),
    ((0,1),(1,1),(1,2),(1,3),(2,3),(2,2),(2,1),(3,1),(3,2)),
    ((0,1),(0,2),(0,3),(1,3),(1,2),(1,1),(2,1),(3,1),(3,2)),
    ((0,1),(0,2),(0,3),(1,3),(1,2),(1,1),(2,1),(2,2),(3,2)),
    ((0,1),(0,2),(0,3),(1,3),(2,3),(2,2),(2,1),(3,1),(3,2)),
)


def placement(route):
    straight,corner = iter((0,1,2)),iter(range(3,9))
    items = []
    for index,cell in enumerate(route):
        before = route[index-1] if index else (-1,1)
        after = route[index+1] if index+1 < len(route) else (4,2)
        ports = frozenset(DIRECTIONS.index((other[0]-cell[0],other[1]-cell[1])) for other in (before,after))
        piece = next(straight) if ports in (frozenset((N,S)),frozenset((E,W))) else next(corner)
        items.append((piece,cell,ports))
    return tuple(items)


def put(puzzle,item):
    index,cell,ports = item
    assert puzzle.pick(index)
    for _ in range(4):
        if puzzle.pieces[index].ports == ports:break
        assert puzzle.rotate()
    assert not puzzle.completed
    assert puzzle.drop(cell)
