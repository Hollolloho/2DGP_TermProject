"""Six transverse lanes: geometry, continuous rolling, CCD and walking rhythm."""
from math import ceil, isclose, sqrt

from SourceCode.six_lane_trap import (
    SixLaneTrap, LANE_COUNT, LANE_DEPTH, LANE_START, SLOPE,
    RADIUS, BALL_SPEED, ROLL_LIMIT, CYCLE_SECONDS, EXIT_Z, WALK_SPEED,
    floor_height, lane_at, capsule_hit, PASSAGE_HALF_WIDTH,
)


def check_geometry_and_rolling():
    room = SixLaneTrap()
    assert (LANE_COUNT, LANE_DEPTH, LANE_START, EXIT_Z) == (6,3.,3.,24.)
    assert lane_at(3.-1e-6) is None and lane_at(21.) is None
    for lane in range(6):
        center = LANE_START+(lane+.5)*LANE_DEPTH
        assert lane_at(center) == lane and lane_at(LANE_START+lane*LANE_DEPTH) == lane
        expected = -SLOPE if lane%2 == 0 else SLOPE
        assert isclose(floor_height(1.,center),expected)
        assert isclose(floor_height(-1.,center),-expected)
        assert isclose(room.phase_offsets[lane],-center/WALK_SPEED)
        for time in (0.,.25,1.,4.67,12.):
            stone = room.stone_at(lane,time)
            repeat = room.stone_at(lane,time+CYCLE_SECONDS)
            assert stone.active and stone.direction == (1 if lane%2 == 0 else -1)
            assert stone.z == center and stone.radius == RADIUS and stone.speed == BALL_SPEED
            assert -ROLL_LIMIT-1e-8 <= stone.x <= ROLL_LIMIT+1e-8
            assert isclose(stone.y,expected*stone.x+RADIUS*sqrt(1+SLOPE*SLOPE))
            assert isclose(stone.x,repeat.x,abs_tol=1e-8) and repeat.cycle == stone.cycle+1
            assert isclose(stone.distance,repeat.distance,abs_tol=1e-8)
        # Sample within one roll, away from the offstage wrap.
        room.phase_offsets[lane] = 1.
        a,b = room.stone_at(lane,0.),room.stone_at(lane,.1)
        assert isclose(b.x-a.x,a.direction*BALL_SPEED*.1)
        assert isclose(b.distance-a.distance,BALL_SPEED*.1*sqrt(1+SLOPE*SLOPE))
    for boundary in range(7):
        z = LANE_START+boundary*LANE_DEPTH
        for x in (-1.3,-1.,0.,1.,1.3):
            assert abs(floor_height(x,z-1e-6)-floor_height(x,z+1e-6)) < .00001
    for hz in (30,60,120):
        room = SixLaneTrap()
        room.x,room.z,room.vz = 2.,6.-.01,WALK_SPEED
        room.advance(1/hz,forward=1)
        assert room.blocked and room.z < 6. and room.vz == 0.
        room.x = 0.
        for _ in range(hz//4):
            room.advance(1/hz,forward=1)
        assert room.z > 6. and not room.blocked
    print('PASS: six adjacent alternating slopes, level center seams, off-center ledges and six continuous periodic rolls.')


def check_swept_contacts():
    assert capsule_hit((-3.,.85,0.),(3.,.85,0.))
    assert not capsule_hit((-3.,4.,0.),(3.,4.,0.)), 'vertical separation must matter'
    assert capsule_hit((1.70,.85,0.),(1.70,.85,0.))
    assert not capsule_hit((1.72,.85,0.),(1.72,.85,0.))
    for hz in (30,60,120):
        # Both adjacent rows can hit at their shared z=6 boundary.
        for lane in (0,1):
            room = SixLaneTrap()
            room.phase_offsets = [0.]*6
            room.phase_offsets[lane] = CYCLE_SECONDS/2
            assert room._swept_contact((0.,6.),(0.,6.),0.,1/hz), (hz,lane)
        room = SixLaneTrap()
        room.phase_offsets = [0.]*6
        room.phase_offsets[0] = CYCLE_SECONDS/2
        assert not room._swept_contact((0.,0.),(0.,0.),0.,1/hz)
        assert not room._swept_contact((0.,9.),(0.,9.),0.,1/hz)
        assert room._swept_contact((0.,0.),(0.,9.),0.,1/hz), 'fast player tunneled through row'
        # A grazing transverse roll can miss at both actual frame endpoints.
        room.phase_offsets[0] = CYCLE_SECONDS/2-.5/hz
        grazing = (0.,4.5+1.70999)
        assert not room._swept_contact(grazing,grazing,0.,0.)
        assert not room._swept_contact(grazing,grazing,1/hz,0.)
        assert room._swept_contact(grazing,grazing,0.,1/hz), 'rolling frame tunneled past capsule'
        room.phase_offsets[0] = CYCLE_SECONDS-.5/hz
        assert not room._swept_contact((0.,4.5),(0.,4.5),0.,1/hz), 'offstage wrap swept across corridor'
        # Real advance detects and counts a contact once, then permits separation.
        room.phase_offsets[0] = CYCLE_SECONDS/2
        room.z = 4.5
        room.advance(1/hz)
        assert room.ball_touching and room.contacts == 1
        room.advance(1/hz)
        assert room.contacts == 1
        room.z = 0.
        room.advance(1/hz)
        assert not room.ball_touching
    print('PASS: 30/60/120 Hz capsule height/radius, either shared-boundary row, fast crossing and offstage-wrap CCD.')


def walk_after_wait(hz, wait, x=0.):
    room = SixLaneTrap()
    room.x = x
    room.stamina = 0.
    for _ in range(round(wait*hz)):
        room.advance(1/hz)
        assert room.z == 0. and not room.ball_touching
    for _ in range(20*hz):
        room.advance(1/hz,forward=1)
        if room.ball_touching:
            return False,room
        if room.automatic_exit():
            assert room.x == x and room.contacts == 0 and not room.blocked
            assert room.stamina == 0. and room.exit_used == 'front'
            return True,room
    raise AssertionError((hz,wait,'walking never reached front'))


def check_walking_windows():
    ticks = range(ceil(10*CYCLE_SECONDS))
    common = set(ticks)
    for hz in (30,60,120):
        safe = {tick for tick in ticks if walk_after_wait(hz,tick/10)[0]}
        common &= safe
        ok,room = walk_after_wait(hz,.5)
        assert ok and room.state == 'clear' and room.z == EXIT_Z and room.time < 11.
        assert not walk_after_wait(hz,3.)[0], 'mistimed walking must still meet a rock'
        for x in (-PASSAGE_HALF_WIDTH,-1.,1.,PASSAGE_HALF_WIDTH):
            assert walk_after_wait(hz,.5,x)[0], (hz,x)
        # See the first rock pass the center, then follow on foot to the exit.
        assert all(walk_after_wait(hz,t)[0] for t in (5.2,5.8,6.4))
        print(f'PASS: {hz} Hz .5s initial wait then uninterrupted W clears front in {room.time:.3f}s at 0 ST.')
    longest = current = 0
    for tick in ticks:
        current = current+1 if tick in common else 0
        longest = max(longest,current)
    assert set(range(21)) <= common and (longest-1)*.1 >= 2., sorted(common)
    print(f'PASS: whole-period .1s wait scan has a common {(longest-1)*.1:.1f}s continuous walking window across all three rates.')


def run():
    check_geometry_and_rolling()
    check_swept_contacts()
    check_walking_windows()


if __name__ == '__main__':
    run()
