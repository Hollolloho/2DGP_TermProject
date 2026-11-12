"""입력 처리, 상태 갱신, 화면 출력을 반복하는 게임 프레임워크."""
import argparse
import os
from pathlib import Path
import time


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=117)
    parser.add_argument('--smoke', action='store_true', help='Test input and export frames headlessly')
    parser.add_argument('--overview', action='store_true', help='Start in full-view mode')
    parser.add_argument('--trap-preview', action='store_true', help='Start in the trap room')
    args = parser.parse_args()
    if args.smoke and args.trap_preview:
        parser.error('--smoke and --trap-preview are separate review modes')
    if args.smoke:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'

    # 화면 없는 검사 설정을 먼저 읽은 다음 SDL을 불러온다.
    import pico2d.pico2d as p
    from game_view import LW, LH, SCALE
    from play_mode import PlayMode

    project = Path(__file__).resolve().parent
    p.open_canvas(LW * SCALE, LH * SCALE, sync=not args.smoke)
    mode = None
    try:
        if not p.renderer:
            p.renderer = p.SDL_CreateRenderer(p.window, -1, p.SDL_RENDERER_SOFTWARE)
        assert p.renderer
        p.print_fps = lambda: None
        p.SDL_SetWindowTitle(p.window, 'Maze · Quarter-view / First-person trap · pico2d'.encode())
        if not args.smoke:
            # Python 호스트 창이 숨겨져 있어도 실제 게임 창은 표시한다.
            p.SDL_HideWindow(p.window)
            p.SDL_ShowWindow(p.window)
            p.SDL_RaiseWindow(p.window)
        mode = PlayMode(project, args)
        if args.smoke:
            from check_game_render import run as check_render
            check_render(mode)
        else:
            run_loop(mode, p)
    finally:
        if mode:
            mode.finish()
        p.close_canvas()


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
