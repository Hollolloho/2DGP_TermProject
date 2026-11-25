"""본게임 돌방 모델의 공유 자원·시간·복귀·즉사·출구 우선순위 검사."""
from math import isclose
from unittest.mock import patch

from SourceCode.maze_model import Game, Player, PHASE_SECONDS
from SourceCode.six_lane_trap import SixLaneTrap, EXIT_Z


def entered(stamina=37., hp=61, phase=0):
    game = Game(117, 0)
    game.phase = game.layout_phase = phase
    game.grid = game.layout_for_phase(phase)
    game.observed, game.visited = game.observed_by_phase[phase], game.visited_by_phase[phase]
    x,y = game.boulder_entry
    game.player.x, game.player.y = x+.4, y+.6
    game.player.direction, game.player.screen_facing = 2, 'nw'
    game.player.hp, game.player.stamina = hp, stamina
    game.player.torch = game.fountain_used = True
    game.time, game.phase_time = 23., 12.
    assert game.can_stand(game.player.x,game.player.y)
    assert game.enter_boulder()
    assert game.state == 'trap' and game.trap_kind == 'boulder'
    return game


def check_entry_and_return():
    owner = Player(2.,3.,hp=43,stamina=26.)
    room = SixLaneTrap(owner)
    room.reset()
    assert room.hp == owner.hp == 43 and room.stamina == owner.stamina == 26.
    room.stamina = 19.
    assert owner.stamina == 19.
    game = entered()
    room = game.boulder_room
    assert room.player is game.player
    saved = game.player.x, game.player.y, game.player.direction, game.player.screen_facing
    assert room.time == room.z == room.stride == 0 and len(room.stones) == 6
    assert room.state == 'crossing'
    assert game.time == 23. and game.phase_time == 12.
    assert room.hp == 61 and room.stamina == 37.
    assert game.boulder_discovered and not game.boulder_completed
    assert not game.trap_completed and game.landing_cell is None
    for _ in range(10):
        game.update(.05,dy=-1)
    assert room.state == 'crossing' and room.z > 0
    room.turn(1200)
    for _ in range(4):
        game.update(.05,dy=-1)
    assert room.state == 'crossing' and room.yaw != 0.
    assert isclose(game.time,23.+room.time) and isclose(game.phase_time,12.+room.time)
    assert (game.player.x,game.player.y,game.player.direction,game.player.screen_facing) == saved
    local_time = room.time
    game.request_boulder_exit()
    game.request_boulder_return()
    assert game.state == 'trap'
    game.update(.02,dx=1,dy=-1,sprint=True)
    assert game.state == 'explore' and room.time == local_time
    assert (game.player.x,game.player.y,game.player.direction,game.player.screen_facing) == saved
    assert room.vx == room.vz == 0 and not room.running
    assert not game.boulder_return_requested and not game.boulder_exit_requested
    assert not game.boulder_completed and game.boulder_exit not in game.visited
    assert game.player.hp == 61 and game.player.stamina == 37.
    assert game.enter_boulder() and game.boulder_room is room
    assert room.time == 0 and room.state == 'crossing' and room.stamina == 37.
    game.return_from_trap()
    game.map_open = True
    assert not game.enter_boulder()
    with patch.object(Game, 'choose_boulder_shortcut', return_value=None):
        absent = Game(117,1)
    assert not absent.enter_boulder() and absent.boulder_room is None
    distant = Game(117,0)
    assert not distant.enter_boulder() and distant.boulder_room is None
    print('PASS: six-lane entry/reset shares HP/ST and world clocks; exact fractional position/facing returns and safe entry guards.')


def check_resources_and_camera():
    for phase in range(3):
        for stamina in (0.,25.,50.,100.):
            for sprint in (False, True):
                game = entered(stamina,phase=phase)
                game.update(.05,dy=-1,sprint=sprint)
                running = sprint and stamina >= .9
                expected = min(100.,stamina+(.4 if phase == 2 else 0.))-(.9 if running else 0.)
                assert isclose(game.player.stamina,expected), (phase,stamina,sprint,game.player.stamina)
                assert game.boulder_room.stamina == game.player.stamina
                assert game.boulder_room.running == running
                assert game.boulder_room.z > 0 and game.player.hp == 61
                assert isclose(game.boulder_room.time,.05) and isclose(game.time,23.05)
                assert isclose(game.phase_time,12.05)
    front, rear = entered(), entered()
    front.boulder_room.z = rear.boulder_room.z = 1.
    rear.boulder_room.turn(1200)
    for _ in range(20):
        front.update(.02,dx=.3,dy=-1)
        rear.update(.02,dx=.3,dy=-1)
        assert isclose(front.boulder_room.x,-rear.boulder_room.x,abs_tol=1e-10)
        assert isclose(front.boulder_room.z-1.,1.-rear.boulder_room.z,abs_tol=1e-10)
    assert rear.boulder_room.yaw != front.boulder_room.yaw
    print('PASS: 24 phase/ST/sprint cases charge 18 ST/s once, dawn recovers once, empty ST walks and a half turn reverses both movement components.')


def check_result_priority():
    for exit_mode in ('f','auto'):
        for outcome in ('phase','escape','collision','success'):
            game = entered()
            room = game.boulder_room
            saved = game.trap_return
            room.time = 6.
            room.x,room.z = 0., EXIT_Z-(.4 if exit_mode == 'f' else 0.)
            if exit_mode == 'f':
                game.request_boulder_exit()
            if outcome in ('phase','escape'):
                game.request_boulder_return()
            if outcome == 'phase':
                game.phase_time = PHASE_SECONDS-.01
            # At the front door no natural stone overlaps. Inject only the
            # already-tested contact result to exercise simultaneous outcomes.
            with patch.object(room,'_swept_contact',return_value=outcome == 'collision'), \
                 patch.object(game,'return_from_trap',wraps=game.return_from_trap) as returned:
                game.update(.02)
                assert returned.call_count == (0 if outcome == 'collision' else 1)
            assert not game.boulder_return_requested and not game.boulder_exit_requested
            assert (game.trap_cell,game.boulder_entry) == ((9,3),(9,6))
            if outcome in ('phase','escape'):
                assert game.state == ('shifting' if outcome == 'phase' else 'explore')
                assert (game.player.x,game.player.y) == saved and game.player.direction == 2
                assert room.time == 6. and room.exit_used is None and game.player.hp == 61
                assert game.landing_cell is None and not game.boulder_completed
                assert game.boulder_exit not in game.visited
                if outcome == 'phase':
                    assert game.time == 23. and game.player.stamina == 37.
            elif outcome == 'collision':
                assert game.state == 'failed' and room.hp == game.player.hp == 0
                assert not game.boulder_completed and room.exit_used is None
                assert game.boulder_exit not in game.visited and game.landing_cell is None
                frozen = game.time,room.time,room.stones
                game.update(.05,dy=-1,sprint=True)
                assert (game.time,room.time,room.stones) == frozen
            else:
                assert game.state == 'explore' and game.boulder_completed
                assert (game.player.x,game.player.y) == tuple(n+.5 for n in game.boulder_exit)
                assert game.boulder_exit in game.visited
                assert room.state == 'clear' and room.exit_used == 'front'
                assert not game.trap_completed and game.player.hp == 61
                assert game.player.screen_facing == 'nw'
    print('PASS: phase -> Esc -> fatal contact -> F/automatic exit; one result per tick, no false landing or double return.')


def check_course_and_targets():
    for hz in (30,60,120):
        game = entered(100.)
        room = game.boulder_room
        puzzle_path = game.puzzle.path[:]
        game.puzzle_reserved_phase = game.next_phase
        # Default rhythm permits a pure walking crossing after waiting at C.
        for _ in range(hz//2):
            game.update(1/hz)
        assert isclose(room.time,.5) and room.z == 0.
        for index in range(hz*20):
            game.update(1/hz,dy=-1)
            if game.state != 'trap':
                break
        assert game.state == 'explore' and room.state == 'clear' and room.exit_used == 'front', (hz,room.time,room.z)
        assert game.boulder_completed and game.player.hp == 61 and game.player.stamina == 100.
        assert room.contacts == 0 and room.x == 0 and not room.blocked
        assert isclose(game.time,23.+room.time) and isclose(game.phase_time,12.+room.time)
        assert game.puzzle.path == puzzle_path and game.puzzle_reserved_phase == game.next_phase
        assert game.boulder_exit in game.visited
        game.player.x,game.player.y = 9.4,6.6
        assert game.enter_boulder()
        game.request_boulder_return()
        game.update(.02)
        assert game.boulder_completed and game.boulder_exit in game.visited
        game.player.x,game.player.y = 9.4,3.6
        game.interact()
        assert game.state == 'trap' and game.trap_kind == 'blade'
        game.trap_progress = 1
        game.update(.02)
        assert (game.player.x,game.player.y) == tuple(n+.5 for n in game.trap_exit)
        assert game.landing_cell == game.trap_exit and game.trap_exit in game.visited
        assert game.boulder_completed and game.trap_completed
        game.boulder_exit_requested = game.boulder_return_requested = True
        fresh = Game(game.seed,game.run_number+1)
        frozen = room.time,room.stones,room.player
        fresh.update(.02)
        assert not fresh.trap_completed and fresh.boulder_room is None and not fresh.boulder_completed
        assert not fresh.boulder_exit_requested and not fresh.boulder_return_requested
        assert fresh.player.hp == fresh.player.stamina == 100
        assert (room.time,room.stones,room.player) == frozen and room.player is not fresh.player
        print(f'PASS: {hz} Hz center-W walking course reaches D without sprint/contact; C cancel and blade/puzzle/new-run stay independent.')


def check_general_entry(seed, run):
    game = Game(seed, run)
    assert game.boulder_entry is not None
    x,y = game.boulder_entry
    game.player.x,game.player.y = x+.4,y+.6
    game.player.hp,game.player.stamina = 67,41.
    game.player.torch = True
    game.update_visibility()
    saved = game.player.x,game.player.y,game.player.direction,game.player.screen_facing
    game.interact()
    assert game.state == 'trap' and game.trap_kind == 'boulder'
    room = game.boulder_room
    assert room.player is game.player and room.hp == 67 and room.stamina == 41.
    game.request_boulder_return()
    game.update(.02)
    assert game.state == 'explore' and not game.boulder_completed
    assert (game.player.x,game.player.y,game.player.direction,game.player.screen_facing) == saved
    game.interact()
    assert game.state == 'trap' and game.boulder_room is room and room.time == 0
    room.x,room.z = 0.,EXIT_Z-.4
    game.request_boulder_exit()
    game.update(.02)
    assert game.state == 'explore' and game.boulder_completed
    assert (game.player.x,game.player.y) == tuple(n+.5 for n in game.boulder_exit)
    assert game.landing_cell == game.boulder_exit and game.boulder_exit in game.visited
    assert game.player.hp == 67
    fresh = Game(seed, run+1)
    assert not fresh.trap_completed and fresh.boulder_room is None and not fresh.boulder_completed
    assert not fresh.boulder_return_requested and not fresh.boulder_exit_requested
    assert fresh.player.hp == fresh.player.stamina == 100
    assert room.player is not fresh.player


def run():
    check_entry_and_return()
    check_resources_and_camera()
    check_result_priority()
    check_course_and_targets()
    for seed, run in ((117,1),(117,2),(0,0),(120,0)):
        check_general_entry(seed, run)
    print('PASS: general C entry, exact cancellation, successful D landing and fresh-run resource/request reset across four seed/run examples.')


if __name__ == '__main__':
    run()
