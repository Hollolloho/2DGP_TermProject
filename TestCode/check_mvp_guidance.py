"""목표와 선택 가능한 검수 코스 추천. 모델 기록을 바꾸지 않고 기존 상태를 읽는다."""
import ctypes
import math
from unittest.mock import patch
from SourceCode.maze_model import Game
from SourceCode.game_view import View,GOAL_HUD_RECT,PHASE_HUD_RECT,LW,LH


def course():
    game = Game(117,test_course=True)
    game.banner_until = 0.
    return game


def check_text():
    general = Game(117)
    assert not View.course_recommendation(general)
    game = course()
    assert View.course_recommendation(game) == ('횃불에 다가가 F',)
    game.player.torch = True
    assert 'A 칼날방' in ' '.join(View.course_recommendation(game))
    game.trap_completed = True
    assert '다음 C 돌방' in ' '.join(View.course_recommendation(game))
    game.boulder_completed = True
    assert '다음 P 마우스 문' in ' '.join(View.course_recommendation(game))
    game.puzzle_reserved_phase = game.next_phase
    assert View.course_recommendation(game) == ('P 예약됨','다음 밤에 열림')
    game.puzzle_reserved_phase,game.puzzle_open = None,True
    assert 'L 석판 방에서' in ' '.join(View.course_recommendation(game))
    game.connection.completed = True
    assert '맞은편까지 걷기' in ' '.join(View.course_recommendation(game)) and not game.path_completed
    game.path_completed = True
    assert 'U에서 두 경로 비교' in View.course_recommendation(game)
    game.shortcut_choice.select(1);game.shortcut_choice.confirm(game.next_phase)
    assert View.course_recommendation(game) == ('2번 통로 예약','다음 밤에 열림')
    game.shortcut_choice.apply_phase(game.next_phase)
    assert View.course_recommendation(game) == ('2번 문 통과','중앙 로프에서 F')
    # 앞 단계를 건너뛰어도 이미 진행한 후속 단계로부터 이전 확인을 강요하지 않는다.
    skipped = course();skipped.path_completed = True
    assert 'U에서 두 경로 비교' in View.course_recommendation(skipped)
    skipped.shortcut_choice.select(0);skipped.shortcut_choice.confirm(skipped.next_phase)
    assert '1번 통로 예약' in View.course_recommendation(skipped)
    for state in ('puzzle','trap','path_room','shifting','clear','failed'):
        game.state = state
        assert not View.course_recommendation(game)
    game.state = 'explore'
    game.map_open = True;assert not View.course_recommendation(game);game.map_open = False
    game.phase_warning = True;assert not View.course_recommendation(game);game.phase_warning = False
    game.guard_attack_at = game.time+1;assert not View.course_recommendation(game);game.guard_attack_at = None
    game.message('시간대 전환으로 입장 위치 복귀',5)
    assert not View.course_recommendation(game)
    assert View.course_recommendation(course()) == ('횃불에 다가가 F',)
    # 진행 플래그 없이도 중앙 로프에서 F 탈출은 그대로 허용된다.
    skipped = course();x,y = skipped.exit
    skipped.player.x,skipped.player.y = x+.5,y+.5
    skipped.update_visibility();skipped.interact()
    assert skipped.state == 'clear' and not skipped.trap_completed and not skipped.path_completed
    print('PASS: general/course separation, draft/reserved/open/assembled/crossed guidance, skipped stages, hidden UI states, priority and fresh reset; course exit remains optional.')


def run(app):
    import pico2d.pico2d as p
    from .check_boulder_render import press,labels,picture
    from .check_game_render import regain_focus
    original = app.game
    original_course = app.test_course
    def capture(name,width,height,glyph=None):
        world_clock = app.game.time,app.game.phase_time,app.game.guard_attack_at,app.game.attack_time
        picture(app)
        # 새 검사 인스턴스의 화면 전환만 끝낸다. 공격·물리·시간대 시계는 유지한다.
        app.game.ui_time += .4
        picture(app)
        assert world_clock == (app.game.time,app.game.phase_time,app.game.guard_attack_at,app.game.attack_time)
        actual_width,actual_height = ctypes.c_int(),ctypes.c_int()
        assert p.SDL_GetRendererOutputSize(p.renderer,ctypes.byref(actual_width),ctypes.byref(actual_height)) == 0
        assert (actual_width.value,actual_height.value) == (width,height)
        data = (ctypes.c_ubyte*(width*height*4))()
        rect = p.SDL_Rect(0,0,width,height)
        assert p.SDL_RenderReadPixels(p.renderer,ctypes.byref(rect),p.SDL_PIXELFORMAT_RGBA32,data,width*4) == 0
        assert len(set(data[::4])) > 16,'capture is still covered by the transition fade'
        if glyph is not None:
            (x,y,w,h),color = glyph
            count = sum(tuple(data[(row*width+col)*4:(row*width+col)*4+3]) == color
                        for row in range(round(y*height/LH),round((y+h)*height/LH))
                        for col in range(round(x*width/LW),round((x+w)*width/LW)))
            assert count >= 12,(name,'HUD glyph pixels missing',count)
        surface = p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:assert p.IMG_SavePNG(surface,str(app.output/name).encode('utf-8')) == 0
        finally:p.SDL_FreeSurface(surface)
    try:
        check_text()
        assert GOAL_HUD_RECT[0]+GOAL_HUD_RECT[2] < PHASE_HUD_RECT[0]
        for width,height in ((1280,800),(960,600)):
            p.SDL_SetWindowSize(p.window,width,height);regain_focus(app)
            app.test_course = True
            app.game = game = Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
            app.release_input();game.guard_hp = 0
            picture(app);game.ui_time += .4
            assert '목표: 중앙 로프에서 F 탈출' in labels(app)
            assert app.view.text_cache['목표: 중앙 로프에서 F 탈출',(219,211,183),'font'].w <= 190
            press(app,p.SDLK_f)
            assert game.player.torch
            for _ in range(65):app.update(.05)
            assert '추천: A 칼날방' in labels(app)
            # 안내 함수와 그리기가 플레이 기록을 바꾸지 않는다.
            saved = tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            for _ in range(3):picture(app)
            assert saved == tuple((set(a),set(b)) for a,b in zip(game.observed_by_phase,game.visited_by_phase))
            capture(f'mvp-guidance-course-{width}.png',width,height)
            for setup in ('p-reserved','p-open','assembled','crossed','choice-reserved','choice-open'):
                game.banner_until = 0.
                if setup == 'p-reserved':game.puzzle_reserved_phase = game.next_phase
                elif setup == 'p-open':game.puzzle_reserved_phase,game.puzzle_open = None,True
                elif setup == 'assembled':game.connection.completed = True
                elif setup == 'crossed':game.path_completed = True
                elif setup == 'choice-reserved':game.shortcut_choice.select(0);game.shortcut_choice.confirm(game.next_phase)
                else:game.shortcut_choice.apply_phase(game.next_phase)
                picture(app)
                lines = View.course_recommendation(game)
                for index,line in enumerate(lines):
                    text = ('추천: ' if index == 0 else '')+line
                    assert app.view.text_cache[text,(200,206,182),'small'].w <= 190,(setup,text)
            press(app,p.SDLK_m)
            assert not any(text.startswith(('목표:','추천:')) for text in labels(app))
            press(app,p.SDLK_ESCAPE)
            game.phase_warning = True
            assert not any(text.startswith(('목표:','추천:')) for text in labels(app))
            game.phase_warning = False
            game.guard_attack_at = game.time+1
            assert not any(text.startswith(('목표:','추천:')) for text in labels(app))
            game.guard_attack_at = None
            for state in ('clear','failed'):
                game.state = state
                assert not any(text.startswith(('목표:','추천:')) for text in labels(app))
            press(app,p.SDLK_r)
            assert app.game.test_course and not app.game.player.torch
            assert '목표: 중앙 로프에서 F 탈출' in labels(app)
            # 실제 P와 석판 방 진입 중에도 탐색 목표를 덮어 쓰지 않는다.
            app.game = panel = Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
            panel.guard_hp = 0;app.release_input()
            for cell in (panel.puzzle_gate[1],panel.path_entry):
                panel.player.x,panel.player.y = cell[0]+.5,cell[1]+.5
                panel.update_visibility();press(app,p.SDLK_f)
                assert panel.state in ('puzzle','path_room')
                assert not any(text.startswith(('목표:','추천:')) for text in labels(app))
                press(app,p.SDLK_ESCAPE)
            app.test_course = False
            app.game = game = Game(0,player_clips=app.view.player_catalog['clips'])
            app.release_input();picture(app);game.ui_time += .4
            text = labels(app)
            assert '목표: 중앙 로프에서 F 탈출' in text and not any(value.startswith('추천:') for value in text)
            capture(f'mvp-guidance-general-{width}.png',width,height)
            print(f'PASS: {width}x{height} SDL torch changes course recommendation, all guidance text fits, map/warning hiding, R reset and general-only goal; no fog/visit changes.')
            # 같은 공격 예고를 실제 AI 갱신으로 만들고 두 퍼즐 화면에서 확인한다.
            app.test_course = True
            for kind in ('choice','maze'):
                app.game = game = Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
                app.release_input()
                cell = game.choice_start if kind == 'choice' else game.puzzle_gate[1]
                game.player.x,game.player.y = cell[0]+.5,cell[1]+.5
                game.guard = cell;game.update_visibility();press(app,p.SDLK_f)
                assert game.state == 'puzzle' and game.puzzle_tab == kind
                app.update(.02)
                assert game.guard_attack_at is not None
                assert '수호자 공격 예고' in labels(app)
                if kind == 'choice':
                    title = app.view.text_cache['숏컷 경로 선택',(232,217,180),'title']
                    warning = app.view.text_cache['수호자 공격 예고',(239,164,109),'font']
                    assert 320+title.w/2+8 < 480-warning.w/2
                    capture(f'mvp-guidance-choice-warning-{width}.png',width,height,
                            ((420,51,120,20),(239,164,109)))
            # 실제 SDL 상대 이동으로 옆과 뒤를 봐도 좌우 기준은 입장 정면이다.
            app.game = game = Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
            app.release_input();game.guard_hp = 0
            x,y = game.boulder_entry;game.player.x,game.player.y = x+.5,y+.5
            game.update_visibility();press(app,p.SDLK_f)
            assert game.state == 'trap' and game.trap_kind == 'boulder'
            room = game.boulder_room
            original_position = room.x,room.z
            def motion(relative_x):
                event=p.SDL_Event();event.type=p.SDL_MOUSEMOTION;event.motion.xrel=relative_x
                assert p.SDL_PushEvent(event)==1
                app.handle_events()
            motion(0)
            for quarter in (1,2):
                motion(600)
                assert abs(abs(room.yaw)-quarter*math.pi/2) < 1e-6
                assert (room.x,room.z) == original_position
                text = labels(app)
                status = next(value for value in text if '(입장 방향 기준)' in value)
                assert '왼쪽 → 오른쪽' in status
                assert app.view.text_cache[status,(228,204,153),'font'].w < 440
            capture(f'mvp-guidance-boulder-back-{width}.png',width,height,
                    ((12,350,450,24),(228,204,153)))
            print(f'PASS: {width}x{height} actual guardian windup is visible on both puzzle panels; SDL 90/180 look keeps entry-relative rock direction and clear HUD spacing.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.test_course = original_course
        app.game = original;app.release_input();regain_focus(app);picture(app)


if __name__ == '__main__':
    check_text()
