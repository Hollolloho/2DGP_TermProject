"""전체 폭 미로와 고정 HUD의 표시·상호작용·방문 지도 검사."""
from unittest.mock import patch

import pico2d.pico2d as p
from SourceCode.maze_model import Game
from SourceCode.game_view import MAP_RECT, PHASE_HUD_RECT, VITALS_HUD_RECT
from .check_boulder_render import press, step, labels, pixels


def run(app):
    original = app.game
    app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
    app.release_input()
    view = app.view
    try:
        game.player.hp,game.player.stamina = 73,42.
        view.draw(game)
        game.ui_time += .4
        with patch.object(view,'hud_panel',wraps=view.hud_panel) as panel:
            texts = labels(app)
        assert MAP_RECT == (0,0,640,400) and view.world_scale == 1
        assert PHASE_HUD_RECT in [call.args[0] for call in panel.call_args_list]
        assert not any(call.args[0][0] < 153 and call.args[0][1] >= 318 for call in panel.call_args_list)
        assert '낮 · 60초' in texts and ' 73' in texts and ' 42' in texts
        assert texts.count('F 횃불 획득') == 1
        assert not any(any(old in text for old in ('FPS','WASD','두 키 조합','F  상호작용','미궁 탐색')) for text in texts)
        for name,hp,stamina in (('full',100,100.),('partial',73,42.),('empty',0,0.)):
            game.player.hp,game.player.stamina = hp,stamina
            texts = labels(app)
            assert f'{hp:3d}' in texts and f'{int(stamina):3d}' in texts
            frame = pixels(app)
            def rgb(x,y):
                index = ((y*2)*1280+x*2)*4
                return tuple(frame[index:index+3])
            for y,height,value,color in ((356,6,hp,(155,76,59)),(370,4,stamina,(110,130,91))):
                for row in range(y-height//2,y+height//2):
                    for x in range(40,124):
                        expected = color if x < 40+round(84*value/100) else (35,32,29)
                        assert rgb(x,row) == expected,(name,x,row)
                assert rgb(39,y) == (8,11,12) and rgb(124,y) == (8,11,12)
            view.capture(app.output/f'hud/vitals-{name}.png')
            with patch.object(view,'hud_vitals',lambda game:None):
                view.draw(game)
                baseline = pixels(app)
            changed = [index//4 for index in range(0,len(frame),4)
                       if frame[index:index+4] != baseline[index:index+4]]
            x,y,w,h = VITALS_HUD_RECT
            assert changed and len(changed) < 8000
            assert all(x*2 <= point%1280 < (x+w)*2 and y*2 <= point//1280 < (y+h)*2
                       for point in changed), 'vitals cover the former panel or spill outside their bounds'
        game.player.hp,game.player.stamina = 73,42.
        view.draw(game)
        a,b = view.world(0,0),view.world(1,0)
        assert (b[0]-a[0],b[1]-a[1]) == (32,16)
        view.capture(app.output/'hud/01-explore.png')
        game.player.x,game.player.y = 9.5,4.9
        game.update_visibility()
        assert not any(text.startswith('F ') for text in labels(app)), 'F hint outside interaction range'
        press(app,p.SDLK_m)
        before = game.time
        step(app)
        assert game.map_open and game.time > before
        view.draw(game)
        view.capture(app.output/'hud/02-map.png')
        press(app,p.SDLK_ESCAPE)
        assert not game.map_open and app.running
        game.puzzle_reserved_phase = game.next_phase
        texts = labels(app)
        assert '다음 밤 개방 예정' in texts and 'F 퍼즐' not in texts
        view.capture(app.output/'hud/04-puzzle-reserved.png')
        game.puzzle_reserved_phase,game.puzzle_open = None,True
        wall = game.puzzle_gate[0]
        game.grid[wall[1]][wall[0]] = 0
        texts = labels(app)
        assert '퍼즐 통로 개방됨' in texts and 'F 퍼즐' not in texts
        view.capture(app.output/'hud/05-puzzle-open.png')
        game.phase_time,game.phase_warning = 55.,True
        assert '곧 밤 · 05초' in labels(app)
        view.capture(app.output/'hud/03-phase-warning.png')
        # 사용한 샘도 F 입력을 소비하므로 겹친 퍼즐 안내와 P 배지를 숨기지 않는다.
        app.game = overlap = Game(25,player_clips=view.player_catalog['clips'])
        overlap.player.x,overlap.player.y = 5.5,2.25
        overlap.player.torch,overlap.fountain_used = True,True
        overlap.update_visibility()
        assert overlap.puzzle_available() and overlap.close_to(overlap.fountain)
        with patch.object(view,'badge',wraps=view.badge) as badge:
            texts = labels(app)
        assert 'F 퍼즐' not in texts
        assert any(call.args[0] == 'P' for call in badge.call_args_list)
        press(app,p.SDLK_f)
        assert overlap.state == 'explore' and overlap.banner == '이미 사용한 샘물입니다'
        print('PASS: frameless 84px HP/ST tracks at 6/4px, full/partial/zero values and fixed bounds; unoccupied scenery stays visible.')
        print('PASS: full-width 32/16 projection, phase HUD, contextual F, no sidebar/debug list and live M map.')
        print('PASS: used-fountain/puzzle overlap matches F input priority and preserves the P badge.')
        from .check_mvp_guidance import run as check_mvp_guidance
        check_mvp_guidance(app)
    finally:
        app.game = original
        app.release_input()
        view.draw(original)
