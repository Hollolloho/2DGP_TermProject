"""월드 통로 방: 보통 진입, 역투영 드래그, R, 실제 WASD 통과의 SDL 회귀."""
from math import ceil
import ctypes
from unittest.mock import patch
import pico2d.pico2d as p
from SourceCode.maze_model import Game, PHASE_SECONDS
from SourceCode.puzzle_layout import room_screen, connection_center
from SourceCode.world_path_room import LOOSE_POSITIONS
from SourceCode.path_connection import E,W,RUNES
from .runed_path_fixtures import ROUTES,placement
from .check_game_render import inject_mouse
from .check_boulder_render import keys,press,picture,pixels,labels


def run(app):
    original = app.game
    def mouse(kind,point,held=True):
        inject_mouse(kind,point,held)
        app.handle_events()
    def advance(seconds):
        count = max(1,ceil(seconds/.05))
        for _ in range(count):
            app.update(seconds/count)
            picture(app)
    def rotate_to(index,ports):
        game = app.game
        for _ in range(4):
            if game.connection.pieces[index].ports == frozenset(ports):return
            press(app,p.SDLK_r)
            assert app.game is game
            advance(.15)
        raise AssertionError('R did not rotate the held slab')
    def put(index,cell,ports):
        mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*LOOSE_POSITIONS[index]))
        assert app.game.connection.held == index
        rotate_to(index,ports)
        mouse(p.SDL_MOUSEMOTION,connection_center(cell))
        advance(.45)
        assert not app.game.connection.completed
        mouse(p.SDL_MOUSEBUTTONUP,connection_center(cell))
        advance(.15)
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
    def native_start():
        app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
        app.release_input()
        picture(app);tick(20)
        press(app,p.SDLK_f)
        assert game.player.torch and game.state == 'explore'
        keys(app,(p.SDLK_w,));tick(20);keys(app)
        assert abs(game.player.x-9.5) < 1e-6 and abs(game.player.y-1.5) < 1e-6
        assert 'F 길의 방' in labels(app)
        return game
    def rune_pixels():
        picture(app)
        frame = pixels(app)
        for index,cell in enumerate(RUNES):
            reached = cell in app.game.connection.reached_runes
            color = ((250,209,116),(144,218,240))[index] if reached else ((197,155,89),(110,165,190))[index]
            sx,sy = app.view.world(cell[0]+.5,cell[1]+.5)
            count = sum(tuple(frame[(y*1280+x)*4:(y*1280+x)*4+3]) == color
                        for y in range(round((sy-18)*2),round((sy-4)*2))
                        for x in range(round((sx-8)*2),round((sx+8)*2)))
            assert count > 15,(index,reached,'rune hidden by slab art')
    def capture_window(width,height,name):
        picture(app)
        data = (ctypes.c_ubyte*(width*height*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,width*4) == 0
        surface = p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:
            path = app.output/name
            assert p.IMG_SavePNG(surface,str(path).encode('utf-8')) == 0
        finally:
            p.SDL_FreeSurface(surface)
    try:
        for width,height in ((1280,800),(960,600)):
            p.SDL_SetWindowSize(p.window,width,height)
            game = native_start()
            enter(width == 1280)
            # 9개 모두 원래 바닥 자리로 드롭하고 네 번 회전해 원상복구한다.
            for index,center in enumerate(LOOSE_POSITIONS):
                rotation = game.connection.pieces[index].rotation
                mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*center))
                assert game.connection.held == index
                for _ in range(4):press(app,p.SDLK_r)
                mouse(p.SDL_MOUSEMOTION,room_screen(*center))
                mouse(p.SDL_MOUSEBUTTONUP,room_screen(*center))
                assert game.connection.pieces[index].cell is None
                assert game.connection.pieces[index].rotation == rotation
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
            press(app,p.SDLK_r);press(app,p.SDLK_ESCAPE)
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
            # 별도 오답 사례: 출구만 연결/문양 하나만 연결해도 바닥은 열리지 않는다.
            for index,piece in enumerate(game.connection.pieces):
                if piece.cell is not None:
                    mouse(p.SDL_MOUSEBUTTONDOWN,connection_center(piece.cell))
                    mouse(p.SDL_MOUSEBUTTONUP,room_screen(*LOOSE_POSITIONS[index]))
            wrong_route = (((0,1),(0,2),(1,2),(2,2),(3,2)) if width == 1280 else
                           ((0,1),(1,1),(2,1),(2,2),(3,2)))
            for item in placement(wrong_route):put(*item)
            assert game.connection.exit_connected and not game.connection.completed
            assert len(game.connection.reached_runes) == (0 if width == 1280 else 1)
            assert any('문양이 빠졌습니다' in text for text in labels(app))
            rune_pixels()

            # 시간 측정은 새 회차의 보통 진입부터 시작하며 검사 중 타이머를 고치지 않는다.
            game = native_start();enter()
            advance(15.)
            mouse(p.SDL_MOUSEBUTTONDOWN,room_screen(*LOOSE_POSITIONS[8]))
            mouse(p.SDL_MOUSEMOTION,connection_center((0,3)))
            assert game.connection.held == 8
            assert max(abs(a-b) for a,b in zip(app.view.connection_pointer,connection_center((0,3)))) < 1.5
            rune_pixels();capture_window(width,height,f'runed-room-progress-{width}.png')
            mouse(p.SDL_MOUSEBUTTONUP,room_screen(*LOOSE_POSITIONS[8]))
            assert game.connection.pieces[8].cell is None
            route = ROUTES[0 if width == 1280 else 1]
            items = placement(route)
            for offset,item in enumerate(items):
                index,cell,ports = item
                if width == 960 and offset == len(items)-1:
                    put(index,cell,frozenset((port-1)%4 for port in ports))
                    assert not game.connection.completed
                    mouse(p.SDL_MOUSEBUTTONDOWN,connection_center(cell))
                    mouse(p.SDL_MOUSEBUTTONUP,connection_center(cell))
                    press(app,p.SDLK_r)
                else:put(*item)
                assert game.connection.reached_runes == frozenset(RUNES).intersection(route[:offset+1])
                if offset == 5:
                    # 입구를 떼면 표시도 즉시 미연결로 돌아가며 잘못 놓으면 복구된다.
                    first = items[0]
                    mouse(p.SDL_MOUSEBUTTONDOWN,connection_center(first[1]))
                    assert not game.connection.reached_runes
                    assert '태양 · 미연결' in labels(app) and '초승달 · 미연결' in labels(app)
                    mouse(p.SDL_MOUSEBUTTONUP,connection_center(items[1][1]))
                    assert game.connection.reached_runes == frozenset(RUNES).intersection(route[:offset+1])
            assert game.connection.completed and game.state == 'path_room' and not game.path_completed
            assert game.puzzle_reserved_phase is None and not game.puzzle_open
            assert '태양 · 연결됨' in labels(app) and '초승달 · 연결됨' in labels(app)
            rune_pixels()
            with patch.object(app.view,'line',wraps=app.view.line) as lines:
                picture(app)
            for left,top,right,bottom in game.world_path.barriers:
                ax,ay = app.view.world(left,top);bx,by = app.view.world(right,bottom)
                assert any(call.args == (ax,ay-4,bx,by-4,(174,161,126)) for call in lines.call_args_list)
            blocked = next((a,b) for a in route for b in route
                           if abs(a[0]-b[0])+abs(a[1]-b[1]) == 1
                           and abs(route.index(a)-route.index(b)) != 1)
            walk_to((-.5,1.5))
            tested_wall = False
            mapping = {(-1,0):p.SDLK_w,(1,0):p.SDLK_s,(0,-1):p.SDLK_d,(0,1):p.SDLK_a}
            for cell in route:
                point = cell[0]+.5,cell[1]+.5
                walk_to(point)
                assert game.state == 'path_room' and not game.path_completed
                if cell == blocked[0]:
                    dx,dy = blocked[1][0]-cell[0],blocked[1][1]-cell[1]
                    keys(app,(mapping[dx,dy],));tick(25);keys(app)
                    assert (game.player.x-point[0])*dx+(game.player.y-point[1])*dy <= .290001
                    walk_to(point);tested_wall = True
            assert tested_wall
            walk_to((4.5,2.5))
            assert game.state == 'path_room' and not game.path_completed
            capture_window(width,height,f'runed-room-complete-{width}.png')
            walk_to((5.6,2.5))
            assert game.state == 'explore' and game.path_completed and game.can_stand(game.player.x,game.player.y)
            assert (game.player.x,game.player.y)==(19.5,9.5) and game.path_exit in game.visited
            assert game.puzzle_reserved_phase is None and not game.attack_hits_ms
            forward_time = game.phase_time
            enter()
            assert game.world_path.reverse
            with patch.object(app.view,'text',wraps=app.view.text) as text:
                picture(app)
            ex,ey = app.view.world(-3,1.5);ox,oy = app.view.world(5.7,2.5)
            assert any(call.args[:3] == ('출구',ex,ey-84) for call in text.call_args_list)
            assert any(call.args[:3] == ('입구 · 후퇴',ox+30,oy+18) for call in text.call_args_list)
            assert any('맞은편 문까지' in call.args[0] for call in text.call_args_list)
            capture_window(width,height,f'runed-room-reverse-{width}.png')
            for point in ((4.5,2.5),*((x+.5,y+.5) for x,y in reversed(route)),(-.5,1.5),(-1.5,1.5),(-2.8,1.5)):
                walk_to(point)
            assert game.state == 'explore' and (game.player.x,game.player.y) == (8.5,1.5)
            assert game.phase_time < PHASE_SECONDS
            print(f'PASS: {width}x{height} actual 9 slabs: all loose slots/four rotations/shelf return, bad drop/Esc/focus rollback, missing-rune exit refusal, live rune pixels and closed-side SDL blocking; both rune orders solve.')
            print(f'PASS: {width}x{height} native torch/W/F/entry -> assemble -> physical exit -> reverse return; scripted 15s reading + edits + blocked-side attempt included: outward {forward_time:.2f}s, round trip {game.phase_time:.2f}s/60s; not human play timing.')
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
