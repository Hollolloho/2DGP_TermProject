"""쿼터뷰 통로 조립 방의 고정 바닥과 통과 조건. 좌표 단위는 본 미로와 같은 한 칸이다."""
from .path_connection import PathConnection

ENTER_SECONDS = 1.0
START = (-2.3,1.5)
REVERSE_START = (5.2,2.5)
LOOSE_POSITIONS = ((-2.5,.5),(-1.5,.5),(-2.5,2.5),(-1.5,2.5),(-2.5,3.5))
FIXED_FLOOR = frozenset({(x,y) for x in (-3,-2) for y in range(4)} | {(-1,1),(4,2),(5,2)})


class WorldPathRoom:
    def __init__(self):
        self.puzzle = PathConnection()
        self.reset()

    def reset(self):
        self.puzzle.reset()
        self.stage = 'idle'
        self.elapsed = 0.
        self.reverse = False

    def start(self, reverse=False):
        self.puzzle.cancel()
        self.stage,self.elapsed,self.reverse = 'entering',0.,reverse

    @property
    def floor(self):
        # 출입 플랫폼은 보드의 W 입구/E 출구에만 닿는다. 다른 모서리로 건너뛸 수 없다.
        return FIXED_FLOOR | (set(self.puzzle.route()) if self.puzzle.completed else set())

    def solid(self, x, y):
        return (x,y) not in self.floor

    def endpoint(self, x, y):
        if x < -2.72 and abs(y-1.5) < .35:
            return 'entry'
        if x > 5.55 and abs(y-2.5) < .35:
            return 'exit'
        return None
