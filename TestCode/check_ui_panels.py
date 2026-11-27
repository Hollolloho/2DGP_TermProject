"""선택 포커스·지도 입력 해제·결과 이유/R을 실제 SDL 이벤트로 검사한다."""
import ctypes
from unittest.mock import patch
from SourceCode.maze_model import Game,PHASE_SECONDS,TRAP_PLANES,blade_position,shortest_path
from SourceCode.game_view import CHOICE_CARD_RECTS,CHOICE_CONFIRM_RECT,RESULT_RESTART_RECT
from SourceCode.six_lane_trap import CYCLE_SECONDS
from SourceCode import ui_theme as ui


def run(app):
    import pico2d.pico2d as p
    from .check_game_render import inject_key,inject_mouse,regain_focus
    from .check_boulder_render import press,picture,pixels,labels,keys
    from .check_shortcut_choice import walk_cells
    original,original_course=app.game,app.test_course
    def fresh(course=True):
        app.test_course=course
        app.game=game=Game(117,player_clips=app.view.player_catalog['clips'],test_course=course)
        app.release_input();regain_focus(app);game.guard_hp=0;game.banner_until=0.
        return game
    def open_choice():
        game=fresh();x,y=game.choice_start
        game.player.x,game.player.y=x+.5,y+.5;game.update_visibility();press(app,p.SDLK_f)
        assert game.state=='puzzle' and game.puzzle_tab=='choice'
        return game
    def center(rect):
        x,y,w,h=rect;return x+w/2,y+h/2
    def mouse(kind,point,held=False):
        inject_mouse(kind,point,held);app.handle_events()
    def click(point):
        mouse(p.SDL_MOUSEBUTTONDOWN,point);mouse(p.SDL_MOUSEBUTTONUP,point)
    def capture(name,width,height):
        before=app.game.time,app.game.phase_time
        picture(app);app.game.ui_time+=.4;picture(app)
        assert before==(app.game.time,app.game.phase_time)
        assert app.view.output_size()==(width,height)
        data=(ctypes.c_ubyte*(width*height*4))()
        rect=p.SDL_Rect(0,0,width,height)
        assert p.SDL_RenderReadPixels(p.renderer,ctypes.byref(rect),p.SDL_PIXELFORMAT_RGBA32,data,width*4)==0
        assert len(set(data[::4]))>16
        frame=pixels(app)
        assert sum(frame[i:i+3]==bytes(ui.TEXT) for i in range(0,len(frame),4))>=12
        surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:assert p.IMG_SavePNG(surface,str(app.output/f'{name}-{width}x{height}.png').encode('utf-8'))==0
        finally:p.SDL_FreeSurface(surface)
    def pixel(x,y):
        frame=pixels(app);offset=(y*2*1280+x*2)*4
        return tuple(frame[offset:offset+3])
    try:
        for width,height in ((1280,800),(960,600),(1280,720),(1920,1080),(2560,1080)):
            p.SDL_SetWindowSize(p.window,width,height)
            game=open_choice()
            saved=tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            assert app.view.choice_focus==0 and game.shortcut_choice.preview is None
            capture('choice-focus',width,height)
            x,y,_,_=CHOICE_CARD_RECTS[0]
            assert pixel(x+5,y+5)==ui.FOCUS
            press(app,p.SDLK_DOWN);press(app,p.SDLK_RETURN)
            assert app.view.choice_focus==2 and game.shortcut_choice.preview is None and not game.choice_confirm_requested
            capture('choice-disabled',width,height)
            press(app,p.SDLK_UP);press(app,p.SDLK_RIGHT)
            assert app.view.choice_focus==1 and game.shortcut_choice.preview is None
            press(app,p.SDLK_RETURN);press(app,p.SDLK_RETURN);app.update(.02)
            assert game.shortcut_choice.preview==1 and game.shortcut_choice.selected is None
            assert not app.held and not game.attack_hits_ms
            press(app,p.SDLK_ESCAPE);press(app,p.SDLK_f)
            assert app.view.choice_focus==1 and game.shortcut_choice.preview==1
            mouse(p.SDL_MOUSEMOTION,center(CHOICE_CARD_RECTS[0]))
            assert app.view.choice_focus==1 and app.view.choice_hover==0
            capture('choice-draft-hover',width,height)
            x,y,_,_=CHOICE_CARD_RECTS[1]
            assert pixel(x,y)==ui.BRASS and pixel(x+5,y+5)==ui.FOCUS
            press(app,p.SDLK_TAB);assert app.view.choice_focus==2
            press(app,p.SDLK_RETURN)
            assert game.choice_confirm_requested and game.shortcut_choice.selected is None
            assert '확정 처리 대기' in labels(app)
            capture('choice-pending',width,height)
            press(app,p.SDLK_LEFT);click(center(CHOICE_CARD_RECTS[0]))
            assert app.view.choice_focus==2 and game.choice_confirm_requested and game.shortcut_choice.preview==1
            assert saved==tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            app.update(.02)
            assert game.state=='explore' and game.shortcut_choice.selected==1
            assert not app.held and not game.attack_hits_ms and not app.puzzle_mouse_held

            game=open_choice();click(center(CHOICE_CARD_RECTS[0]))
            press(app,p.SDLK_RETURN)
            assert game.shortcut_choice.preview==0 and not game.choice_confirm_requested
            # Shift+Tab 순환도 임시 선택이나 확정을 실행하지 않는다.
            event=p.SDL_Event();event.type=p.SDL_KEYDOWN;event.key.keysym.sym=p.SDLK_TAB;event.key.keysym.mod=p.KMOD_SHIFT
            assert p.SDL_PushEvent(event)==1;app.handle_events()
            assert app.view.choice_focus==2 and game.shortcut_choice.preview==0
            press(app,p.SDLK_RETURN)
            press(app,p.SDLK_ESCAPE);app.update(.02)
            assert game.state=='explore' and game.shortcut_choice.selected is None and not game.attack_hits_ms

            game=fresh();walk_cells(game,shortest_path(game.grid,game.spawn,game.exit)[:12]);press(app,p.SDLK_m)
            saved=tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            discovered=game.trap_discovered,game.boulder_discovered,game.path_discovered
            game.trap_discovered=game.boulder_discovered=game.path_discovered=False
            with patch.object(app.view,'badge',wraps=app.view.badge) as badges:
                app.view.map_overlay(game)
            assert not badges.called
            game.trap_discovered,game.boulder_discovered,game.path_discovered=discovered
            capture('map',width,height)
            assert saved==tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            position=game.player.x,game.player.y
            keys(app,(p.SDLK_w,));app.update(.02);press(app,p.SDLK_ESCAPE)
            assert not game.map_open and not app.held
            app.update(.05)
            assert position==(game.player.x,game.player.y)
            inject_key(p.SDLK_w,False);app.handle_events()

            game=fresh();x,y=game.exit
            game.player.x,game.player.y=x+.5,y+.5;game.update_visibility();press(app,p.SDLK_f)
            assert game.state=='clear' and '중앙 로프에서 탈출했습니다' in labels(app)
            capture('result-clear',width,height)
            press(app,p.SDLK_RETURN)
            assert app.game is not game and app.game.state=='explore' and app.game.test_course and not app.held
            assert not app.game.attack_hits_ms
            restarted=app.game
            event=p.SDL_Event();event.type=p.SDL_KEYDOWN;event.key.keysym.sym=p.SDLK_RETURN;event.key.repeat=1
            assert p.SDL_PushEvent(event)==1;app.handle_events();app.update(.02)
            assert app.game is restarted and app.game.run_number==0 and not app.held and not app.game.attack_hits_ms
            game=fresh(False);game.player.hp=15;game.take_guard_hit()
            assert game.state=='failed' and game.player.hp==0
            assert '수호자의 공격으로 체력을 모두 잃었습니다' in labels(app)
            capture('result-guardian',width,height)
            mouse(p.SDL_MOUSEBUTTONDOWN,center(RESULT_RESTART_RECT))
            assert app.game.run_number==1 and app.game.phase==1 and app.game.player.hp==100 and not app.held
            assert app.puzzle_mouse_held
            mouse(p.SDL_MOUSEMOTION,(320,340),True);app.update(.02)
            assert not app.game.attack_hits_ms and (app.game.player.x,app.game.player.y)==tuple(n+.5 for n in app.game.spawn)
            mouse(p.SDL_MOUSEBUTTONUP,center(RESULT_RESTART_RECT))
            assert not app.puzzle_mouse_held
            print(f'PASS: {width}x{height} focus/hover/draft/disabled/pending pixels, separate keyboard confirm, mixed input without attack/movement leak, private map + Esc release, result reason and course/general R.')

        for cause in ('focus','hit','phase'):
            game=open_choice();press(app,p.SDLK_RETURN);press(app,p.SDLK_DOWN);press(app,p.SDLK_RETURN)
            assert game.choice_confirm_requested
            if cause=='focus':
                event=p.SDL_Event();event.type=p.SDL_WINDOWEVENT;event.window.event=p.SDL_WINDOWEVENT_FOCUS_LOST
                assert p.SDL_PushEvent(event)==1;app.handle_events()
            elif cause=='phase':game.phase_time=PHASE_SECONDS-.01
            else:game.guard=game.choice_start;game.guard_hp=3;game.guard_attack_at=game.time+.01
            app.update(.02)
            assert game.shortcut_choice.selected is None and not game.choice_confirm_requested and not app.held
            if cause=='focus':regain_focus(app)
            if cause=='phase':assert game.state=='shifting' and game.shortcut_choice.preview is None
            elif cause=='hit':assert game.state=='explore' and game.player.hp==85

        p.SDL_SetWindowSize(p.window,1280,800)
        game=fresh();x,y=game.trap_cell;game.player.x,game.player.y=x+.5,y+.5
        game.update_visibility();press(app,p.SDLK_f);game.player.hp=20
        game.trap_progress=TRAP_PLANES[0];game.trap_x=blade_position(game.time+.02,0)
        app.update(.02)
        assert game.state=='failed' and '칼날에 맞아 체력을 모두 잃었습니다' in labels(app)
        capture('result-blade',1280,800)
        game=fresh();x,y=game.boulder_entry;game.player.x,game.player.y=x+.5,y+.5
        game.update_visibility();press(app,p.SDLK_f);room=game.boulder_room
        room.x,room.z=0.,4.5;room.phase_offsets[0]=CYCLE_SECONDS/2-room.time
        app.update(.02)
        assert game.state=='failed' and '돌에 깔렸습니다' in labels(app)
        capture('result-boulder',1280,800)
        print('PASS: focus loss, guardian hit and phase beat keyboard confirmation; actual fatal blade/boulder branches provide the result reason without rule changes.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.test_course=original_course;app.game=original;app.release_input();regain_focus(app);picture(app)


if __name__=='__main__':
    from . import check_ui_layout
    check_ui_layout.run=run
    check_ui_layout.main()
