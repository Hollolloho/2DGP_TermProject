"""두 숏컷 중 하나의 확정·다음 시간대 예약. 지형 조회는 상태를 바꾸지 않는다."""
from dataclasses import dataclass

CHOICE_START = (23,7)
CHOICE_GOAL = (17,9)


@dataclass(frozen=True)
class ShortcutRoute:
    label: str
    gate: tuple[int,int]
    path: tuple[tuple[int,int],...]
    exposed_cells: tuple[tuple[int,int],...]  # 초기 수호자 6칸+벽 가림 기준. 이동 후 안전 보장이 아니다.

    @property
    def distance(self):
        return len(self.path)-1

    @property
    def exposure_centres(self):
        return len(self.exposed_cells)


ROUTE_OPTIONS = (
    ShortcutRoute('노출길',(23,10),
                  ((23,7),(23,8),(23,9),(23,10),(23,11),(22,11),(21,11),
                   (20,11),(19,11),(19,10),(19,9),(18,9),(17,9)),
                  ((23,11),(22,11),(21,11),(20,11),(19,11))),
    ShortcutRoute('엄폐길',(16,8),
                  ((23,7),(23,8),(23,9),(22,9),(21,9),(21,8),(21,7),(20,7),
                   (19,7),(18,7),(17,7),(16,7),(16,8),(16,9),(17,9)),()),
)


class ShortcutChoice:
    def __init__(self):
        self.reset()

    def reset(self):
        self.preview = self.selected = self.reserved_phase = None
        self.opened = False

    def select(self, index):
        if self.selected is not None or type(index) is not int or index not in (0,1):
            return False
        self.preview = index
        return True

    def cancel(self):
        if self.selected is not None:
            return False
        self.preview = None
        return True

    def confirm(self, next_phase):
        if (self.selected is not None or self.preview is None
                or type(next_phase) is not int or next_phase not in (0,1,2)):
            return False
        self.selected = self.preview
        self.reserved_phase = next_phase
        return True

    def route_for_phase(self, phase):
        if self.selected is not None and (self.opened or self.reserved_phase == phase):
            return self.selected
        return None

    def apply_phase(self, phase):
        if self.reserved_phase is None or self.reserved_phase != phase:
            return False
        self.opened = True
        self.reserved_phase = None
        return True
