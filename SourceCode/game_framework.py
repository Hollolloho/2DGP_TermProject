"""입력 처리, 상태 갱신, 화면 출력을 반복하는 게임 프레임워크."""
import argparse
import ctypes
import os
from pathlib import Path
import time
from .window_input import disable_text_input


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    layout = parser.add_mutually_exclusive_group()
    layout.add_argument('--seed', type=int, default=117)
    layout.add_argument('--test-course', action='store_true', help='Play the repeatable trap and puzzle course')
    parser.add_argument('--smoke', action='store_true', help='Test input and export frames headlessly')
    parser.add_argument('--overview', action='store_true', help='Start in full-view mode')
    parser.add_argument('--trap-preview', action='store_true', help='Start in the trap room')
    args = parser.parse_args()
    if args.test_course and (args.smoke or args.trap_preview):
        parser.error('--test-course starts at spawn and runs separately from --smoke and --trap-preview')
    if args.smoke and args.trap_preview:
        parser.error('--smoke and --trap-preview are separate review modes')
    if args.smoke:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'

    # 화면 없는 검사 설정을 먼저 읽은 다음 SDL을 불러온다.
    import pico2d.pico2d as p
    from .game_view import LW, LH, SCALE
    from .play_mode import PlayMode

    project = Path(__file__).resolve().parents[1]
    width, height = LW * SCALE, LH * SCALE
    p.open_canvas(width, height, sync=not args.smoke)
    disable_text_input(p)
    mode = None
    try:
        if not p.renderer:
            p.renderer = p.SDL_CreateRenderer(p.window, -1, p.SDL_RENDERER_SOFTWARE)
        assert p.renderer
        p.print_fps = lambda: None
        title = '2DGP | Test Course' if args.test_course else 'Maze · Quarter-view / First-person trap · pico2d'
        p.SDL_SetWindowTitle(p.window, title.encode())
        if not args.smoke:
            # Python 호스트 창이 숨겨져 있어도 실제 게임 창은 표시한다.
            p.SDL_HideWindow(p.window)
            p.SDL_ShowWindow(p.window)
            p.SDL_RaiseWindow(p.window)
        show_intro = not (args.smoke or args.overview or args.trap_preview)
        if show_intro:
            from .title_menu import discard_startup_input, show_title_menu

            if not show_school_credit(p, project, width, height):
                return
            if not show_title_menu(project):
                return
        mode = PlayMode(project, args)
        if show_intro:
            discard_startup_input()
        if args.smoke:
            from TestCode.check_game_render import run as check_render
            check_render(mode)
        else:
            run_loop(mode, p)
    finally:
        if mode:
            mode.finish()
        p.close_canvas()


def show_school_credit(p, project, width, height):
    credit = p.load_image(str(project / 'sprite/ui/tuk_credit.png'))
    destination = p.SDL_Rect((width-credit.w)//2, (height-credit.h)//2, credit.w, credit.h)
    event = p.SDL_Event()
    deadline = None
    while True:
        skip = False
        # 전환 전에 현재 입력을 모두 소비해 클릭이 게임의 공격으로 이어지지 않게 한다.
        while p.SDL_PollEvent(ctypes.byref(event)):
            if event.type == p.SDL_WINDOWEVENT and event.window.event == p.SDL_WINDOWEVENT_FOCUS_GAINED:
                disable_text_input(p)
            if event.type == p.SDL_QUIT or (event.type == p.SDL_WINDOWEVENT and
                                            event.window.event == p.SDL_WINDOWEVENT_CLOSE):
                return False
            if event.type == p.SDL_KEYDOWN and not event.key.repeat:
                skip |= event.key.keysym.sym in (p.SDLK_RETURN, p.SDLK_KP_ENTER, p.SDLK_SPACE)
            elif event.type == p.SDL_MOUSEBUTTONDOWN:
                skip |= event.button.button == p.SDL_BUTTON_LEFT
        if skip or (deadline is not None and time.perf_counter() >= deadline):
            return True

        p.SDL_SetRenderDrawColor(p.renderer, 255, 255, 255, 255)
        p.SDL_RenderClear(p.renderer)
        p.SDL_RenderCopy(p.renderer, credit.texture, None, destination)
        p.SDL_RenderPresent(p.renderer)
        if deadline is None:
            deadline = time.perf_counter() + 2.0
        p.delay(.01)


def run_loop(mode, p):
    previous = time.perf_counter()
    next_status = 0
    while mode.running:
        now = time.perf_counter()
        dt = min(.05, now - previous)
        previous = now

        mode.handle_events()
        mode.update(dt)
        mode.render(dt)

        if now >= next_status:
            mode.save_status()
            next_status = now + 1
        p.delay(.002)
