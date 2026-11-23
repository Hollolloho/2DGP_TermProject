"""The first mouse puzzle and its logical screen coordinates."""
import math

BOARD = (66, 126, 22)
MAZE = (
    '#############',
    '#S..#..2...G#',
    '###.#.###.#.#',
    '#...........#',
    '#.#.#.#.###.#',
    '#1....#..3..#',
    '#.#.###.###.#',
    '#.#.###...#.#',
    '#############',
)
START_CELL = (1, 1)
GOAL_CELL = (11, 1)
WAYPOINTS = ((1,5),(7,1),(9,5))


def cell_rect(x, y):
    left, top, size = BOARD
    return left+x*size, top+y*size, size, size


def cell_center(x, y):
    left, top, size, _ = cell_rect(x, y)
    return left+size//2, top+size//2


def cell_at(point):
    """Map logical pixels to a tile with inclusive top/left and exclusive bottom/right."""
    left, top, size = BOARD
    x, y = int((point[0]-left)//size), int((point[1]-top)//size)
    if 0 <= y < len(MAZE) and 0 <= x < len(MAZE[y]):
        return x, y
    return None


def is_passage(cell):
    x, y = cell
    return 0 <= y < len(MAZE) and 0 <= x < len(MAZE[y]) and MAZE[y][x] != '#'


def crossed_cells(start, end, destination):
    """Return the cells visited by a mouse segment, or None if it cuts a wall."""
    x, y = cell_at(start)
    left, top, size = BOARD
    dx, dy = end[0]-start[0], end[1]-start[1]
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    next_x = (left+(x+(sx > 0))*size-start[0])/dx if dx else math.inf
    next_y = (top+(y+(sy > 0))*size-start[1])/dy if dy else math.inf
    cells = [(x, y)]
    while (x, y) != destination:
        if x == destination[0]:
            next_x = math.inf
        if y == destination[1]:
            next_y = math.inf
        if math.isclose(next_x, next_y, rel_tol=0., abs_tol=1e-12):
            return None  # There is no intermediate neighbor at an exact diagonal crossing.
        if next_x < next_y:
            x += sx
            next_x += size/abs(dx)
        else:
            y += sy
            next_y += size/abs(dy)
        if not is_passage((x, y)):
            return None
        cells.append((x, y))
    return cells


def visit(path, node):
    if len(path) > 1 and node == path[-2]:
        path.pop()
    elif node in path:
        return False
    else:
        path.append(node)
    return True


def can_preview(path, node):
    return is_passage(node) and (node not in path or (len(path) > 1 and node == path[-2]))


def waypoint_state(path):
    """현재 경로에 남은 번호가 정확히 1→2→3의 접두 순서인지 확인한다."""
    progress = 0
    for node in path:
        if node in WAYPOINTS:
            if progress >= len(WAYPOINTS) or node != WAYPOINTS[progress]:
                return progress,True
            progress += 1
    return progress,False


class MouseMaze:
    def __init__(self):
        self.reset()

    def reset(self):
        self.path = [START_CELL]
        self.cursor = cell_center(*START_CELL)
        self.preview_cell = None
        self.release()
        self.hit_wall = False

    @property
    def cell(self):
        return self.path[-1]

    @property
    def dragging(self):
        return self.pointer is not None

    @property
    def retained_path(self):
        # 되짚는 커서가 마지막 노드에서 물러난 순간부터 그 노드는 금빛 경로에 없다.
        if len(self.path) > 1 and self.preview_cell == self.path[-2]:
            return self.path[:-1]
        return self.path

    @property
    def progress(self):
        return waypoint_state(self.retained_path)[0]

    @property
    def sequence_error(self):
        return waypoint_state(self.retained_path)[1]

    @property
    def completed(self):
        progress,error = waypoint_state(self.retained_path)
        return self.retained_path[-1] == GOAL_CELL and progress == len(WAYPOINTS) and not error

    def release(self):
        self.pointer = None

    def press(self, point):
        if not self.dragging and cell_at(point) in (self.cell, cell_at(self.cursor)):
            self.pointer = point
            self.hit_wall = False

    def move(self, point):
        if not self.dragging:
            return False
        cell = cell_at(point)
        if cell is None or not is_passage(cell) or not self._trace(point, cell):
            self.hit_wall = True
            return False
        self.hit_wall = False
        self.pointer = point
        return self.completed

    def _trace(self, point, cell):
        cells = crossed_cells(self.pointer, point, cell)
        if cells is None:
            return False
        path = self.path[:]
        if cells[0] != self.cell:
            cells.insert(0, self.cell)
        # An event can extend across a corner when its actual segment visits the bend.
        for before, current, after in zip(cells, cells[1:], cells[2:]):
            if before[0] == after[0] or before[1] == after[1]:
                continue
            if not self._visit_straight(path, current):
                return False

        if cell == GOAL_CELL:
            # The raw segment has already been checked for every crossed tile.
            if not self._visit_straight(path, cell):
                return False
            self.path = path
            self.cursor = cell_center(*cell)
            self.preview_cell = None
            return True

        approach = None
        if cell != path[-1]:
            if len(cells) > 1:
                approach = cells[-2]
            elif self.preview_cell == cell:
                approach = path[-1]
        motion_x, motion_y = point[0]-self.pointer[0], point[1]-self.pointer[1]
        turn_axis = None
        if approach is not None:
            bend_x, bend_y = cell_center(*cell)
            along_x = cell[0] != approach[0]
            parallel, across = ((point[0]-bend_x, point[1]-bend_y) if along_x else
                                (point[1]-bend_y, point[0]-bend_x))
            advance = cell[0]-approach[0] if along_x else cell[1]-approach[1]
            before_center = parallel*advance < 0
            direction = 1 if across > 0 else -1
            outgoing = (cell[0], cell[1]+direction) if along_x else (cell[0]+direction, cell[1])
            forward = (cell[0]+advance, cell[1]) if along_x else (cell[0], cell[1]+advance)
            forward_motion, turn_motion = ((motion_x, motion_y) if along_x else (motion_y, motion_x))
            turn = direction*turn_motion
            # A large sample can reach the bend and steer out before reaching its center.
            # Require real sideways motion as well as proximity to the outgoing edge.
            steering = turn >= 3 and abs(across) > abs(parallel)
            if self.preview_cell == cell:
                steering |= turn > abs(forward_motion)
            if ((before_center or not is_passage(forward)) and across and steering
                    and can_preview(path, outgoing)):
                if not self._visit_straight(path, cell):
                    return False
                turn_axis = not along_x

        x, y = path[-1]
        center_x, center_y = cell_center(x, y)
        dx, dy = cell[0]-x, cell[1]-y
        if dx and dy:
            return False
        offset_x, offset_y = point[0]-center_x, point[1]-center_y
        if turn_axis is not None:
            along_x = turn_axis
        elif self.preview_cell is not None and path[-1] == self.cell:
            # Stay on the current edge until input reaches its origin or next node.
            preview_x, preview_y = self.preview_cell
            along_x = preview_x != x
            extent = offset_x*(preview_x-x) if along_x else offset_y*(preview_y-y)
            if (dy if along_x else dx) and extent > 0:
                return False
            if extent <= 0:
                if dx or dy:
                    along_x = bool(dx)
                else:
                    self.cursor = center_x, center_y
                    self.preview_cell = None
                    return True
        elif dx or dy:
            along_x = bool(dx)
        else:
            # Along a straight edge, a constant lateral offset must not steer into a wall.
            if abs(motion_x) == abs(motion_y):
                along_x = abs(offset_x) >= abs(offset_y)
            else:
                along_x = abs(motion_x) > abs(motion_y)
        if not (dx or dy) and (turn_axis is None):
            x_neighbor = x+(1 if offset_x > 0 else -1), y
            y_neighbor = x, y+(1 if offset_y > 0 else -1)
            can_x = offset_x != 0 and can_preview(path, x_neighbor)
            can_y = offset_y != 0 and can_preview(path, y_neighbor)
            # Prefer a connected axis when the stronger component points into masonry.
            if not can_x and not can_y:
                self.path = path
                self.cursor = center_x, center_y
                self.preview_cell = None
                return True
            if not can_x:
                along_x = False
            elif not can_y:
                along_x = True
        offset = offset_x if along_x else offset_y
        if not offset:
            self.path = path
            self.cursor = center_x, center_y
            self.preview_cell = None
            return True

        direction = 1 if offset > 0 else -1
        step_x, step_y = (direction, 0) if along_x else (0, direction)
        count, remaining = divmod(abs(offset), BOARD[2])
        x, y = x+step_x*int(count), y+step_y*int(count)
        if not self._visit_straight(path, (x, y)):
            return False

        preview = (x+step_x, y+step_y) if remaining else None
        if preview is not None:
            if not is_passage(preview):
                if cell == self.cell:
                    return False
                # Offsets beyond a terminal node can end on that node.
                remaining, preview = 0, None
            elif preview in path and (len(path) < 2 or preview != path[-2]):
                return False
        self.path = path
        center_x, center_y = cell_center(x, y)
        self.cursor = center_x+step_x*remaining, center_y+step_y*remaining
        self.preview_cell = preview
        return True

    @staticmethod
    def _visit_straight(path, target):
        x, y = path[-1]
        dx, dy = target[0]-x, target[1]-y
        if dx and dy:
            return False
        distance = abs(dx or dy)
        if distance:
            step_x, step_y = dx//distance, dy//distance
            for n in range(1, distance+1):
                node = x+n*step_x, y+n*step_y
                if not is_passage(node) or not visit(path, node):
                    return False
        return True
