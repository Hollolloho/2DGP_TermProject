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
        assert VITALS_HUD_RECT in [call.args[0] for call in panel.call_args_list]
        assert '낮 · 60초' in texts and ' 73' in texts and ' 42' in texts
        assert texts.count('F 횃불 획득') == 1
        assert not any(any(old in text for old in ('FPS','WASD','두 키 조합','F  상호작용','미궁 탐색')) for text in texts)
        frame = pixels(app)
        def rgb(x,y):
            index = ((y*2)*1280+x*2)*4
            return tuple(frame[index:index+3])
        assert rgb(74,332) == (155,76,59) and rgb(150,332) == (41,39,34)
        assert rgb(74,353) == (119,139,89) and rgb(120,353) == (41,39,34)
        a,b = view.world(0,0),view.world(1,0)
        assert (b[0]-a[0],b[1]-a[1]) == (32,16)
        view.capture(app.output/'hud/01-explore.png')
        game.player.x,game.player.y = 9.5,1.5
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
        print('PASS: full-width world keeps 32/16 projection; phase/HP/ST anchors, values and colors; contextual F, no sidebar/debug list and live M map.')
    finally:
        app.game = original
        app.release_input()
        view.draw(original)
