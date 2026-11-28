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
from SourceCode.maze_model import COLS, DIAGONAL_FACINGS, ROWS, WALK_SPEED, Game, project
from SourceCode.window_input import disable_text_input

PACK = Path('sprite/quarter/player_explorer_walk_tuscan_v1')
VIDEO_PACK = Path('sprite/quarter/player_explorer_video_nw_review_v1')
FIELD_PACK = Path('sprite/quarter/player_explorer_field_nw_v2')
FIELD_IDLE_PACK = Path('sprite/quarter/player_explorer_field_draft_v1')
SE_PACK = Path('sprite/quarter/player_explorer_field_se_v4')
SE_PREVIOUS_PACK = Path('sprite/quarter/player_explorer_field_se_v3')
NE_PACK = Path('sprite/quarter/player_explorer_field_ne_omni_v1')
NE_PREVIOUS_PACK = Path('sprite/quarter/player_explorer_field_ne_v3')
SW_PACK = Path('sprite/quarter/player_explorer_field_sw_omni_v1')
FIELD_SW = '--field-sw' in sys.argv
FIELD_NE = FIELD_SW or '--field-ne' in sys.argv
FIELD_SE = FIELD_NE or '--field-se' in sys.argv
FIELD_NW = FIELD_SE or '--field-nw' in sys.argv
VIDEO_NW = FIELD_NW or '--video-nw' in sys.argv
DEFAULT_VARIANT = (
    'field-sw' if FIELD_SW else 'field-ne' if FIELD_NE else 'field-se' if FIELD_SE else
    'field' if FIELD_NW else 'video' if VIDEO_NW else 'after'
)
COMPARISON_VARIANT = (
    'field-sw-previous' if FIELD_SW else 'field-ne-previous' if FIELD_NE else
    'field-se-previous' if FIELD_SE else
    'video' if FIELD_NW else 'after' if VIDEO_NW else 'before'
)
KEYS = {p.SDLK_w: (-1, 0), p.SDLK_a: (0, 1),
        p.SDLK_s: (1, 0), p.SDLK_d: (0, -1)}
FACES = {p.SDLK_w: 'nw', p.SDLK_a: 'sw', p.SDLK_s: 'se', p.SDLK_d: 'ne'}
TITLE = b'Walk MVP - NW NE 16 - Flat Ground Review'


class ReviewView(View):
    def __init__(self):
        super().__init__(ROOT)
        self.variants = {}
        video_packs = []
        if VIDEO_NW:
            video_packs.append(('video', VIDEO_PACK))
        if FIELD_NW:
            video_packs.append(('field', FIELD_PACK))
        packs = [('after', PACK), ('before', PACK/'baseline'), *video_packs]
        self.video_paces = {}
        for name, directory in packs:
            data = json.loads((ROOT/directory/'walk.json').read_text(encoding='utf-8'))
            assert data['pivot'] == [32, 54] and data['frame_size'] == [64, 64]
            texture = 'review-' + name
            self.images[texture] = self.load(directory/data['image'], pixel=True)
            self.variants[name] = {
                key: {**clip, 'review_texture': texture}
                for key, clip in data['clips'].items()
            }
            if name in ('video', 'field'):
                video_clip = self.variants[name]['walk-nw']
                self.video_paces[name] = (WALK_SPEED * data['source']['video_period_s'],
                                          video_clip['cycle_distance_px'])
                self.variants[name] = self.variants['after'] | {'walk-nw': video_clip}
        idle = json.loads((ROOT/PACK/'idle.json').read_text(encoding='utf-8'))
        self.images['review-idle'] = self.load(PACK/idle['image'], pixel=True)
        idle_clips = {
            key: {**clip, 'review_texture': 'review-idle'}
            for key, clip in idle['clips'].items()
        }
        self.player_catalog['clips'].update(idle_clips)
        self.nw_idles = {'after': idle_clips['idle-nw']}
        for name, directory in video_packs:
            idle_pack = FIELD_IDLE_PACK if name == 'field' else directory
            video_idle = json.loads((ROOT/idle_pack/'idle.json').read_text(encoding='utf-8'))
            assert video_idle['pivot'] == idle['pivot'] and video_idle['frame_size'] == idle['frame_size']
            texture = f'review-{name}-idle'
            self.images[texture] = self.load(idle_pack/video_idle['image'], pixel=True)
            self.nw_idles[name] = {**video_idle['clips']['idle-nw'], 'review_texture': texture}
        if FIELD_SE:
            self.se_idles = {}
            for variant, pack in (('field-se-previous', SE_PREVIOUS_PACK), ('field-se', SE_PACK)):
                texture = f'review-{variant}'
                self.se_idles[variant] = self.field_clip(pack, 'idle', 'se', f'{texture}-idle')
                self.variants[variant] = {
                    **self.variants['field'],
                    'walk-se': self.field_clip(pack, 'walk', 'se', texture),
                }
                self.nw_idles[variant] = self.nw_idles['field']
        if FIELD_NE:
            before_ne, after_ne = 'field-ne-previous', 'field-ne'
            self.variants[before_ne] = {
                **self.variants['field-se'],
                'walk-ne': self.field_clip(NE_PREVIOUS_PACK, 'walk', 'ne', 'review-field-ne-previous'),
            }
            self.variants[after_ne] = {
                **self.variants['field-se'],
                'walk-ne': self.field_clip(NE_PACK, 'walk', 'ne', 'review-field-ne'),
            }
            self.ne_idles = {
                before_ne: self.field_clip(NE_PREVIOUS_PACK, 'idle', 'ne', 'review-field-ne-previous-idle'),
                after_ne: self.field_clip(NE_PACK, 'idle', 'ne', 'review-field-ne-idle'),
            }
            for variant in (before_ne, after_ne):
                self.nw_idles[variant] = self.nw_idles['field']
                self.se_idles[variant] = self.se_idles['field-se']
        if FIELD_SW:
            self.variants[COMPARISON_VARIANT] = dict(self.variants['field-ne'])
            self.variants[DEFAULT_VARIANT] = {
                **self.variants['field-ne'],
                'walk-sw': self.field_clip(SW_PACK, 'walk', 'sw', 'review-field-sw'),
            }
            self.sw_idles = {
                COMPARISON_VARIANT: idle_clips['idle-sw'],
                DEFAULT_VARIANT: self.field_clip(SW_PACK, 'idle', 'sw', 'review-field-sw-idle'),
            }
            for variant in (COMPARISON_VARIANT, DEFAULT_VARIANT):
                self.nw_idles[variant] = self.nw_idles['field-ne']
                self.se_idles[variant] = self.se_idles['field-ne']
                self.ne_idles[variant] = self.ne_idles['field-ne']
        self.variant = 'after'
        self.authored_pace = True
        self.playback_rate = 1.
        self.actual_fps = 0.
        self.set_pace(not VIDEO_NW)
        self.set_variant(DEFAULT_VARIANT)

    def field_clip(self, pack, action, facing, texture):
        data = json.loads((ROOT/pack/f'{action}.json').read_text(encoding='utf-8'))
        assert data['pivot'] == [32, 54] and data['frame_size'] == [64, 64]
        self.images[texture] = self.load(pack/data['image'], pixel=True)
        return {**data['clips'][f'{action}-{facing}'], 'review_texture': texture}

    def set_variant(self, name):
        self.variant = name
        self.player_catalog['clips'].update(self.variants[name])
        if VIDEO_NW:
            self.player_catalog['clips']['idle-nw'] = self.nw_idles[name]
        if FIELD_SE:
            self.player_catalog['clips']['idle-se'] = self.se_idles[name]
        if FIELD_NE:
            self.player_catalog['clips']['idle-ne'] = self.ne_idles[name]
        if FIELD_SW:
            self.player_catalog['clips']['idle-sw'] = self.sw_idles[name]

    def set_pace(self, authored):
        self.authored_pace = authored
        distance = WALK_SPEED*.8 if authored or VIDEO_NW else 35.77708763999664
        for clips in self.variants.values():
            for clip in clips.values():
                clip['cycle_distance_px'] = distance
        for name, (source_distance, contact_distance) in self.video_paces.items():
            self.variants[name]['walk-nw']['cycle_distance_px'] = (
                source_distance if authored else contact_distance
            )
        if FIELD_SE:
            distance = self.variants['field']['walk-nw']['cycle_distance_px']
            for name in (DEFAULT_VARIANT, COMPARISON_VARIANT):
                self.variants[name]['walk-se']['cycle_distance_px'] = distance
                if FIELD_NE:
                    self.variants[name]['walk-ne']['cycle_distance_px'] = distance
                if FIELD_SW:
                    self.variants[name]['walk-sw']['cycle_distance_px'] = distance

    def walk_period(self, facing):
        return self.player_catalog['clips']['walk-'+facing]['cycle_distance_px']/WALK_SPEED

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
        if FIELD_SW:
            label = {'SW': '탐험가 A 영상' if self.variant == DEFAULT_VARIANT else '기존 A',
                     'NW': '탐험가 W v2', 'SE': '탐험가 S v4', 'NE': '탐험가 D 영상'}[face]
        elif FIELD_NE:
            label = {'NE': '탐험가 D 영상' if self.variant == 'field-ne' else '탐험가 D v3',
                     'NW': '탐험가 W v2', 'SE': '탐험가 S v4'}.get(face, '기존')
        elif FIELD_SE:
            label = {'SE': '탐험가 S v4' if self.variant == 'field-se' else '탐험가 S v3',
                     'NW': '탐험가 W v2'}.get(face, '기존')
        elif VIDEO_NW:
            label = {'field': '탐험가 W v2', 'video': '영상 W', 'after': '기존 W'}[self.variant]
        else:
            label = '수정 후' if self.variant == 'after' else '수정 전'
        tone = (245, 230, 200)
        self.rectangle(14, 12, 440, 96, (24, 24, 28, 240))
        self.text(f'{label} · {face} {state} {index:02}/{len(clip["frames"])-1:02}'
                  f' · {self.walk_period(face.lower()):.3f}초', 24, 21, tone, size='hud_font')
        self.text(f'게임 {WALK_SPEED:.1f}px/s · 재생 {self.playback_rate:g}배'
                  f' · 표시 {self.actual_fps:.0f}FPS', 24, 44, tone)
        comparison_key = ('Tab A 전후 비교' if FIELD_SW else 'Tab D 전후 비교' if FIELD_NE else
                          'Tab S 전후 비교' if FIELD_SE else 'Tab 전후 비교')
        self.text('W 북서  A 남서  S 남동  D 북동  |  '+comparison_key, 24, 65, tone)
        pace_keys = ('1 영상 동기 / 2 접지 동기' if FIELD_SE
                     else '1 영상 주기  2 접지 기준' if VIDEO_NW else '1 0.8초  2 0.4초')
        self.text(pace_keys+'  F3 느리게  Space 정지  [ ] 한 장  R 중앙', 24, 86, tone)
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
        player.direction = 0 if FIELD_SW else 3 if FIELD_NE else 2 if FIELD_SE else 1 if VIDEO_NW else 3
        player.screen_facing = DIAGONAL_FACINGS[player.direction]
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
                    self.view.set_variant(
                        COMPARISON_VARIANT if self.view.variant == DEFAULT_VARIANT else DEFAULT_VARIANT
                    )
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
    for variant in (COMPARISON_VARIANT, DEFAULT_VARIANT):
        mode.view.set_variant(variant)
        for authored in (True, False):
            mode.view.set_pace(authored)
            if FIELD_SE:
                period = mode.view.walk_period('nw')
                sync_keys = (p.SDLK_w, p.SDLK_s, p.SDLK_d) if FIELD_NE else (p.SDLK_w, p.SDLK_s)
                if FIELD_SW:
                    sync_keys += (p.SDLK_a,)
                for key in sync_keys:
                    assert mode.view.walk_period(FACES[key]) == period
                    mode.reset()
                    mode.held = [key]
                    for frame in range(1, 49):
                        # Both half-frame ticks fit within the game's 50 ms update cap.
                        mode.update(period/32)
                        mode.update(period/32)
                        _, index = mode.view.player_pose(mode.game)
                        assert index == frame % 16
            for key, face in FACES.items():
                period = mode.view.walk_period(face)
                expected_clip = mode.view.variants[variant]['walk-'+face]
                for fps in (60, 30, 20):
                    mode.reset()
                    mode.held = [key]
                    initial = project(mode.game.player.x, mode.game.player.y)
                    ticks = round(3*period*fps)
                    for tick in range(ticks):
                        mode.update(1/fps)
                        clip, index = mode.view.player_pose(mode.game)
                        assert clip is expected_clip and 0 <= index < len(clip['frames'])
                    distance = math.dist(initial, project(mode.game.player.x, mode.game.player.y))
                    assert math.isclose(distance, ticks/fps*WALK_SPEED, abs_tol=1e-7)
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
                    idle_variant = 'field' if FIELD_SE else variant
                    expected_idle = 'review-idle'
                    if face == 'nw' and idle_variant in mode.view.video_paces:
                        expected_idle = f'review-{idle_variant}-idle'
                    elif face == 'se' and FIELD_SE:
                        expected_idle = 'review-field-se-idle' if FIELD_NE else f'review-{variant}-idle'
                    elif face == 'ne' and FIELD_NE:
                        expected_idle = 'review-field-ne-idle' if FIELD_SW else f'review-{variant}-idle'
                    elif face == 'sw' and FIELD_SW and variant == DEFAULT_VARIANT:
                        expected_idle = 'review-field-sw-idle'
                    assert clip['review_texture'] == expected_idle
                    mode.held = [key]
                    mode.update(.001)
                    clip, _ = mode.view.player_pose(mode.game)
                    assert clip is mode.view.variants[variant]['walk-'+face]
                    assert math.isclose(player.gait_phase,
                                        (saved+.001/mode.view.walk_period(face)) % 1., abs_tol=1e-8)
                    restarts += 1
                    for other, other_face in FACES.items():
                        if other == key:
                            continue
                        player.gait_phase = phase
                        mode.held = [other]
                        mode.update(.001)
                        clip, index = mode.view.player_pose(mode.game)
                        expected = (phase+.001/mode.view.walk_period(other_face)) % 1.
                        assert clip['direction'] == other_face
                        assert math.isclose(player.gait_phase, expected, abs_tol=1e-8)
                        turns += 1
    assert all(len(c['frames']) == 16 for c in mode.view.variants['after'].values())
    for variant in mode.view.video_paces:
        for name, clip in mode.view.variants[variant].items():
            if name == 'walk-nw':
                assert len(clip['frames']) == 16 and clip['review_texture'] == f'review-{variant}'
            else:
                assert clip is mode.view.variants['after'][name]
    if FIELD_NW:
        assert mode.view.video_paces['field'] == mode.view.video_paces['video']
        versions = [mode.view.variants[name]['walk-nw'] for name in ('field', 'video')]
        assert versions[0]['durations_ms'] == versions[1]['durations_ms']
    if FIELD_SE:
        a, b = (mode.view.variants[name] for name in (COMPARISON_VARIANT, DEFAULT_VARIANT))
        action = 'walk-sw' if FIELD_SW else 'walk-ne' if FIELD_NE else 'walk-se'
        assert all(a[name] is b[name] for name in a if name != action)
        assert b[action]['review_texture'] == f'review-{DEFAULT_VARIANT}'
        assert len(b[action]['frames']) == 16
        for key in ('cycle_distance_px', 'step_events', 'phase_offset_frames'):
            assert a[action][key] == b[action][key]
        assert b[action]['cycle_distance_px'] == b['walk-nw']['cycle_distance_px']
        group = 'W/A/S/D' if FIELD_SW else 'W/S/D' if FIELD_NE else 'W/S'
        print(f'PASS: {group} select the same frame at equal travel for 3 loops in both pace modes.')
    mode.view.set_variant(DEFAULT_VARIANT)
    mode.reset()
    mode.view.draw(mode.game)
    mode.game.ui_time += 1.
    mode.view.draw(mode.game)
    if VIDEO_NW:
        review_key = p.SDLK_a if FIELD_SW else p.SDLK_d if FIELD_NE else p.SDLK_s if FIELD_SE else p.SDLK_w
        mode.held = [review_key]
        mode.update(.001)
        mode.view.draw(mode.game)
        mode.held.clear()
        mode.update(.001)
        mode.view.draw(mode.game)
        selected = {p.SDLK_a: 'A', p.SDLK_d: 'D', p.SDLK_s: 'S', p.SDLK_w: 'W'}[review_key]
        print(f'PASS: {selected} Idle and Walk render, including stop and restart.')
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
        title = b'Explorer A Omni Idle + Walk - Flat Ground Review' if FIELD_SW else (
            b'Explorer D Omni Idle + Walk - Flat Ground Review' if FIELD_NE else
            b'Explorer S v4 Idle + Walk - Flat Ground Review' if FIELD_SE else
            b'Explorer W v2 Idle + Walk - Flat Ground Review' if FIELD_NW else
            b'W NW Idle + Walk - Flat Ground Review' if VIDEO_NW else TITLE
        )
        p.SDL_SetWindowTitle(p.window, title)
        if not checking:
            p.SDL_HideWindow(p.window)
            p.SDL_ShowWindow(p.window)
            p.SDL_RaiseWindow(p.window)
        mode = FlatReview()
        if checking:
            check(mode)
        else:
            label = {'field-sw': 'Explorer A Omni Idle + Walk (16 frames)',
                     'field-ne': 'Explorer D Omni Idle + Walk (16 frames)',
                     'field-se': 'Explorer S v4 Idle + Walk (16 frames)',
                     'field': 'Explorer W Idle + Walk (16 frames)',
                     'video': 'W NW video Idle + Walk (16 frames)',
                     'after': 'Walk MVP NW/NE16'}[DEFAULT_VARIANT]
            print(f'{label} ready. WASD/Tab/F3/Space/[ ].', flush=True)
            run_loop(mode, p)
    finally:
        if mode is not None:
            mode.view.close()
        p.close_canvas()


if __name__ == '__main__':
    main()
