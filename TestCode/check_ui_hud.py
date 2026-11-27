"""HUD 대비·정보 우선순위와 퍼즐 자원 안전영역. --sdl --output DIRECTORY로 확인한다."""
import ctypes
from unittest.mock import patch
from SourceCode import ui_theme as ui


def contrast(a,b):
    def luminance(rgb):
        values=[c/255/12.92 if c/255 <= .04045 else ((c/255+.055)/1.055)**2.4 for c in rgb]
        return sum(c*w for c,w in zip(values,(.2126,.7152,.0722)))
    light,dark=sorted((luminance(a),luminance(b)),reverse=True)
    return (light+.05)/(dark+.05)


def check_palette():
    assert all(contrast(color,ui.SURFACE)>=4.5 for color in (ui.TEXT,ui.MUTED,ui.BRASS,ui.FOCUS,ui.DANGER))
    assert all(contrast(color,ui.TRACK)>=3 for color in (ui.HEALTH,ui.STAMINA))
    print('PASS: informational/action/danger text >=4.5 contrast and both labelled resource tracks >=3 against their UI surfaces.')


def run(app):
    import pico2d.pico2d as p
    from SourceCode.maze_model import Game
    from .check_boulder_render import labels,picture,pixels,press
    from .check_game_render import regain_focus
    original,original_course=app.game,app.test_course
    check_palette()
    def fresh():
        app.test_course=True
        app.game=game=Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
        app.release_input();game.guard_hp=0;game.banner_until=0.
        return game
    try:
        for width,height in ((1280,800),(960,600),(2560,1080)):
            p.SDL_SetWindowSize(p.window,width,height);regain_focus(app)
            def capture(name):
                picture(app);app.game.ui_time+=.4;picture(app)
                assert app.view.output_size()==(width,height)
                data=(ctypes.c_ubyte*(width*height*4))()
                rect=p.SDL_Rect(0,0,width,height)
                assert p.SDL_RenderReadPixels(p.renderer,ctypes.byref(rect),p.SDL_PIXELFORMAT_RGBA32,data,width*4)==0
                assert len(set(data[::4]))>16
                surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
                assert surface
                try:assert p.IMG_SavePNG(surface,str(app.output/f'hud-{name}-{width}x{height}.png').encode('utf-8'))==0
                finally:p.SDL_FreeSurface(surface)
            game=fresh();capture('main')
            press(app,p.SDLK_f)
            for _ in range(65):app.update(.05)
            assert '추천: A 칼날방' in labels(app)
            capture('course')
            game.puzzle_reserved_phase=game.next_phase
            game.shortcut_choice.select(0);game.shortcut_choice.confirm(game.next_phase)
            game.banner_until=0.
            with patch.object(app.view,'text',wraps=app.view.text) as drawn:
                picture(app)
            status=[call for call in drawn.call_args_list if 'P 문 ·' in call.args[0]]
            assert len(status)==1 and '경로 1 ·' in status[0].args[0]
            assert status[0].args[1] >= 222
            capture('reservations')
            game.puzzle_reserved_phase,game.puzzle_open=None,True
            x,y=game.puzzle_gate[0];game.grid[y][x]=0
            x,y=game.path_entry;game.player.x,game.player.y=x+.5,y+.5
            game.update_visibility();press(app,p.SDLK_f)
            for _ in range(21):app.update(.05)
            text=labels(app)
            assert '끊긴 길의 방' in text
            assert not any('P 문 개방' in value or '경로 1 ·' in value for value in text)
            capture('slab-title')
            game=fresh();game.player.hp,game.player.stamina=73,42.
            x,y=game.puzzle_gate[1];game.player.x,game.player.y=x+.5,y+.5
            game.update_visibility();press(app,p.SDLK_f)
            assert game.state=='puzzle' and game.puzzle_tab=='maze'
            picture(app);game.ui_time+=.4;picture(app);frame=pixels(app)
            for cy,height_pixels,value,color in ((356,6,73,ui.HEALTH),(370,4,42,ui.STAMINA)):
                for py in range(cy-height_pixels//2,cy+height_pixels//2):
                    for px in range(40,124):
                        offset=((py*2)*1280+px*2)*4
                        expected=color if px<40+round(84*value/100) else ui.TRACK
                        assert tuple(frame[offset:offset+3])==expected,('P obscures vitals',px,py)
            assert {'HP','ST',' 73',' 42'} <= set(labels(app))
            capture('puzzle-resource-safe')
            print(f'PASS: {width}x{height} quiet HUD, one reservation line, room-specific title priority and uncovered P resource pixels; existing game values retained.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.test_course=original_course;app.game=original;app.release_input();regain_focus(app);picture(app)


if __name__=='__main__':
    check_palette()
    from . import check_ui_layout
    check_ui_layout.run=run
    check_ui_layout.main()
