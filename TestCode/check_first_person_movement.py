"""Exercise all three playable models in metres, independent of frame drawing."""
import math

from BoulderPractice.boulder_practice import Practice
from SourceCode.maze_model import Game, TRAP_LATERAL, TRAP_LENGTH



def check_room(kind):
    standalone = kind == 'practice'
    blade = kind == 'blade'
    game = Practice() if standalone else Game(117)
    speed = 1.8 if blade else 2.55
    dt = .01

    def reset():
        if standalone:
            game.reset()
            game.z = 1.4
        else:
            if blade:
                game.return_from_trap()
                game._enter_trap('blade')
                game.trap_progress = 1.4/TRAP_LENGTH
            else:
                game.boulder_room.reset()
                game.boulder_room.z = 1.4

    if not standalone:
        game.player.x,game.player.y = (v+.5 for v in (game.trap_cell if blade else game.boulder_entry))
        game.interact()
        assert game.trap_kind == kind

    room = game if standalone else game.boulder_room

    def look(degrees):
        if blade:
            game.trap_yaw = math.radians(degrees)
        else:
            room.yaw = math.radians(degrees)

    def position():
        if blade:
            return game.trap_x*TRAP_LATERAL,game.trap_progress*TRAP_LENGTH
        return room.x,room.z

    def tick(right,forward):
        game.update(dt,right,forward if standalone else -forward)

    def assert_vector(actual,expected):
        assert math.dist(actual,expected)<1e-8,(kind,actual,expected)

    for degrees in (0,90,-90,180,37):
        angle = math.radians(degrees)
        cosine,sine = math.cos(angle),math.sin(angle)
        for right,forward in ((0,1),(0,-1),(1,0),(-1,0),(1,1),(.25,.4)):
            reset()
            look(degrees)
            start = position()
            tick(0,0)
            assert_vector(position(),start)
            scale = speed/max(1.,math.hypot(right,forward))
            expected = ((right*cosine+forward*sine)*scale,(forward*cosine-right*sine)*scale)
            for _ in range(24):
                tick(right,forward)
            before = position()
            tick(right,forward)
            observed = tuple((a-b)/dt for a,b in zip(position(),before))
            assert_vector(observed,expected)

    reset()
    for _ in range(25):
        tick(0,1)
    for degrees,expected in ((90,(speed,0)),(-90,(-speed,0)),(180,(0,-speed))):
        before = position()
        look(degrees)
        tick(0,1)
        assert_vector(tuple((a-b)/dt for a,b in zip(position(),before)),expected)
    print(f'PASS {kind}: five headings, WASD, diagonal and analog speed, '
          'stationary rotation, and held forward changing direction on the first tick.')


if __name__ == '__main__':
    for room_kind in ('blade','boulder','practice'):
        check_room(room_kind)
