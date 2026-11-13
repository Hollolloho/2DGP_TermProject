"""main.py --smoke에서 실행하는 실제 SDL 입력·화면 검사."""
import json
import ctypes
from bisect import bisect_right
from itertools import accumulate
import pico2d.pico2d as p
from maze_model import DIRECTIONS, TRAP_LENGTH, Game, shortest_path
from maze_model import PHASE_SECONDS, PHASE_WARNING_SECONDS, SHIFT_SWAP_AT
from maze_model import WALK_SPEED, RUN_SPEED, PLAYER_HALF_SIZE
from game_view import LW, LH, SCALE, project
from trap_view import project as project_trap
from mouse_maze import BOARD


def inject_key(key, down=True):
    event=p.SDL_Event()
    event.type=p.SDL_KEYDOWN if down else p.SDL_KEYUP
    event.key.keysym.sym=key
    event.key.repeat=0
    assert p.SDL_PushEvent(event)==1


def inject_mouse(event_type, point, held=True):
    event = p.SDL_Event()
    event.type = event_type
    x, y = (round(coord*SCALE) for coord in point)
    if event_type == p.SDL_MOUSEMOTION:
        event.motion.x, event.motion.y = x, y
        event.motion.state = p.SDL_BUTTON_LMASK if held else 0
    else:
        event.button.x, event.button.y = x, y
        event.button.button = p.SDL_BUTTON_LEFT
    assert p.SDL_PushEvent(event) == 1


def run(app):
    output = app.output
    from math import ceil, hypot, isclose

    g=app.game
    player = g.player
    step = .025
    w, a, s, d = p.SDLK_w, p.SDLK_a, p.SDLK_s, p.SDLK_d
    diagonals = ((s, a), (w, a), (s, d), (w, d))  # DIRECTIONS order

    def press(*keys, ticks=0, timesteps=None, track_camera=False):
        for key in keys:
            inject_key(key)
        app.handle_events()
        for dt in ([step]*ticks if timesteps is None else timesteps):
            app.update(dt)
            if track_camera:
                app.view.position_camera(app.game)
        for key in keys:
            inject_key(key, down=False)
        app.handle_events()

    def walk_tile(*keys):
        seconds = hypot(*project(1, 0))/WALK_SPEED
        # 한 칸이 틱의 정수배여도 마지막에 0초 갱신을 추가하지 않는다.
        ticks = ceil(seconds/step)
        press(*keys, timesteps=[seconds/ticks]*ticks)

    def walk_path(start, end):
        path = shortest_path(g.grid, start, end)
        for (x, y), (nx, ny) in zip(path, path[1:]):
            walk_tile(*diagonals[DIRECTIONS.index((nx-x, ny-y))])

    def click_attack():
        event = p.SDL_Event()
        event.type = p.SDL_MOUSEBUTTONDOWN
        event.button.button = p.SDL_BUTTON_LEFT
        assert p.SDL_PushEvent(event) == 1
        app.handle_events()

    def check_puzzle_input():
        room = Game(117, player_clips=app.view.player_catalog['clips'])
        app.game = room
        wall, near, far = room.puzzle_gate
        room.player.x, room.player.y = near[0]+.5, near[1]+.5
        room.update_visibility()
        left, top, size = BOARD
        center = lambda x, y: (left+(x+.5)*size, top+(y+.5)*size)
        start, corner, goal = center(1, 1), center(3, 1), center(7, 1)
        down, motion, up = p.SDL_MOUSEBUTTONDOWN, p.SDL_MOUSEMOTION, p.SDL_MOUSEBUTTONUP

        def mouse(kind, point, held=True):
            inject_mouse(kind, point, held)
            app.handle_events()

        try:
            press(p.SDLK_f)
            assert room.state == 'puzzle'
            app.view.draw(room)
            press(ticks=12)
            app.view.draw(room)
            app.view.capture(output/'puzzle-preview.png')
            press(w, p.SDLK_m, ticks=4)
            assert room.phase_time > 0 and not room.map_open and not app.held
            mouse(down, start)
            mouse(motion, goal)
            assert room.puzzle.hit_wall and room.player.hp == 100
            mouse(up, goal)
            mouse(down, start)
            mouse(motion, corner)
            mouse(up, goal)
            mouse(motion, center(3, 3), False)
            assert room.puzzle.point == corner and not room.puzzle.dragging
            mouse(down, corner)
            lost = p.SDL_Event()
            lost.type = p.SDL_WINDOWEVENT
            lost.window.event = p.SDL_WINDOWEVENT_FOCUS_LOST
            assert p.SDL_PushEvent(lost) == 1
            app.handle_events()
            mouse(motion, center(3, 3))
            assert room.puzzle.point == corner and not room.puzzle.dragging
            mouse(up, corner)
            press(p.SDLK_ESCAPE)
            assert app.running and room.state == 'explore' and room.puzzle.point == corner
            press(p.SDLK_f)
            mouse(down, corner)
            for point in (center(3, 3), center(5, 3), center(5, 1), goal):
                mouse(motion, point)
            assert room.state == 'explore' and room.puzzle_reserved_phase == 1 and room.solid(*wall)
            mouse(down, goal)  # A duplicate down before release must not become an attack.
            assert not room.attack_hits_ms
            mouse(up, goal)
            room.phase_time = PHASE_SECONDS-.01
            app.update(.02)
            assert room.state == 'shifting' and room.solid(*wall)
            while room.state == 'shifting':
                app.update(.05)
            assert room.puzzle_open and not room.solid(*wall)
            app.view.draw(room)
            assert app.view.light_revision == room.layout_revision
            app.view.capture(output/'puzzle-open.png')
            walk_tile(s, a)
            assert (int(room.player.x), int(room.player.y)) == wall
            walk_tile(s, a)
            assert (int(room.player.x), int(room.player.y)) == far
            press(p.SDLK_r)
            fresh = app.game
            assert fresh.run_number == 1 and fresh.solid(*fresh.puzzle_gate[0])
            assert not fresh.puzzle_open and fresh.puzzle_reserved_phase is None
            print('PASS: SDL mouse maze input, focus/release/resume, reservation, drawn opening, traversal and R reset.')
        finally:
            app.game = g
            app.held.clear()
            app.puzzle_mouse_held = False

    def check_dagger_timeline(room):
        view = app.view
        commands = (('n', (w,), (-1, -1)), ('s', (s,), (1, 1)),
                    ('w', (a,), (-1, 1)), ('e', (d,), (1, -1)),
                    ('nw', (w, a), (-1, 0)), ('ne', (w, d), (0, -1)),
                    ('sw', (s, a), (0, 1)), ('se', (s, d), (1, 0)))
        fx_starts = view.dagger_fx['frame_starts_ms']
        assert fx_starts == [200, 217, 233, 250, 267, 283, 300, 317, 333, 350, 367, 383]
        # 각 검격의 프레임 중앙과 타격 경계 전후를 검사한다.
        strike_checks = {(start+end)/2: index for index, (start, end) in
                         enumerate(zip(fx_starts, fx_starts[1:]+[400]))}
        strike_checks.update({199: None, 200: 0, 232: 1, 233: 2, 234: 2, 400: None})
        fx_checks = strike_checks | {ms+233: index for ms, index in strike_checks.items()}
        hit_checks = (232, 233, 234, 465, 466, 467)
        image = view.image
        foot_x, foot_y = 180, 140
        pivot_x, pivot_y = view.player_catalog['pivot']
        calls = []

        def record(name, rect, source, *args, **kwargs):
            calls.append((name, rect, source))
            image(name, rect, source, *args, **kwargs)

        def tip_pixels(x, y):
            rect = p.SDL_Rect(round(x)-4, round(y)-4, 9, 9)
            pixels = (ctypes.c_ubyte*(rect.w*rect.h*4))()
            assert p.SDL_RenderReadPixels(p.renderer, rect, p.SDL_PIXELFORMAT_RGBA32, pixels, rect.w*4) == 0
            return bytes(pixels)

        view.world_scale = 1
        p.SDL_SetRenderTarget(p.renderer, view.logical)
        view.image = record
        try:
            for facing, keys, (dx, dy) in commands:
                room.player.x, room.player.y = 15.5, 11.5
                room.guard, room.guard_hp = (15+dx, 11+dy), 3
                room.attack_time = 10.
                press(*keys, ticks=1)
                click_attack()
                assert room.attack_facing == facing and room.attack_clip == 'attack-'+facing
                assert room.guard_hp == 3
                body = room.player_clips[room.attack_clip]
                fx = view.dagger_fx['clips'][facing]
                durations = body['durations_ms']
                body_starts = [0, *accumulate(durations[:-1])]
                body_checks = {start+duration/2: i for i, (start, duration) in
                               enumerate(zip(body_starts, durations))}
                hits = [event for event in body['events'] if event['name'] == 'hit']
                assert room.attack_hits_ms == (233, 466)
                for hit in hits:
                    ms, frame = hit['at_ms'], hit['frame']
                    assert ms == body_starts[frame]
                    body_checks.update({ms-1: frame-1, ms: frame, ms+1: frame})
                for ms in sorted(body_checks.keys() | fx_checks.keys() | {400, 750}):
                    remaining = ms/1000-room.attack_time
                    ticks = ceil(remaining/.05)
                    press(timesteps=[remaining/ticks]*ticks)
                    if room.attack_time < ms/1000:
                        press(timesteps=[ms/1000-room.attack_time])
                    expected_hp = 3-sum(ms >= hit for hit in (233, 466))
                    assert room.guard_hp == expected_hp, (facing, ms, room.guard_hp)
                    if ms == 400:
                        click_attack()
                        assert isclose(room.attack_time, .4)
                    if ms in body_checks:
                        assert view.player_frame(room) == body['frames'][body_checks[ms]]['rect']
                    if ms in fx_checks:
                        calls.clear()
                        view.clear()
                        view.player(foot_x, foot_y, room)
                        index = fx_checks[ms]
                        if index is None:
                            assert [item[0] for item in calls] == ['player']
                        else:
                            pos = 0 if fx['draw_layer'] == 'back' else 1
                            assert len(calls) == 2 and calls[1-pos][0] == 'player'
                            body_index = bisect_right(body_starts, ms)-1
                            tip_x, tip_y = fx['tip_px'][body_index]
                            anchor_x, anchor_y = fx['anchor_px'][index]
                            tip_x, tip_y = foot_x-pivot_x+tip_x, foot_y-pivot_y+tip_y
                            source = fx['frames'][index]['rect']
                            expected = (tip_x-anchor_x, tip_y-anchor_y, *source[2:])
                            name, destination, drawn_source = calls[pos]
                            assert name == 'dagger-slash' and drawn_source == source
                            assert all(isclose(actual, target, abs_tol=1e-9)
                                       for actual, target in zip(destination, expected))
                            if ms in hit_checks:
                                with_effect = tip_pixels(tip_x, tip_y)
                                view.clear()
                                image(*calls[1-pos])
                                assert with_effect != tip_pixels(tip_x, tip_y), (facing, 'occluded effect tip')
                                # Moving attacks use the same tip, with legs underneath the masked upper body.
                                room.player.walk_now()
                                calls.clear()
                                view.clear()
                                view.player(foot_x, foot_y, room)
                                assert len(calls) == 3
                                assert calls[0 if pos == 0 else 2] == (name, destination, drawn_source)
                                layers = [call for call in calls if call[0] == 'moving-attack']
                                assert len(layers) == 2 and layers[1][2] == body['upper_layer_rects'][body_index]
                                with_moving_effect = tip_pixels(tip_x, tip_y)
                                view.clear()
                                for layer in layers:
                                    image(*layer)
                                assert with_moving_effect != tip_pixels(tip_x, tip_y), (facing, 'occluded moving effect tip')
                                room.player.rest()
                click_attack()
                assert room.attack_time == 0.
        finally:
            view.image = image
            p.SDL_SetRenderTarget(p.renderer, None)
        print('PASS: SDL 8 attack directions, 233/466ms body frames and hits, tip-aligned effect pixels and draw layer.')

    def check_attack_render():
        room = Game(g.seed, player_clips=app.view.player_catalog['clips'])
        room.grid = [[0]*len(row) for row in room.grid]
        room.player.x, room.player.y = 15.5, 11.5
        room.guard = (15, 12)
        app.game = room
        try:
            press(s, a, ticks=1)
            click_attack()
            clip = room.player_clips['attack-sw']
            assert room.attack_facing == 'sw' and room.guard_hp == 3
            assert app.view.player_frame(room) == clip['frames'][0]['rect']
            press(w, d, ticks=1)
            assert room.player.screen_facing == 'ne' and room.attack_facing == 'sw'
            assert app.view.player_frame(room) == clip['frames'][0]['rect']
            view = app.view
            walk_sw = room.player_clips['walk-sw']
            phase = (-room.player.gait_phase) % 1
            leg_index = int(phase*len(walk_sw['frames'])+1e-9) % len(walk_sw['frames'])
            calls = []
            image, effect = view.image, view.effect
            old_scale, view.world_scale = view.world_scale, 1
            room.player.torch = True
            guard = room.guard
            room.guard = (1, 1)
            try:
                view.image = lambda name, dst, src: calls.append((name, dst, src))
                view.effect = lambda name, x, y, time, scale: calls.append((name, (x, y), None))
                view.player(180, 140, room)
                mount = clip['torch_mounts'][0]
                assert calls == [
                    ('torch', (148+mount[0], 86+mount[1]), None),
                    ('moving-attack', (148, 86, 64, 64), walk_sw['leg_layer_rects'][leg_index]),
                    ('moving-attack', (148, 86, 64, 64), clip['upper_layer_rects'][0]),
                ]
                press(w, d, timesteps=[.05]*14+[.026])
                assert room.attack_time >= .75 and room.player.screen_facing == 'ne'
                assert room.guard_hp == 3
                calls.clear()
                view.player(180, 140, room)
                walk, frame = view.locomotion_pose(room, 'walk')
                assert walk is room.player_clips['walk-ne']
                assert calls == [
                    ('player', (148, 86, 64, 64), walk['frames'][frame]['rect']),
                    ('torch', (148+walk['torch_mounts'][frame][0], 86+walk['torch_mounts'][frame][1]), None),
                ]
            finally:
                room.player.torch = False
                room.guard = guard
                view.image, view.effect, view.world_scale = image, effect, old_scale
            room.player.x, room.player.y = 15.5, 11.5
            press(s, a, ticks=1)
            click_attack()
            hit = next(event for event in clip['events'] if event['name'] == 'hit')
            before_hit = hit['at_ms']/1000-room.attack_time-.001
            ticks = ceil(before_hit/.05)
            press(timesteps=[before_hit/ticks]*ticks)
            assert room.guard_hp == 3
            press(timesteps=[.002])
            assert room.guard_hp == 2
            assert app.view.player_frame(room) == clip['frames'][hit['frame']]['rect']
            check_dagger_timeline(room)
            press(p.SDLK_r)
            assert app.game is not room and app.game.attack_facing is None and app.game.attack_clip is None
            assert app.game.guard_hp == 3
            print('PASS: SDL NE movement during SW attack keeps SW upper body and torch, reverses SW gait, then resumes NE walk; hit and R verified.')
        finally:
            app.game = g
            app.held.clear()

    def check_controls():
        room = Game(g.seed, player_clips=app.view.player_catalog['clips'])
        room.grid = [[0] * len(row) for row in room.grid]
        actor = room.player
        actor.x, actor.y = 15.5, 11.5
        app.game = room
        view = app.view
        view.position_camera(room)
        clips = view.player_catalog['clips']

        def check_move(keys, sx, sy, direction, running=False):
            grid_x, grid_y = actor.x, actor.y
            start_x, start_y = view.world(grid_x, grid_y)
            press(*keys, ticks=1)
            screen_x, screen_y = view.world(actor.x, actor.y)
            for delta, sign in ((screen_x-start_x, sx), (screen_y-start_y, sy)):
                if sign:
                    assert delta*sign > 0
                else:
                    assert isclose(delta, 0, abs_tol=1e-9)
            distance = hypot(*project(actor.x-grid_x, actor.y-grid_y))
            assert isclose(distance, (RUN_SPEED if running else WALK_SPEED)*step)
            assert actor.direction == direction
            assert actor.screen_facing == {
                (0, -1): 'n', (0, 1): 's', (-1, 0): 'w', (1, 0): 'e',
                (-1, -1): 'nw', (1, -1): 'ne', (-1, 1): 'sw', (1, 1): 'se',
            }[(sx, sy)]
            assert actor.state == ('sprint' if running else 'walk')
            state = 'run' if running else 'walk'
            clip_name = room.locomotion_clip_name(state)
            if sx and sy:
                assert clip_name == f'{state}-{actor.screen_facing}'
            clip = clips[clip_name]
            assert view.player_frame(room) in [frame['rect'] for frame in clip['frames']]

        try:
            for keys, (sx, sy, facing) in zip(diagonals,
                    ((-1, 1, 0), (-1, -1, 1), (1, 1, 2), (1, -1, 3))):
                check_move(keys, sx, sy, facing)
                check_move((*keys, p.SDLK_LSHIFT), sx, sy, facing, running=True)
            for key, sx, sy, facing in ((w, 0, -1, 3), (a, -1, 0, 1),
                                         (s, 0, 1, 0), (d, 1, 0, 2)):
                actor.direction = facing
                check_move((key,), sx, sy, facing)
                check_move((key,), sx, sy, facing)

            # Releasing one key of an up-right chord retains the compatible facing.
            check_move((w, d), 1, -1, 3)
            check_move((d,), 1, 0, 3)
            check_move((w, s, d), 1, 0, 3)
            start = actor.x, actor.y, actor.direction
            for keys in ((w, s), (a, d), (p.SDLK_UP,), (p.SDLK_LEFT,),
                         (p.SDLK_DOWN,), (p.SDLK_RIGHT,)):
                press(*keys, ticks=4)
                assert (actor.x, actor.y, actor.direction) == start

            # 8방향 × 4개 초기 방향 × 보행/달리기 × 4개 dt 조건을 실제 SDL 입력으로 검사한다.
            schedules = {
                '30 FPS': [1/30]*30,
                '60 FPS': [1/60]*60,
                '120 FPS': [1/120]*120,
                'variable': [1/120, 1/40, 1/60, 1/20]*10,
            }
            commands = (((w,), 0, -1), ((a,), -1, 0), ((s,), 0, 1), ((d,), 1, 0),
                        ((w, a), -2, -1), ((w, d), 2, -1), ((s, a), -2, 1), ((s, d), 2, 1))
            max_speed_error = 0.

            def reset(x=15.5, y=11.5, direction=0):
                actor.x, actor.y, actor.direction = x, y, direction
                actor.stamina = 100.
                actor.rest()
                room.phase_time = 0.

            for times in schedules.values():
                elapsed = sum(times)
                for running in (False, True):
                    speed = RUN_SPEED if running else WALK_SPEED
                    for direction in range(4):
                        for keys, sx, sy in commands:
                            reset(direction=direction)
                            # 카메라 추적·전체 보기 배율이 이동 계산에 끼어들지 않아야 한다.
                            room.reveal_all = direction % 2 == 1
                            view.camera_game = None
                            view.position_camera(room)
                            origin = view.origin
                            screen_before = view.world(actor.x, actor.y)
                            chord = (*keys, p.SDLK_LSHIFT) if running else keys
                            press(*chord, timesteps=times, track_camera=True)
                            ground_delta = project(actor.x-15.5, actor.y-11.5)
                            expected = speed*elapsed/hypot(sx, sy)
                            assert isclose(ground_delta[0], sx*expected, abs_tol=1e-8)
                            assert isclose(ground_delta[1], sy*expected, abs_tol=1e-8)
                            max_speed_error = max(max_speed_error, abs(hypot(*ground_delta)/elapsed-speed))
                            screen_after = view.world(actor.x, actor.y)
                            for index in (0, 1):
                                without_camera = (screen_after[index]-screen_before[index]
                                                  -view.origin[index]+origin[index])/view.world_scale
                                assert isclose(without_camera, ground_delta[index], abs_tol=1e-8)
                            stopped = actor.x, actor.y
                            press(ticks=1)
                            assert (actor.x, actor.y) == stopped and actor.state == 'idle'

            # 한 칸 통로에서 단일 키는 벽 직전까지 직선 이동하고 멈춘다.
            room.reveal_all = False
            room.grid = [[int(x != 15) for x in range(len(row))] for row in room.grid]
            clearance = .5-PLAYER_HALF_SIZE
            for times in schedules.values():
                for running in (False, True):
                    for key, gx, gy in ((w, -1, -1), (a, -1, 1), (s, 1, 1), (d, 1, -1)):
                        reset()
                        chord = (key, p.SDLK_LSHIFT) if running else (key,)
                        press(*chord, timesteps=times)
                        assert isclose(actor.x-15.5, gx*clearance, abs_tol=2e-7)
                        assert isclose(actor.y-11.5, gy*clearance, abs_tol=2e-7)
                        assert actor.state == 'idle' and room.can_stand(actor.x, actor.y)
                        stopped = actor.x, actor.y
                        press(*chord, ticks=8)
                        assert (actor.x, actor.y) == stopped and actor.state == 'idle'
                    # 벽에 거의 닿아 있어도 통로와 평행한 두 키 입력은 계속 이동한다.
                    for keys, sign in (((s, a), 1), ((w, d), -1)):
                        reset(x=15.79-1e-7)
                        chord = (*keys, p.SDLK_LSHIFT) if running else keys
                        press(*chord, timesteps=times)
                        assert actor.x == 15.79-1e-7
                        speed = RUN_SPEED if running else WALK_SPEED
                        assert isclose(actor.y-11.5, sign*speed/hypot(*project(1, 0))*sum(times))
                        assert room.can_stand(actor.x, actor.y)

            # 끝점은 안전하지만 중간에 모퉁이를 스치는 경로도 4방향 모두 막아야 한다.
            for turns, key in enumerate((s, a, w, d)):
                room.grid = [[0]*len(row) for row in room.grid]
                px, py, wx, wy, gx, gy = .28, .695, 1., 0., 1., 1.
                for _ in range(turns):
                    px, py, wx, wy, gx, gy = -py, px, -wy, wx, -gy, gx
                room.grid[round(11+wy)][round(15+wx)] = 1
                start_x, start_y = 15.5+px, 11.5+py
                for times in schedules.values():
                    reset(start_x, start_y)
                    proposed = .05*WALK_SPEED/hypot(*project(gx, gy))
                    assert room.can_stand(start_x+gx*proposed, start_y+gy*proposed)
                    press(key, timesteps=times)
                    assert isclose(actor.x-start_x, gx*.01, abs_tol=2e-7)
                    assert isclose(actor.y-start_y, gy*.01, abs_tol=2e-7)
                    assert room.can_stand(actor.x, actor.y) and actor.state == 'idle'

            # L자 통로의 모서리를 가로지르지 않고, 통로 축을 따라 꺾어서 통과한다.
            room.grid = [[int(not (x == 15 or y == 11)) for x in range(len(row))] for y, row in enumerate(room.grid)]
            reset(15.5, 10.5)
            press(s, ticks=16)
            assert actor.x < 15.8 and actor.y < 10.8
            reset(15.5, 10.5)
            walk_tile(s, a)
            walk_tile(s, d)
            assert isclose(actor.x, 16.5) and isclose(actor.y, 11.5)
            assert room.can_stand(actor.x, actor.y)

            # 실제 입력으로 상하좌우 자세와 걷기 0.8초 주기를 검사한다.
            room.grid = [[0]*len(row) for row in room.grid]
            walk_schedules = {'20 FPS': [.05]*16}
            walk_schedules.update({name: times[:round(len(times)*.8)] for name, times in schedules.items()})
            cardinal = ((w, 'n', 'north', 0, -1), (s, 's', 'south', 0, 1),
                        (a, 'w', 'west', -1, 0), (d, 'e', 'east', 1, 0))
            for key, facing, label, sx, sy in cardinal:
                walk_name, idle_name = f'walk-{facing}', f'idle-{facing}'
                walk = clips[walk_name]
                assert len(walk['frames']) == 16 and walk['durations_ms'] == [50]*16
                offset = walk['phase_offset_frames']
                for schedule, times in walk_schedules.items():
                    reset()
                    actor.gait_phase = actor.gait_distance = 0.
                    inject_key(key)
                    app.handle_events()
                    elapsed = 0.
                    seen = set()
                    for tick, dt in enumerate(times, start=1):
                        app.update(dt)
                        elapsed += dt
                        index = (int(elapsed/.05+1e-9)+offset) % 16
                        assert room.locomotion_clip_name('walk') == walk_name
                        frame = view.player_frame(room)
                        assert frame == walk['frames'][index]['rect'], (walk_name, schedule, elapsed, index)
                        seen.add(tuple(frame))
                        if schedule == '20 FPS':
                            view.draw(room)
                            if tick % 4 == 0:
                                view.capture(output/f'{label}-walk-{tick:02}.png')
                    assert isclose(elapsed, .8) and len(seen) == 16
                    assert actor.gait_phase == 0.
                    assert isclose(actor.gait_distance, WALK_SPEED*.8, abs_tol=1e-8)
                    dx, dy = project(actor.x-15.5, actor.y-11.5)
                    assert isclose(dx, sx*WALK_SPEED*.8, abs_tol=1e-8)
                    assert isclose(dy, sy*WALK_SPEED*.8, abs_tol=1e-8)
                    inject_key(key, down=False)
                    app.handle_events()
                    press(ticks=1)
                    assert room.locomotion_clip_name('idle') == idle_name
                    assert view.player_frame(room) == clips[idle_name]['frames'][0]['rect']
                print(f'PASS: {walk_name} 16 frames in 0.8s at 20/30/60/120 FPS and variable dt, projected speed and {idle_name} on release.')
            print('PASS: W/S/A/D select all four cardinal idle poses on release.')
            print(f'PASS: 256 SDL speed cases (30/60/120 FPS + variable dt), max error {max_speed_error:.3g} px/s; straight wall stops, swept corners, narrow corridors and immediate release.')
        finally:
            app.game = g
            app.held.clear()

    def snapshot(name):
        # Draw once to start a mode transition, then capture after its fade.
        app.view.draw(g)
        for _ in range(16): app.update(.025)
        app.view.draw(g)
        app.view.capture(output/name)

    def check_phase_render():
        """실제 SDL 키로 전환·통과·함정 복귀·R을 확인하고 비교 프레임을 남긴다."""
        room = Game(g.seed, player_clips=app.view.player_catalog['clips'])
        app.game = room
        next_grid = room.maze_layouts.grids[1]
        opened = next((x, y) for y, row in enumerate(room.grid) for x, wall in enumerate(row)
                      if wall and not next_grid[y][x])
        x, y = opened
        entry = next((x+dx, y+dy) for dx, dy in DIRECTIONS
                     if not room.solid(x+dx, y+dy) and not next_grid[y+dy][x+dx])
        room.player.x, room.player.y = entry[0]+.5, entry[1]+.5
        room.player.torch = True
        room.update_visibility()
        room.ui_time = 1.

        def frame(name):
            app.render(.025)
            app.view.capture(output/'phase_changes'/name)

        def hud_pixels():
            # 같은 변형 구간의 HUD 픽셀이 진동으로 이동하지 않는지 검사한다.
            rect = p.SDL_Rect(512*SCALE, 30*SCALE, 128*SCALE, 340*SCALE)
            pixels = (ctypes.c_ubyte*(rect.w*rect.h*4))()
            p.SDL_SetRenderTarget(p.renderer, app.view.display)
            try:
                assert p.SDL_RenderReadPixels(p.renderer, rect, p.SDL_PIXELFORMAT_RGBA32, pixels, rect.w*4) == 0
                return bytes(pixels)
            finally:
                p.SDL_SetRenderTarget(p.renderer, None)

        class SoundCount:
            def __init__(self):
                self.calls = 0

            def play(self):
                self.calls += 1

        original_step, original_blade = app.audio.step, app.audio.blade
        step_sound, warning_sound = SoundCount(), SoundCount()
        app.audio.step, app.audio.blade = step_sound, warning_sound
        try:
            app.view.draw(room)
            room.phase_time = PHASE_SECONDS-PHASE_WARNING_SECONDS-.01
            press(ticks=1)
            assert room.phase_warning
            for _ in range(4):
                app.audio.update(room)
            assert warning_sound.calls == 1
            room.ui_time += .4
            frame('01-warning.png')
            room.phase_time = PHASE_SECONDS-.01
            inject_key(w)
            app.handle_events()
            app.update(.02)
            assert room.state == 'shifting' and not app.held
            world = room.time, room.attack_time, room.player.stamina
            for _ in range(3):
                app.update(.05)
            for _ in range(4):
                app.audio.update(room)
            assert step_sound.calls == warning_sound.calls == 1
            press(p.SDLK_f, p.SDLK_m, d)
            assert room.state == 'shifting' and not room.map_open and not app.held
            frame('02-wall-lowering.png')
            hud_before = hud_pixels()
            for _ in range(2):
                app.update(.05)
            frame('03-before-swap.png')
            assert hud_pixels() == hud_before, 'HUD moved during the world shake.'
            for _ in range(2):
                app.update(.05)
            assert room.phase == 1 and room.layout_revision == 1 and not room.solid(*opened)
            frame('04-after-swap.png')
            assert set(app.view.discovery) == room.observed
            assert set(app.view.exposure) <= room.observed
            for _ in range(2):
                app.update(.05)
            frame('05-wall-settling.png')
            while room.state == 'shifting':
                app.update(.05)
            assert (room.time, room.attack_time, room.player.stamina) == world
            frame('06-new-layout.png')
            direction = DIRECTIONS.index((opened[0]-entry[0], opened[1]-entry[1]))
            walk_tile(*diagonals[direction])
            assert all(isclose(value, cell+.5) for value, cell in zip((room.player.x, room.player.y), opened))
            frame('07-open-passage-walked.png')

            # 지도를 열어도 시간은 흐르고, 변형 후에는 새 시간대의 기록만 표시한다.
            press(p.SDLK_m)
            room.phase_time = PHASE_SECONDS-.01
            press(ticks=1)
            assert room.state == 'shifting' and room.map_open
            while room.state == 'shifting':
                app.update(.05)
            assert room.map_open and room.visited is room.visited_by_phase[room.phase]
            frame('08-phase-map.png')
            press(p.SDLK_m)

            # 칼날방에서 전환 경계를 밟아도 외부 소수 좌표와 자원을 유지한다.
            room.player.x, room.player.y = room.trap_cell[0]+.4, room.trap_cell[1]+.6
            saved = room.player.x, room.player.y, room.player.direction
            press(p.SDLK_f)
            assert room.state == 'trap'
            room.phase_time = PHASE_SECONDS-.01
            hp_stamina = room.player.hp, room.player.stamina
            press(w, ticks=1)
            assert room.state == 'shifting' and not app.held
            assert (room.player.x, room.player.y, room.player.direction) == saved
            while room.state == 'shifting':
                app.update(.05)
            assert (room.player.x, room.player.y, room.player.direction) == saved
            assert (room.player.hp, room.player.stamina) == hp_stamina
            frame('09-trap-exact-return.png')

            # 중간 교체의 앞·뒤에서 R: 새 판에는 이전 교체·연출·관찰 캐시가 남지 않는다.
            for after_swap in (False, True):
                room = app.game
                room.phase_time = PHASE_SECONDS-.01
                app.update(.02)
                while after_swap and room.shift_elapsed <= SHIFT_SWAP_AT:
                    app.update(.05)
                run = room.run_number
                press(p.SDLK_r)
                fresh = app.game
                assert fresh is not room and fresh.run_number == run+1
                assert fresh.player.gait_distance == fresh.player.gait_phase == 0
                assert fresh.player_clips is app.view.player_catalog['clips']
                assert fresh.phase == fresh.layout_phase == (run+1) % 3
                assert not fresh.shift_cells and fresh.layout_revision == 0 and not fresh.phase_warning
                for _ in range(32):
                    app.update(.025)
                assert fresh.state == 'explore' and fresh.layout_revision == 0
                assert fresh.player.hp == fresh.player.stamina == 100
                assert not fresh.player.torch and not fresh.fountain_used
                assert fresh.grid == fresh.maze_layouts.grids[fresh.phase]
                assert not app.held
                app.view.draw(fresh)
                assert app.view.light_game is fresh and set(app.view.discovery) == fresh.observed
            # 새로 닫힌 벽 뒤의 옛 시야·광원 캐시를 지우고, SDL 이동도 차단한다.
            room = Game(g.seed, player_clips=app.view.player_catalog['clips'])
            app.game = room
            next_grid = room.maze_layouts.grids[1]
            closed = next((x, y) for y, row in enumerate(room.grid) for x, wall in enumerate(row)
                          if not wall and next_grid[y][x])
            x, y = closed
            dx, dy = next((dx, dy) for dx, dy in DIRECTIONS
                          if not room.solid(x-dx, y-dy) and not room.solid(x+dx, y+dy))
            near, behind = (x-dx, y-dy), (x+dx, y+dy)
            room.player.x, room.player.y = near[0]+.5, near[1]+.5
            room.player.torch = True
            room.update_visibility()
            assert behind in room.visible
            app.view.draw(room)
            assert behind in app.view.discovery
            room.phase_time = PHASE_SECONDS-.01
            app.update(.02)
            while room.state == 'shifting':
                app.update(.05)
            assert closed in room.visible and behind not in room.visible
            assert behind not in room.observed and behind not in room.visited
            walk_tile(*diagonals[DIRECTIONS.index((dx, dy))])
            assert (int(room.player.x), int(room.player.y)) == near
            assert room.can_stand(room.player.x, room.player.y)
            frame('10-closed-wall-blocks.png')
            assert behind not in app.view.discovery and behind not in app.view.exposure
            print('PASS: SDL shift, fixed HUD, one-shot sounds, opened-passage walking, phase map, trap return and restart before/after swap.')
        finally:
            app.audio.step, app.audio.blade = original_step, original_blade
            app.game = g
            app.held.clear()

    if g.reveal_all:
        press(p.SDLK_v)
    for _ in range(20):
        app.update(.025)
    snapshot('01-directional-view.png')
    check_controls()
    check_attack_render()
    check_puzzle_input()
    from checks_gait import check_gait_view
    check_gait_view(app.view)
    app.view.draw(g)
    start_screen = app.view.world(player.x, player.y)
    walk_path(g.spawn, g.torch_cell)
    assert all(isclose(position, cell+.5) for position, cell in zip((player.x, player.y), g.torch_cell))
    assert player.state == 'walk'
    press(p.SDLK_f)
    assert player.torch
    app.view.draw(g)
    assert app.view.world(player.x, player.y) != start_screen
    app.view.capture(output/'01b-quarter-moved.png')

    press(p.SDLK_v)
    assert g.reveal_all
    snapshot('02-quarter-overview.png')
    press(p.SDLK_m)
    assert g.map_open
    snapshot('03-visited-map.png')
    press(p.SDLK_m)
    press(p.SDLK_v)
    assert not g.map_open and not g.reveal_all

    # Follow the real corridor from the torch to A using regular movement input.
    walk_path(g.torch_cell, g.trap_cell)
    before = player.x, player.y
    assert all(isclose(position, cell+.5) for position, cell in zip(before, g.trap_cell))
    press(p.SDLK_f)
    assert g.state=='trap'
    fixed_center = project_trap(g, 0, 0, TRAP_LENGTH)
    press(w, ticks=20)
    closer = project_trap(g, 0, 0, TRAP_LENGTH)
    assert g.trap_progress > 0 and (player.x, player.y) == before
    assert closer[0] == fixed_center[0] and closer[1] > fixed_center[1]
    snapshot('04-first-person-trap.png')
    press(a, ticks=4)
    left_x = g.trap_x
    assert left_x < 0
    press(d, ticks=12)
    assert g.trap_x > left_x
    forward_progress = g.trap_progress
    press(s, ticks=12)
    assert g.trap_progress < forward_progress
    press(p.SDLK_ESCAPE)
    assert g.state=='explore' and (player.x, player.y) == before
    snapshot('05-quarter-return-a.png')

    press(p.SDLK_f)
    assert g.state == 'trap'
    app.view.draw(g)
    press(w, ticks=300)
    assert g.state == 'explore' and g.trap_completed and g.trap_exit in g.visited
    assert (player.x, player.y) == (g.trap_exit[0]+.5, g.trap_exit[1]+.5)
    snapshot('06-quarter-return-b.png')
    check_phase_render()
    app.save_status()
    (output/'render_checks.json').write_text(json.dumps({'native_renderer':'pico2d + SDL2',
        'window_size':[LW*SCALE,LH*SCALE],'logical_quarter_view':[LW,LH],
        'sdl_F_torch':True,'sdl_V_overview':True,'sdl_M_map':True,
        'sdl_WASD_move':True,'sdl_WASD_diagonal_walk_run':True,
        'sdl_east_walk_16_frames':True,'sdl_east_idle_on_release':True,
        'sdl_north_walk_16_frames':True,'sdl_south_walk_16_frames':True,'sdl_west_walk_16_frames':True,
        'sdl_cardinal_idle_on_release':True,
        'sdl_opposite_keys_cancel':True,'sdl_arrows_inactive':True,'sdl_straight_wall_stop':True,
        'sdl_equal_projected_speed':True,'sdl_30_60_120_variable_dt':True,'sdl_swept_corner_collision':True,
        'sdl_trap_WASD':True,
        'sdl_F_trap':True,'sdl_W_fixed_first_person':True,
        'sdl_Esc_exact_return':True,'sdl_W_shortcut_arrival':True,
        'sdl_phase_shift':True,'fixed_hud_during_shift':True,'one_shot_phase_sounds':True,
        'sdl_walk_new_passage':True,'sdl_phase_map':True,'sdl_phase_trap_return':True,
        'sdl_closed_wall_blocks':True,'new_wall_hides_old_visibility_cache':True,
        'sdl_attack_direction_hit_and_restart':True,
        'sdl_attack_233_466ms_double_hit_all_directions':True,
        'sdl_animated_dagger':True,
        'sdl_R_before_after_swap':True},indent=2),encoding='utf-8')
