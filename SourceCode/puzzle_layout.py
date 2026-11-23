"""월드 통로 방의 쿼터뷰 투영과 동일한 역투영 피킹."""
import math
from .maze_model import project, HALF_TILE_W, HALF_TILE_H
from .world_path_room import LOOSE_POSITIONS

ROOM_ORIGIN = (375,166)
ROOM_SCALE = 1.1


def room_screen(x, y):
    sx,sy = project(x,y)
    return ROOM_ORIGIN[0]+sx*ROOM_SCALE,ROOM_ORIGIN[1]+sy*ROOM_SCALE


def room_point(point):
    x = (point[0]-ROOM_ORIGIN[0])/ROOM_SCALE/HALF_TILE_W
    y = (point[1]-ROOM_ORIGIN[1])/ROOM_SCALE/HALF_TILE_H
    return (x+y)/2,(y-x)/2


def connection_cell(point):
    x,y = room_point(point)
    return (math.floor(x),math.floor(y)) if 0 <= x < 4 and 0 <= y < 4 else None


def connection_center(cell):
    return room_screen(cell[0]+.5,cell[1]+.5)


def on_loose_floor(point):
    x,y = room_point(point)
    return -3 <= x < -1 and -1 <= y < 5


def connection_piece_at(puzzle, point):
    cell = connection_cell(point)
    if cell is not None:
        return puzzle.piece_at(cell)
    x,y = room_point(point)
    return next((index for index,(cx,cy) in enumerate(LOOSE_POSITIONS)
                 if puzzle.pieces[index].cell is None and puzzle.held != index
                 and abs(x-cx) < .5 and abs(y-cy) < .5),None)
