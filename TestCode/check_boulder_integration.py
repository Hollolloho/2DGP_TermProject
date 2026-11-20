"""본게임 돌방 모델의 공유 자원·시간·복귀·즉사·출구 우선순위 검사."""
from math import isclose
from unittest.mock import patch

from BoulderPractice.boulder_practice import Practice, OBSTACLES
from SourceCode.maze_model import Game, Player, PHASE_SECONDS


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
    room = Practice(owner)
    room.reset()
    assert room.hp == owner.hp == 43 and room.stamina == owner.stamina == 26.
    room.stamina = 19.
    assert owner.stamina == 19.
    game = entered()
    room = game.boulder_room
    assert room.player is game.player
    saved = game.player.x, game.player.y, game.player.direction, game.player.screen_facing
    assert room.time == room.z == room.stride == 0 and room.ball_z == -3.
    assert game.time == 23. and game.phase_time == 12.
    assert room.hp == 61 and room.stamina == 37.
    assert game.boulder_discovered and not game.boulder_completed
    assert not game.trap_completed and game.landing_cell is None
    for _ in range(98):
        game.update(.05,dy=-1)
    assert room.state == 'ready' and room.ball_z == -3.
    for _ in range(4):
        game.update(.05,dy=-1,look_back=True)
    assert room.state == 'chasing' and room.ball_z > -3.
    assert isclose(game.time,23.+room.time) and isclose(game.phase_time,12.+room.time)
    assert (game.player.x,game.player.y,game.player.direction,game.player.screen_facing) == saved
    local_time = room.time
    game.request_boulder_exit()
    game.request_boulder_return()
    assert game.state == 'trap'
    game.update(.02,dx=1,dy=-1,sprint=True)
    assert game.state == 'explore' and room.time == local_time
    assert (game.player.x,game.player.y,game.player.direction,game.player.screen_facing) == saved
    assert room.vx == room.vz == 0 and not room.look_back and not room.running
    assert not game.boulder_return_requested and not game.boulder_exit_requested
    assert not game.boulder_completed and game.boulder_exit not in game.visited
    assert game.player.hp == 61 and game.player.stamina == 37.
    assert game.enter_boulder() and game.boulder_room is room
    assert room.time == 0 and room.state == 'ready' and room.stamina == 37.
    game.return_from_trap()
    game.map_open = True
    assert not game.enter_boulder()
    absent = Game(117,1)
    assert not absent.enter_boulder() and absent.boulder_room is None
    distant = Game(117,0)
    assert not distant.enter_boulder() and distant.boulder_room is None
    print('PASS: entry/reset shares HP/ST and world clocks; exact fractional position/facing returns; delayed release and safe entry guards.')


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
    for _ in range(80):
        front.update(.02,dx=.3,dy=-1)
        rear.update(.02,dx=.3,dy=-1,look_back=True)
        assert (front.boulder_room.x,front.boulder_room.z) == (rear.boulder_room.x,rear.boulder_room.z)
    assert rear.boulder_room.look_back and not front.boulder_room.look_back
    print('PASS: 24 phase/ST/sprint cases charge 18 ST/s once, dawn recovers once, empty ST walks and Q preserves movement.')


def check_result_priority():
    for exit_mode in ('f','auto'):
        for outcome in ('phase','escape','collision','success'):
            game = entered()
            room = game.boulder_room
            saved = game.trap_return
            room.release()
            room.time = 6.
            room.x,room.z = (-1. if exit_mode == 'f' else -1.4),46.
            room.ball_z = -10. if outcome == 'success' else 46.
            if exit_mode == 'f':
                game.request_boulder_exit()
            if outcome in ('phase','escape'):
                game.request_boulder_return()
            if outcome == 'phase':
                game.phase_time = PHASE_SECONDS-.01
            with patch.object(game,'return_from_trap',wraps=game.return_from_trap) as returned:
                game.update(.02)
                assert returned.call_count == (0 if outcome == 'collision' else 1)
            assert not game.boulder_return_requested and not game.boulder_exit_requested
            assert (game.trap_cell,game.trap_exit,game.boulder_entry,game.boulder_exit) == ((9,3),(20,11),(9,6),(11,13))
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
                frozen = game.time,room.time,room.ball_z,room.ball_distance
                game.update(.05,dy=-1,sprint=True)
                assert (game.time,room.time,room.ball_z,room.ball_distance) == frozen
            else:
                assert game.state == 'explore' and game.boulder_completed
                assert (game.player.x,game.player.y) == (11.5,13.5)
                assert game.landing_cell == game.boulder_exit and game.boulder_exit in game.visited
                assert room.state == 'clear' and room.exit_used == 'narrow'
                assert not game.trap_completed and game.player.hp == 61
                assert game.landing_until == game.time+10.
    print('PASS: phase -> Esc -> fatal contact -> F/automatic exit; one result per tick, no false D discovery or double return.')


def check_course_and_targets():
    for exit_name in ('narrow','wide'):
        game = entered(100.)
        room = game.boulder_room
        puzzle_path = game.puzzle.path[:]
        game.puzzle_reserved_phase = game.next_phase
        for index in range(4000):
            pending = [entry for entry in OBSTACLES if room.z < entry[2]+entry[4]+.3]
            target = (-.85 if pending[0][1] > 0 else .85) if pending else (-1. if exit_name == 'narrow' else 1.)
            dx = 1 if room.x < target-.045 else -1 if room.x > target+.045 else 0
            if room.exit_nearby() == exit_name:
                game.request_boulder_exit()
            game.update(.02,dx,-1,room.gap < 6,look_back=index%31 < 9)
            if game.state != 'trap':
                break
        assert game.state == 'explore' and room.state == 'clear' and room.exit_used == exit_name
        assert game.boulder_completed and game.player.hp == 61 and game.player.stamina >= 0
        assert isclose(game.time,23.+room.time) and isclose(game.phase_time,12.+room.time)
        assert game.puzzle.path == puzzle_path and game.puzzle_reserved_phase == game.next_phase
        assert game.landing_cell == game.boulder_exit
        game.player.x,game.player.y = 9.4,6.6
        assert game.enter_boulder()
        game.request_boulder_return()
        game.update(.02)
        assert game.boulder_completed and game.landing_cell == game.boulder_exit
        game.player.x,game.player.y = 9.4,3.6
        game.interact()
        assert game.state == 'trap' and game.trap_kind == 'blade'
        game.return_from_trap(completed=True)
        assert (game.player.x,game.player.y) == (20.5,11.5) and game.landing_cell == game.trap_exit
        assert game.boulder_completed and game.trap_completed
        game.boulder_exit_requested = game.boulder_return_requested = True
        fresh = Game(game.seed,game.run_number+1)
        frozen = room.time,room.ball_z,room.player
        fresh.update(.02)
        assert fresh.boulder_room is None and not fresh.boulder_completed
        assert not fresh.boulder_exit_requested and not fresh.boulder_return_requested
        assert fresh.player.hp == fresh.player.stamina == 100
        assert (room.time,room.ball_z,room.player) == frozen and room.player is not fresh.player
        print(f'PASS: full {exit_name} course reaches D; C cancel and A/B keep their targets, puzzle and fresh-run state.')


def run():
    check_entry_and_return()
    check_resources_and_camera()
    check_result_priority()
    check_course_and_targets()


if __name__ == '__main__':
    run()
