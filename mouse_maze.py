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


def segment_hits(start, end, rect):
    """Clip the segment to a closed rectangle, including a touch at a corner."""
    enter, leave = 0., 1.
    for a, b, low, size in zip(start, end, rect[:2], rect[2:]):
        delta = b-a
        if delta == 0:
            if not low <= a <= low+size:
                return False
            continue
        first, last = sorted(((low-a)/delta, (low+size-a)/delta))
        enter, leave = max(enter, first), min(leave, last)
        if enter > leave:
            return False
    return True


class MouseMaze:
    start_rect = cell_rect(1, 1)
    goal_rect = cell_rect(7, 1)
    walls = tuple(cell_rect(x, y) for y, row in enumerate(MAZE)
                  for x, tile in enumerate(row) if tile == '#')

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
            self.dragging = (sum((a-b)**2 for a, b in zip(point, self.point)) <= 8**2
                             and not any(segment_hits(self.point, point, wall) for wall in self.walls))
        if self.dragging:
            self.hit_wall = False
            self.point = point

    def move(self, point):
        if not self.dragging:
            return False
        left, top, size = BOARD
        inside = (left < point[0] < left+len(MAZE[0])*size
                  and top < point[1] < top+len(MAZE)*size)
        if not inside or any(segment_hits(self.point, point, wall) for wall in self.walls):
            self.reset()
            self.hit_wall = True
            return False
        finished = segment_hits(self.point, point, self.goal_rect)
        self.point = point
        return finished
