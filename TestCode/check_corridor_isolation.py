"""두 함정 렌더러의 같은 SDL 프로세스 내 독립성 검사. 창 없이 실행한다."""
import ctypes
import math
import os
from pathlib import Path


def run(output=None):
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pico2d.pico2d as p
    from SourceCode import trap_view
    from SourceCode.game_view import View
    from SourceCode.maze_model import Game
    from BoulderPractice.boulder_practice import Practice, View as BoulderView

    output = Path(output) if output else None
    root = Path(__file__).resolve().parents[1]
    poses = ((0., 0., 0., 7.), (.32, -.6, 1.8, 7.5),
             (.66, .7, 2.7, 8.), (.94, 0., 1.8, 8.5))

    def settings():
        return (trap_view.WIDTH, trap_view.HEIGHT, trap_view.TOP, trap_view.FOCAL,
                trap_view.TRAP_LENGTH, trap_view.TRAP_HALF_WIDTH, trap_view.TRAP_HEIGHT,
                trap_view.TRAP_PLANES, trap_view.camera, trap_view.project)

    def pixels(target, width, height):
        previous = p.SDL_GetRenderTarget(p.renderer)
        try:
            assert p.SDL_SetRenderTarget(p.renderer, target) == 0
            data = (ctypes.c_ubyte*(width*height*4))()
            assert p.SDL_RenderReadPixels(p.renderer, None, p.SDL_PIXELFORMAT_RGBA32,
                                         data, width*4) == 0
            return bytes(data)
        finally:
            p.SDL_SetRenderTarget(p.renderer, previous)

    def blade_frames(view):
        frames, projections = [], []
        view.draw(game)
        game.ui_time += 1.
        for progress, x, velocity, time in poses:
            game.trap_progress, game.trap_x = progress, x
            game.trap_velocity, game.time = velocity, time
            game.trap_stride = progress*9.
            view.draw(game)
            frames.append(pixels(view.display, 1280, 800))
            projections.append((trap_view.camera(game), trap_view.project(game, .5, 1., 10.)))
        return frames, projections

    p.open_canvas(1280, 800, sync=False)
    if not p.renderer:
        p.renderer = p.SDL_CreateRenderer(p.window, -1, p.SDL_RENDERER_SOFTWARE)
    assert p.renderer
    blade = boulder = other_blade = None
    try:
        before = settings()
        assert before[:8] == (1280, 800, 60, 790., 9., 1.6, 3., (.30, .58, .82))
        game = Game(117)
        game.player.x, game.player.y = game.trap_cell[0]+.5, game.trap_cell[1]+.5
        game.interact()
        assert game.state == 'trap'
        blade = View(root)
        baseline, projections = blade_frames(blade)
        assert all(len(set(frame[::4])) > 30 for frame in baseline), 'blank blade reference'
        if output:
            blade.capture(output/'blade-before.png')

        for width, height in ((640, 400), (1280, 800), (1440, 900)):
            boulder = BoulderView(p, width, height)
            assert settings() == before, 'BoulderView changed the blade module settings'
            room = Practice()
            room.release()
            room.time, room.x, room.z = 9., .6, 12.
            room.ball_z, room.ball_distance, room.ball_speed = 5., 8., 3.7
            for rear in (False, True):
                room.yaw = math.pi if rear else 0.
                boulder.draw(room)
                reference = pixels(boulder.canvas, width, height)
                assert len(set(reference[::4])) > 30, 'blank boulder reference'
                actual, points = blade_frames(blade)
                assert actual == baseline, (width, height, rear, 'blade pixels changed')
                assert points == projections, 'blade camera/projection changed'
                assert settings() == before
                boulder.draw(room)
                assert pixels(boulder.canvas, width, height) == reference, 'boulder pixels changed'
                if output and (width, height) == (1280, 800):
                    boulder.capture(output/f'boulder-{"rear" if rear else "front"}.png')
            boulder.close()
            boulder = None
            print(f'PASS: {width}x{height} front/rear boulder and four blade poses keep identical pixels.')

        other_blade = View(root)
        actual, points = blade_frames(other_blade)
        assert actual == baseline and points == projections
        assert settings() == before
        if output:
            other_blade.capture(output/'blade-after.png')
        print('PASS: blade defaults, 9m/three blades, camera and later-created View stay unchanged.')
    finally:
        if boulder:
            boulder.close()
        if other_blade:
            other_blade.close()
        if blade:
            blade.close()
        p.close_canvas()


if __name__ == '__main__':
    run()
