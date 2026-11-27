"""숏컷 비교·확정·예약·직접 보행을 실제 SDL 이벤트로 검사한다. 사람 플레이 기록은 아니다."""
from math import ceil
import ctypes
import pico2d.pico2d as p
from SourceCode.maze_model import Game,PHASE_SECONDS,shortest_path
from SourceCode.shortcut_choice import CHOICE_START,CHOICE_GOAL
from SourceCode.game_view import CHOICE_CARD_RECTS,CHOICE_CONFIRM_RECT
from SourceCode import ui_theme as ui
from .check_game_render import inject_mouse, regain_focus
from .check_boulder_render import keys,press,picture,pixels,labels


def run(app):
    original = app.game
    def mouse(kind,point,held=True):
        inject_mouse(kind,point,held);app.handle_events()
    def click(point):
        mouse(p.SDL_MOUSEBUTTONDOWN,point);mouse(p.SDL_MOUSEBUTTONUP,point)
    def center(rect):
        x,y,w,h = rect
        return x+w/2,y+h/2
    def advance(seconds):
        count = max(1,ceil(seconds/.05))
        for _ in range(count):app.update(seconds/count);picture(app)
    def fresh(at_start=False):
        app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
        app.release_input()
        if at_start:game.player.x,game.player.y = CHOICE_START[0]+.5,CHOICE_START[1]+.5
        game.update_visibility();picture(app)
        return game
    def walk(route,observe=None):
        mapping = {(-1,0):p.SDLK_w,(1,0):p.SDLK_s,(0,-1):p.SDLK_d,(0,1):p.SDLK_a}
        game = app.game
        for cell in route:
            for _ in range(100):
                dx,dy = cell[0]+.5-game.player.x,cell[1]+.5-game.player.y
                if max(abs(dx),abs(dy)) < 1e-5:break
                if abs(dx) > 1e-5:direction,distance = (1 if dx > 0 else -1,0),abs(dx)
                else:direction,distance = (0,1 if dy > 0 else -1),abs(dy)
                keys(app,(mapping[direction],));app.update(min(.02,distance/2.5));picture(app)
                if observe is not None:observe()
                assert game.state == 'explore'
            else:raise AssertionError(('SDL walk blocked',cell,game.player.x,game.player.y))
            keys(app)
    def capture(name,width,height):
        picture(app)
        actual_width,actual_height = ctypes.c_int(),ctypes.c_int()
        assert p.SDL_GetRendererOutputSize(p.renderer,ctypes.byref(actual_width),ctypes.byref(actual_height)) == 0
        actual = actual_width.value,actual_height.value
        assert actual == (width,height),('capture_size',actual,(width,height))
        data = (ctypes.c_ubyte*(width*height*4))()
        region = p.SDL_Rect(0,0,width,height)
        assert p.SDL_RenderReadPixels(p.renderer,ctypes.byref(region),p.SDL_PIXELFORMAT_RGBA32,data,width*4) == 0
        surface = p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:assert p.IMG_SavePNG(surface,str(app.output/name).encode('utf-8')) == 0
        finally:p.SDL_FreeSurface(surface)
    def open_panel(game):
        press(app,p.SDLK_f)
        assert game.state == 'puzzle' and game.puzzle_tab == 'choice'
    try:
        for width,height,index in ((1280,800,0),(960,600,1)):
            p.SDL_SetWindowSize(p.window,width,height)
            game = fresh()
            if width == 1280:
                try:capture('invalid-output-size.png',width-1,height)
                except AssertionError as error:assert error.args[0][0] == 'capture_size'
                else:raise AssertionError('mismatched renderer size was read into a smaller buffer')
            game.guard_hp = 0  # 이 사례는 입력·충돌·경로를 분리 검증한다.
            press(app,p.SDLK_f);assert game.player.torch
            walk(shortest_path(game.grid,game.spawn,CHOICE_START))
            assert 'F 숏컷 비교' in labels(app)
            open_panel(game)
            saved = tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            click(center(CHOICE_CONFIRM_RECT));advance(.02)
            assert game.shortcut_choice.selected is None and not game.choice_confirm_requested
            click(center(CHOICE_CARD_RECTS[1-index]));click(center(CHOICE_CARD_RECTS[index]))
            assert game.shortcut_choice.preview == index and game.shortcut_choice.selected is None
            before = game.phase_time;advance(.2)
            assert game.phase_time > before and game.state == 'puzzle'
            text = labels(app)
            assert all(any(value in item for item in text) for value in ('1번 통로','2번 통로','12칸','14칸','기준 노출 0곳','다음 밤 개방','이 경로 확정'))
            assert saved == tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            frame = pixels(app)
            for x,y,w,h in CHOICE_CARD_RECTS:
                color = tuple(frame[(round(y)*2*1280+round(x)*2)*4:][:3])
                assert color == (ui.BRASS if CHOICE_CARD_RECTS[index] == (x,y,w,h) else ui.RULE)
            capture(f'choice-compare-{width}.png',width,height)
            press(app,p.SDLK_ESCAPE)
            assert game.state == 'explore' and game.shortcut_choice.preview == index
            open_panel(game)
            assert game.shortcut_choice.preview == index
            click(center(CHOICE_CONFIRM_RECT))
            assert game.choice_confirm_requested and game.shortcut_choice.selected is None
            mouse(p.SDL_MOUSEMOTION,(80,90),False)
            click(center(CHOICE_CARD_RECTS[1-index]))
            assert game.choice_confirm_requested and game.shortcut_choice.preview == index
            advance(.02)
            assert game.state == 'explore' and game.shortcut_choice.selected == index
            selected,other = game.route_options[index],game.route_options[1-index]
            assert not game.shortcut_choice.opened and all(game.grid[o.gate[1]][o.gate[0]] for o in game.route_options)
            assert game.puzzle_reserved_phase is None
            capture(f'choice-reserved-{width}.png',width,height)
            game.phase_time = PHASE_SECONDS-.01;advance(.02)
            advance(.2);assert not game.shortcut_choice.opened
            advance(.15);assert game.shortcut_choice.opened
            advance(.3)
            assert game.state == 'explore' and game.grid[other.gate[1]][other.gate[0]] == 1
            gait = game.player.gait_distance
            walk(selected.path)
            assert (game.player.x,game.player.y) == (CHOICE_GOAL[0]+.5,CHOICE_GOAL[1]+.5)
            assert selected.gate in game.visited and game.player.gait_distance > gait
            capture(f'choice-arrival-{width}.png',width,height)
            walk(tuple(reversed(selected.path)))
            walk(shortest_path(game.maze_layouts.grids[game.phase],CHOICE_START,CHOICE_GOAL))
            # 미선택 벽에도 SDL 이동을 보내 열린 후보와 구분한다.
            before_cell = other.path[other.path.index(other.gate)-1]
            game.player.x,game.player.y = before_cell[0]+.5,before_cell[1]+.5
            dx,dy = other.gate[0]-before_cell[0],other.gate[1]-before_cell[1]
            mapping = {(-1,0):p.SDLK_w,(1,0):p.SDLK_s,(0,-1):p.SDLK_d,(0,1):p.SDLK_a}
            keys(app,(mapping[dx,dy],));advance(.5);keys(app)
            assert abs(game.player.x-before_cell[0]-.5)*abs(dx)+abs(game.player.y-before_cell[1]-.5)*abs(dy) <= .290001
            print(f'PASS: {width}x{height} SDL spawn/torch/WASD to U, two scaled route cards, click-only draft, separate queued confirm, next swap only, choice {index+1} real two-way walk, closed other gate and ordinary route; comparison does not reveal visited map.')

        # A generated route with different endpoints must be reachable through
        # the normal interaction and use its own mini-map and next-phase door.
        app.game = game = Game(117,2,player_clips=app.view.player_catalog['clips'])
        app.release_input()
        game.guard_hp = 0
        assert game.route_options and game.choice_start != CHOICE_START
        walk(shortest_path(game.grid,game.spawn,game.choice_start))
        open_panel(game)
        assert game.route_options[0].label in labels(app)
        click(center(CHOICE_CARD_RECTS[0]))
        click(center(CHOICE_CONFIRM_RECT))
        app.update(.02)
        assert game.shortcut_choice.selected==0
        game.phase_time=PHASE_SECONDS-.01
        advance(.8)
        walk(game.route_options[0].path)
        walk(game.route_options[0].path[::-1])
        print('PASS: generated seed 117/run 2 SDL route from spawn, cards, reservation and round trip.')

        # 같은 밤·U·초기 수호자로 두 길을 자동 보행한다. 중앙 칸 노출 수와 실시간 추적은 구분한다.
        for index in (0,1):
            game = fresh(True);game.guard_hp = 0;open_panel(game)
            click(center(CHOICE_CARD_RECTS[index]));click(center(CHOICE_CONFIRM_RECT));advance(.02)
            game.phase_time = PHASE_SECONDS-.01;advance(.02);advance(.65)
            game.guard = game.guard_home;game.guard_hp = 3
            game.guard_seen_until = game.guard_ready_at = game.guard_alert_until = 0.
            game.guard_attack_at = None
            observed = {'noticed':False,'moved':False}
            def observe():
                observed['noticed'] |= game.guard_seen_until > game.time
                observed['moved'] |= (game.guard_x,game.guard_y) != (game.guard_home[0]+.5,game.guard_home[1]+.5)
            start = game.time
            walk(game.route_options[index].path,observe)
            assert observed['noticed'] == (index == 0) and observed['moved'] == (index == 0)
            assert (game.player.x,game.player.y) == (CHOICE_GOAL[0]+.5,CHOICE_GOAL[1]+.5)
            print(f'PASS: reference SDL night/U/initial guardian, route {index+1}: {game.time-start:.2f}s, noticed={observed["noticed"]}, pursuit={observed["moved"]}, HP lost={100-game.player.hp}; automated fixed input, not human safety/playtime evidence.')

        # 동시 입력은 별도 사례로 검사해 보통 경로의 보행과 구분한다.
        for cause in ('escape','focus','hit','phase'):
            game = fresh(True);open_panel(game)
            click(center(CHOICE_CARD_RECTS[1]))
            before = game.time
            if cause == 'hit':
                game.guard = (23,9)
                position = game.guard_x,game.guard_y
                advance(.2)
                assert game.time > before and (game.guard_x,game.guard_y) != position
                game.guard = CHOICE_START;game.guard_attack_at = game.time+.01
            mouse(p.SDL_MOUSEBUTTONDOWN,center(CHOICE_CONFIRM_RECT))
            assert game.choice_confirm_requested
            if cause == 'escape':press(app,p.SDLK_ESCAPE)
            elif cause == 'phase':game.phase_time = PHASE_SECONDS-.01
            elif cause == 'focus':
                event=p.SDL_Event();event.type=p.SDL_WINDOWEVENT;event.window.event=p.SDL_WINDOWEVENT_FOCUS_LOST
                assert p.SDL_PushEvent(event)==1
                app.handle_events()
            app.update(.02)
            assert game.shortcut_choice.selected is None and not game.choice_confirm_requested
            if cause == 'focus':regain_focus(app)
            if cause == 'phase':assert game.shortcut_choice.preview is None and game.state == 'shifting'
            else:assert game.shortcut_choice.preview == 1
            if cause == 'hit':assert game.player.hp == 85 and game.state == 'explore'
            mouse(p.SDL_MOUSEBUTTONDOWN,(610,90));assert not game.attack_hits_ms
            mouse(p.SDL_MOUSEBUTTONUP,(610,90))
        game = fresh(True);open_panel(game);click(center(CHOICE_CARD_RECTS[0]))
        press(app,p.SDLK_r)
        assert app.game is not game and app.game.shortcut_choice.preview is None
        assert app.game.shortcut_choice.selected is None and not app.game.shortcut_choice.opened
        print('PASS: actual SDL Esc/focus/hit/phase beats pending confirm without attack leak; same-phase draft survives, guardian/time run in comparison, R resets all choice records.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.game = original;app.release_input();picture(app)
