"""Wall-free candidate walk review. Run from any directory; --check is headless."""
import ctypes
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
if '--check' in sys.argv:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pico2d.pico2d as p
from SourceCode.game_framework import run_loop
from SourceCode.game_view import View, LW, LH, SCALE
from SourceCode.maze_model import COLS, ROWS, WALK_SPEED, Game, project
from SourceCode.window_input import disable_text_input

PACK = Path('sprite/quarter/player_explorer_walk_tuscan_v1')
KEYS = {p.SDLK_w: (-1, 0), p.SDLK_a: (0, 1),
        p.SDLK_s: (1, 0), p.SDLK_d: (0, -1)}
FACES = {p.SDLK_w: 'nw', p.SDLK_a: 'sw', p.SDLK_s: 'se', p.SDLK_d: 'ne'}
TITLE = b'Walk MVP - NW NE 16 - Flat Ground Review'


class ReviewView(View):
    def __init__(self):
        super().__init__(ROOT)
        self.variants = {}
        for name, directory in (('after', PACK), ('before', PACK/'baseline')):
            data = json.loads((ROOT/directory/'walk.json').read_text(encoding='utf-8'))
            assert data['pivot'] == [32, 54] and data['frame_size'] == [64, 64]
            texture = 'review-' + name
            self.images[texture] = self.load(directory/data['image'], pixel=True)
            self.variants[name] = {
                key: {**clip, 'review_texture': texture}
                for key, clip in data['clips'].items()
            }
        idle = json.loads((ROOT/PACK/'idle.json').read_text(encoding='utf-8'))
        self.images['review-idle'] = self.load(PACK/idle['image'], pixel=True)
        self.player_catalog['clips'].update({
            key: {**clip, 'review_texture': 'review-idle'}
            for key, clip in idle['clips'].items()
        })
        self.variant = 'after'
        self.authored_pace = True
        self.playback_rate = 1.
        self.actual_fps = 0.
        self.set_pace(True)
        self.set_variant('after')

    def set_variant(self, name):
        self.variant = name
        self.player_catalog['clips'].update(self.variants[name])

    def set_pace(self, authored):
        self.authored_pace = authored
        distance = WALK_SPEED*.8 if authored else 35.77708763999664
        for clips in self.variants.values():
            for clip in clips.values():
                clip['cycle_distance_px'] = distance
        self.period = distance/WALK_SPEED

    def player_body(self, game, clip, index, destination, alpha=255):
        if 'review_texture' in clip:
            self.image(clip['review_texture'], destination,
                       clip['frames'][index]['rect'], alpha=alpha)
        else:
            super().player_body(game, clip, index, destination, alpha)

    def update_lighting(self, game):
        pass

    def terrain_light(self, game, x, y):
        return (249, 245, 235), 1.

    def hud(self, game, fps=0):
        clip, index = self.player_pose(game)
        face = game.locomotion_clip_name('walk')[5:].upper()
        state = 'Walk' if game.player.state == 'walk' else 'Idle'
        label = '수정 후' if self.variant == 'after' else '수정 전'
        tone = (245, 230, 200)
        self.rectangle(14, 12, 440, 96, (24, 24, 28, 240))
        self.text(f'{label} · {face} {state} {index:02}/{len(clip["frames"])-1:02}'
                  f' · {self.period:.3f}초', 24, 21, tone, size='hud_font')
        self.text(f'게임 {WALK_SPEED:.1f}px/s · 재생 {self.playback_rate:g}배'
                  f' · 표시 {self.actual_fps:.0f}FPS', 24, 44, tone)
        self.text('W 북서  A 남서  S 남동  D 북동  |  Tab 전후 비교', 24, 65, tone)
        self.text('1 0.8초  2 0.4초  F3 느리게  Space 정지  [ ] 한 장  R 중앙', 24, 86, tone)
        self.rectangle(466, 12, 158, 157, (31, 31, 34, 245))
        self.text('확대', 477, 20, tone)
        self.player_body(game, clip, index, (481, 34, 128, 128))


class FlatReview:
    def __init__(self):
        self.view = ReviewView()
        self.game = Game(6, player_clips=self.view.player_catalog['clips'])
        game = self.game
        game.grid = [[0]*COLS for _ in range(ROWS)]
        game.observed = {(x, y) for y in range(ROWS) for x in range(COLS)}
        game.guard_hp = 0
        game.exit = game.fountain = game.torch_cell = (-10, -10)
        game.trap_cell = game.trap_exit = game.boulder_entry = game.boulder_exit = None
        game.path_entry = game.path_exit = game.puzzle_gate = None
        game.route_options = []
        game.player.torch = False
        self.held = []
        self.running = True
        self.paused = False
        self.fps_started = time.perf_counter()
        self.fps_frames = 0
        self.reset()

    def reset(self):
        self.held.clear()
        player = self.game.player
        player.x, player.y = COLS/2, ROWS/2
        player.direction = 3
        player.screen_facing = 'ne'
        player.gait_phase = 0.
        player.rest()
        self.view.camera_game = None
        self.paused = False

    def step(self, delta):
        self.paused = True
        self.game.player.state = 'walk'
        clip, index = self.view.player_pose(self.game)
        count = len(clip['frames'])
        offset = clip.get('phase_offset_frames', 0)
        self.game.player.gait_phase = ((index+delta-offset) % count)/count

    def handle_events(self):
        event = p.SDL_Event()
        while p.SDL_PollEvent(ctypes.byref(event)):
            if event.type == p.SDL_QUIT:
                self.running = False
            elif event.type == p.SDL_WINDOWEVENT:
                if event.window.event == p.SDL_WINDOWEVENT_FOCUS_LOST:
                    self.held.clear()
                elif event.window.event == p.SDL_WINDOWEVENT_FOCUS_GAINED:
                    disable_text_input(p)
            elif event.type == p.SDL_KEYUP:
                key = event.key.keysym.sym
                if key in self.held:
                    self.held.remove(key)
            elif event.type == p.SDL_KEYDOWN and not event.key.repeat:
                key = event.key.keysym.sym
                if key in KEYS:
                    if key not in self.held:
                        self.held.append(key)
                    if self.paused:
                        self.game.player.screen_facing = FACES[key]
                elif key == p.SDLK_ESCAPE:
                    self.running = False
                elif key == p.SDLK_r:
                    self.reset()
                elif key in (p.SDLK_1, p.SDLK_2):
                    self.view.set_pace(key == p.SDLK_1)
                elif key == p.SDLK_TAB:
                    self.view.set_variant('before' if self.view.variant == 'after' else 'after')
                elif key == p.SDLK_F3:
                    self.view.playback_rate = .25 if self.view.playback_rate == 1. else 1.
                elif key == p.SDLK_SPACE:
                    self.paused = not self.paused
                elif key in (p.SDLK_LEFTBRACKET, p.SDLK_RIGHTBRACKET):
                    self.step(-1 if key == p.SDLK_LEFTBRACKET else 1)

    def update(self, dt):
        if not self.paused:
            self.game.phase_time = 0.
            self.game.update(dt*self.view.playback_rate,
                             *(KEYS[self.held[-1]] if self.held else (0, 0)))

    def render(self, dt):
        self.fps_frames += 1
        elapsed = time.perf_counter()-self.fps_started
        if elapsed >= .5:
            self.view.actual_fps = self.fps_frames/elapsed
            self.fps_started = time.perf_counter()
            self.fps_frames = 0
        self.view.draw(self.game, self.view.actual_fps)
        p.SDL_RenderPresent(p.renderer)

    def save_status(self):
        pass


def check(mode):
    turns = restarts = cadence = 0
    for variant in ('before', 'after'):
        mode.view.set_variant(variant)
        for authored in (True, False):
            mode.view.set_pace(authored)
            for key, face in FACES.items():
                for fps in (60, 30, 20):
                    mode.reset()
                    mode.held = [key]
                    initial = project(mode.game.player.x, mode.game.player.y)
                    for tick in range(round(3*mode.view.period*fps)):
                        mode.update(1/fps)
                        clip, index = mode.view.player_pose(mode.game)
                        assert clip['direction'] == face and 0 <= index < len(clip['frames'])
                    distance = math.dist(initial, project(mode.game.player.x, mode.game.player.y))
                    assert math.isclose(distance, 3*mode.view.period*WALK_SPEED, abs_tol=1e-7)
                    cadence += 1
            for phase in (0., .25, .5, .75, .9375):
                for key, face in FACES.items():
                    mode.reset()
                    player = mode.game.player
                    player.gait_phase = phase
                    mode.held = [key]
                    mode.update(.001)
                    mode.held.clear()
                    mode.update(.001)
                    saved = player.gait_phase
                    clip, index = mode.view.player_pose(mode.game)
                    assert player.state == 'idle' and clip['direction'] == face
                    assert clip['review_texture'] == 'review-idle'
                    mode.held = [key]
                    mode.update(.001)
                    assert math.isclose(player.gait_phase,
                                        (saved+.001/mode.view.period) % 1., abs_tol=1e-8)
                    restarts += 1
                    for other, other_face in FACES.items():
                        if other == key:
                            continue
                        player.gait_phase = phase
                        mode.held = [other]
                        mode.update(.001)
                        clip, index = mode.view.player_pose(mode.game)
                        expected = (phase+.001/mode.view.period) % 1.
                        assert clip['direction'] == other_face
                        assert math.isclose(player.gait_phase, expected, abs_tol=1e-8)
                        turns += 1
    assert all(len(c['frames']) == 16 for c in mode.view.variants['after'].values())
    mode.view.set_variant('after')
    mode.reset()
    mode.view.draw(mode.game)
    mode.game.ui_time += 1.
    mode.view.draw(mode.game)
    print(f'PASS: {cadence} cadence cases x3 loops, {restarts} restarts, '
          f'{turns} turns; matching Idle4, current Walk16x4; speed {WALK_SPEED:.6f}px/s.')


def main():
    checking = '--check' in sys.argv
    p.open_canvas(LW*SCALE, LH*SCALE, sync=not checking)
    disable_text_input(p)
    mode = None
    try:
        if not p.renderer:
            p.renderer = p.SDL_CreateRenderer(p.window, -1, p.SDL_RENDERER_SOFTWARE)
        assert p.renderer, p.SDL_GetError()
        p.print_fps = lambda: None
        p.SDL_SetWindowTitle(p.window, TITLE)
        if not checking:
            p.SDL_HideWindow(p.window)
            p.SDL_ShowWindow(p.window)
            p.SDL_RaiseWindow(p.window)
        mode = FlatReview()
        if checking:
            check(mode)
        else:
            print('Walk MVP ready: NW/NE16, matching Idle4, WASD/Tab/F3/Space/[ ].', flush=True)
            run_loop(mode, p)
    finally:
        if mode is not None:
            mode.view.close()
        p.close_canvas()


if __name__ == '__main__':
    main()
