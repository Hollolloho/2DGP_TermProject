"""The first mouse puzzle and its logical screen coordinates."""

BOARD = (66, 134, 34)
MAZE = (
    '#########',
    '#S..#..G#',
    '###.#.###',
    '#.....###',
    '#########',
)


def cell_rect(x, y):
    left, top, size = BOARD
    return left+x*size, top+y*size, size, size


class MouseMaze:
    start_rect = cell_rect(1, 1)
    goal_rect = cell_rect(7, 1)

    def __init__(self):
        self.reset()

    def reset(self):
        self.point = None
        self.dragging = False
        self.hit_wall = False

    def press(self, point):
        if self.dragging:
            return
        if self.point is None:
            x, y, size, _ = self.start_rect
            self.dragging = x < point[0] < x+size and y < point[1] < y+size
        else:
            self.dragging = sum((a-b)**2 for a, b in zip(point, self.point)) <= 8**2
        if self.dragging:
            self.hit_wall = False
            self.point = point

    def move(self, point):
        if not self.dragging:
            return False
        self.point = point
        return False
