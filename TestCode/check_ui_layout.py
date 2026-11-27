"""공용 8:5 출력과 포인터 역변환. --sdl --output DIRECTORY로 실제 SDL 화면도 검사한다."""
import argparse
import ctypes
import math
from pathlib import Path
from unittest.mock import patch
from SourceCode.ui_layout import fit_viewport,window_to_logical,logical_to_window

SIZES = ((1280,800),(960,600),(1280,720),(1920,1080),(2560,1080))
RECTS = ((0,0,1280,800),(0,0,960,600),(64,0,1152,720),(96,0,1728,1080),(416,0,1728,1080))


def check_math():
    for size,expected in zip(SIZES,RECTS):
        assert fit_viewport(*size) == expected
    for output in (*SIZES,(1279,799),(1024,1024),(800,1280)):
        x,y,w,h = fit_viewport(*output)
        assert w*400 == h*640 and 0 <= x and 0 <= y and x+w <= output[0] and y+h <= output[1]
        for window in (output,(output[0]//2,output[1]//2)):
            for point in ((0,0),(639,399),(320,200),(176,195),(464,195),(320,306),(82,148)):
                screen = logical_to_window(point,window,output)
                recovered = window_to_logical(screen,window,output)
                tolerance = max(1,math.ceil(640*output[0]/(w*window[0])),math.ceil(400*output[1]/(h*window[1])))
                assert recovered is not None and max(abs(a-b) for a,b in zip(point,recovered)) <= tolerance
        assert window_to_logical((-1,0),output,output) is None
        assert window_to_logical((x+w,y+h),output,output) is None
        if x:assert window_to_logical((x-1,output[1]//2),output,output) is None
        if y:assert window_to_logical((output[0]//2,y-1),output,output) is None
    assert window_to_logical((0,0),(0,0),(0,0)) is None
    print('PASS: exact 8:5 fit, five requested sizes, odd/portrait layouts, integer pointer round trips, 2x drawable DPI, bars and zero-size rejection.')


def run(app):
    import pico2d.pico2d as p
    from SourceCode.maze_model import Game
    from SourceCode.game_view import CHOICE_CARD_RECTS,CHOICE_CONFIRM_RECT,PUZZLE_OFFSET_X
    from SourceCode.mouse_maze import START_CELL,cell_center
    from SourceCode.puzzle_layout import room_screen
    from SourceCode.world_path_room import LOOSE_POSITIONS
    from .check_boulder_render import press,picture
    from .check_game_render import regain_focus
    original,original_course = app.game,app.test_course
    check_math()
    def fresh():
        app.test_course = True
        app.game = game = Game(117,player_clips=app.view.player_catalog['clips'],test_course=True)
        app.release_input();game.guard_hp = 0
        return game
    def raw(kind,point,held=True):
        event=p.SDL_Event();event.type=kind
        if kind == p.SDL_MOUSEMOTION:
            event.motion.x,event.motion.y = point
            event.motion.state = p.SDL_BUTTON_LMASK if held else 0
        else:event.button.x,event.button.y,event.button.button = *point,p.SDL_BUTTON_LEFT
        assert p.SDL_PushEvent(event)==1
        app.handle_events()
    def click(point):
        raw(p.SDL_MOUSEBUTTONDOWN,point);raw(p.SDL_MOUSEBUTTONUP,point)
    try:
        for size,viewport in zip(SIZES,RECTS):
            width,height = size;x,y,w,h = viewport
            p.SDL_SetWindowSize(p.window,width,height);regain_focus(app)
            assert app.view.output_size() == size
            def point(logical):
                # 별도로 정한 기대 사각형에서 SDL 좌표를 만들어 역변환 오류를 검증한다.
                return math.ceil(x+logical[0]*w/640),math.ceil(y+logical[1]*h/400)
            margin = (x-1,height//2) if x else (width//2,y-1) if y else (-1,height//2)
            def capture(name):
                picture(app);app.game.ui_time += .4
                p.SDL_SetRenderDrawColor(p.renderer,255,0,255,255);p.SDL_RenderClear(p.renderer)
                picture(app)
                data=(ctypes.c_ubyte*(width*height*4))()
                rect=p.SDL_Rect(0,0,width,height)
                assert p.SDL_RenderReadPixels(p.renderer,ctypes.byref(rect),p.SDL_PIXELFORMAT_RGBA32,data,width*4)==0
                def rgb(px,py):return tuple(data[(py*width+px)*4:(py*width+px)*4+3])
                if x:
                    assert all(rgb(px,py)==(0,0,0) for px in (0,x-1,x+w,width-1) for py in (0,height//2,height-1))
                if y:
                    assert all(rgb(px,py)==(0,0,0) for px in (0,width//2,width-1) for py in (0,y-1,y+h,height-1))
                assert len(set(data[::4]))>16
                surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
                assert surface
                try:assert p.IMG_SavePNG(surface,str(app.output/f'viewport-{name}-{width}x{height}.png').encode('utf-8'))==0
                finally:p.SDL_FreeSurface(surface)
            game=fresh();capture('main')
            with patch.object(game,'attack',wraps=game.attack) as attack:
                click(margin);assert not attack.called
                click(point((320,200)));assert attack.call_count==1
            game=fresh();cx,cy=game.choice_start
            game.player.x,game.player.y=cx+.5,cy+.5;game.update_visibility();press(app,p.SDLK_f)
            assert game.state=='puzzle' and game.puzzle_tab=='choice'
            click(margin);assert game.shortcut_choice.preview is None
            cx,cy,cw,ch=CHOICE_CARD_RECTS[1]
            click(point((cx+cw/2,cy+ch/2)))
            assert game.shortcut_choice.preview==1
            capture('choice')
            cx,cy,cw,ch=CHOICE_CONFIRM_RECT;click(point((cx+cw/2,cy+ch/2)))
            app.update(.02);assert game.shortcut_choice.selected==1 and game.state=='explore'
            game=fresh();cx,cy=game.puzzle_gate[1]
            game.player.x,game.player.y=cx+.5,cy+.5;game.update_visibility();press(app,p.SDLK_f)
            with patch.object(game.puzzle,'press',wraps=game.puzzle.press) as pressed:
                click(margin);assert not pressed.called
            sx,sy=cell_center(*START_CELL)
            raw(p.SDL_MOUSEBUTTONDOWN,point((sx+PUZZLE_OFFSET_X,sy)))
            assert game.puzzle.dragging
            raw(p.SDL_MOUSEBUTTONUP,margin);assert not game.puzzle.dragging
            press(app,p.SDLK_ESCAPE)
            game=fresh();cx,cy=game.path_entry
            game.player.x,game.player.y=cx+.5,cy+.5;game.update_visibility();press(app,p.SDLK_f)
            for _ in range(21):app.update(.05)
            rotation=game.connection.pieces[0].rotation
            raw(p.SDL_MOUSEBUTTONDOWN,point(room_screen(*LOOSE_POSITIONS[0])))
            assert game.connection.held==0
            press(app,p.SDLK_r)
            raw(p.SDL_MOUSEMOTION,margin);raw(p.SDL_MOUSEBUTTONUP,margin)
            assert not game.connection.dragging and game.connection.pieces[0].cell is None
            assert game.connection.pieces[0].rotation==rotation
            for kind in ('blade','boulder'):
                game=fresh();cx,cy=game.trap_cell if kind=='blade' else game.boulder_entry
                game.player.x,game.player.y=cx+.5,cy+.5;game.update_visibility();press(app,p.SDLK_f)
                assert game.state=='trap' and game.trap_kind==kind
                capture(kind)
            print(f'PASS: SDL {width}x{height}, common main/blade/boulder viewport {viewport}; black margins, inside attack/card/P/slab input, blocked margin input and canceled margin drops.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.test_course=original_course;app.game=original;app.release_input();regain_focus(app);picture(app)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdl',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.sdl:
        check_math();return
    import os,sys
    os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    from SourceCode import game_framework,play_mode
    from . import check_game_render
    init=play_mode.PlayMode.__init__
    def start(self,*values,**options):
        if args.output is not None:options['output']=args.output
        init(self,*values,**options)
    with patch.object(play_mode.PlayMode,'__init__',start),patch.object(check_game_render,'run',run):
        sys.argv=['ui-layout-check','--smoke'];game_framework.run()


if __name__=='__main__':
    main()
