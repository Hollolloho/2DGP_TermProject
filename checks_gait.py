"""실제 지면 거리 기반 보행 검사. 모델 검사는 SDL 없이 실행한다."""
import math
from maze_model import Game, COLS, ROWS, DIRECTIONS, PHASE_SECONDS
from maze_model import WALK_CYCLE_PX, RUN_CYCLE_PX, WALK_SPEED, RUN_SPEED, project


SCHEDULES = ([1/30]*30, [1/60]*60, [1/120]*120,
             [1/120, 1/40, 1/60, 1/20]*10)


def room(player_clips=None):
    game = Game(player_clips=player_clips)
    game.grid = [[0]*COLS for _ in range(ROWS)]
    game.player.x, game.player.y = 15.5, 11.5
    return game


def assert_phase(actual, expected):
    error = (actual-expected+.5) % 1.-.5
    assert abs(error) < 1e-8, (actual, expected)


def gait(player):
    return player.gait_distance, player.gait_phase


def finish_shift(game):
    while game.state == 'shifting':
        game.update(.05, 1, 1, True)


def check_gait():
    check_clip_metadata()
    for running, speed, cycle in ((False, WALK_SPEED, WALK_CYCLE_PX),
                                  (True, RUN_SPEED, RUN_CYCLE_PX)):
        for schedule in SCHEDULES:
            for dx, dy in (*DIRECTIONS, (1, 1), (-1, 1), (1, -1), (-1, -1)):
                game = room()
                player = game.player
                player.gait_phase = .125
                for dt in schedule:
                    game.update(dt, dx, dy, running)
                actual = math.hypot(*project(player.x-15.5, player.y-11.5))
                assert math.isclose(actual, speed*sum(schedule), abs_tol=1e-8)
                assert math.isclose(player.gait_distance, actual, abs_tol=1e-8)
                assert_phase(player.gait_phase, .125+actual/cycle)

        # 마지막 부분 이동만 주기에 반영하고, 벽에 막힌 동안은 그대로 멈춘다.
        game = room()
        player = game.player
        game.grid[11][16] = 1
        player.x = 15.78
        game.update(.05, 1, 0, running)
        actual = math.hypot(*project(player.x-15.78, player.y-11.5))
        assert 0 < actual < speed*.05
        assert math.isclose(player.gait_distance, actual, abs_tol=1e-8)
        assert_phase(player.gait_phase, actual/cycle)
        stopped = gait(player)
        for _ in range(20):
            game.update(.025, 1, 0, running)
        assert gait(player) == stopped and player.state == 'idle'
        facing = player.screen_facing
        game.update(.025, 1, -1, running)
        assert player.screen_facing == facing and gait(player) == stopped

    game = room()
    player = game.player
    # 방향 전환과 걷기↔달리기가 위상을 초기화하지 않는다.
    expected = 0.
    for dx, dy, running in ((0, 1, False), (0, 1, True), (-1, 0, True),
                             (1, 0, False), (0, -1, False)):
        game.update(.025, dx, dy, running)
        expected += .025*(RUN_SPEED/RUN_CYCLE_PX if running else WALK_SPEED/WALK_CYCLE_PX)
        assert_phase(player.gait_phase, expected)
    stopped = gait(player)
    for _ in range(20):
        game.update(.025)
    assert gait(player) == stopped and player.state == 'idle'
    game.map_open = True
    for _ in range(20):
        game.update(.025, 1, 1, True)
    assert gait(player) == stopped and player.state == 'idle'
    game.map_open = False
    game.attack()
    for _ in range(20):
        game.update(.025)
    assert gait(player) == stopped

    # 닫히는 칸의 안전 위치 보정은 걸음으로 계산하지 않는다.
    game = Game()
    player = game.player
    player.gait_distance, player.gait_phase = 13.25, .3125
    player.screen_facing = 'n'
    closed = next((x, y) for y, row in enumerate(game.grid) for x, wall in enumerate(row)
                  if not wall and game.maze_layouts.grids[1][y][x])
    player.x, player.y = closed[0]+.5, closed[1]+.5
    position, stopped = (player.x, player.y), gait(player)
    game.phase_time = PHASE_SECONDS-.01
    game.update(.02, 1, 1, True)
    finish_shift(game)
    assert (player.x, player.y) != position and gait(player) == stopped
    assert player.screen_facing == 'n'
    assert game.can_stand(player.x, player.y)

    # 함정방 이동, A 복귀, B 도착, 변형 강제 복귀 모두 쿼터뷰 보행과 분리된다.
    for outcome in ('cancel', 'complete', 'shift'):
        player.x, player.y = game.trap_cell[0]+.5, game.trap_cell[1]+.5
        game.interact()
        assert game.state == 'trap'
        for _ in range(10):
            game.update(.025, 0, -1, True)
        if outcome == 'shift':
            game.phase_time = PHASE_SECONDS-.01
            game.update(.02, 0, -1)
            finish_shift(game)
        else:
            game.return_from_trap(completed=outcome == 'complete')
        assert game.state == 'explore' and gait(player) == stopped
        assert player.screen_facing == 'n'
    assert gait(Game().player) == (0., 0.)
    print('PASS: distance gait across 8 directions and 30/60/120/variable dt; partial/full collision, release, map, state changes, relocation and trap teleports.')


def check_clip_metadata():
    """이미지를 만들지 않고 메모리 토큰으로 16프레임 선택·메타 연결을 검사한다."""
    import json
    from pathlib import Path
    from game_view import View
    from maze_model import DIAGONAL_FACINGS

    catalog = json.loads((Path(__file__).parent/'sprite/quarter/player_explorer_v1/explorer.json').read_text(encoding='utf-8'))
    # 최종 에셋 교체 후에도 '정면 클립·보행 메타 없음' 호환 검사를 유지한다.
    legacy = {name: {key: value for key, value in clip.items()
                     if key not in ('cycle_distance_px', 'phase_offset_frames')}
              for name, clip in catalog['clips'].items() if name.rsplit('-', 1)[-1] in DIAGONAL_FACINGS}
    clips = dict(legacy)
    commands = ((-1, -1, 'n'), (1, 1, 's'), (1, -1, 'e'), (-1, 1, 'w'),
                (-1, 0, 'nw'), (0, -1, 'ne'), (0, 1, 'sw'), (1, 0, 'se'))
    for index, (_, _, facing) in enumerate(commands):
        for state in ('walk', 'run', 'idle'):
            clips[state+'-'+facing] = {
                'frames': [{'rect': object()} for _ in range(16)],
                'durations_ms': [100]*16, 'loop': True,
                'cycle_distance_px': (53 if state == 'walk' else 87)+index*3,
                'phase_offset_frames': 0 if facing == 'nw' else (3 if state == 'walk' else -2),
            }
        clips['attack-'+facing] = {
            'frames': [{'rect': object()} for _ in range(6)],
            'durations_ms': [83, 84, 66, 84, 100, 116],
            'events': [{'name': 'hit', 'at_ms': 233}],
            'loop': False,
        }
    # player_frame은 SDL 리소스를 사용하지 않아 플레이 창 없이 실제 선택 함수를 검사한다.
    view = View.__new__(View)
    view.player_catalog, view.facing = {'clips': clips}, DIAGONAL_FACINGS
    view.animated_player, view.animation_state, view.animation_started = None, None, 0.
    for running in (False, True):
        state = 'run' if running else 'walk'
        speed = RUN_SPEED if running else WALK_SPEED
        for schedule in SCHEDULES:
            for dx, dy, facing in commands:
                game = room(clips)
                player = game.player
                player.gait_phase = .25
                for dt in schedule:
                    game.update(dt, dx, dy, running)
                clip = clips[state+'-'+facing]
                assert player.screen_facing == facing
                assert_phase(player.gait_phase, .25+speed*sum(schedule)/clip['cycle_distance_px'])
                index = (int(player.gait_phase*16+1e-9)+clip['phase_offset_frames']) % 16
                for _ in range(3):
                    assert view.player_frame(game) is clip['frames'][index]['rect']
                stopped = gait(player)
                game.update(.01)
                assert player.screen_facing == facing and gait(player) == stopped
                assert view.player_frame(game) is clips['idle-'+facing]['frames'][0]['rect']
                # 공격은 클릭한 방향을 고정해 이후 이동 방향의 영향을 받지 않는다.
                game.attack()
                attack = clips['attack-'+facing]
                game.update(.025, -dx, -dy)
                assert player.screen_facing != facing
                assert game.attack_facing == facing and game.attack_hit_at == .233
                assert view.player_frame(game) is attack['frames'][0]['rect']

    game = room(clips)
    player = game.player
    # 같은 접지 위상은 방향·상태를 바꿔도 유지하며, 각 클립 오프셋만 적용한다.
    for running in (False, True):
        player.sprint_now() if running else player.walk_now()
        state = 'run' if running else 'walk'
        for _, _, facing in commands:
            player.screen_facing = facing
            clip = clips[state+'-'+facing]
            for index in range(16):
                player.gait_phase = (index+.25)/16
                assert view.player_frame(game) is clip['frames'][(index+clip['phase_offset_frames']) % 16]['rect']
                assert player.gait_phase == (index+.25)/16
    expected = player.gait_phase
    for dx, dy, facing, running in ((1, 1, 's', False), (1, 1, 's', True), (-1, 0, 'nw', True)):
        clip = clips[('run' if running else 'walk')+'-'+facing]
        game.update(.025, dx, dy, running)
        expected += .025*(RUN_SPEED if running else WALK_SPEED)/clip['cycle_distance_px']
        assert_phase(player.gait_phase, expected)

    # 없는 정면 클립은 원래 호환 대각선과 그 보폭·오프셋을 함께 사용한다.
    view.player_catalog = {'clips': legacy}
    for running in (False, True):
        game = room(legacy)
        game.update(.025, -1, -1, running)
        player = game.player
        assert player.screen_facing == 'n'
        state = 'run' if running else 'walk'
        name = game.locomotion_clip_name(state)
        assert name == state+'-nw'
        clip = legacy[name]
        cycle = RUN_CYCLE_PX if running else WALK_CYCLE_PX
        assert_phase(player.gait_phase, player.gait_distance/cycle)
        offset = 0 if running else 1
        index = (int(player.gait_phase*len(clip['frames']))+offset) % len(clip['frames'])
        assert view.player_frame(game) == clip['frames'][index]['rect']
        game.update(.01)
        assert game.locomotion_clip_name('idle') == 'idle-nw'
        assert view.player_frame(game) == legacy['idle-nw']['frames'][0]['rect']
        game.attack()
        assert game.attack_facing == 'n' and game.attack_clip == 'attack-nw'
        assert view.player_frame(game) == legacy['attack-nw']['frames'][0]['rect']
    print('PASS: metadata stride/offset, all 16 frame indices, 8 movement/idle and locked attack facings; legacy fallback.')


def check_gait_view(view):
    """실제 SDL View를 반복 그려도 모델 위상과 선택 프레임은 같아야 한다."""
    for running in (False, True):
        reference = None
        for schedule in SCHEDULES:
            for draws in (0, 1, 2):
                game = room(view.player_catalog['clips'])
                player = game.player
                player.gait_phase = .125
                for dt in schedule:
                    game.update(dt, 0, 1, running)
                    for _ in range(draws):
                        view.draw(game)
                result = (*gait(player), view.player_frame(game))
                if reference is None:
                    reference = result
                assert math.isclose(result[0], reference[0], abs_tol=1e-8)
                assert_phase(result[1], reference[1])
                assert result[2] == reference[2]

    game = room(view.player_catalog['clips'])
    player = game.player
    game.update(.05, 0, 1)
    saved = gait(player)
    for running in (False, True, False):
        player.sprint_now() if running else player.walk_now()
        state = 'run' if running else 'walk'
        for direction, facing in enumerate(view.facing):
            player.direction = direction
            player.screen_facing = facing
            clip = view.player_catalog['clips'][state+'-'+facing]
            offset = clip.get('phase_offset_frames', int(state == 'walk' and facing == 'nw'))
            index = (int(saved[1]*len(clip['frames']))+offset) % len(clip['frames'])
            assert view.player_frame(game) == clip['frames'][index]['rect']
            game.reveal_all = not game.reveal_all
            view.camera_game = None
            view.draw(game)
            assert gait(player) == saved

    # 정지 애니메이션·공격은 기존 시간 리듬을 계속 사용한다.
    game.update(.025)
    assert player.state == 'idle'
    initial = view.player_frame(game)
    idle = view.player_catalog['clips'][game.locomotion_clip_name('idle')]
    for _ in range(math.ceil(idle['durations_ms'][0]/50)+1):
        game.update(.05)
    assert view.player_frame(game) != initial and gait(player) == saved
    game.attack()
    attack_start = view.player_frame(game)
    for _ in range(3):
        game.update(.05)
    assert view.player_frame(game) != attack_start and gait(player) == saved
    print('PASS: actual SDL draw frequency 0/1/2 per update preserves gait and frame across all dt schedules; camera/zoom, clip changes, timed idle and attack.')


if __name__ == '__main__':
    check_gait()
