"""실제 새 P 판을 두 해상도에서 오답·되짚기·재개 후 풀고 문을 통과하는 SDL 검사."""
from math import ceil
import ctypes
import pico2d.pico2d as p
from SourceCode.maze_model import Game, PHASE_SECONDS
from SourceCode.mouse_maze import BOARD, START_CELL, GOAL_CELL, WAYPOINTS, cell_center
from SourceCode.game_view import PUZZLE_OFFSET_X
from .check_game_render import inject_mouse
from .check_boulder_render import keys,press,picture,pixels,labels
from .check_waypoint_maze import SOLUTION_CORNERS, EXIT_SHORTCUT, SECOND_FIRST


def run(app):
    original = app.game
    def mouse(kind,point):
        inject_mouse(kind,(point[0]+PUZZLE_OFFSET_X,point[1]))
        app.handle_events()
    def advance(seconds):
        count = max(1,ceil(seconds/.05))
        for _ in range(count):app.update(seconds/count)
    def move(point,batch=False):
        start = app.game.puzzle.pointer
        assert start is not None
        distance = max(abs(point[0]-start[0]),abs(point[1]-start[1]))
        duration = .3*distance/BOARD[2]
        count = 1 if batch else max(1,ceil(distance/4))
        for step in range(1,count+1):
            mouse(p.SDL_MOUSEMOTION,(start[0]+(point[0]-start[0])*step/count,
                                     start[1]+(point[1]-start[1])*step/count))
            advance(duration/count)
            picture(app)
    def cells(route,batch=False):
        for cell in route:move(cell_center(*cell),batch)
    def capture_small_window(width,height):
        # 논리 텍스처를 다시 확대하지 않고 실제 960×600 백버퍼의 글자를 검수한다.
        picture(app)
        data = (ctypes.c_ubyte*(width*height*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,width*4) == 0
        surface = p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:
            assert p.IMG_SavePNG(surface,str(app.output/'mouse-maze-waypoints-960.png').encode('utf-8')) == 0
        finally:
            p.SDL_FreeSurface(surface)
    try:
        for width,height in ((1280,800),(960,600)):
            p.SDL_SetWindowSize(p.window,width,height)
            app.game = game = Game(117,player_clips=app.view.player_catalog['clips'])
            app.release_input()
            wall,near,far = game.puzzle_gate
            game.player.x,game.player.y = near[0]+.5,near[1]+.5
            game.guard_hp,game.player.torch = 0,True
            game.update_visibility();picture(app);advance(.4)
            press(app,p.SDLK_f)
            assert game.state == 'puzzle' and game.puzzle.progress == 0
            mouse(p.SDL_MOUSEBUTTONDOWN,cell_center(*START_CELL))
            cells(EXIT_SHORTCUT)
            assert game.state == 'puzzle' and game.puzzle.cell == GOAL_CELL
            assert game.puzzle.progress == 0 and game.puzzle_reserved_phase is None
            assert any('도착 전' in text for text in labels(app))
            cells(((11,3),(3,3),(3,1),START_CELL))
            assert game.puzzle.path == [START_CELL]
            cells(SECOND_FIRST,batch=True)
            assert game.puzzle.sequence_error and game.puzzle.progress == 0
            assert game.puzzle_reserved_phase is None and game.solid(*wall)
            assert any('되짚어 순서' in text for text in labels(app))
            cells(((5,1),(5,3),(3,3),(3,1),START_CELL),batch=True)
            assert not game.puzzle.sequence_error and game.puzzle.progress == 0
            advance(15.)
            cells(SOLUTION_CORNERS[:4])
            assert game.puzzle.progress == 1
            mouse(p.SDL_MOUSEBUTTONUP,game.puzzle.cursor)
            saved = game.puzzle.path[:],game.puzzle.cursor
            press(app,p.SDLK_ESCAPE);press(app,p.SDLK_f)
            assert game.state == 'puzzle' and (game.puzzle.path,game.puzzle.cursor) == saved
            assert game.puzzle.progress == 1
            mouse(p.SDL_MOUSEBUTTONDOWN,game.puzzle.cursor)
            game.guard = near
            game.guard_hp,game.guard_attack_at = 3,game.time+.01
            app.update(.02)
            assert game.state == 'explore' and game.player.hp == 85 and game.puzzle.progress == 1
            assert app.puzzle_mouse_held and not game.puzzle.dragging
            mouse(p.SDL_MOUSEBUTTONDOWN,cell_center(*GOAL_CELL))
            assert not game.attack_hits_ms
            mouse(p.SDL_MOUSEBUTTONUP,game.puzzle.cursor)
            game.guard_hp = 0
            press(app,p.SDLK_f)
            assert game.state == 'puzzle' and (game.puzzle.path,game.puzzle.cursor) == saved
            mouse(p.SDL_MOUSEBUTTONDOWN,game.puzzle.cursor)
            cells(SOLUTION_CORNERS[4:7],batch=True)
            assert game.puzzle.progress == 2 and WAYPOINTS[1] in game.puzzle.path
            move(cell_center(*WAYPOINTS[1]))
            x,y = cell_center(*WAYPOINTS[1])
            move((x-3,y))
            assert game.puzzle.progress == 1 and game.puzzle.cell == WAYPOINTS[1]
            mouse(p.SDL_MOUSEBUTTONUP,game.puzzle.cursor)
            mouse(p.SDL_MOUSEBUTTONDOWN,game.puzzle.cursor)
            move((x,y));move(cell_center(9,1))
            assert game.puzzle.progress == 2
            texts = labels(app)
            assert all(text in texts for text in ('1 완료','2 완료','3 다음','1','2','3'))
            assert '좌클릭 드래그 · 1 → 2 → 3 → 도착' in texts
            frame = pixels(app)
            for cell,color in zip(WAYPOINTS,((188,205,154),(188,205,154),(239,183,104))):
                x,y = cell_center(*cell)
                index = ((y-8)*2*1280+(x+PUZZLE_OFFSET_X)*2)*4
                assert tuple(frame[index:index+3]) == color,'waypoint status border is not visible'
            if width == 1280:
                app.view.capture(app.output/'mouse-maze-waypoints-progress.png')
            else:
                capture_small_window(width,height)
            cells(SOLUTION_CORNERS[7:11],batch=True)
            assert game.puzzle.progress == 3 and game.state == 'puzzle'
            assert any('도착으로' in text for text in labels(app))
            cells(SOLUTION_CORNERS[11:])
            assert game.state == 'explore' and game.puzzle_reserved_phase == game.next_phase
            assert game.solid(*wall) and not game.puzzle_open and game.phase_time < 50
            elapsed = game.phase_time
            mouse(p.SDL_MOUSEBUTTONDOWN,cell_center(*GOAL_CELL))
            assert not game.attack_hits_ms
            mouse(p.SDL_MOUSEBUTTONUP,cell_center(*GOAL_CELL))
            game.phase_time = PHASE_SECONDS-.01;app.update(.02)
            while game.state == 'shifting':app.update(.05)
            assert game.puzzle_open and not game.solid(*wall)
            keys(app,(p.SDLK_a,))
            for _ in range(40):app.update(.02)
            keys(app)
            assert abs(game.player.y-far[1]-.5) < 1e-6 and far in game.visited
            print(f'PASS: {width}x{height} actual new board: goal-only/2-first rejected, ordered batches, partial rewind, Esc/hit resume, visible 1/2/3 status and next-phase SDL door crossing; scripted errors+15s read+solve {elapsed:.2f}s/60s, not human play timing.')

        press(app,p.SDLK_r)
        fresh = app.game
        near = fresh.puzzle_gate[1]
        fresh.player.x,fresh.player.y = near[0]+.5,near[1]+.5
        fresh.guard_hp = 0;fresh.update_visibility();press(app,p.SDLK_f)
        mouse(p.SDL_MOUSEBUTTONDOWN,cell_center(*START_CELL))
        cells(SOLUTION_CORNERS[:4])
        assert fresh.puzzle.progress == 1
        fresh.phase_time = PHASE_SECONDS-.01;app.update(.02)
        assert fresh.state == 'shifting' and fresh.puzzle.progress == 0 and fresh.puzzle.path == [START_CELL]
        assert fresh.puzzle_reserved_phase is None
        mouse(p.SDL_MOUSEBUTTONUP,cell_center(*START_CELL))
        while fresh.state == 'shifting':app.update(.05)
        press(app,p.SDLK_f)
        assert fresh.state == 'puzzle' and fresh.puzzle.progress == 0 and not fresh.puzzle.sequence_error
        print('PASS: actual new-board phase interruption/reopen resets sequence and trace; 60-second world timer unchanged.')
    finally:
        p.SDL_SetWindowSize(p.window,1280,800)
        app.game = original
        app.release_input()
        picture(app)
