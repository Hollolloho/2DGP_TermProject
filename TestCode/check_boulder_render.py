"""본게임의 실제 SDL 키 입력·C/D 표시·돌 장면과 복귀를 검사한다."""
import ctypes
from math import ceil, hypot, isclose
from unittest.mock import patch

import pico2d.pico2d as p
from SourceCode.maze_model import Game, WALK_SPEED, PHASE_SECONDS, project
from SourceCode.game_view import BOULDER_SIGN_HEIGHT
from BoulderPractice.boulder_practice import OBSTACLES
from .check_game_render import inject_key


def keys(app, desired=()):
    desired = set(desired)
    for key in app.held-desired:
        inject_key(key, False)
    for key in desired-app.held:
        inject_key(key)
    app.handle_events()


def press(app, key):
    inject_key(key)
    app.handle_events()
    inject_key(key, False)
    app.handle_events()


def step(app, dt=.02):
    app.update(dt)
    if app.smoke:
        app.audio.update(app.game)


def picture(app, name=None):
    app.view.draw(app.game, 50)
    if name:
        app.view.capture(app.output/'boulder'/name)


def pixels(app):
    previous = p.SDL_GetRenderTarget(p.renderer)
    app.view.select_readback_target()
    data = (ctypes.c_ubyte*(1280*800*4))()
    try:
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,1280*4) == 0
        return bytes(data)
    finally:
        p.SDL_SetRenderTarget(p.renderer,previous)


def labels(app):
    values = []
    original = app.view.text
    def text(value,*args,**kwargs):
        values.append(value)
        return original(value,*args,**kwargs)
    with patch.object(app.view,'text',side_effect=text):
        picture(app)
    return values


def map_badges(app):
    values = []
    original = app.view.badge
    def badge(value,*args,**kwargs):
        values.append(value)
        return original(value,*args,**kwargs)
    with patch.object(app.view,'badge',side_effect=badge):
        picture(app)
    return values


def check_warning_visibility(app):
    game, view = app.game, app.view
    calls = []
    original = view.image
    def image(name,rect,*args,**kwargs):
        if name == 'boulder-warning-wall':calls.append((rect,kwargs['tint']))
        return original(name,rect,*args,**kwargs)
    with (patch.object(view,'image',side_effect=image),
          patch.object(view,'hud_panel',wraps=view.hud_panel) as panel):
        picture(app)
        actual = pixels(app)
    hints = [call.args[0] for call in panel.call_args_list if call.args[0][2:] == (176,36)]
    assert len(hints) == 1
    _,player_y = view.world(game.player.x,game.player.y)
    assert hints[0][1]+hints[0][3] <= player_y-54, 'C hint overlaps the player head'
    assert len(calls) == 1
    (x,y,w,h),tint = calls[0]
    assert (w,h) == (24,30)
    asset = view.images['boulder-warning-wall']
    assert (asset.w,asset.h) == (192,240)
    anchor = view.world(9.02,7.5)
    assert isclose(x+95/8,anchor[0]) and isclose(y+171/8+BOULDER_SIGN_HEIGHT,anchor[1])
    light,brightness = view.terrain_light(game,*game.boulder_entry)
    assert tint == tuple(round(channel*brightness) for channel in light)
    with patch.object(view,'boulder_sign',lambda *args:None):
        picture(app)
        baseline = pixels(app)
    changed = [index//4 for index in range(0,len(actual),4) if actual[index:index+4] != baseline[index:index+4]]
    assert len(changed) > 200
    assert all(round(x)*2 <= point%1280 < (round(x)+24)*2 and
               round(y)*2 <= point//1280 < (round(y)+30)*2 for point in changed)
    # 카메라만 옮겨도 벽과 표지는 같은 화면 변위를 따른다.
    origin = view.origin
    view.camera = view.camera[0]+20,view.camera[1]+10
    calls.clear()
    with patch.object(view,'image',side_effect=image):
        picture(app,'01b-C-camera.png')
    shifted = calls[0][0]
    assert (shifted[0]-x,shifted[1]-y) == (view.origin[0]-origin[0],view.origin[1]-origin[1])
    assert shifted[:2] != (x,y)
    picture(app)
    print('PASS: wall sign is uniformly scaled to 24x30, rivet-mounted, lit with its wall and moves with the camera; real pixels stay inside the world sign.')


def check_sign_boundaries(app):
    original = app.game
    view = app.view
    try:
        app.game = game = Game(117,player_clips=view.player_catalog['clips'])
        game.player.x,game.player.y = 9.5,5.1
        game.update_visibility()
        picture(app)
        game.ui_time += .4
        with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
            texts = labels(app)
        assert not game.boulder_available() and sign.call_count == 1
        assert 'F 진입' not in texts and not any('즉사' in text for text in texts)
        assert view.boulder_sign_mount(game)[2] not in game.visible
        picture(app,'00-C-approach.png')
        # 앞쪽 플레이어는 표지 뒤에 그리지 않는다. 벽 -> 표지 -> 플레이어 순서다.
        game.player.y = 7.5
        game.update_visibility()
        order = []
        wall,sign,player = view.shifting_wall,view.boulder_sign,view.player
        def draw_wall(*args):
            if args[-2] == (8,7):order.append('wall')
            return wall(*args)
        def draw_sign(*args):
            order.append('sign')
            return sign(*args)
        def draw_player(*args):
            order.append('player')
            return player(*args)
        with (patch.object(view,'shifting_wall',side_effect=draw_wall),
              patch.object(view,'boulder_sign',side_effect=draw_sign),
              patch.object(view,'player',side_effect=draw_player)):
            picture(app,'01c-C-foreground-player.png')
        assert order == ['wall','sign','player']
        for seed,run in ((117,0),(120,0),(117,1)):
            app.game = hidden = Game(seed,run,player_clips=view.player_catalog['clips'])
            hidden.reveal_all = (seed,run) != (117,0)
            with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
                picture(app)
            assert sign.call_count == 0, 'sign leaked through unseen terrain or into another seed/run'
        app.game = game
        game.player.x,game.player.y = 7.5,7.5
        game.update_visibility()
        assert game.boulder_entry not in game.visible and not game.clear_line_to(9.02,7.5)
        with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
            picture(app,'01d-C-wall-occlusion.png')
        assert sign.call_count == 0
        print('PASS: C wall face/sign visible before F range, foreground depth order, solid-wall LOS and absent signs in unseen/unsupported seed/run.')
    finally:
        app.game = original
        app.release_input()
        picture(app)


def check_course(app):
    game = app.game
    if (game.seed,game.run_number,game.time) != (117,0,0.):
        app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    app.release_input()
    assert (game.player.x,game.player.y) == (10.5,1.5)
    picture(app)
    # 일반 실행의 초기 스폰에서 S 1칸 → A 2칸 → W 2칸 → A 3칸.
    tile_seconds = hypot(*project(1,0))/WALK_SPEED
    for key,count in ((p.SDLK_s,1),(p.SDLK_a,2),(p.SDLK_w,2),(p.SDLK_a,3)):
        ticks = ceil(count*tile_seconds/.02)
        keys(app,(key,))
        for _ in range(ticks):
            step(app,count*tile_seconds/ticks)
        keys(app)
    assert isclose(game.player.x,9.5,abs_tol=1e-7) and isclose(game.player.y,6.5,abs_tol=1e-7)
    assert game.boulder_available() and game.player.hp == 100
    texts = labels(app)
    assert any('즉사' in text for text in texts)
    assert any('5초' in text and '후방 추격' in text for text in texts)
    assert texts.count('F 진입') == 1
    assert not any('장애물' in text or '측면 출구로' in text for text in texts)
    check_warning_visibility(app)
    picture(app,'01-C-warning.png')
    press(app,p.SDLK_m)
    assert game.map_open and not game.boulder_available()
    assert 'C' in map_badges(app) and 'D' not in map_badges(app)
    picture(app,'02-C-map.png')
    press(app,p.SDLK_ESCAPE)
    assert not game.map_open and app.running
    keys(app,(p.SDLK_w,p.SDLK_LSHIFT,p.SDLK_q))
    press(app,p.SDLK_f)
    assert game.state == 'trap' and game.trap_kind == 'boulder' and not app.held
    room = game.boulder_room
    picture(app)
    assert max(pixels(app)[::4]) <= 1, 'room entry must use the main fade'
    for _ in range(16):
        step(app)
    texts = labels(app)
    assert any('돌 출발까지' in text for text in texts)
    assert not any('무적' in text or 'HP 100 고정' in text for text in texts)
    assert max(pixels(app)[::4]) > 100 and not p.SDL_GetRenderTarget(p.renderer)
    p.SDL_SetRenderTarget(p.renderer,app.view.display)
    target = ctypes.cast(p.SDL_GetRenderTarget(p.renderer),ctypes.c_void_p).value
    app.view.boulder_scene.draw_scene(room)
    assert ctypes.cast(p.SDL_GetRenderTarget(p.renderer),ctypes.c_void_p).value == target, 'scene changed the main render target'
    p.SDL_SetRenderTarget(p.renderer,None)
    picture(app,'03-boulder-ready.png')
    saved = game.player.x,game.player.y
    original_blade = app.audio.blade
    class Count:
        calls = 0
        def play(self):
            self.calls += 1
    sound = Count()
    app.audio.blade = sound
    rear_seen = False
    try:
        for index in range(4000):
            pending = [obstacle for obstacle in OBSTACLES if room.z < obstacle[2]+obstacle[4]+.3]
            target_x = (-.85 if pending[0][1] > 0 else .85) if pending else -1.
            desired = {p.SDLK_w}
            if room.x < target_x-.045:desired.add(p.SDLK_d)
            elif room.x > target_x+.045:desired.add(p.SDLK_a)
            if room.gap < 6:desired.add(p.SDLK_LSHIFT)
            if 6. < room.time < 6.8:desired.add(p.SDLK_q)
            keys(app,desired)
            if room.exit_nearby() == 'narrow':
                press(app,p.SDLK_f)
                assert game.state == 'trap' and game.boulder_exit_requested
                picture(app,'05-side-exit.png')
            step(app)
            if room.look_back and not rear_seen:
                assert room.vz > 0, 'Q reversed forward movement'
                picture(app,'04-boulder-rear.png')
                rear_seen = True
            if game.state != 'trap':
                break
            assert (game.player.x,game.player.y) == saved
        assert game.state == 'explore' and game.boulder_completed and rear_seen
        assert (game.player.x,game.player.y) == (11.5,13.5) and not app.held
        assert room.player is game.player and room.hp == game.player.hp == 100
        assert sound.calls == 0 and not game.phase_warning, 'blade proximity leaked into the boulder course'
        assert game.boulder_exit in game.visited and game.landing_cell == game.boulder_exit
        picture(app,'06-D-first-return.png')
        assert len(set(pixels(app)[::4])) > 30, 'return fade hid the landing frame'
        for _ in range(20):step(app)
        picture(app,'07-D-arrival.png')
        press(app,p.SDLK_m)
        assert game.map_open and {'C','D'} <= set(map_badges(app))
        picture(app,'08-D-map.png')
        press(app,p.SDLK_ESCAPE)
        assert not game.map_open and app.running
    finally:
        app.audio.blade = original_blade
    print('PASS: real SDL spawn route -> C warning/map -> F -> W/A/D/Shift/Q boulder course -> F -> D/map; shared HUD, native target/fade, no practice HUD or blade sound.')


def check_boundaries(app):
    for outcome in ('phase','escape','collision'):
        app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
        app.release_input()
        game.player.x,game.player.y = 9.4,6.6
        game.player.hp,game.player.stamina = 61,37.
        press(app,p.SDLK_f)
        picture(app)
        for _ in range(16):step(app)
        picture(app)
        room = game.boulder_room
        saved = game.trap_return
        room.release()
        room.x,room.z,room.ball_z = -1.4,46.,46.
        if outcome == 'phase':game.phase_time = PHASE_SECONDS-.01
        keys(app,(p.SDLK_w,p.SDLK_LSHIFT,p.SDLK_q))
        press(app,p.SDLK_f)
        if outcome != 'collision':press(app,p.SDLK_ESCAPE)
        assert game.state == 'trap', 'Esc/F resolved before the world phase boundary'
        step(app)
        assert not app.held and not game.boulder_completed
        assert game.boulder_exit not in game.visited
        if outcome == 'collision':
            assert game.state == 'failed' and game.player.hp == 0
            for _ in range(16):step(app)
        else:
            assert game.state == ('shifting' if outcome == 'phase' else 'explore')
            assert (game.player.x,game.player.y) == saved and game.player.hp == 61
        picture(app,f'09-{outcome}.png')
    press(app,p.SDLK_r)
    assert app.game is not game and app.game.run_number == 1
    assert app.game.boulder_room is None and not app.held and not app.puzzle_mouse_held
    assert app.game.player.hp == app.game.player.stamina == 100

    app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    game.player.x,game.player.y = 9.4,6.6
    press(app,p.SDLK_f)
    keys(app,(p.SDLK_w,p.SDLK_LSHIFT,p.SDLK_q))
    game.request_boulder_exit()
    event = p.SDL_Event()
    event.type = p.SDL_WINDOWEVENT
    event.window.event = p.SDL_WINDOWEVENT_FOCUS_LOST
    assert p.SDL_PushEvent(event) == 1
    app.handle_events()
    before = game.time
    step(app)
    assert game.time > before and not game.boulder_room.look_back
    assert not app.held and not game.boulder_exit_requested and not game.boulder_return_requested
    print('PASS: SDL Esc/F/phase/contact priority, failure, R, focus loss and held/Q/exit clearing.')


def run(app):
    original = app.game
    app.game = Game(117,player_clips=app.view.player_catalog['clips'])
    try:
        check_sign_boundaries(app)
        check_course(app)
        check_boundaries(app)
    finally:
        app.game = original
        app.release_input()
        picture(app)
