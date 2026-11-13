"""Quarter-view exploration and fixed-front 2D-perspective trap rendering."""
from bisect import bisect_right
import ctypes
from itertools import accumulate
import json
import math
from pathlib import Path
import pico2d.pico2d as p
from maze_model import BASE_SIGHT_RADIUS, TORCH_SIGHT_RADIUS, COLS, ROWS, PHASES, TRAP_LENGTH
from maze_model import PHASE_SECONDS, SHIFT_SECONDS, SHIFT_SWAP_AT
from maze_model import ATTACK_FORWARD, DEFAULT_ATTACK_HIT_MS, HALF_TILE_W, HALF_TILE_H, project
from trap_view import Corridor

LW, LH, SCALE = 640, 400, 2
MAP_RECT = (8, 32, 496, 368)
WALL_NEIGHBORS = ((0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8))
MEMORY_LIGHT = .32
LIGHT_FADE_SECONDS = .20
TORCH_MOUNT_HEIGHT = 24
PLAYER_ATLAS_DIR = Path('sprite/quarter/player_explorer_attack_v2')


class View:
    def __init__(self, root):
        self.root = Path(root)
        self.images, self.effects = {}, {}
        self.text_cache={}
        self.atlases = {}
        self.small = p.load_font('C:/Windows/Fonts/malgun.ttf', 10)
        self.font = p.load_font('C:/Windows/Fonts/malgun.ttf', 12)
        self.title = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 17)
        self.big = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 46)
        player = PLAYER_ATLAS_DIR
        self.player_catalog = json.loads((self.root/player/'explorer.json').read_text(encoding='utf-8'))
        directions = self.player_catalog['world_direction_to_screen']
        self.facing = tuple(directions[name] for name in ('down', 'left', 'right', 'up'))
        self.images['player'] = self.load(player/self.player_catalog['image'], pixel=True)
        if layer_image := self.player_catalog.get('moving_attack_image'):
            self.images['moving-attack'] = self.load(player/layer_image, pixel=True)
        for name, folder in (('terrain', 'terrain_v1'), ('props', 'props_v1'),
                             ('guardian', 'guardian_v1'), ('shortcuts', 'shortcuts_v1')):
            directory = Path('sprite/quarter')/folder
            data = json.loads((self.root/directory/'catalog.json').read_text(encoding='utf-8'))
            self.images[name] = self.load(directory/data['image'], pixel=True)
            self.atlases[name] = data['frames']
        torch = Path('sprite/topdown/effects/torch')
        self.effects['torch'] = json.loads((self.root/torch.with_suffix('.json')).read_text())
        self.images['torch'] = self.load(torch.with_suffix('.png'), pixel=True)
        dagger_dir = Path('sprite/quarter/effects')
        self.dagger_fx = json.loads((self.root/dagger_dir/'dagger-slash.json').read_text(encoding='utf-8'))
        self.dagger_frame_starts_ms = tuple(self.dagger_fx['frame_starts_ms'])
        self.dagger_end_ms = self.dagger_fx['start_ms']+self.dagger_fx['duration_ms']
        self.images['dagger-slash'] = self.load(dagger_dir/self.dagger_fx['image'], pixel=True)
        self.logical = self.target(LW, LH)
        self.display = self.target(LW*SCALE, LH*SCALE)
        self.corridor = Corridor(self)
        self.origin, self.world_scale = (0, 0), 1
        self.camera, self.camera_game = None, None
        self.light_game, self.light_time, self.torch_light = None, 0., 0.
        self.discovery, self.exposure = {}, {}
        self.light_revision = -1
        self.last_mode, self.mode_changed = None, -10
        self.mode_game = None

    def load(self, path, pixel=False):
        image = p.load_image(str(self.root/path))
        p.SDL_SetTextureScaleMode(image.texture, p.SDL_ScaleModeNearest if pixel else p.SDL_ScaleModeLinear)
        p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND)
        return image

    def atlas(self, x, y, name, frame, tint=(255, 255, 255), opacity=1.):
        item = self.atlases[name][frame]
        sx, sy, w, h = item['rect']
        px, py = item['pivot']
        scale = self.world_scale
        self.image(name, (x-px*scale, y-py*scale, w*scale, h*scale),
                   (sx, sy, w, h), tint, alpha=round(255*opacity))

    @staticmethod
    def target(w, h):
        texture = p.SDL_CreateTexture(p.renderer, p.SDL_PIXELFORMAT_RGBA8888, p.SDL_TEXTUREACCESS_TARGET, w, h)
        assert texture, p.SDL_GetError()
        p.SDL_SetTextureScaleMode(texture, p.SDL_ScaleModeNearest)
        p.SDL_SetTextureBlendMode(texture, p.SDL_BLENDMODE_BLEND)
        return texture

    @staticmethod
    def rectangle(x, y, w, h, color):
        p.SDL_SetRenderDrawBlendMode(p.renderer, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetRenderDrawColor(p.renderer, *color[:3], color[3] if len(color)>3 else 255)
        p.SDL_RenderFillRect(p.renderer, p.SDL_Rect(round(x), round(y), round(w), round(h)))

    @staticmethod
    def line(x1, y1, x2, y2, color):
        p.SDL_SetRenderDrawColor(p.renderer, *color, 255)
        p.SDL_RenderDrawLine(p.renderer, round(x1), round(y1), round(x2), round(y2))

    @staticmethod
    def clear(color=(9, 13, 17, 255)):
        p.SDL_SetRenderDrawColor(p.renderer, *color)
        p.SDL_SetRenderDrawBlendMode(p.renderer, p.SDL_BLENDMODE_NONE)
        p.SDL_RenderClear(p.renderer)

    def image(self, name, rect, source=None, tint=(255, 255, 255), angle=0, flip=False, alpha=255):
        if not alpha:
            return
        image = self.images[name]
        p.SDL_SetTextureColorMod(image.texture, *tint)
        if alpha != 255:
            p.SDL_SetTextureAlphaMod(image.texture, alpha)
        dst = p.SDL_Rect(*(round(v) for v in rect))
        src = p.SDL_Rect(*source) if source else None
        if angle or flip:
            p.SDL_RenderCopyEx(p.renderer, image.texture, src, dst, angle, None, p.SDL_FLIP_HORIZONTAL if flip else p.SDL_FLIP_NONE)
        else:
            p.SDL_RenderCopy(p.renderer, image.texture, src, dst)
        if alpha != 255:
            p.SDL_SetTextureAlphaMod(image.texture, 255)

    def text(self, text, x, y, color=(199, 203, 189), size='small'):
        key=(text,color,size)
        image=self.text_cache.get(key)
        if image is None:
            surface=p.TTF_RenderUTF8_Blended(getattr(self,size).font,text.encode('utf-8'),p.SDL_Color(*color,255))
            assert surface
            try:
                texture=p.SDL_CreateTextureFromSurface(p.renderer,surface)
                assert texture
                image=p.Image(texture)
            finally:
                p.SDL_FreeSurface(surface)
            self.text_cache[key]=image
            if len(self.text_cache)>512:
                self.text_cache.pop(next(iter(self.text_cache)))
        image.draw(x+image.w/2,LH-y)

    def attack_frame_index(self, game):
        clip = self.player_catalog['clips'].get(game.attack_clip)
        if clip is not None:
            for index, end_ms in enumerate(accumulate(clip['durations_ms'])):
                if game.attack_time < end_ms/1000:
                    return index
        return None

    def player_frame(self, game):
        clip, index = self.player_pose(game)
        return clip['frames'][index]['rect']

    def player_pose(self, game):
        clips = self.player_catalog['clips']
        attack_index = self.attack_frame_index(game)
        if attack_index is not None:
            return clips[game.attack_clip], attack_index
        state = {'walk': 'walk', 'sprint': 'run'}.get(game.player.state, 'idle')
        return self.locomotion_pose(game, state)

    def locomotion_pose(self, game, state):
        name = game.locomotion_clip_name(state)
        clip = self.player_catalog['clips'][name]
        if state == 'idle':
            return clip, clip.get('still_frame', 0)

        # 거리 위상과 클립별 접지 오프셋으로 보행 프레임을 선택한다.
        offset = clip.get('phase_offset_frames', int(name == 'walk-nw'))
        count = len(clip['frames'])
        index = int(game.player.gait_phase*count+1e-9)
        return clip, (index+offset) % count

    def dagger_frame(self, game, x, y, body, attack_index):
        # 각 타격에서 같은 검격 효과를 재생하고, 효과의 타격 포즈를 이벤트에 맞춘다.
        time = game.attack_time
        for hit_ms in game.attack_hits_ms:
            offset_ms = hit_ms-DEFAULT_ATTACK_HIT_MS
            start = (self.dagger_frame_starts_ms[0]+offset_ms)/1000
            end = (self.dagger_end_ms+offset_ms)/1000
            if start <= time < end:
                break
        else:
            return None
        clip = self.dagger_fx['clips'][body['direction']]
        index = bisect_right(self.dagger_frame_starts_ms, time, key=lambda ms: (ms+offset_ms)/1000)-1
        rect = clip['frames'][index]['rect']
        scale = self.world_scale
        # Follow the dagger pose currently shown in the body atlas, including the recovery.
        tip_x, tip_y = clip['tip_px'][attack_index]
        px, py = self.player_catalog['pivot']
        anchor_x, anchor_y = clip['anchor_px'][index]
        dst = (x+(tip_x-px-anchor_x)*scale, y+(tip_y-py-anchor_y)*scale,
               rect[2]*scale, rect[3]*scale)
        return clip['draw_layer'], dst, rect

    def player(self, x, y, game):
        scale = self.world_scale
        clip, index = self.player_pose(game)
        frame = clip['frames'][index]['rect']
        px, py = self.player_catalog['pivot']
        left, top = x-px*scale, y-py*scale
        mounts = clip.get('torch_mounts') if game.player.torch else None
        torch = None
        if mounts:
            ax, ay = mounts[index]
            torch = (left+ax*scale, top+ay*scale, game.time, .22*scale)
        torch_in_front = clip.get('direction') in ('n', 'ne', 'e', 'nw')

        attacking = clip is self.player_catalog['clips'].get(game.attack_clip)
        dagger = self.dagger_frame(game, x, y, clip, index) if attacking else None
        if dagger and dagger[0] == 'back':
            self.image('dagger-slash', dagger[1], dagger[2])
        if torch and not torch_in_front:
            self.effect('torch', *torch)
        movement = {'walk': 'walk', 'sprint': 'run'}.get(game.player.state)
        destination = (left, top, frame[2]*scale, frame[3]*scale)
        if movement and 'upper_layer_rects' in clip:
            legs = self.moving_attack_legs(game, movement, clip['direction'])
            self.image('moving-attack', destination, legs)
            self.image('moving-attack', destination, clip['upper_layer_rects'][index])
        else:
            self.image('player', destination, frame)
        if torch and torch_in_front:
            self.effect('torch', *torch)
        if dagger and dagger[0] == 'front':
            self.image('dagger-slash', dagger[1], dagger[2])

    def moving_attack_legs(self, game, state, facing):
        # Keep the view of the legs aligned to the locked upper body. Backward
        # movement plays the same distance-based stride in reverse.
        clips = self.player_catalog['clips']
        name = state+'-'+facing
        if name not in clips:
            # Cardinal sprints use diagonal sprites in normal play. During a
            # cardinal attack use the matching walk legs to keep both views aligned.
            name = 'walk-'+facing
        clip = clips[name]
        frames = clip['leg_layer_rects']
        ax, ay = ATTACK_FORWARD[facing]
        mx, my = ATTACK_FORWARD.get(game.player.screen_facing, (ax, ay))
        phase = game.player.gait_phase
        # Undo the screen's 2:1 ground projection before testing direction.
        if ax*mx/HALF_TILE_W**2 + ay*my/HALF_TILE_H**2 < 0:
            phase = (-phase) % 1
        index = int(phase*len(frames)+1e-9) + clip.get('phase_offset_frames', int(name == 'walk-nw'))
        return frames[index % len(frames)]

    def guardian(self, x, y, game, tint):
        self.atlas(x, y, 'guardian', 'idle_'+self.facing[game.guard_direction], tint)
        if game.time < game.guard_alert_until:
            scale = self.world_scale
            self.rectangle(x-12*scale, y-56*scale, 24*scale, 2*scale, (36,29,26))
            self.rectangle(x-12*scale, y-56*scale, 8*game.guard_hp*scale, 2*scale, (155,75,59))

    def prop(self, x, y, frame, tint, game):
        scale = self.world_scale
        if frame.startswith('torch_wall_'):
            y -= TORCH_MOUNT_HEIGHT*scale
        self.atlas(x, y, 'props', frame, tint)
        wick = self.atlases['props'][frame].get('wick_anchor')
        if wick is not None and not game.player.torch:
            px, py = self.atlases['props'][frame]['pivot']
            self.effect('torch', x+(wick[0]-px)*scale, y+(wick[1]-py)*scale, game.time, .26*scale)

    def world(self, x, y):
        sx, sy = project(x, y)
        return self.origin[0]+sx*self.world_scale, self.origin[1]+sy*self.world_scale

    def position_camera(self, game):
        left, top, width, height = MAP_RECT
        center_x, center_y = left+width/2, top+height/2
        if game.reveal_all:
            self.world_scale = .25
            mid_x, mid_y = project(COLS/2, ROWS/2)
            # Center the full ground bounds with room for the walls above them.
            self.origin = (round(center_x-mid_x*.25), round(center_y-(mid_y-32)*.25))
            return
        self.world_scale = 1
        px, py = project(game.player.x, game.player.y)
        if self.camera_game is not game or self.last_mode == 'trap':
            self.camera_game = game
            self.camera = (center_x-px, center_y-py)
        cx, cy = self.camera
        self.camera = (min(center_x+84-px, max(center_x-84-px, cx)),
                       min(center_y+56-py, max(center_y-56-py, cy)))
        self.origin = tuple(round(coordinate) for coordinate in self.camera)

    def badge(self, label, x, y, color):
        self.rectangle(x-5,y-6,11,12,(17,22,23,230))
        self.rectangle(x-5,y-6,11,1,color)
        self.text(label,x-3,y,color)

    @staticmethod
    def shortcut_mount(game, cell):
        # Prefer a rear wall so the opening faces the camera.
        for dx,dy,facing in ((0,-1,'south'),(-1,0,'east')):
            if game.solid(cell[0]+dx,cell[1]+dy):
                return cell[0]+.5+dx*.48,cell[1]+.5+dy*.48,facing
        for dx,dy,facing in ((1,0,'west'),(0,1,'north')):
            if game.solid(cell[0]+dx,cell[1]+dy):
                return cell[0]+.5,cell[1]+.5,facing
        return cell[0]+.5,cell[1]+.5,'south'

    def shortcut(self, x, y, facing, arrival, tint):
        frame = ('trap_arrival_' if arrival else 'trap_entry_')+facing
        self.atlas(x, y, 'shortcuts', frame, tint)

    def update_lighting(self, game):
        if game is not self.light_game or self.light_revision != game.layout_revision:
            self.light_game = game
            self.light_revision = game.layout_revision
            self.light_time = game.ui_time
            self.torch_light = float(game.player.torch)
            # 다른 시간대 캐시로 새 벽 너머나 미방문 칸이 드러나지 않게 초기화한다.
            self.discovery = dict.fromkeys(game.observed, 1.)
            self.exposure = dict.fromkeys(game.visible, 1.)
        step = min(1., max(0., game.ui_time-self.light_time)/LIGHT_FADE_SECONDS)
        self.light_time = game.ui_time
        self.torch_light = min(1., self.torch_light+step) if game.player.torch else max(0., self.torch_light-step)
        for cell in game.observed:
            self.discovery[cell] = min(1., self.discovery.get(cell, 0.)+step)
            exposure = self.exposure.get(cell, 0.)
            self.exposure[cell] = min(1., exposure+step) if cell in game.visible else max(0., exposure-step)

    def terrain_light(self, game, x, y):
        reach = BASE_SIGHT_RADIUS+(TORCH_SIGHT_RADIUS-BASE_SIGHT_RADIUS)*self.torch_light
        distance = math.hypot(x+.5-game.player.x, y+.5-game.player.y)
        # Smoothstep across the outer 60% of the radius, with a full-light center.
        edge = max(0., min(1., (reach-distance)/(.6*reach)))
        radial = edge*edge*(3.-2.*edge)
        light = radial*self.exposure.get((x, y), 0.)
        brightness = self.discovery.get((x, y), 0.)*(MEMORY_LIGHT+(1.-MEMORY_LIGHT)*light)
        if game.reveal_all:
            brightness = 1. if (x, y) in game.visible else .8
        phase_tint=((.94,.96,1.),(.70,.79,.94),(.82,.90,.96))[game.phase]
        if self.torch_light:
            phase_tint = tuple(min(1., c+warm*light*self.torch_light) for c, warm in zip(phase_tint, (.30,.13,0.)))
        return tuple(round(255*c) for c in phase_tint), brightness

    def tile_tint(self, game, x, y):
        tint, brightness = self.terrain_light(game, x, y)
        return tuple(round(channel*brightness) for channel in tint)

    def terrain(self, x, y, frame, tint, brightness, opacity=1.):
        if brightness > 0:
            self.atlas(x, y, 'terrain', frame, tint, opacity)
        if brightness < 1:
            # Shade only the sprite's shape. The underlying wall stays opaque.
            self.atlas(x, y, 'terrain', frame, (0, 0, 0), (1.-brightness)*opacity)

    def shifting_wall(self, x, y, frame, tint, brightness, cell, game):
        """바뀌는 벽만 내려앉거나 솟아오르게 한다. 충돌은 모델의 교체 시점을 따른다."""
        opacity = 1.
        if game.state == 'shifting' and cell in game.shift_cells:
            if game.shift_applied:
                opacity = (game.shift_elapsed-SHIFT_SWAP_AT)/(SHIFT_SECONDS-SHIFT_SWAP_AT)
            else:
                opacity = 1.-game.shift_elapsed/SHIFT_SWAP_AT
            opacity = max(0., min(1., opacity))
        # 테스트 연출값: 최대 24 논리 픽셀을 내려서 기존 벽 에셋을 재사용한다.
        self.terrain(x, y+(1.-opacity)*24*self.world_scale, frame, tint, brightness, opacity)

    def wall_mask(self, game, x, y):
        mask = 0
        for dx, dy, bit in WALL_NEIGHBORS:
            nx, ny = x+dx, y+dy
            if 0 <= nx < COLS and 0 <= ny < ROWS and game.grid[ny][nx]:
                # Keep the end cap until the neighboring wall has faded in.
                if game.reveal_all or self.discovery.get((nx, ny)) == 1.:
                    mask |= bit
        return mask

    def effect(self, name, x, y, seconds, scale=1, angle=0):
        data = self.effects[name]
        meta = data['meta']['pixelfx']
        frame_id = int(max(0, seconds)*meta['fps'])
        if meta['loop']:
            frame_id %= meta['frames']
        elif frame_id >= meta['frames']:
            return
        frame = data['frames'][frame_id]['frame']
        ox, oy = meta['pivot']
        self.image(name, (x-ox*scale, y-oy*scale, frame['w']*scale, frame['h']*scale),
                   (frame['x'], frame['y'], frame['w'], frame['h']), angle=angle)

    def quarter(self, game):
        self.clear((0, 0, 0, 255))
        self.position_camera(game)
        if game.state == 'shifting':
            # 테스트 진동: 미로 좌표만 최대 2픽셀 이동하며 HUD·지도는 고정한다.
            pulse = math.sin(math.pi*game.shift_elapsed/SHIFT_SECONDS)
            shake = round(2*pulse*math.sin(game.shift_elapsed*80))
            self.origin = self.origin[0]+shake, self.origin[1]-shake
        self.update_lighting(game)
        left, top, width, height = MAP_RECT
        p.SDL_RenderSetClipRect(p.renderer, p.SDL_Rect(*MAP_RECT))
        scene = []
        drawn_cells = {(x, y) for y in range(ROWS) for x in range(COLS)} if game.reveal_all else game.observed

        def place(draw, x, y, *args):
            scene.append((x+y, draw, (*self.world(x, y), *args)))

        for x, y in drawn_cells:
            sx, sy = self.world(x+.5, y+.5)
            if not (left-32 <= sx <= left+width+32 and top-16 <= sy <= top+height+80):
                continue
            tint, brightness = self.terrain_light(game, x, y)
            variant = (x*3+y*5+game.seed) % 4
            self.terrain(sx, sy, f'floor_{variant}', tint, brightness)
            if game.grid[y][x]:
                mask = self.wall_mask(game, x, y)
                place(self.shifting_wall, x+.5, y+.5, f'wall_{mask}', tint, brightness, (x, y), game)

        for (x, y), frame in ((game.exit, 'rope_exit'),
                              (game.fountain, 'fountain_empty' if game.fountain_used else 'fountain_full')):
            if (x, y) in game.visible or game.reveal_all:
                place(self.prop, x+.5, y+.5, frame, self.tile_tint(game, x, y), game)

        x, y = game.torch_cell
        if game.torch_wall is not None and ((x, y) in game.visible or game.reveal_all):
            # 에셋 방향은 통로에서 본 벽 위치가 아니라 벽의 노출 면 기준이다.
            side = 'right' if game.torch_wall[0] < x else 'left'
            state = 'empty' if game.player.torch else 'full'
            place(self.prop, *game.torch_wall_contact, f'torch_wall_{side}_{state}',
                  self.tile_tint(game, x, y), game)

        markers = []
        for cell, arrival in ((game.trap_cell, False), (game.trap_exit, True)):
            if cell not in game.visible and not game.reveal_all:
                continue
            x, y, facing = self.shortcut_mount(game, cell)
            place(self.shortcut, x, y, facing, arrival, self.tile_tint(game, *cell))
            sx, sy = self.world(cell[0]+.5, cell[1]+.5)
            color = (127,197,183) if arrival else (218,175,107)
            markers.append(('B' if arrival else 'A', sx+18*self.world_scale, sy, color))
            if arrival and game.time < game.landing_until:
                pulse = math.sin(game.time*5)
                radius = (12+3*pulse)*self.world_scale
                self.rectangle(sx-radius, sy+6*self.world_scale, radius*2, 2,
                               (*color, round(100+40*pulse)))

        if game.guard_hp and (game.guard in game.visible or game.reveal_all):
            x, y = game.guard
            place(self.guardian, x+.5, y+.5, game, self.tile_tint(game, x, y))
        place(self.player, game.player.x, game.player.y, game)
        # Sort all upright art together by its ground point, independent of sprite height.
        for _, draw, params in sorted(scene, key=lambda item: item[0]):
            draw(*params)
        for marker in markers:
            self.badge(*marker)
        p.SDL_RenderSetClipRect(p.renderer, None)

    def trap(self, game):
        self.corridor.draw(game)

    def hud_trap(self, game):
        self.rectangle(0,0,640,30,(12,18,22,235))
        self.text('HP',12,14,(207,202,184))
        self.rectangle(33,11,80,5,(48,45,41))
        self.rectangle(33,11,game.player.hp*.8,5,(169,83,64))
        self.text('ST',126,14,(207,202,184))
        self.rectangle(148,11,70,5,(48,45,41))
        self.rectangle(148,11,game.player.stamina*.7,5,(113,143,106))
        self.text('칼날의 통로',272,15,(217,198,154),size='font')
        self.text(f'{PHASES[game.phase]} {math.ceil(PHASE_SECONDS-game.phase_time):02d}s',417,14,(217,190,131))
        self.text('A 입구 → B 출구',537,14,(134,192,179))
        self.rectangle(0,397,640,3,(28,32,31))
        self.rectangle(0,397,640*game.trap_progress,3,(179,151,94))
        self.rectangle(157,368,326,22,(13,17,18,210))
        self.text('W/S 전진·후진   A/D 회피   Shift 달리기',173,380,(224,212,183))
        self.text(f'출구까지 {max(0,TRAP_LENGTH*(1-game.trap_progress)):.1f} m',535,379,(205,196,166))
        flash=max(0,1-(game.time-game.trap_hit_at)/.2)
        if flash:
            self.rectangle(0,30,640,367,(145,30,18,round(75*flash)))
        if game.time<game.banner_until:
            self.rectangle(145,35,350,21,(12,16,18,205))
            self.text(game.banner,155,45,(221,203,165))
        if game.phase_warning:
            self.text('곧 미로 변형 · 입장 전 위치로 복귀',190,69,(239,183,104),size='font')

    def hud(self, game, fps=0):
        self.rectangle(0,0,640,30,(12,18,22))
        self.text('초보자를 위한 미로 탈출 안내서',10,14,size='font')
        self.rectangle(512,30,128,370,(16,23,27))
        self.rectangle(512,30,1,370,(71,77,70))
        self.text('미궁 탐색 · 쿼터뷰',523,49,size='font')
        self.text(f'{PHASES[game.phase]}  {math.ceil(PHASE_SECONDS-game.phase_time):02d}s',523,73,(217,190,131),size='font')
        if game.state == 'shifting':
            phase_status = '벽·통로 변형 중'
        elif game.phase_warning:
            phase_status = f'곧 {PHASES[(game.phase+1) % 3]} · 변형 예고'
        else:
            phase_status = f'적용 지형 · {PHASES[game.layout_phase]}'
        self.text(phase_status,523,91,(217,180,115) if game.phase_warning else (129,139,137))
        for y,label,value,color in [(115,'HP',game.player.hp,(158,77,66)),(148,'ST',game.player.stamina,(113,143,106))]:
            self.text(f'{label}  {int(value):3d}',523,y,(194,198,182))
            self.rectangle(523,y+10,104,6,(36,43,44))
            self.rectangle(523,y+10,value*1.04,6,color)
        self.text('횃불: 획득' if game.player.torch else '횃불: 미획득',523,187,(217,185,111))
        if game.state=='trap':
            lines=['W / S  전진·후진','A / D  칼날 회피','Esc  입장 전 복귀',f'진행 {int(game.trap_progress*100)}%']
        else:
            lines=['WASD  화면 상하좌우','두 키 조합  대각선','Shift  달리기','좌클릭  검 공격','F  상호작용','M  방문 지도','V  시야 / 전체 보기','R  새 회차','F10  화면 저장','Esc  창 닫기']
        for i,line in enumerate(lines):
            self.text(line,523,215+i*16,(175,183,175))
        if game.reveal_all and game.state=='explore':
            self.text('전체 보기 · 디자인 확인용',12,44,(219,190,123))
        if game.time < game.banner_until:
            self.rectangle(10,371,490,23,(10,14,17,230))
            self.text(game.banner,19,383,(225,208,164),size='font')
        self.text(f'{fps:.0f} FPS',574,387,(106,120,119))

    def map_overlay(self, game):
        self.rectangle(0,0,640,400,(5,10,14,244))
        self.text(f'{PHASES[game.phase]} 방문 지도',40,37,size='title')
        self.text('지나간 통로만 표시 · M / Esc 닫기 · 세계 시간은 계속 진행',40,64)
        step,ox,oy=11,145,100
        for x,y in game.visited:
            self.rectangle(ox+x*step,oy+y*step,step-1,step-1,(145,143,119))
        if game.trap_discovered:
            ax,ay=game.trap_cell
            self.badge('A',ox+(ax+.5)*step,oy+(ay+.5)*step,(218,175,107))
        if game.trap_completed:
            bx,by=game.trap_exit
            self.badge('B',ox+(bx+.5)*step,oy+(by+.5)*step,(127,197,183))
        x,y=game.player.x,game.player.y
        self.rectangle(ox+x*step-2,oy+y*step-2,5,5,(231,214,156))
        self.text('노랑: 플레이어    A: 함정방 입구    B: 도착점',145,370)

    def draw(self, game, fps=0):
        p.canvas_width,p.canvas_height=LW,LH
        if game.state=='trap':
            p.SDL_SetRenderTarget(p.renderer,self.display)
            self.trap(game)
            p.SDL_SetRenderTarget(p.renderer,self.logical)
            self.clear((0,0,0,0))
        else:
            p.SDL_SetRenderTarget(p.renderer,self.logical)
            self.quarter(game)
        self.hud_trap(game) if game.state=='trap' else self.hud(game,fps)
        if game.map_open and game.state=='explore':
            self.map_overlay(game)
        if game.state=='clear':
            self.rectangle(0,0,LW,LH,(0,0,0,240))
            self.text('CLEAR',225,180,(226,213,171),size='big')
            self.text('중앙 탈출구에 도달했습니다 · R 새 회차',200,236,size='font')
        elif game.state=='failed':
            self.rectangle(0,0,LW,LH,(0,0,0,240))
            self.text('실패',275,180,(218,126,109),size='big')
            self.text('체력이 0이 됐습니다 · R 새 회차',230,236,size='font')
        # 탐색↔변형에는 전체 암전을 넣지 않아 벽 연출과 고정 HUD가 보이게 한다.
        display_mode = 'explore' if game.state == 'shifting' else game.state
        if self.mode_game is not game or self.last_mode != display_mode:
            self.mode_game = game
            self.last_mode, self.mode_changed = display_mode, game.ui_time
        fade=max(0,1-(game.ui_time-self.mode_changed)/.28)
        if fade:
            self.rectangle(0,0,LW,LH,(0,0,0,round(255*fade)))
        p.SDL_SetRenderTarget(p.renderer,self.display)
        p.SDL_RenderCopy(p.renderer,self.logical,None,None)
        p.SDL_SetRenderTarget(p.renderer,None)
        p.SDL_RenderCopy(p.renderer,self.display,None,None)

    def capture(self, path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        p.SDL_SetRenderTarget(p.renderer,self.display)
        w,h=LW*SCALE,LH*SCALE
        pixels=(ctypes.c_ubyte*(w*h*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,pixels,w*4)==0
        surface=p.SDL_CreateRGBSurfaceWithFormatFrom(pixels,w,h,32,w*4,p.SDL_PIXELFORMAT_RGBA32)
        assert surface
        try:
            assert p.IMG_SavePNG(surface,str(path).encode('utf-8'))==0
        finally:
            p.SDL_FreeSurface(surface)
            p.SDL_SetRenderTarget(p.renderer,None)

    def close(self):
        self.atlases.clear()
        self.images.clear()
        self.effects.clear()
        self.text_cache.clear()
        self.small=self.font=self.title=self.big=None
        for texture in (self.logical,self.display):
            p.SDL_DestroyTexture(texture)
