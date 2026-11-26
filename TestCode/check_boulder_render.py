"""본게임의 실제 SDL 키 입력·C 입구 표시·돌 장면과 복귀를 검사한다."""
import ctypes
from math import ceil, hypot, isclose, pi
from unittest.mock import patch

import pico2d.pico2d as p
from SourceCode.maze_model import Game, WALK_SPEED, PHASE_SECONDS, project
from SourceCode.game_view import BOULDER_SIGN_HEIGHT
from SourceCode.six_lane_trap import CYCLE_SECONDS
from .check_game_render import inject_key


def keys(app, desired=()):
    desired = set(desired)
    for key in app.held-desired:
        inject_key(key, False)
    for key in desired-app.held:
        inject_key(key)
    app.handle_events()


def move_mouse(app, dx):
    event = p.SDL_Event()
    event.type = p.SDL_MOUSEMOTION
    event.motion.xrel = dx
    assert p.SDL_PushEvent(event) == 1
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
    mount = view.boulder_sign_mount(game)
    ex,ey = game.boulder_entry
    assert mount == (ex+.02,ey+1.5,(ex-1,ey+1))
    anchor = view.world(*mount[:2])
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
        app.game = Game(117,player_clips=view.player_catalog['clips'])
        with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
            picture(app)
        assert sign.call_count == 0, 'sign leaked through unseen terrain'
        with patch.object(Game,'choose_boulder_shortcut',return_value=None):
            omitted = Game(120,player_clips=view.player_catalog['clips'])
        for absent in (omitted,):
            app.game = absent
            assert absent.boulder_entry is None
            absent.reveal_all = True
            with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
                picture(app)
            assert sign.call_count == 0, 'an omitted entrance retained a wall sign'
        for seed,run in ((117,1),(117,2),(0,0),(120,0)):
            app.game = supported = Game(seed,run,player_clips=view.player_catalog['clips'])
            assert supported.boulder_entry is not None
            ex,ey = supported.boulder_entry
            supported.player.x,supported.player.y = ex+.5,ey+.5
            supported.update_visibility()
            picture(app)
            supported.ui_time += .4
            with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
                picture(app)
            assert sign.call_count == 1
            check_warning_visibility(app)
        app.game = game
        game.player.x,game.player.y = 7.5,7.5
        game.update_visibility()
        assert game.boulder_entry not in game.visible and not game.clear_line_to(9.02,7.5)
        with patch.object(view,'boulder_sign',wraps=view.boulder_sign) as sign:
            picture(app,'01d-C-wall-occlusion.png')
        assert sign.call_count == 0
        print('PASS: general C wall signs have actual world pixels; unseen, blocked and safely omitted entries do not show a sign.')
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
    assert any('여섯 경사 구간' in text for text in texts)
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
    keys(app,(p.SDLK_w,p.SDLK_LSHIFT))
    press(app,p.SDLK_f)
    assert game.state == 'trap' and game.trap_kind == 'boulder' and not app.held
    room = game.boulder_room
    picture(app)
    assert max(pixels(app)[::4]) <= 1, 'room entry must use the main fade'
    for _ in range(16):
        step(app)
    texts = labels(app)
    assert any('교차 경사 돌방' in text for text in texts)
    assert any('1/6' in text for text in texts) and any('돌 주기' in text for text in texts)
    assert any('W/S' in text and 'A/D' in text and 'Shift' in text and 'Q' not in text for text in texts)
    assert not any('돌 출발까지' in text or '추격' in text or '측면 출구' in text for text in texts)
    assert not any('무적' in text or 'HP 100 고정' in text for text in texts)
    assert max(pixels(app)[::4]) > 100 and not p.SDL_GetRenderTarget(p.renderer)
    p.SDL_SetRenderTarget(p.renderer,app.view.display)
    target = ctypes.cast(p.SDL_GetRenderTarget(p.renderer),ctypes.c_void_p).value
    app.view.boulder_scene.draw_scene(room)
    assert ctypes.cast(p.SDL_GetRenderTarget(p.renderer),ctypes.c_void_p).value == target, 'scene changed the main render target'
    p.SDL_SetRenderTarget(p.renderer,None)
    picture(app,'03-six-lane-entry.png')
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
        # Count the fade's .32s in the initial wait; never stop after W begins.
        for _ in range(9):step(app)
        assert isclose(room.time,.5) and room.z == 0.
        for index in range(1000):
            keys(app,(p.SDLK_w,))
            if room.exit_nearby() == 'front':
                press(app,p.SDLK_f)
                assert game.state == 'trap' and game.boulder_exit_requested
                assert 'F  정면 출구 이용' in labels(app)
                picture(app,'05-front-exit.png')
            step(app)
            if room.time > 1. and not rear_seen:
                move_mouse(app,0)
                move_mouse(app,1200)
                assert isclose(abs(room.yaw),pi) and room.vz > 0
                picture(app,'04-boulder-rear.png')
                move_mouse(app,-1200)
                rear_seen = True
            if game.state != 'trap':
                break
            assert (game.player.x,game.player.y) == saved
        assert game.state == 'explore' and game.boulder_completed and rear_seen
        assert (game.player.x,game.player.y) == tuple(n+.5 for n in game.boulder_exit) and not app.held
        assert room.player is game.player and room.hp == game.player.hp == 100
        assert game.player.stamina == 100. and room.contacts == 0 and room.x == 0.
        assert sound.calls == 0 and not game.phase_warning, 'blade proximity leaked into the boulder course'
        assert game.landing_cell == game.boulder_exit and game.boulder_exit in game.visited
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
    print('PASS: real SDL spawn route -> C warning/map -> F -> .5s wait + continuous W and mouse look -> front F -> D; shared HUD/target/fade, no sprint/contact/practice HUD or blade sound.')


def check_movement_audio(app):
    assert not p.SDL_IsTextInputActive()
    app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    app.release_input()
    # Use a traversable route and dispatch through SDL_PollEvent. Count actual
    # mixer starts separately from movement and the stone's continuous pan.
    game.player.x,game.player.y = 10.5,3.5
    with patch.object(p, 'Mix_PlayChannel', wraps=p.Mix_PlayChannel) as play:
        for _ in range(5):
            keys(app,(p.SDLK_w,))
            step(app)
            keys(app)
        assert game.player.x < 10.5 and p.SDLK_w not in app.held
        assert play.call_count == 0, play.call_args_list
        game.player.x,game.player.y = 9.5,6.5
        press(app,p.SDLK_f)
        step(app)
        assert play.call_count == 1 and play.call_args.args[2] == -1
        for _ in range(5):
            keys(app,(p.SDLK_w,))
            step(app)
            keys(app)
        assert game.boulder_room.z > 0. and play.call_count == 1
    print('PASS: text input disabled, five SDL W down/up pairs moved in each room; zero maze sounds and one continuous stone loop.')


def check_mouse_look(app):
    def focus(kind):
        event = p.SDL_Event()
        event.type = p.SDL_WINDOWEVENT
        event.window.event = kind
        assert p.SDL_PushEvent(event) == 1
        app.handle_events()

    def mouse_state():
        return p.SDL_GetRelativeMouseMode(), p.SDL_ShowCursor(p.SDL_QUERY)

    app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    app.release_input()
    focus(p.SDL_WINDOWEVENT_FOCUS_GAINED)
    initial = mouse_state()
    game.player.x,game.player.y = 9.5,6.5
    press(app,p.SDLK_f)
    room = game.boulder_room
    assert app.mouse.restore is not None
    if p.SDL_GetCurrentVideoDriver() != b'dummy':
        assert p.SDL_GetRelativeMouseMode() and p.SDL_ShowCursor(p.SDL_QUERY) == 0
    move_mouse(app,9000)
    assert room.yaw == 0.
    picture(app)
    for _ in range(20):
        step(app)
    with patch.object(p, 'Mix_SetPanning', wraps=p.Mix_SetPanning) as pan:
        def frame_and_pan():
            step(app,0.)
            picture(app)
            return pixels(app), pan.call_args.args[1:]
        forward, stereo = frame_and_pan()
        assert stereo[0] != stereo[1] and max(forward[::4]) > 100
        keys(app,(p.SDLK_q,))
        assert frame_and_pan() == (forward, stereo)
        keys(app)
        assert frame_and_pan() == (forward, stereo)
        move_mouse(app,1200)
        rear, reversed_stereo = frame_and_pan()
        assert isclose(abs(room.yaw),pi) and rear != forward and reversed_stereo == stereo[::-1]
        move_mouse(app,-1200)
    keys(app,(p.SDLK_w,))
    app.update(.02)
    assert room.z>0 and room.x==0
    previous_z=room.z
    move_mouse(app,600)
    app.update(.02)
    assert room.x>0 and isclose(room.z,previous_z,abs_tol=1e-9) and isclose(room.yaw,pi/2)
    keys(app,(p.SDLK_a,))
    app.update(.02)
    assert room.z > 0 and isclose(room.yaw,pi/2)
    focus(p.SDL_WINDOWEVENT_LEAVE)
    assert mouse_state()==initial and not app.held
    move_mouse(app,700)
    assert isclose(room.yaw,pi/2)
    focus(p.SDL_WINDOWEVENT_ENTER)
    move_mouse(app,700)
    assert isclose(room.yaw,pi/2)
    focus(p.SDL_WINDOWEVENT_FOCUS_LOST)
    assert not app.held and mouse_state() == initial
    move_mouse(app,-600)
    assert isclose(room.yaw,pi/2)
    focus(p.SDL_WINDOWEVENT_FOCUS_GAINED)
    move_mouse(app,-9999)
    move_mouse(app,-1200)
    assert isclose(room.yaw,-pi/2)
    press(app,p.SDLK_ESCAPE)
    app.update(.02)
    assert game.state == 'explore' and mouse_state() == initial
    press(app,p.SDLK_f)
    assert room.yaw == 0.
    room.x, room.z = 0.,4.5
    room.phase_offsets[0] = CYCLE_SECONDS/2-room.time
    app.update(.02)
    assert game.state == 'failed' and mouse_state() == initial
    print('PASS: SDL relative motion, both side views, view-relative movement, inert Q down/up (pixels and pan), 180-degree mouse look, focus/re-entry delta suppression and cursor restoration after Esc/failure.')


def check_controls(app):
    app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    app.release_input()
    game.player.x,game.player.y = 9.4,6.6
    game.player.stamina = 37.
    press(app,p.SDLK_f)
    room = game.boulder_room
    for key,axis,sign in ((p.SDLK_w,'vz',1),(p.SDLK_s,'vz',-1),
                          (p.SDLK_a,'vx',-1),(p.SDLK_d,'vx',1)):
        room.x = room.z = room.vx = room.vz = 0.
        keys(app,(key,))
        for _ in range(4):step(app)
        assert getattr(room,axis)*sign > 0, (key,axis,getattr(room,axis))
        assert game.player.hp == 100 and game.player.stamina == 37.
    room.x = room.z = room.vx = room.vz = 0.
    keys(app,(p.SDLK_w,p.SDLK_s,p.SDLK_a,p.SDLK_d))
    step(app)
    assert room.x == room.z == room.vx == room.vz == 0.
    keys(app,(p.SDLK_w,p.SDLK_LSHIFT))
    for _ in range(4):step(app)
    assert room.running and room.z > 0.
    assert isclose(game.player.stamina,37.-4*.02*18)
    before = room.z
    keys(app,(p.SDLK_w,))
    for _ in range(4):step(app)
    assert not room.running and room.z > before
    press(app,p.SDLK_ESCAPE)
    assert game.state == 'trap', 'Esc must queue until the shared phase update'
    step(app)
    assert game.state == 'explore' and not app.held and room.vx == room.vz == 0.
    press(app,p.SDLK_f)
    assert game.state == 'trap' and game.boulder_room is room and room.time == 0.
    press(app,p.SDLK_r)
    assert app.game is not game and app.game.boulder_room is None and not app.held
    print('PASS: SDL W/S/A/D axes, opposing cancellation, shared Shift cost, deferred Esc/re-entry and R reset.')


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
        room.x,room.z = 0.,4.5
        room.phase_offsets[0] = CYCLE_SECONDS/2-room.time
        if outcome == 'phase':game.phase_time = PHASE_SECONDS-.01
        keys(app,(p.SDLK_w,p.SDLK_LSHIFT))
        press(app,p.SDLK_f)
        if outcome != 'collision':press(app,p.SDLK_ESCAPE)
        assert game.state == 'trap', 'Esc/F resolved before the world phase boundary'
        step(app)
        assert not app.held and not game.boulder_completed
        assert game.landing_cell is None and game.boulder_exit not in game.visited
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
    keys(app,(p.SDLK_w,p.SDLK_LSHIFT))
    game.request_boulder_exit()
    event = p.SDL_Event()
    event.type = p.SDL_WINDOWEVENT
    event.window.event = p.SDL_WINDOWEVENT_FOCUS_LOST
    assert p.SDL_PushEvent(event) == 1
    app.handle_events()
    before = game.time
    step(app)
    assert game.time > before and app.mouse.restore is None
    assert not app.held and not game.boulder_exit_requested and not game.boulder_return_requested
    print('PASS: SDL Esc/F/phase/contact priority, failure, R, focus loss and held/exit clearing.')


def run(app):
    original = app.game
    original_focus = app.focused
    app.game = Game(117,player_clips=app.view.player_catalog['clips'])
    try:
        check_movement_audio(app)
        check_mouse_look(app)
        check_sign_boundaries(app)
        check_controls(app)
        check_course(app)
        check_boundaries(app)
    finally:
        app.game = original
        app.focused = original_focus
        app.release_input()
        app.sync_mouse()
        picture(app)
