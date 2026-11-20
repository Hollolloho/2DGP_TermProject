"""본게임의 실제 SDL 키 입력·C/D 표시·돌 장면과 복귀를 검사한다."""
import ctypes
from math import ceil, hypot, isclose
from unittest.mock import patch

import pico2d.pico2d as p
from SourceCode.maze_model import Game, WALK_SPEED, PHASE_SECONDS, project
from SourceCode.game_view import BOULDER_WARNING_RECT
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
        if name == 'boulder-warning-sign':calls.append(rect)
        return original(name,rect,*args,**kwargs)
    with patch.object(view,'image',side_effect=image):
        picture(app)
        actual = pixels(app)
    x,y,w,h = BOULDER_WARNING_RECT
    assert calls == [(x+8,y+10,52,52)]
    assert view.images['boulder-warning-sign'].w == view.images['boulder-warning-sign'].h == 192
    with patch.object(view,'boulder_warning',lambda game:None):
        picture(app)
        baseline = pixels(app)
    changed = [index//4 for index in range(0,len(actual),4) if actual[index:index+4] != baseline[index:index+4]]
    assert changed and all(x*2 <= point%1280 < (x+w)*2 and y*2 <= point//1280 < (y+h)*2 for point in changed)
    _, player_y = view.world(game.player.x,game.player.y)
    _, badge_y = view.world(game.boulder_entry[0]+.5,game.boulder_entry[1]+.5)
    assert max(player_y+10*view.world_scale,badge_y+8) < y, 'warning overlaps player/C badge'
    assert x+8+52+10 <= x+70 and y+10+52 <= y+h
    picture(app)
    print('PASS: RGBA sign is 52x52 logical pixels; warning/icon/text stay below the C badge and player.')


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
    assert any('5초' in text and '뒤에서' in text for text in texts)
    assert any('장애물' in text and '측면 출구' in text for text in texts) and any('F 진입' in text for text in texts)
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
        check_course(app)
        check_boundaries(app)
    finally:
        app.game = original
        app.release_input()
        picture(app)
