"""python -m SourceCode.main --smoke에서 실행하는 실제 SDL 입력·화면 검사."""
import json
import ctypes
from bisect import bisect_right
from itertools import accumulate
from unittest.mock import patch
import pico2d.pico2d as p
from SourceCode.maze_model import DIRECTIONS, TRAP_LENGTH, Game, shortest_path
from SourceCode.maze_model import PHASE_SECONDS, PHASE_WARNING_SECONDS, SHIFT_SWAP_AT
from SourceCode.maze_model import WALK_SPEED, RUN_SPEED, PLAYER_HALF_SIZE
from SourceCode.maze_model import GUARD_DAMAGE
from SourceCode.game_view import LW, LH, SCALE, project
from SourceCode.game_view import PUZZLE_OFFSET_X, PHASE_HUD_RECT
from SourceCode.trap_view import project as project_trap
from SourceCode.mouse_maze import BOARD, MAZE, START_CELL, GOAL_CELL, cell_center
from .mouse_maze_fixture import legacy_mouse_maze
from SourceCode.ui_layout import logical_to_window


def inject_key(key, down=True):
    event=p.SDL_Event()
    event.type=p.SDL_KEYDOWN if down else p.SDL_KEYUP
    event.key.keysym.sym=key
    event.key.repeat=0
    assert p.SDL_PushEvent(event)==1


def regain_focus(app):
    event = p.SDL_Event()
    event.type = p.SDL_WINDOWEVENT
    event.window.event = p.SDL_WINDOWEVENT_FOCUS_GAINED
    assert p.SDL_PushEvent(event)==1
    app.handle_events()


def inject_mouse(event_type, point, held=True):
    event = p.SDL_Event()
    event.type = event_type
    width, height = ctypes.c_int(), ctypes.c_int()
    p.SDL_GetWindowSize(p.window, ctypes.byref(width), ctypes.byref(height))
    output_width,output_height = ctypes.c_int(),ctypes.c_int()
    assert p.SDL_GetRendererOutputSize(p.renderer,ctypes.byref(output_width),ctypes.byref(output_height)) == 0
    x,y = logical_to_window(point,(width.value,height.value),(output_width.value,output_height.value))
    if event_type == p.SDL_MOUSEMOTION:
        event.motion.x, event.motion.y = x, y
        event.motion.state = p.SDL_BUTTON_LMASK if held else 0
    else:
        event.button.x, event.button.y = x, y
        event.button.button = p.SDL_BUTTON_LEFT
    assert p.SDL_PushEvent(event) == 1


def run(app):
    from .check_boulder_render import run as check_boulder_render
    check_boulder_render(app)
    from .check_game_hud import run as check_game_hud
    check_game_hud(app)
    from .check_ui_layout import run as check_ui_layout
    check_ui_layout(app)
    from .check_connection_render import run as check_connection_render
    check_connection_render(app)
    from .check_waypoint_render import run as check_waypoint_render
    check_waypoint_render(app)
    from .check_shortcut_render import run as check_shortcut_render
    check_shortcut_render(app)
    output = app.output
    from math import ceil, hypot, isclose

    g=app.game
    player = g.player
    step = .025
    w, a, s, d = p.SDLK_w, p.SDLK_a, p.SDLK_s, p.SDLK_d
    grid_keys = (a, w, s, d)  # DIRECTIONS order
    north, south, west, east = (w, d), (s, a), (w, a), (s, d)

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
        path = shortest_path(app.game.grid, start, end)
        for (x, y), (nx, ny) in zip(path, path[1:]):
            walk_tile(grid_keys[DIRECTIONS.index((nx-x, ny-y))])

    def click_attack():
        event = p.SDL_Event()
        event.type = p.SDL_MOUSEBUTTONDOWN
        event.button.button = p.SDL_BUTTON_LEFT
        assert p.SDL_PushEvent(event) == 1
        app.handle_events()

    def check_puzzle_approaches():
        view = app.view
        room = Game(117, 2, player_clips=view.player_catalog['clips'])
        app.game = room
        wall, near, far = room.puzzle_gate
        assert room.phase == 2 and (near, far) == ((17, 5), (17, 7))
        hint = 'F 퍼즐'
        interact = p.SDLK_f

        def HUD_text():
            with patch.object(view, 'text', wraps=view.text) as text:
                view.draw(room)
            return {call.args[0] for call in text.call_args_list}

        try:
            for approach, position in ((near, (17.5, 5.5)), (far, (17.28, 7.21))):
                room.player.x, room.player.y = position
                room.update_visibility()
                assert wall in room.visible and approach in room.visible
                with patch.object(view, 'badge', wraps=view.badge) as badge:
                    assert hint in HUD_text()
                assert not [call for call in badge.call_args_list if call.args[0] == 'P'], 'active P must have one F prompt'

                press(interact)
                assert room.state == 'puzzle' and hint not in HUD_text()
                press(p.SDLK_ESCAPE)
                assert room.state == 'explore'

            press(p.SDLK_m)
            press(interact)
            assert room.map_open and room.state == 'explore' and hint not in HUD_text()
            press(p.SDLK_m)

            room.puzzle_reserved_phase = room.next_phase
            press(interact)
            assert room.state == 'explore' and hint not in HUD_text()
            room.puzzle_reserved_phase = None
            room.puzzle_open = True
            room.grid[wall[1]][wall[0]] = 0
            press(interact)
            assert room.state == 'explore' and hint not in HUD_text()
            print('PASS: SDL dawn puzzle P and F at both sides, exact far position, Esc, map, reserved and open gates.')
        finally:
            app.game = g
            app.held.clear()

    @legacy_mouse_maze
    def check_puzzle_input():
        room = Game(117, player_clips=app.view.player_catalog['clips'])
        app.game = room
        wall, near, far = room.puzzle_gate
        left, top, size = BOARD
        center = cell_center
        start, corner, goal = center(*START_CELL), center(3, 1), center(*GOAL_CELL)
        below = center(3, 3)
        preview = (corner[0], corner[1]+12)
        resized = (corner[0], corner[1]+21)
        down, motion, up = p.SDL_MOUSEBUTTONDOWN, p.SDL_MOUSEMOTION, p.SDL_MOUSEBUTTONUP

        def mouse(kind, point, held=True):
            inject_mouse(kind, (point[0]+PUZZLE_OFFSET_X,point[1]), held)
            app.handle_events()

        def puzzle_pixels(rect):
            rect = p.SDL_Rect(rect.x+PUZZLE_OFFSET_X*SCALE,rect.y,rect.w,rect.h)
            pixels = (ctypes.c_uint32*(rect.w*rect.h))()
            app.view.draw(room)
            app.view.select_readback_target()
            try:
                assert p.SDL_RenderReadPixels(p.renderer, rect, p.SDL_PIXELFORMAT_RGBA32,
                                              pixels, rect.w*4) == 0
                return pixels
            finally:
                p.SDL_SetRenderTarget(p.renderer, None)

        def check_route(active, inactive):
            def at(point):
                rect = p.SDL_Rect(point[0]*SCALE, point[1]*SCALE, 1, 1)
                return puzzle_pixels(rect)[0]

            for point, should_change in [(point, True) for point in active]+[(point, False) for point in inactive]:
                foreground = at(point)
                with patch.object(app.view, 'puzzle_route'):
                    background = at(point)
                assert (foreground != background) == should_change, point

        def floor_pixels(*cells):
            board = p.SDL_Rect(left*SCALE, top*SCALE, len(MAZE[0])*size*SCALE, len(MAZE)*size*SCALE)
            pixels = puzzle_pixels(board)
            samples = []
            for x, y in cells:
                cx, cy = center(x, y)
                # Sample the same point within each tile, away from its trace, marker and label.
                index = ((cy-top-8)*board.w+cx-left+8)*SCALE
                samples.append(pixels[index])
            return tuple(samples)

        try:
            walk_path(room.spawn, near)
            assert (int(room.player.x), int(room.player.y)) == near
            press(p.SDLK_f)
            assert room.state == 'puzzle'
            app.view.draw(room)
            press(ticks=12)
            check_route([start], [corner])
            first_floor = START_CELL, (2, 1)
            bend_floors = (3, 1), (3, 2), (3, 3)
            fixed_tiles = (4, 1), GOAL_CELL
            initial_start, initial_next = floor_pixels(*first_floor)
            bend_baseline = floor_pixels(*bend_floors)
            fixed_baseline = floor_pixels(*fixed_tiles)
            app.view.capture(output/'puzzle-preview.png')
            press(w, p.SDLK_m, ticks=4)
            assert room.phase_time > 0 and not room.map_open and not app.held
            mouse(down, start)
            mouse(motion, (start[0]+size//2, start[1]))
            middle_start, middle_next = floor_pixels(*first_floor)
            mouse(motion, center(2, 1))
            moved_start, moved_next = floor_pixels(*first_floor)
            # SDL's RGBA32 exposes the red byte first, and the gold tint increases it.
            assert (moved_start & 255) < (middle_start & 255) < (initial_start & 255)
            assert (initial_next & 255) < (middle_next & 255) < (moved_next & 255)
            mouse(motion, (167, 207))  # 입구 안쪽의 벽을 가로지르지 않는다.
            assert room.puzzle.hit_wall and room.puzzle.cursor == center(2, 1)
            assert floor_pixels(*first_floor) == (moved_start, moved_next)
            mouse(motion, center(3, 2))
            assert room.puzzle.hit_wall and room.puzzle.cursor == center(2, 1)
            rounded = ((170, 185), (175, 186), (179, 190), (182, 197), (182, 199),
                       (182, 202), (182, 209), (182, 219), (182, 226))
            previous = sum(room.puzzle.cursor)
            for point in rounded:
                mouse(motion, point)
                x, y = room.puzzle.cursor
                assert not room.puzzle.hit_wall and x+y > previous, (point, (x, y))
                assert (151 <= x <= 185 and y == 185) or (x == 185 and 185 <= y <= 226)
                previous = x+y
            assert room.puzzle.cursor == (185, 226) and room.puzzle.cell == (3, 2)
            check_route([(164, 185), corner, (185, 226)], [(176, 198), (193, 226)])
            linked_start, linked_next = floor_pixels(*first_floor)
            assert linked_start == moved_start
            assert (initial_next & 255) < (linked_next & 255) < (moved_next & 255)
            past_corner, active_bend, following_bend = floor_pixels(*bend_floors)
            assert (past_corner & 255) > (bend_baseline[0] & 255)
            assert (active_bend & 255) > (bend_baseline[1] & 255)
            assert (following_bend & 255) > (bend_baseline[2] & 255)
            assert floor_pixels(*fixed_tiles) == fixed_baseline
            mouse(motion, corner)
            assert room.puzzle.path == [START_CELL, (2, 1), (3, 1)]
            route_floors = (*first_floor, *bend_floors)
            glow_before_wall = floor_pixels(*route_floors)
            for invalid in (goal, center(5, 3), (left-1, corner[1])):
                mouse(motion, invalid)
                assert room.puzzle.hit_wall and room.player.hp == 100
                assert room.puzzle.path == [START_CELL, (2, 1), (3, 1)]
                assert room.puzzle.dragging and room.puzzle.cursor == corner
            assert floor_pixels(*route_floors) == glow_before_wall
            mouse(motion, (preview[0]+4, preview[1]))
            assert room.puzzle.cell == (3, 1) and room.puzzle.cursor == preview
            assert room.puzzle.preview_cell == (3, 2) and not room.puzzle.hit_wall
            mid = (corner[0]-size//2, corner[1])
            check_route([mid, preview], [(preview[0]+8, preview[1]), center(3, 2)])
            app.view.capture(output/'puzzle-dragged.png')
            try:
                p.SDL_SetWindowSize(p.window, 960, 600)
                mouse(motion, (resized[0]-4, resized[1]))
                assert room.puzzle.cell == (3, 1) and room.puzzle.cursor == resized
                check_route([mid, resized], [(resized[0]-8, resized[1]), center(3, 2)])
            finally:
                p.SDL_SetWindowSize(p.window, LW*SCALE, LH*SCALE)
            paused_glow = floor_pixels(*route_floors)
            mouse(up, goal)
            mouse(motion, below, False)
            assert room.puzzle.cell == (3, 1) and not room.puzzle.dragging
            assert room.puzzle.cursor == resized and room.puzzle.preview_cell == (3, 2)
            check_route([mid, resized], [center(3, 2)])
            assert floor_pixels(*route_floors) == paused_glow
            mouse(down, goal)
            assert not room.puzzle.dragging
            mouse(up, goal)
            mouse(down, resized)
            assert room.puzzle.dragging
            assert floor_pixels(*route_floors) == paused_glow
            lost = p.SDL_Event()
            lost.type = p.SDL_WINDOWEVENT
            lost.window.event = p.SDL_WINDOWEVENT_FOCUS_LOST
            assert p.SDL_PushEvent(lost) == 1
            app.handle_events()
            mouse(motion, below)
            assert room.puzzle.cell == (3, 1) and not room.puzzle.dragging
            regain_focus(app)
            assert room.puzzle.cursor == resized and room.puzzle.preview_cell == (3, 2)
            mouse(up, resized)
            mouse(down, resized)
            press(p.SDLK_ESCAPE)
            assert app.running and room.state == 'explore' and room.puzzle.cell == (3, 1)
            assert not room.puzzle.dragging and room.puzzle.cursor == resized
            mouse(up, resized)
            press(p.SDLK_f)
            assert room.state == 'puzzle'
            assert floor_pixels(*route_floors) == paused_glow
            mouse(down, resized)
            room.guard = (near[0], near[1]-2)
            before_hit = room.player.hp
            saved_path = room.puzzle.path[:]
            for _ in range(100):
                app.update(step)
                if room.state != 'puzzle':
                    break
            assert room.state == 'explore' and room.player.hp == before_hit-GUARD_DAMAGE
            assert not room.puzzle.dragging and room.puzzle.path == saved_path
            assert room.puzzle.cursor == resized and room.puzzle.preview_cell == (3, 2)
            assert app.puzzle_mouse_held and not app.held
            mouse(motion, below)
            mouse(down, below)
            assert room.puzzle.path == saved_path and not room.attack_hits_ms
            mouse(up, below)
            press(p.SDLK_f)
            assert room.state == 'puzzle' and room.puzzle.cursor == resized
            mouse(down, resized)
            mouse(motion, corner)
            active_corner = floor_pixels((3, 1))[0]
            mouse(motion, (corner[0]-size//4, corner[1]))
            early_retraction = floor_pixels((3, 1))[0]
            mouse(motion, mid)
            assert room.puzzle.cell == (3, 1) and room.puzzle.preview_cell == (2, 1)
            retracting_corner = floor_pixels((3, 1))[0]
            assert ((bend_baseline[0] & 255) < (retracting_corner & 255) < (past_corner & 255)
                    < (early_retraction & 255) < (active_corner & 255))
            check_route([start, mid], [corner, resized])
            mouse(motion, center(2, 1))
            assert room.puzzle.cell == (2, 1) and room.puzzle.path == [START_CELL, (2, 1)]
            assert floor_pixels(*bend_floors) == bend_baseline
            assert floor_pixels(*first_floor) == (linked_start, moved_next)
            check_route([start], [mid, corner, resized])
            for point, projected in (
                    (corner, corner), ((185, 247), (185, 247)), ((190, 254), (190, 253)),
                    ((247, 253), (247, 253)), ((253, 259), (253, 253)),
                    ((269, 244), (253, 244)), ((253, 198), (253, 198)),
                    ((236, 184), (253, 185)), ((252, 181), (253, 185))):
                mouse(motion, point)
                assert not room.puzzle.hit_wall and room.puzzle.cursor == projected, (point, room.puzzle.cursor)
                if point in ((190, 254), (253, 259), (269, 244)):
                    for invalid in ((point[0], 270), center(6, 1)):
                        mouse(motion, invalid)
                        assert room.puzzle.hit_wall and room.puzzle.cursor == projected
            check_route([(185, 253), (220, 253), (253, 244), (253, 185)],
                        [(253, 270), (269, 244), (236, 184), center(6, 1)])
            mouse(motion, (264, 192))
            assert room.puzzle.cursor == (264, 185) and room.puzzle.preview_cell == (6, 1)
            check_route([(253, 211), (259, 185), (264, 185)], [(264, 192), center(6, 1)])
            mouse(motion, (264, 194))
            assert not room.puzzle.hit_wall and room.puzzle.cursor == (264, 185)
            mouse(motion, (304, goal[1]))
            assert room.state == 'explore' and room.puzzle_reserved_phase == 1 and room.solid(*wall)
            assert room.puzzle.path == [START_CELL] and not room.puzzle.dragging
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
            walk_tile(a)
            assert (int(room.player.x), int(room.player.y)) == wall
            walk_tile(a)
            assert (int(room.player.x), int(room.player.y)) == far
            press(p.SDLK_r)
            fresh = app.game
            assert fresh.run_number == 1 and fresh.solid(*fresh.puzzle_gate[0])
            assert not fresh.puzzle_open and fresh.puzzle_reserved_phase is None
            assert fresh.puzzle.cell == START_CELL and not fresh.puzzle.dragging
            print('PASS: SDL moving glow and retained trail, rounded corners, projected route at two sizes, backtracking, resume, opening and R reset.')
        finally:
            app.game = g
            app.held.clear()
            app.puzzle_mouse_held = False

    def check_dagger_timeline(room):
        view = app.view
        commands = (('n', north, (-1, -1)), ('s', south, (1, 1)),
                    ('w', west, (-1, 1)), ('e', east, (1, -1)),
                    ('nw', (w,), (-1, 0)), ('ne', (d,), (0, -1)),
                    ('sw', (a,), (0, 1)), ('se', (s,), (1, 0)))
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
        room.update_guard = lambda _dt: None
        app.game = room
        try:
            press(a, ticks=1)
            click_attack()
            clip = room.player_clips['attack-sw']
            assert room.attack_facing == 'sw' and room.guard_hp == 3
            assert app.view.player_frame(room) == clip['frames'][0]['rect']
            press(d, ticks=1)
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
                press(d, timesteps=[.05]*14+[.026])
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
            press(a, ticks=1)
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
        room.guard_hp = 0
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
            actor.x, actor.y = 6.5, 6.5
            assert not any(room.close_to(cell) for cell in
                           (room.torch_cell, room.trap_cell, room.fountain, room.exit))
            assert not room.puzzle_available()
            inject_key(d)
            app.handle_events()
            app.update(step)
            before_f = actor.x, actor.y
            press(p.SDLK_f, ticks=1)
            assert room.state == 'explore' and not actor.torch and d in app.held
            assert actor.x == before_f[0] and isclose(actor.y-before_f[1], -2.5*step)
            inject_key(d, down=False)
            app.handle_events()
            for key, (sx, sy, facing) in zip(grid_keys,
                    ((-1, 1, 0), (-1, -1, 1), (1, 1, 2), (1, -1, 3))):
                check_move((key,), sx, sy, facing)
                check_move((key, p.SDLK_LSHIFT), sx, sy, facing, running=True)
            for keys, sx, sy, facing in ((north, 0, -1, 3), (west, -1, 0, 1),
                                         (south, 0, 1, 0), (east, 1, 0, 2)):
                actor.direction = facing
                check_move(keys, sx, sy, facing)
                check_move(keys, sx, sy, facing)

            # 동쪽 동시 입력은 현재 진행 방향이 두 축 중 하나면 그 방향을 유지한다.
            check_move((d,), 1, -1, 3)
            check_move(east, 1, 0, 3)
            check_move((w, s, d), 1, -1, 3)
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
            commands = ((north, 0, -1), (west, -1, 0), (south, 0, 1), (east, 1, 0),
                        ((w,), -2, -1), ((d,), 2, -1), ((a,), -2, 1), ((s,), 2, 1))
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

            # 한 칸 통로에서 벽을 향한 동시 입력은 벽 직전에 멈춘다.
            room.reveal_all = False
            room.grid = [[int(x != 15) for x in range(len(row))] for row in room.grid]
            clearance = .5-PLAYER_HALF_SIZE
            for times in schedules.values():
                for running in (False, True):
                    for keys, gx, gy in ((north, -1, -1), (west, -1, 1),
                                         (south, 1, 1), (east, 1, -1)):
                        reset()
                        chord = (*keys, p.SDLK_LSHIFT) if running else keys
                        press(*chord, timesteps=times)
                        assert isclose(actor.x-15.5, gx*clearance, abs_tol=2e-7)
                        assert isclose(actor.y-11.5, gy*clearance, abs_tol=2e-7)
                        assert actor.state == 'idle' and room.can_stand(actor.x, actor.y)
                        stopped = actor.x, actor.y
                        press(*chord, ticks=8)
                        assert (actor.x, actor.y) == stopped and actor.state == 'idle'
                    # 벽에 거의 닿아 있어도 통로와 평행한 단일 키 입력은 계속 이동한다.
                    for key, sign in ((a, 1), (d, -1)):
                        reset(x=15.79-1e-7)
                        chord = (key, p.SDLK_LSHIFT) if running else (key,)
                        press(*chord, timesteps=times)
                        assert actor.x == 15.79-1e-7
                        speed = RUN_SPEED if running else WALK_SPEED
                        assert isclose(actor.y-11.5, sign*speed/hypot(*project(1, 0))*sum(times))
                        assert room.can_stand(actor.x, actor.y)

            # 끝점은 안전하지만 중간에 모퉁이를 스치는 경로도 4방향 모두 막아야 한다.
            for turns, keys in enumerate((south, west, north, east)):
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
                    press(*keys, timesteps=times)
                    assert isclose(actor.x-start_x, gx*.01, abs_tol=2e-7)
                    assert isclose(actor.y-start_y, gy*.01, abs_tol=2e-7)
                    assert room.can_stand(actor.x, actor.y) and actor.state == 'idle'

            # L자 통로의 모서리를 가로지르지 않고, 통로 축을 따라 꺾어서 통과한다.
            room.grid = [[int(not (x == 15 or y == 11)) for x in range(len(row))] for y, row in enumerate(room.grid)]
            reset(15.5, 10.5)
            press(*south, ticks=16)
            assert actor.x < 15.8 and actor.y < 10.8
            reset(15.5, 10.5)
            walk_tile(a)
            walk_tile(s)
            assert isclose(actor.x, 16.5) and isclose(actor.y, 11.5)
            assert room.can_stand(actor.x, actor.y)

            # 실제 입력으로 상하좌우 자세와 걷기 0.8초 주기를 검사한다.
            room.grid = [[0]*len(row) for row in room.grid]
            walk_schedules = {'20 FPS': [.05]*16}
            walk_schedules.update({name: times[:round(len(times)*.8)] for name, times in schedules.items()})
            cardinal = ((north, 'n', 'north', 0, -1), (south, 's', 'south', 0, 1),
                        (west, 'w', 'west', -1, 0), (east, 'e', 'east', 1, 0))
            for keys, facing, label, sx, sy in cardinal:
                walk_name, idle_name = f'walk-{facing}', f'idle-{facing}'
                walk = clips[walk_name]
                assert len(walk['frames']) == 16 and walk['durations_ms'] == [50]*16
                offset = walk['phase_offset_frames']
                for schedule, times in walk_schedules.items():
                    reset()
                    actor.gait_phase = actor.gait_distance = 0.
                    for key in keys:
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
                    for key in keys:
                        inject_key(key, down=False)
                    app.handle_events()
                    press(ticks=1)
                    assert room.locomotion_clip_name('idle') == idle_name
                    assert view.player_frame(room) == clips[idle_name]['frames'][0]['rect']
                print(f'PASS: {walk_name} 16 frames in 0.8s at 20/30/60/120 FPS and variable dt, projected speed and {idle_name} on release.')
            print('PASS: four orthogonal screen chords select their cardinal idle poses on release.')
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

    def check_shortcut_visibility():
        view = app.view
        original_seed = app.seed

        def body_pixels(room, target, scale):
            x, y = view.world(room.player.x, room.player.y)
            pivot_x, pivot_y = view.player_catalog['pivot']
            width, height = view.player_catalog['frame_size']
            rect = p.SDL_Rect((round(x)-pivot_x)*scale, (round(y)-pivot_y)*scale,
                              width*scale, height*scale)
            pixels = (ctypes.c_uint32*(rect.w*rect.h))()
            if target is view.display:
                view.select_readback_target()
            else:
                p.SDL_SetRenderTarget(p.renderer, target)
            try:
                assert p.SDL_RenderReadPixels(p.renderer, rect, p.SDL_PIXELFORMAT_RGBA32, pixels, rect.w*4) == 0
                return pixels[:]
            finally:
                p.SDL_SetRenderTarget(p.renderer, None)

        def coverage(room, silhouette=True):
            def capture():
                p.SDL_SetRenderTarget(p.renderer, view.logical)
                view.quarter(room)
                return body_pixels(room, view.logical, 1)

            with patch.object(view, 'player_silhouette'), patch.object(view, 'player'):
                background = capture()
            if silhouette:
                foreground = capture()
            else:
                with patch.object(view, 'player_silhouette'):
                    foreground = capture()
            return sum(a != b for a, b in zip(foreground, background))

        try:
            app.seed = 117
            app.game = Game(117, player_clips=view.player_catalog['clips'])
            for run, exit_cell, resting, facing in (
                    (0, (20, 11), (20.1875, 11+PLAYER_HALF_SIZE), 'ne'),
                    (1, (25, 7), (25.24844235, 7.23167184), 'e')):
                if run:
                    press(p.SDLK_r)
                room = app.game
                actor = room.player
                assert room.run_number == run and room.trap_exit == exit_cell and not actor.torch
                actor.x, actor.y = room.trap_cell[0]+.5, room.trap_cell[1]+.5
                press(p.SDLK_f)
                assert room.state == 'trap'
                view.draw(room)
                press(w, ticks=300)
                assert room.state == 'explore' and room.trap_completed and not actor.torch
                assert (actor.x, actor.y) == (exit_cell[0]+.5, exit_cell[1]+.5)
                view.draw(room)
                assert any(pixel & 0xffffff for pixel in body_pixels(room, view.display, SCALE)), 'black return frame'

                if run:
                    press(*north, timesteps=[.025, .025, .025, .018])
                    press(*east, timesteps=[.006])
                else:
                    press(w, ticks=5)
                    press(d, ticks=5)
                press(ticks=1)
                assert all(isclose(actual, expected, abs_tol=1e-6)
                           for actual, expected in zip((actor.x, actor.y), resting))
                assert actor.state == 'idle' and actor.screen_facing == facing
                assert room.can_stand(actor.x, actor.y) and room.solid(exit_cell[0], exit_cell[1]-1)
                pose = actor.x, actor.y, actor.state, actor.screen_facing
                occluded = coverage(room, silhouette=False)
                with patch.object(view, 'shortcut'):
                    without_arch = coverage(room, silhouette=False)
                readable = coverage(room)
                assert without_arch > occluded+80 and readable > occluded+150 and readable >= 300, (
                    run, occluded, without_arch, readable)
                assert (actor.x, actor.y, actor.state, actor.screen_facing) == pose
                print(f'PASS: B{exit_cell} post-return body pixels {occluded} → {readable} with silhouette.')
        finally:
            app.game, app.seed = g, original_seed
            app.held.clear()

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
            samples = []
            app.view.select_readback_target()
            try:
                x,y,w,h = PHASE_HUD_RECT
                # 상태 글자 주변은 투명하므로 바의 불투명 트랙만 비교한다.
                for x,y,w,h in ((x+4,y+4,w-8,h-8),(40,353,84,6),(40,368,84,4)):
                    rect = p.SDL_Rect(x*SCALE,y*SCALE,w*SCALE,h*SCALE)
                    pixels = (ctypes.c_ubyte*(rect.w*rect.h*4))()
                    assert p.SDL_RenderReadPixels(p.renderer,rect,p.SDL_PIXELFORMAT_RGBA32,pixels,rect.w*4) == 0
                    samples.append(bytes(pixels))
                return b''.join(samples)
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
            walk_tile(grid_keys[direction])
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
            walk_tile(grid_keys[DIRECTIONS.index((dx, dy))])
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
    check_puzzle_approaches()
    check_puzzle_input()
    from .checks_gait import check_gait_view
    check_gait_view(app.view)
    app.view.draw(g)
    start_screen = app.view.world(player.x, player.y)
    walk_path(g.spawn, g.torch_cell)
    assert all(isclose(position, cell+.5) for position, cell in zip((player.x, player.y), g.torch_cell))
    assert player.state == 'walk'
    torch_next = shortest_path(g.grid, g.torch_cell, g.trap_cell)[1]
    torch_step = tuple(end-start for start, end in zip(g.torch_cell, torch_next))
    torch_key = grid_keys[DIRECTIONS.index(torch_step)]
    inject_key(torch_key)
    app.handle_events()
    before_f = player.x, player.y
    press(p.SDLK_f, ticks=1)
    assert g.state == 'explore' and player.torch and torch_key in app.held
    assert all(isclose(end-start, direction*2.5*step, abs_tol=1e-9)
               for start, end, direction in zip(before_f, (player.x, player.y), torch_step))
    inject_key(torch_key, down=False)
    app.handle_events()
    press(grid_keys[DIRECTIONS.index(tuple(-n for n in torch_step))], ticks=1)
    assert all(isclose(actual, expected) for actual, expected in zip((player.x, player.y), before_f))
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
    inject_key(w)
    app.handle_events()
    press(p.SDLK_f, ticks=4)
    assert g.state=='trap' and not app.held
    assert g.trap_progress == g.trap_velocity == 0
    inject_key(w, down=False)
    app.handle_events()
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
    assert (player.x, player.y) == (g.trap_exit[0]+.5,g.trap_exit[1]+.5)
    snapshot('06-quarter-return-b.png')
    check_shortcut_visibility()
    check_phase_render()
    app.save_status()
    (output/'render_checks.json').write_text(json.dumps({'native_renderer':'pico2d + SDL2',
        'window_size':[LW*SCALE,LH*SCALE],'logical_quarter_view':[LW,LH],
        'sdl_F_torch':True,'sdl_F_preserves_walk':True,'sdl_F_clears_on_transition':True,
        'sdl_V_overview':True,'sdl_M_map':True,
        'sdl_WASD_corridor_walk_run':True,'sdl_WASD_chord_screen_directions':True,
        'sdl_east_walk_16_frames':True,'sdl_east_idle_on_release':True,
        'sdl_north_walk_16_frames':True,'sdl_south_walk_16_frames':True,'sdl_west_walk_16_frames':True,
        'sdl_cardinal_idle_on_release':True,
        'sdl_opposite_keys_cancel':True,'sdl_arrows_inactive':True,'sdl_straight_wall_stop':True,
        'sdl_equal_projected_speed':True,'sdl_30_60_120_variable_dt':True,'sdl_swept_corner_collision':True,
        'sdl_trap_WASD':True,
        'sdl_F_trap':True,'sdl_W_forward_first_person':True,
        'sdl_Esc_exact_return':True,'sdl_W_trap_completion':True,
        'sdl_shortcut_return_visible_and_occlusion_assist':True,
        'sdl_phase_shift':True,'fixed_hud_during_shift':True,'one_shot_phase_sounds':True,
        'sdl_dawn_puzzle_both_approaches':True,
        'sdl_walk_new_passage':True,'sdl_phase_map':True,'sdl_phase_trap_return':True,
        'sdl_closed_wall_blocks':True,'new_wall_hides_old_visibility_cache':True,
        'sdl_attack_direction_hit_and_restart':True,
        'sdl_attack_233_466ms_double_hit_all_directions':True,
        'sdl_animated_dagger':True,
        'sdl_R_before_after_swap':True},indent=2),encoding='utf-8')
