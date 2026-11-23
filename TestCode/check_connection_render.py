"""두 창 크기에서 통로 연결 탭의 실제 SDL 조작과 예약 문 통과를 검사한다."""
import pico2d.pico2d as p
from SourceCode.maze_model import Game, PHASE_SECONDS, WALK_SPEED, project
from SourceCode.game_view import PUZZLE_OFFSET_X
from SourceCode.puzzle_layout import CONNECTION_SLOTS, connection_center
from SourceCode.path_connection import N, E, S, W
from .check_game_render import inject_mouse
from .check_boulder_render import keys, press, picture, pixels
from math import hypot, ceil


def run(app):
    original = app.game

    def mouse(kind,point,held=True):
        inject_mouse(kind,(point[0]+PUZZLE_OFFSET_X,point[1]),held)
        app.handle_events()

    def click(point):
        mouse(p.SDL_MOUSEBUTTONDOWN,point)
        mouse(p.SDL_MOUSEBUTTONUP,point)

    def rotate_to(index,ports):
        game = app.game
        run_number = game.run_number
        for _ in range(4):
            if game.connection.pieces[index].ports == frozenset(ports):
                return
            press(app,p.SDLK_r)
            assert app.game is game and game.run_number == run_number
        raise AssertionError('R rotation did not reach the expected ports')

    def put(index,cell,ports):
        mouse(p.SDL_MOUSEBUTTONDOWN,CONNECTION_SLOTS[index])
        assert app.game.connection.held == index
        mouse(p.SDL_MOUSEMOTION,connection_center(cell))
        assert app.view.connection_pointer == connection_center(cell)
        rotate_to(index,ports)
        mouse(p.SDL_MOUSEBUTTONUP,connection_center(cell))

    try:
        for width,height in ((1280,800),(960,600)):
            p.SDL_SetWindowSize(p.window,width,height)
            app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
            app.release_input()
            wall,near,far = game.puzzle_gate
            game.player.x,game.player.y = near[0]+.5,near[1]+.5
            game.player.torch,game.guard_hp = True,0
            game.update_visibility()
            press(app,p.SDLK_f)
            assert game.state == 'puzzle' and game.puzzle_tab == 'maze'
            click((256,66))
            assert game.puzzle_tab == 'connection' and not app.puzzle_mouse_held
            picture(app)
            for _ in range(20):app.update(.02)
            put(0,(0,1),(W,E))
            put(1,(1,1),(W,E))
            saved = game.connection.pieces[0].rotation
            for target in (connection_center((1,1)),(30,320)):
                mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
                press(app,p.SDLK_r)
                mouse(p.SDL_MOUSEMOTION,target)
                mouse(p.SDL_MOUSEBUTTONUP,target)
                assert game.connection.pieces[0].cell == (0,1)
                assert game.connection.pieces[0].rotation == saved and not game.connection.dragging

            for cause in ('escape','hit','focus','missing-button'):
                mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
                press(app,p.SDLK_r)
                if cause == 'escape':
                    press(app,p.SDLK_ESCAPE)
                elif cause == 'hit':
                    game.guard = int(game.player.x),int(game.player.y)
                    game.guard_hp,game.guard_attack_at = 3,game.time+.01
                    app.update(.02)
                    assert game.player.hp == 85
                    game.guard_hp = 0
                elif cause == 'focus':
                    event = p.SDL_Event()
                    event.type = p.SDL_WINDOWEVENT
                    event.window.event = p.SDL_WINDOWEVENT_FOCUS_LOST
                    assert p.SDL_PushEvent(event) == 1
                    app.handle_events()
                else:
                    mouse(p.SDL_MOUSEMOTION,(30,320),False)
                assert not game.connection.dragging and game.connection.pieces[0].cell == (0,1)
                assert game.connection.pieces[0].rotation == saved and game.puzzle_tab == 'connection'
                if cause in ('escape','hit'):
                    assert game.state == 'explore' and app.puzzle_mouse_held
                    mouse(p.SDL_MOUSEBUTTONDOWN,(30,320))
                    assert not game.attack_hits_ms
                mouse(p.SDL_MOUSEBUTTONUP,(30,320))
                if game.state == 'explore':
                    press(app,p.SDLK_f)
                    assert game.puzzle_tab == 'connection'
            click((126,66))
            assert game.puzzle_tab == 'maze' and game.connection.pieces[0].cell == (0,1)
            click((256,66))
            assert game.puzzle_tab == 'connection'
            mouse(p.SDL_MOUSEBUTTONDOWN,connection_center((0,1)))
            mouse(p.SDL_MOUSEBUTTONUP,(290,286))
            assert game.connection.pieces[0].cell is None
            put(0,(0,1),(W,E))

            mouse(p.SDL_MOUSEBUTTONDOWN,CONNECTION_SLOTS[3])
            rotate_to(3,(W,S))
            mouse(p.SDL_MOUSEMOTION,connection_center((2,1)))
            picture(app)
            frame = pixels(app)
            x,y = connection_center((0,1))
            index = (int(y)*2*1280+int(x+PUZZLE_OFFSET_X)*2)*4
            assert tuple(frame[index:index+3]) == (240,208,146), 'stone road is not visibly rendered'
            if width == 1280:
                app.view.capture(app.output/'connection-drag-review.png')
            mouse(p.SDL_MOUSEBUTTONUP,connection_center((2,1)))
            put(4,(2,2),(N,E) if width == 1280 else (N,W))
            put(2,(3,2),(W,E))
            if width == 960:
                assert game.state == 'puzzle' and game.puzzle_reserved_phase is None
                click(connection_center((2,2)))
                press(app,p.SDLK_r)
            assert app.game is game and game.run_number == 0 and game.state == 'explore'
            assert game.puzzle_reserved_phase == game.next_phase and game.solid(*wall)
            assert not game.attack_hits_ms and not app.puzzle_mouse_held
            game.phase_time = PHASE_SECONDS-.01
            app.update(.02)
            while game.state == 'shifting':app.update(.05)
            assert game.puzzle_open and not game.solid(*wall)
            keys(app,(p.SDLK_a,))
            seconds = 2*hypot(*project(1,0))/WALK_SPEED
            ticks = ceil(seconds/.02)
            for _ in range(ticks):app.update(seconds/ticks)
            keys(app)
            assert abs(game.player.x-far[0]-.5) < 1e-6 and abs(game.player.y-far[1]-.5) < 1e-6
            assert far in game.visited, 'native input did not walk through the opened door'
            print(f'PASS: {width}x{height} SDL F/tabs/drag/R, invalid drops/shelf, Esc/hit/focus cancel and same-tab resume; one reservation then native door crossing.')

        press(app,p.SDLK_r)
        fresh = app.game
        assert fresh is not game and fresh.puzzle_tab == 'maze'
        near = fresh.puzzle_gate[1]
        fresh.player.x,fresh.player.y = near[0]+.5,near[1]+.5
        fresh.guard_hp = 0
        fresh.update_visibility()
        press(app,p.SDLK_f)
        click((256,66))
        put(0,(0,1),(W,E))
        mouse(p.SDL_MOUSEBUTTONDOWN,CONNECTION_SLOTS[1])
        fresh.phase_time = PHASE_SECONDS-.01
        app.update(.02)
        assert fresh.state == 'shifting' and fresh.puzzle_tab == 'maze' and not fresh.connection.dragging
        assert all(piece.cell is None for piece in fresh.connection.pieces)
        assert fresh.puzzle_reserved_phase is None
        mouse(p.SDL_MOUSEBUTTONUP,(30,320))
        print('PASS: SDL new round and phase change reset unfinished connections; R edits only the connection tab.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.game = original
        app.release_input()
        picture(app)
