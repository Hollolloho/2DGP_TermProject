"""셀 좌표만 사용하는 통로 연결 퍼즐. X는 오른쪽, Y는 아래, 회전은 시계 방향이다."""
from dataclasses import dataclass

COLS = ROWS = 4
N, E, S, W = range(4)
DIRECTIONS = ((0,-1),(1,0),(0,1),(-1,0))
ENTRY = (0,1),W
EXIT = (3,2),E
INITIAL_PIECES = (('straight',1),('straight',0),('straight',1),('corner',2),('corner',0))


@dataclass
class Piece:
    kind: str
    rotation: int
    cell: tuple[int,int] | None = None

    @property
    def ports(self):
        base = (E,W) if self.kind == 'straight' else (N,E)
        return frozenset((port+self.rotation)%4 for port in base)


def on_board(cell):
    return (isinstance(cell,tuple) and len(cell) == 2
            and all(type(value) is int for value in cell)
            and 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS)


class PathConnection:
    """조작 메서드는 수락 여부를 반환한다. 완료 여부는 completed에서 읽는다."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.pieces = [Piece(kind,rotation) for kind,rotation in INITIAL_PIECES]
        self.selected = self.held = self.origin = None
        self.completed = False

    @property
    def dragging(self):
        return self.held is not None

    def piece_at(self, cell):
        if on_board(cell):
            return next((index for index,piece in enumerate(self.pieces) if piece.cell == cell),None)
        return None

    def pick(self, index):
        """조각 ID를 선택해 잡는다. 선반 조각도 같은 ID를 유지한다."""
        if self.completed or self.dragging or type(index) is not int or not 0 <= index < len(self.pieces):
            return False
        piece = self.pieces[index]
        self.origin = piece.cell,piece.rotation
        self.selected = self.held = index
        piece.cell = None
        return True

    def rotate(self):
        """잡은 조각 또는 마지막 선택을 90도 회전한다. 잡은 동안은 확정하지 않는다."""
        if self.completed or self.selected is None:
            return False
        piece = self.pieces[self.selected]
        piece.rotation = (piece.rotation+1)%4
        if not self.dragging:
            self.completed = self.is_connected()
        return True

    def drop(self, cell=None, *, shelf=False):
        """유효 보드 칸이나 명시한 선반(shelf=True)에 확정한다. 그 밖은 취소한다."""
        if not self.dragging:
            return False
        if not shelf and (not on_board(cell) or self.piece_at(cell) is not None):
            self.cancel()
            return False
        self.pieces[self.held].cell = None if shelf else cell
        self.held = self.origin = None
        self.completed = self.is_connected()
        return True

    def cancel(self):
        """드래그 시작 시의 위치와 회전을 복구한다. 완료 판정은 일으키지 않는다."""
        if not self.dragging:
            return False
        piece = self.pieces[self.held]
        piece.cell,piece.rotation = self.origin
        self.held = self.origin = None
        return True

    def is_connected(self):
        """입구부터 서로 마주보는 포트만 따라간다. 연결 조회 자체는 상태를 바꾸지 않는다."""
        return bool(self.route())

    def route(self):
        """유효한 입구~출구 경로의 셀을 순서대로 반환한다. 불완전하면 빈 튜플이다."""
        board = {piece.cell:piece for piece in self.pieces if piece.cell is not None}
        cell,incoming = ENTRY
        route = []
        while cell not in route:
            route.append(cell)
            piece = board.get(cell)
            if piece is None or incoming not in piece.ports:
                return ()
            if cell == EXIT[0] and EXIT[1] in piece.ports:
                return tuple(route)
            outgoing = next(port for port in piece.ports if port != incoming)
            dx,dy = DIRECTIONS[outgoing]
            cell = cell[0]+dx,cell[1]+dy
            incoming = (outgoing+2)%4
        return ()
