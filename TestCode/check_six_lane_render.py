"""Headless six-lane geometry check. Use --output DIRECTORY to export review frames."""
import argparse
from collections import Counter
import ctypes
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
from unittest.mock import patch
import zlib


def run(output=None):
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pico2d.pico2d as p
    from BoulderPractice.boulder_volume import sloped_rolled_pose
    from SourceCode.six_lane_trap import CYCLE_SECONDS, LANE_COUNT, RADIUS, SixLaneTrap
    from SourceCode.six_lane_view import SixLaneView

    width, height = 1280, 800
    p.open_canvas(width, height, sync=False)
    if not p.renderer:
        p.renderer = p.SDL_CreateRenderer(p.window, -1, p.SDL_RENDERER_SOFTWARE)
    assert p.renderer
    p.print_fps = lambda: None
    view = None
    try:
        view = SixLaneView(p, width, height)
        room = SixLaneTrap()
        def read_frame():
            pixels = (ctypes.c_uint32*(width*height))()
            assert p.SDL_RenderReadPixels(p.renderer, None, p.SDL_PIXELFORMAT_RGBA32,
                                         pixels, width*4) == 0
            return pixels[:]

        def render_stones(stones):
            fixture = SimpleNamespace(**vars(room))
            fixture.floor_height = room.floor_height
            fixture.stones = stones
            view.draw_scene(fixture)
            return read_frame()

        mesh, _ = view.meshes['near']
        for lane in (0,1):
            previous = None
            for phase in range(48):
                stone = room.stone_at(lane, phase*CYCLE_SECONDS/48)
                world, _, contact = sloped_rolled_pose(mesh, RADIUS, stone.distance,
                                                       stone.x, stone.z, stone.slope, stone.direction)
                assert min(y-room.floor_height(x,z) for x,y,z,*_ in world) >= -1e-8
                assert abs(contact[1]-room.floor_height(contact[0],contact[2])) < 1e-9
                if previous is not None:
                    assert world[12][:3] != previous
                previous = world[12][:3]

        # Each stone repeats offstage, and moves only toward its lane's downhill side.
        timings = []
        for seconds in (0., .25, .5, 1., CYCLE_SECONDS):
            samples = [room.stone_at(lane, seconds) for lane in range(LANE_COUNT)]
            assert len(samples) == 6 and all(stone.active for stone in samples)
            timings.append({'seconds': round(seconds, 3),
                            'x': [round(stone.x, 3) for stone in samples],
                            'cycle': [stone.cycle for stone in samples]})
            for stone in samples:
                later = room.stone_at(stone.lane, seconds+.001, cycle=stone.cycle)
                assert (later.x-stone.x)*stone.direction > 0
                assert math.isclose(stone.x, room.stone_at(stone.lane, seconds+CYCLE_SECONDS).x,
                                    abs_tol=1e-9)

        room.time = 3.3
        empty = render_stones([])
        contributions = []
        for stone in room.stones:
            isolated = render_stones([stone])
            changed = sum(a != b for a,b in zip(empty, isolated))
            assert changed > 20, (stone.lane, changed)
            contributions.append(changed)
        view.draw_scene(room)
        entry = read_frame()
        assert sum(value & 0x00ffffff != 0 for value in entry) > width*height//5
        assert len(set(entry)) > 256
        # Freeze the first rock's center and advance only its angular pose.
        first = room.stones[0]
        pose = render_stones([first])
        rotated = render_stones([replace(first,distance=first.distance+first.radius*.5)])
        assert sum(a != b for a,b in zip(pose,rotated)) > 10000
        seam_region = [entry[y*width+x] for y in range(328,800) for x in range(640)]
        assert Counter(seam_region).most_common(1)[0][1] < len(seam_region)//2
        with patch('SourceCode.six_lane_view.row_height', return_value=0.):
            view.draw_scene(room)
            assert sum(a != b for a,b in zip(entry, read_frame())) > 1000
        material = view.rock.texture
        view.rock.texture = view.images['wall'].texture
        try:
            view.draw_scene(room)
            assert sum(a != b for a,b in zip(entry, read_frame())) > 1000
        finally:
            view.rock.texture = material

        room.time = 3.5
        near = room.stones[0]
        room.x, room.z = near.x, near.z+.3
        without = render_stones([])
        clipped = render_stones([near])
        assert 0 in view.visible_stones
        room.x = room.z = 0.
        room.time = 3.3

        # Drawing either previous renderer must not alter the new room's camera or textures.
        from BoulderPractice.boulder_practice import Practice, View as PracticeView
        from SourceCode.game_view import View as GameView
        from SourceCode.maze_model import Game
        standalone, main_view = None, None
        try:
            standalone = PracticeView(p, width, height)
            main_view = GameView(Path(__file__).resolve().parents[1])
            legacy = Practice()
            legacy.time, legacy.z = 1., 4.
            standalone.draw_scene(legacy)
            main_view.corridor.draw(Game())
            view.draw_scene(room)
            assert entry == read_frame()
        finally:
            if standalone is not None:
                standalone.close()
            if main_view is not None:
                main_view.close()

        frames = (
            ('01-entry-six-stones', 3.3, 0., 0., 0.),
            ('02-entry-rotation', 3.42, 0., 0., 0.),
            ('03-far-stone', 1.2, 0., 0., 0.),
            ('04-near-stone', 3.5, 0., 3., 0.),
            ('05-left-on-slope', 1.2, -1.8, 6.5, 0.),
            ('06-right-on-slope', 1.2, 1.8, 6.5, 0.),
            ('07-rear-view', 1.2, 0., 14., 180.),
            ('08-front-exit', 2., 0., 22., 0.),
            ('09-entry-low-side-occlusion', 1.53, 0., 0., 0.),
            ('10-near-4.24-seconds', 4.24, 0., 2., 0.),
            ('11-left-incoming',2.72,0.,4.5,-90.),
            ('12-left-rotation',3.0,0.,4.5,-90.),
            ('13-right-incoming',3.94,0.,7.5,90.),
            ('14-oblique-rows',3.3,-1.,5.4,48.),
            ('15-mouse-turn-opposite',3.94,0.,7.5,-90.),
        )
        if output is not None:
            output = Path(output)
            output.mkdir(parents=True, exist_ok=False)
        summaries = []
        signatures = []
        for name, seconds, x, z, degrees in frames:
            room.yaw = math.radians(degrees)
            room.time, room.x, room.z = seconds, x, z
            view.draw_scene(room)
            pixels = (ctypes.c_ubyte*(width*height*4))()
            assert p.SDL_RenderReadPixels(p.renderer, None, p.SDL_PIXELFORMAT_RGBA32,
                                         pixels, width*4) == 0
            data = bytes(pixels)
            assert any(data[index:index+3] != b'\0\0\0' for index in range(0, len(data), 4))
            assert len({data[index:index+4] for index in range(0, len(data), 16)}) > 128
            if name in ('01-entry-six-stones', '10-near-4.24-seconds'):
                colors = [data[(y*width+x)*4:(y*width+x)*4+4]
                          for y in range(328,800) for x in range(640)]
                assert Counter(colors).most_common(1)[0][1] < len(colors)//2
            signatures.append(zlib.crc32(data))
            if name == '01-entry-six-stones':
                assert set(view.visible_stones) == set(range(LANE_COUNT))
            if name.startswith(('11-', '12-')):
                assert 0 in view.visible_stones
            if name.startswith('13-'):
                assert 1 in view.visible_stones
            if name.startswith('15-'):
                assert 1 not in view.visible_stones
            assert view.last_triangles > 0
            for lane, contact in view.stone_contacts.items():
                assert abs(contact[1]-room.floor_height(contact[0],contact[2])) < 1e-9
            summaries.append({'frame': name, 'seconds': seconds, 'player': [x, z],
                              'yaw_degrees': degrees, 'stones': view.visible_stones,
                              'triangles': view.last_triangles,
                              'draw_ms': round(view.last_draw_ms, 2)})
            if output is not None:
                surface = p.SDL_CreateRGBSurfaceWithFormatFrom(
                    pixels, width, height, 32, width*4, p.SDL_PIXELFORMAT_RGBA32)
                assert surface
                try:
                    path = output/(name+'.png')
                    assert p.IMG_SavePNG(surface, str(path).encode('utf-8')) == 0
                finally:
                    p.SDL_FreeSurface(surface)
        assert len(set(signatures)) == len(frames)
        performance = []
        for name,seconds,z,degrees in (('six-visible-entry',3.3,0.,0.), ('entry-1s',1.,0.,0.),
                                      ('near-stone-4.24s',4.24,2.,0.), ('left-incoming',2.72,4.5,-90.)):
            room.yaw = math.radians(degrees)
            room.time,room.x,room.z = seconds,0.,z
            samples = []
            for index in range(45):
                start = time.perf_counter()
                view.draw_scene(room)
                p.SDL_RenderPresent(p.renderer)
                if index >= 3:
                    samples.append((time.perf_counter()-start)*1000)
            performance.append({'pose': name, 'median_draw_present_ms': round(statistics.median(samples),2),
                                'p95_draw_present_ms': round(sorted(samples)[39],2)})
        print(json.dumps({'passed': True, 'native_size': [width, height],
                          'scene_internal_size': [view.w, view.h],
                          'sloped_contact_phases': 96, 'each_stone_pixels': contributions,
                          'renderer_isolation': True, 'performance': performance, 'timing': timings,
                          'frames': summaries}, ensure_ascii=False, indent=2))
    finally:
        if view is not None:
            view.close()
        p.close_canvas()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create a new directory with review PNGs')
    arguments = parser.parse_args()
    run(arguments.output)
