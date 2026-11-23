"""월드 통로 방: 보통 진입, 역투영 드래그, R, 실제 WASD 통과의 SDL 회귀."""
from math import ceil,hypot
from unittest.mock import patch
import pico2d.pico2d as p
from SourceCode.maze_model import Game, PHASE_SECONDS, WALK_SPEED, project
from SourceCode.puzzle_layout import room_screen, connection_center
from SourceCode.world_path_room import LOOSE_POSITIONS
from SourceCode.path_connection import N,E,S,W
from .check_game_render import inject_mouse
from .check_boulder_render import keys,press,picture,pixels,labels


def run(app):
    original = app.game
    def mouse(kind,point,held=True):
        inject_mouse(kind,point,held)
        app.handle_events()
    def rotate_to(index,ports):
        game = app.game
        for _ in range(4):
            if game.connection.pieces[index].ports == frozenset(ports):return
            press(app,p.SDLK_r)
            assert app.game is game
        raise AssertionError('R did not rotate the held slab')
    def put(index,cell,ports):
        mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*LOOSE_POSITIONS[index]))
        assert app.game.connection.held == index
        rotate_to(index,ports)
        mouse(p.SDL_MOUSEMOTION,connection_center(cell))
        mouse(p.SDL_MOUSEBUTTONUP,connection_center(cell))
        assert app.game.connection.pieces[index].cell == cell
    def tick(count,dt=.02):
        for _ in range(count):
            app.update(dt)
            picture(app)
    def enter(capture=False):
        game = app.game
        saved = game.player.x,game.player.y
        press(app,p.SDLK_f)
        assert game.state == 'path_room' and game.world_path.stage == 'entering'
        assert not app.held
        visible = game.visible
        game.visible = visible | {game.path_exit}
        try:
            with (patch.object(app.view,'path_door',wraps=app.view.path_door) as doors,
                  patch.object(app.view,'atlas',wraps=app.view.atlas) as atlas):
                picture(app)
        finally:
            game.visible = visible
        cell = game.path_exit if game.world_path.reverse else game.path_entry
        x,y,facing = app.view.shortcut_mount(game,cell)
        sx,sy = app.view.world(x,y)
        assert any(call.args[:3] == (sx,sy,facing) and call.args[3] for call in doors.call_args_list), 'entering doorway stayed closed'
        assert any(call.args[:4] == (sx,sy,'shortcuts',f'puzzle_open_{facing}') for call in atlas.call_args_list)
        if not game.path_completed:
            x,y,other_facing = app.view.shortcut_mount(game,game.path_exit)
            ox,oy = app.view.world(x,y)
            assert any(call.args[:4] == (ox,oy,'shortcuts',f'puzzle_closed_{other_facing}') for call in atlas.call_args_list)
        press(app,p.SDLK_r)
        press(app,p.SDLK_s)
        assert app.game is game and not app.held
        for index in range(70):
            app.update(.02)
            picture(app)
            if capture and index in (7,23,39):
                pixels(app)
                app.view.capture(app.output/f'entry-open-{index+1:02}.png')
        assert game.world_path.stage == 'active' and game.can_stand(game.player.x,game.player.y)
        assert game.path_return == saved
    def walk_to(target,capture=None):
        game = app.game
        mapping = {(-1,0):p.SDLK_w,(1,0):p.SDLK_s,(0,-1):p.SDLK_d,(0,1):p.SDLK_a}
        for _ in range(300):
            if game.state != 'path_room':break
            dx,dy = target[0]-game.player.x,target[1]-game.player.y
            if max(abs(dx),abs(dy)) < 1e-5:break
            if abs(dx) > 1e-5:
                direction = (1 if dx > 0 else -1,0);distance=abs(dx)
            else:
                direction = (0,1 if dy > 0 else -1);distance=abs(dy)
            keys(app,(mapping[direction],))
            app.update(min(.02,distance/2.5))
            picture(app)
        else:raise AssertionError(('blocked room walk',target,game.player.x,game.player.y))
        if capture:
            pixels(app)
            app.view.capture(app.output/capture)
        keys(app)
    try:
        for width,height in ((1280,800),(960,600)):
            p.SDL_SetWindowSize(p.window,width,height)
            app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
            app.release_input()
            picture(app);tick(20)
            press(app,p.SDLK_f)
            assert game.player.torch and game.state == 'explore'
            keys(app,(p.SDLK_w,))
            tick(20)
            keys(app)
            assert abs(game.player.x-9.5) < 1e-6 and abs(game.player.y-1.5) < 1e-6
            assert 'F 길의 방' in labels(app)
            enter(width == 1280)
            # 방에서 먼저 해결하지 않으면 앞의 빈 바닥을 건널 수 없다.
            keys(app,(p.SDLK_s,));tick(60);keys(app)
            assert game.state == 'path_room' and game.player.x < -.2
            put(0,(0,1),(W,E));put(1,(1,1),(W,E))
            saved = game.connection.pieces[0].rotation
            for target in (connection_center((1,1)),(610,90)):
                mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
                press(app,p.SDLK_r)
                mouse(p.SDL_MOUSEMOTION,target)
                mouse(p.SDL_MOUSEBUTTONUP,target)
                assert game.connection.pieces[0].cell == (0,1) and game.connection.pieces[0].rotation == saved
            mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
            press(app,p.SDLK_r)
            press(app,p.SDLK_ESCAPE)
            assert game.state == 'explore' and (game.player.x,game.player.y) == game.path_return
            assert game.connection.pieces[0].cell == (0,1) and game.connection.pieces[0].rotation == saved
            mouse(p.SDL_MOUSEBUTTONDOWN,(610,90))
            assert not game.attack_hits_ms
            mouse(p.SDL_MOUSEBUTTONUP,(610,90))
            enter()
            assert game.connection.pieces[1].cell == (1,1)
            mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
            event=p.SDL_Event();event.type=p.SDL_WINDOWEVENT;event.window.event=p.SDL_WINDOWEVENT_FOCUS_LOST
            assert p.SDL_PushEvent(event)==1
            app.handle_events()
            assert not game.connection.dragging and not app.held
            mouse(p.SDL_MOUSEBUTTONUP,(610,90))
            mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*LOOSE_POSITIONS[3]))
            rotate_to(3,(W,S))
            mouse(p.SDL_MOUSEMOTION,connection_center((2,1)))
            picture(app)
            assert game.connection.held == 3
            assert max(abs(a-b) for a,b in zip(app.view.connection_pointer,connection_center((2,1)))) < 1.5
            if width == 1280:
                pixels(app)
                app.view.capture(app.output/'world-room-drag.png')
            mouse(p.SDL_MOUSEBUTTONUP,connection_center((2,1)))
            put(4,(2,2),(N,E) if width == 1280 else (N,W))
            put(2,(3,2),(W,E))
            if width == 960:
                mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((2,2)))
                mouse(p.SDL_MOUSEBUTTONUP,connection_center((2,2)))
                press(app,p.SDLK_r)
            assert game.connection.completed and game.state == 'path_room' and not game.path_completed
            assert game.puzzle_reserved_phase is None and not game.puzzle_open
            for point in ((-.5,1.5),(.5,1.5),(1.5,1.5)):
                walk_to(point)
            if width == 1280:
                picture(app);pixels(app)
                app.view.capture(app.output/'world-room-walking.png')
            for point in ((2.5,1.5),(2.5,2.5),(3.5,2.5),(4.5,2.5)):
                walk_to(point)
                assert game.state == 'path_room' and not game.path_completed
            walk_to((5.6,2.5))
            assert game.state == 'explore' and game.path_completed and game.can_stand(game.player.x,game.player.y)
            assert (game.player.x,game.player.y)==(19.5,9.5) and game.path_exit in game.visited
            assert game.puzzle_reserved_phase is None and not game.attack_hits_ms
            if width == 1280:
                tick(20);pixels(app)
                app.view.capture(app.output/'world-room-arrival.png')
            enter()
            assert game.world_path.reverse
            with patch.object(app.view,'text',wraps=app.view.text) as text:
                picture(app)
            ex,ey = app.view.world(-3,1.5)
            ox,oy = app.view.world(5.7,2.5)
            assert any(call.args[:3] == ('출구',ex,ey+18) for call in text.call_args_list)
            assert any(call.args[:3] == ('입구 · 후퇴',ox,oy+18) for call in text.call_args_list)
            assert any('맞은편 문까지' in call.args[0] for call in text.call_args_list)
            for point in ((4.5,2.5),(3.5,2.5),(2.5,2.5),(2.5,1.5),(.5,1.5),(-1.5,1.5),(-2.8,1.5)):
                walk_to(point)
            assert game.state == 'explore' and (game.player.x,game.player.y) == (8.5,1.5)
            print(f'PASS: {width}x{height} spawn/torch/W/F, open-entry frame, doorway walk/darkness; iso drag/R/cancel; native WASD corners and physical exit alone land across immediately.')
            print(f'PASS: {width}x{height} reverse entry swaps retreat/exit markers and goal text; native WASD returns to the original maze doorway.')
        press(app,p.SDLK_r)
        fresh=app.game
        assert fresh is not game and not fresh.path_completed
        x,y=fresh.path_entry;fresh.player.x,fresh.player.y=x+.5,y+.5;fresh.guard_hp=0;fresh.player.torch=True
        fresh.update_visibility();enter()
        put(0,(0,1),(W,E))
        mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*LOOSE_POSITIONS[1]))
        saved=fresh.path_return
        fresh.phase_time=PHASE_SECONDS-.01
        app.update(.02)
        assert fresh.state=='shifting' and (fresh.player.x,fresh.player.y)==saved
        assert all(piece.cell is None for piece in fresh.connection.pieces) and not fresh.connection.dragging
        assert not fresh.path_completed and fresh.puzzle_reserved_phase is None
        mouse(p.SDL_MOUSEBUTTONUP,(610,90))
        print('PASS: R is rotation only inside the world room; restart and phase boundary cancel edits and restore safe maze coordinates.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.game=original
        app.release_input()
        picture(app)
