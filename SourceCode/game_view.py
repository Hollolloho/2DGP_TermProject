"""Quarter-view exploration and fixed-front 2D-perspective trap rendering."""
from bisect import bisect_right
import ctypes
from itertools import accumulate
import json
import math
from pathlib import Path
import pico2d.pico2d as p
from .maze_model import BASE_SIGHT_RADIUS, TORCH_SIGHT_RADIUS, COLS, ROWS, PHASES, TRAP_LENGTH
from .maze_model import PHASE_SECONDS, SHIFT_SECONDS, SHIFT_SWAP_AT
from .maze_model import ATTACK_FORWARD, DEFAULT_ATTACK_HIT_MS, HALF_TILE_W, HALF_TILE_H, project
from .trap_view import Corridor, VERTEX
from .mouse_maze import BOARD, MAZE, WAYPOINTS, GOAL_CELL, cell_center, cell_rect
from .path_connection import DIRECTIONS as CONNECTION_DIRECTIONS, RUNES
from .puzzle_layout import ROOM_ORIGIN, ROOM_SCALE, room_point, connection_cell, on_loose_floor
from .world_path_room import FIXED_FLOOR, LOOSE_POSITIONS, ENTER_SECONDS

LW, LH, SCALE = 640, 400, 2
MAP_RECT = (0, 0, LW, LH)
PHASE_HUD_RECT = (222, 8, 196, 28)
VITALS_HUD_RECT = (15, 348, 138, 44)
PUZZLE_OFFSET_X = 60
BOULDER_SIGN_SCALE = .125
BOULDER_SIGN_HEIGHT = 20
WALL_NEIGHBORS = ((0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8))
MEMORY_LIGHT = .32
LIGHT_FADE_SECONDS = .20
TORCH_MOUNT_HEIGHT = 24
OCCLUSION_SILHOUETTE_ALPHA = 176
PLAYER_ATLAS_DIR = Path('sprite/quarter/player_explorer_attack_v2')


class View:
    def __init__(self, root):
        self.root = Path(root)
        self.images, self.effects = {}, {}
        self.text_cache={}
        self.atlases = {}
        self.small = p.load_font('C:/Windows/Fonts/malgun.ttf', 10)
        self.font = p.load_font('C:/Windows/Fonts/malgun.ttf', 12)
        self.hud_font = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 13)
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
        self.images['mouse-maze-panel'] = self.load('sprite/ui/mouse-maze-panel.png')
        self.images['boulder-warning-wall'] = self.load('sprite/quarter/props_v1/boulder-warning-wall-east.png')
        self.logical = self.target(LW, LH)
        self.display = self.target(LW*SCALE, LH*SCALE)
        self.display_ready = False
        self.corridor = Corridor(self)
        self.boulder_scene = None
        self.connection_pointer = None
        self.origin, self.world_scale = (0, 0), 1
        self.camera, self.camera_game = None, None
        self.light_game, self.light_time, self.torch_light = None, 0., 0.
        self.discovery, self.exposure = {}, {}
        self.light_revision = -1
        self.last_mode, self.mode_changed = None, -10
        self.last_trap_kind = None
        self.mode_game = None
        self.mode_fade_strength = 1.

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

    def text(self, text, x, y, color=(199, 203, 189), size='small', center=False, right=False):
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
        image.draw(x if center else x-image.w/2 if right else x+image.w/2,LH-y)

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
        destination = (left, top, frame[2]*scale, frame[3]*scale)
        self.player_body(game, clip, index, destination)
        if torch and torch_in_front:
            self.effect('torch', *torch)
        if dagger and dagger[0] == 'front':
            self.image('dagger-slash', dagger[1], dagger[2])

    def player_body(self, game, clip, index, destination, alpha=255):
        blend = {'alpha': alpha} if alpha != 255 else {}
        movement = {'walk': 'walk', 'sprint': 'run'}.get(game.player.state)
        if movement and 'upper_layer_rects' in clip:
            legs = self.moving_attack_legs(game, movement, clip['direction'])
            self.image('moving-attack', destination, legs, **blend)
            self.image('moving-attack', destination, clip['upper_layer_rects'][index], **blend)
        else:
            self.image('player', destination, clip['frames'][index]['rect'], **blend)

    def player_silhouette(self, x, y, game):
        clip, index = self.player_pose(game)
        _, _, width, height = clip['frames'][index]['rect']
        px, py = self.player_catalog['pivot']
        self.player_body(game, clip, index, (x-px, y-py, width, height),
                         alpha=OCCLUSION_SILHOUETTE_ALPHA)

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
        if game.guard_attack_at is not None:
            self.text('!', x-3, y-68*self.world_scale, (255,204,112), size='font')
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
        if self.camera_game is not game or self.last_mode in ('trap','path_room'):
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

    def path_door(self, x, y, facing, opened, tint):
        self.atlas(x,y,'shortcuts',f'puzzle_{"open" if opened else "closed"}_{facing}',tint)

    @staticmethod
    def boulder_sign_mount(game):
        if game.boulder_entry is None:
            return None
        x,y = game.boulder_entry
        wall = x-1,y+1
        if not game.solid(*wall) or game.solid(x,y+1):
            return None
        return x+.02,y+1.5,wall

    def boulder_sign(self, x, y, tint, brightness):
        scale = BOULDER_SIGN_SCALE*self.world_scale
        # 동향 면 투영이 들어간 원본을 균일 축소하고 리벳을 벽 높이에 고정한다.
        self.image('boulder-warning-wall',
                   (x-95*scale,y-BOULDER_SIGN_HEIGHT*self.world_scale-171*scale,192*scale,240*scale),
                   tint=tuple(round(channel*brightness) for channel in tint))

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
        player_x, player_y = self.world(game.player.x, game.player.y)
        show_silhouette = False
        in_exploration_view = game.state == 'explore' and not game.reveal_all
        drawn_cells = {(x, y) for y in range(ROWS) for x in range(COLS)} if game.reveal_all else game.observed
        sign_mount = self.boulder_sign_mount(game)
        sign_visible = (sign_mount is not None and (game.boulder_entry in game.visible or game.reveal_all)
                        and (game.reveal_all or game.clear_line_to(*sign_mount[:2])))
        if sign_visible:
            # 타일 중심이 가려져도 통로 쪽 동향 면은 보인다. 표지가 공중에 뜨지 않게 벽도 그린다.
            drawn_cells = drawn_cells | {sign_mount[2]}

        def place(draw, x, y, *args):
            scene.append((x+y, draw, (*self.world(x, y), *args)))

        gate = game.puzzle_gate
        gate_cell = gate[0] if gate else None
        for x, y in drawn_cells:
            sx, sy = self.world(x+.5, y+.5)
            if not (left-32 <= sx <= left+width+32 and top-16 <= sy <= top+height+80):
                continue
            tint, brightness = self.terrain_light(game, x, y)
            if sign_visible and (x,y) == sign_mount[2]:
                tint, brightness = self.terrain_light(game, *game.boulder_entry)
            variant = (x*3+y*5+game.seed) % 4
            self.terrain(sx, sy, f'floor_{variant}', tint, brightness)
            if (x, y) == gate_cell:
                _, near, _ = gate
                facing = {(0, 1): 'south', (1, 0): 'east', (0, -1): 'north', (-1, 0): 'west'}
                direction = facing[near[0]-x, near[1]-y]
                state = 'open' if game.puzzle_open else 'closed'
                place(self.atlas, x+.5, y+.5, 'shortcuts', f'puzzle_{state}_{direction}', tint)
                continue
            if game.grid[y][x]:
                mask = self.wall_mask(game, x, y)
                place(self.shifting_wall, x+.5, y+.5, f'wall_{mask}', tint, brightness, (x, y), game)
                # Approximate overlap with the solid part of a foreground tile.
                if in_exploration_view and abs(sx-player_x) < 34 and 0 < sy-player_y <= 48:
                    show_silhouette = True

        if sign_visible:
            tint,brightness = self.terrain_light(game, *game.boulder_entry)
            place(self.boulder_sign, *sign_mount[:2], tint, brightness)

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
        if gate and (gate_cell in game.visible or game.reveal_all):
            color = (127,197,183) if game.puzzle_open else (218,175,107)
            for x, y in gate[1:]:
                if (x, y) in game.visible or game.reveal_all:
                    if self.interaction_hint(game) == ((x,y), 'F 퍼즐'):
                        continue
                    sx, sy = self.world(x+.5, y+.5)
                    markers.append(('P', sx-12*self.world_scale, sy, color))
        for cell, arrival, label in ((game.trap_cell, False, 'A'), (game.trap_exit, True, 'B'),
                                     (game.boulder_entry, False, 'C'), (game.boulder_exit, True, 'D')):
            if cell is None or (cell not in game.visible and not game.reveal_all):
                continue
            x, y, facing = self.shortcut_mount(game, cell)
            place(self.shortcut, x, y, facing, arrival, self.tile_tint(game, *cell))
            if arrival and in_exploration_view:
                arch_x, arch_y = self.world(x, y)
                if abs(arch_x-player_x) < 40 and 0 < arch_y-player_y <= 48:
                    show_silhouette = True
            sx, sy = self.world(cell[0]+.5, cell[1]+.5)
            color = (127,197,183) if arrival else (218,175,107)
            markers.append((label, sx+18*self.world_scale, sy, color))
            if arrival and game.landing_cell == cell and game.time < game.landing_until:
                pulse = math.sin(game.time*5)
                radius = (12+3*pulse)*self.world_scale
                self.rectangle(sx-radius, sy+6*self.world_scale, radius*2, 2,
                               (*color, round(100+40*pulse)))

        for cell,arrival in ((game.path_entry,False),(game.path_exit,True)):
            if cell is None or (cell not in game.visible and not game.reveal_all):
                continue
            x,y,facing = self.shortcut_mount(game,cell)
            entering = (game.state == 'path_room' and game.world_path.stage == 'entering'
                        and cell == (game.path_exit if game.world_path.reverse else game.path_entry))
            place(self.path_door,x,y,facing,game.path_completed or entering,self.tile_tint(game,*cell))
            sx,sy = self.world(cell[0]+.5,cell[1]+.5)
            color = (151,210,174) if not arrival or game.path_completed else (173,167,142)
            markers.append(('L',sx+18*self.world_scale,sy,color))
            self.line(sx-10*self.world_scale,sy+6*self.world_scale,sx+10*self.world_scale,sy+6*self.world_scale,color)

        if game.guard_hp and (game.guard in game.visible or game.reveal_all):
            x, y = game.guard
            place(self.guardian, game.guard_x, game.guard_y, game, self.tile_tint(game, x, y))
        place(self.player, game.player.x, game.player.y, game)
        # Sort all upright art together by its ground point, independent of sprite height.
        for _, draw, params in sorted(scene, key=lambda item: item[0]):
            draw(*params)
        # Keep the depth-sorted scene intact and reveal only the player's pose.
        if show_silhouette:
            self.player_silhouette(player_x, player_y, game)
        for marker in markers:
            self.badge(*marker)
        p.SDL_RenderSetClipRect(p.renderer, None)

    def trap(self, game):
        if game.trap_kind == 'boulder':
            if self.boulder_scene is None:
                from BoulderPractice.boulder_practice import View as BoulderView
                self.boulder_scene = BoulderView(p, LW*SCALE, LH*SCALE, top=30*SCALE)
            self.boulder_scene.draw_scene(game.boulder_room)
        else:
            self.corridor.draw(game)

    def hud_room_header(self, game, title, route):
        self.rectangle(0,0,640,30,(12,18,22,235))
        self.text('HP',12,14,(207,202,184))
        self.rectangle(33,11,80,5,(48,45,41))
        self.rectangle(33,11,game.player.hp*.8,5,(169,83,64))
        self.text('ST',126,14,(207,202,184))
        self.rectangle(148,11,70,5,(48,45,41))
        self.rectangle(148,11,game.player.stamina*.7,5,(113,143,106))
        self.text(title,272,15,(217,198,154),size='font')
        self.text(f'{PHASES[game.phase]} {math.ceil(PHASE_SECONDS-game.phase_time):02d}s',417,14,(217,190,131))
        self.text(route,537,14,(134,192,179))

    def hud_boulder(self, game):
        from BoulderPractice.boulder_practice import LENGTH
        room = game.boulder_room
        self.hud_room_header(game, '돌 추격 통로', 'C 입구 → D 도착')
        self.rectangle(0,348,640,52,(12,18,22,235))
        if room.state == 'ready':
            status = f'돌 출발까지 {max(0.,5.-room.time):.1f}초 · 지금 이동할 수 있습니다'
        elif room.look_back:
            status = '뒤를 확인하는 중 · W는 계속 전진'
        else:
            status = '장애물을 우회하고 측면 출구로 탈출하세요'
        self.text(status,16,361,(228,204,153),size='font')
        self.text(f'뒤쪽 돌 {max(0.,room.gap):.1f} m',472,361,(227,158,111),size='font')
        self.text('W/S 이동  A/D 장애물 우회  Shift 달리기  Q 뒤 확인  Esc 복귀',16,382,(202,199,179))
        self.rectangle(0,397,640,3,(28,32,31))
        self.rectangle(0,397,640*min(1.,room.z/LENGTH),3,(179,151,94))
        if room.exit_nearby():
            self.rectangle(250,306,140,26,(13,17,18,220))
            self.text('F  측면 출구 이용',265,319,(242,219,148),size='font')
        if game.phase_warning:
            self.text('곧 미로 변형 · 입장 전 위치로 복귀',190,69,(239,183,104),size='font')

    def hud_trap(self, game):
        self.hud_room_header(game, '칼날의 통로', 'A 입구 → B 출구')
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

    def hud_panel(self, rect):
        x,y,w,h = rect
        cut = 4
        self.rectangle(x,y+cut,w,h-2*cut,(17,19,19))
        for row in range(cut):
            inset = cut-row
            self.rectangle(x+inset,y+row,w-2*inset,1,(17,19,19))
            self.rectangle(x+inset,y+h-1-row,w-2*inset,1,(17,19,19))
        points = ((x+cut,y),(x+w-1-cut,y),(x+w-1,y+cut),(x+w-1,y+h-1-cut),
                  (x+w-1-cut,y+h-1),(x+cut,y+h-1),(x,y+h-1-cut),(x,y+cut))
        for start,end in zip(points,(*points[1:],points[0])):
            self.line(*start,*end,(142,117,78))

    def interaction_hint(self, game):
        if game.state != 'explore' or game.map_open:
            return None
        if not game.player.torch and game.close_to(game.torch_cell):
            return game.torch_cell, 'F 횃불 획득'
        if game.close_to(game.trap_cell):
            return game.trap_cell, 'F 칼날방'
        if game.boulder_available():
            return game.boulder_entry, 'F 진입'
        if game.path_available():
            cell = game.path_exit if game.path_completed and game.close_to(game.path_exit) else game.path_entry
            return cell,'F 길의 방'
        if game.close_to(game.fountain):
            return None if game.fountain_used else (game.fountain, 'F 샘물 회복')
        if game.close_to(game.exit):
            return game.exit, 'F 탈출'
        if game.puzzle_available():
            cell = next(cell for cell in game.puzzle_gate[1:] if game.close_to(cell,.75))
            return cell, 'F 퍼즐'
        return None

    def hud_vitals(self, game):
        def label(value, x, y, color=(235,224,200), right=False):
            self.text(value,x+1,y+1,(7,9,9),right=right)
            self.text(value,x,y,color,right=right)

        for y,name,value,height,color in ((356,'HP',game.player.hp,6,(155,76,59)),
                                          (370,'ST',game.player.stamina,4,(110,130,91))):
            label(name,16,y)
            label(f'{int(value):3d}',150,y,right=True)
            self.rectangle(39,y-height/2-1,86,height+2,(8,11,12))
            self.rectangle(40,y-height/2,84,height,(35,32,29))
            fill = round(84*max(0.,min(1.,value/100)))
            if fill:
                self.rectangle(40,y-height/2,fill,height,color)

    def hud(self, game, fps=0):
        remaining = max(0., PHASE_SECONDS-game.phase_time)
        warning = game.phase_warning or game.state == 'shifting'
        phase = f'곧 {PHASES[game.next_phase]}' if game.phase_warning else PHASES[game.phase]
        title = '미로 변형 중' if game.state == 'shifting' else f'{phase} · {math.ceil(remaining):02d}초'
        self.hud_panel(PHASE_HUD_RECT)
        self.text(title,320,18,(239,187,108) if warning else (231,221,198),size='hud_font',center=True)
        self.rectangle(234,28,172,3,(40,39,33))
        self.rectangle(234,28,172*remaining/PHASE_SECONDS,3,(215,160,81) if warning else (171,139,88))
        puzzle_status = None
        if game.puzzle_gate:
            if game.puzzle_open:
                puzzle_status = '퍼즐 통로 개방됨'
            elif game.puzzle_reserved_phase is not None:
                puzzle_status = f'다음 {PHASES[game.puzzle_reserved_phase]} 개방 예정'
        if puzzle_status and game.state != 'puzzle' and not game.map_open:
            self.hud_panel((238,42,164,20))
            self.text(puzzle_status,320,52,(211,194,145),size='font',center=True)

        self.hud_vitals(game)

        if game.state == 'explore' and not game.map_open:
            self.hud_panel((548,366,76,22))
            self.text('M  지도',586,377,(222,210,181),size='font',center=True)
        hint = self.interaction_hint(game)
        if hint:
            cell,label = hint
            x,y = self.world(cell[0]+.5,cell[1]+.5)
            x,y = max(66,min(LW-66,x)),max(96,min(282,y-64))
            boulder = cell == game.boulder_entry
            if boulder:
                x,y = max(96,min(LW-96,x)),y-18
            self.hud_panel((x-88,y-11,176,36) if boulder else (x-56,y-11,112,22))
            self.text(label,x,y,(237,208,157),size='font',center=True)
            if boulder:
                self.text('돌 접촉 즉사 · 5초 뒤 후방 추격',x,y+17,(224,213,188),center=True)
        if (game.time < game.banner_until and not warning and game.state == 'explore'
                and not game.map_open and not game.banner.startswith('횃불에 접근해 F')
                and not (puzzle_status and game.banner.startswith('퍼즐 완료'))):
            top = 68 if puzzle_status else 52
            self.hud_panel((80,top,480,26))
            self.text(game.banner,320,top+13,(225,208,164),size='font',center=True)

    def puzzle_overlay(self, game):
        self.rectangle(0,37,LW,LH-37,(0,0,0,130))
        previous = p.SDL_Rect()
        p.SDL_RenderGetViewport(p.renderer,ctypes.byref(previous))
        p.SDL_RenderSetViewport(p.renderer,p.SDL_Rect(PUZZLE_OFFSET_X,0,LW-PUZZLE_OFFSET_X,LH))
        try:
            self.puzzle_panel(game)
        finally:
            p.SDL_RenderSetViewport(p.renderer,previous)

    def puzzle_panel(self, game):
        parchment = (234, 219, 183)
        muted = (186, 172, 146)
        ember = (239, 183, 104)
        moss = (188, 205, 154)
        mortar = (32, 26, 22)
        wall_tint = (218, 202, 178)
        floor_tint = (92, 98, 99)
        trail_tint = (119, 112, 97)
        active_tint = (133, 121, 95)

        def stone(rect, x, y, solid, tint):
            material = 'raw_wall' if solid else 'raw_floor'
            self.image(material, rect, (x % 9*130, y % 9*130, 130, 130), tint)

        self.image('mouse-maze-panel', (16, 37, 488, 326))
        self.text('마우스 미로',66,68,parchment,size='title')
        self.text('Esc 닫기',394,68,muted,size='font')
        if game.guard_attack_at is not None:
            self.text('수호자 공격 예고',270,68,(239,164,109),size='font')
        self.text('좌클릭 드래그 · 1 → 2 → 3 → 도착' if WAYPOINTS else '좌클릭을 누른 채 도착까지 선 잇기',
                  66,94,parchment,size='font')
        if WAYPOINTS:
            for index in range(len(WAYPOINTS)):
                state = '완료' if index < game.puzzle.progress else '다음' if index == game.puzzle.progress else '대기'
                color = moss if state == '완료' else ember if state == '다음' else muted
                self.text(f'{index+1} {state}',66+92*index,113,color,size='font')
        else:
            self.text('버튼을 놓으면 커서에서 다시 시작',66,113,muted)

        bx,by,size = BOARD
        self.rectangle(bx-2,by-2,len(MAZE[0])*size+4,len(MAZE)*size+4,mortar)
        tile_tints = {'#': wall_tint, 'G': (148, 119, 83)}
        puzzle = game.puzzle
        linked_cells = set(puzzle.retained_path)
        active_cells = (puzzle.cell, puzzle.preview_cell)
        cursor_x, cursor_y = puzzle.cursor
        for y, row in enumerate(MAZE):
            for x, tile in enumerate(row):
                rect = cell_rect(x, y)
                cell = (x, y)
                tint = tile_tints.get(tile, trail_tint if cell in linked_cells else floor_tint)
                if tile != '#' and cell in active_cells:
                    cx, cy = cell_center(x, y)
                    distance = abs(cursor_x-cx)+abs(cursor_y-cy)
                    weight = max(0., 1-distance/rect[2])
                    tint = tuple(round(base+(active-base)*weight)
                                 for base, active in zip(tint, active_tint))
                stone(rect, x, y, tile == '#', tint)

        for y, row in enumerate(MAZE):
            for x, tile in enumerate(row):
                if tile == '#':
                    continue
                left, top, width, height = cell_rect(x, y)
                cx, cy = left+width//2, top+height//2
                for dx, dy in ((1, 0), (0, 1)):
                    nx, ny = x+dx, y+dy
                    if ny < len(MAZE) and nx < len(row) and MAZE[ny][nx] != '#':
                        end_x, end_y = cx+dx*width, cy+dy*height
                        self.line(cx, cy, end_x, end_y, (22, 19, 16))
                        self.line(cx+dy, cy+dx, end_x+dy, end_y+dx, (120, 105, 81))
                self.rectangle(cx-2, cy-2, 5, 5, (30, 26, 22))
                self.rectangle(cx-1, cy-1, 3, 3, (154, 135, 101))
                if tile in 'SG':
                    label, accent = ('출발', parchment) if tile == 'S' else ('도착', ember)
                    self.rectangle(cx-4, cy-4, 9, 9, mortar)
                    self.rectangle(cx-3, cy-3, 7, 7, accent)
                    if WAYPOINTS:
                        self.text(label,cx,top+height-5,accent,center=True)
                    else:
                        self.text(label,left+7,top+27,accent)

        self.puzzle_route(game)
        for index,cell in enumerate(WAYPOINTS):
            cx,cy = cell_center(*cell)
            color = moss if index < puzzle.progress else ember if index == puzzle.progress else muted
            if puzzle.sequence_error and index > puzzle.progress and cell in puzzle.retained_path:
                color = (231,134,109)
            self.rectangle(cx-7,cy-8,14,16,(20,23,22))
            self.rectangle(cx-7,cy-8,14,1,color)
            self.rectangle(cx-7,cy+7,14,1,color)
            self.text(str(index+1),cx,cy,color,size='hud_font',center=True)
        footer = 344 if WAYPOINTS else 331
        if game.puzzle.hit_wall:
            self.text('연결이 막혔습니다 · 통로로 돌아와 이어 그리기',66,footer,ember,size='font')
        elif WAYPOINTS:
            if puzzle.sequence_error:
                message = f'다음 {puzzle.progress+1}번부터 · 되짚어 순서를 복구하세요'
            elif puzzle.cell == GOAL_CELL and puzzle.progress < len(WAYPOINTS):
                message = '도착 전 1 → 2 → 3 필요 · 되짚어 다시 잇기'
            else:
                target = f'다음 {puzzle.progress+1}번' if puzzle.progress < len(WAYPOINTS) else '도착으로'
                message = f'{target} · 완료 시 다음 {PHASES[game.next_phase]}에 문 개방'
            self.text(message,66,footer,ember if puzzle.sequence_error or puzzle.cell == GOAL_CELL else parchment,size='font')
        else:
            self.text('완료하면 다음 시간대에 문이 열립니다.',66,footer,parchment,size='font')

        wall, near, far = game.puzzle_gate
        wx, wy = wall
        for index, (title, grid, accent, opening) in enumerate((
            ('현재 · 닫힘', game.grid, ember, False),
            (f'{PHASES[game.next_phase]} · 개방', game.maze_layouts.grids[game.next_phase], moss, True),
        )):
            top = 154 + index*88
            self.text(title, 394, top-10, accent)
            self.rectangle(392, top-2, 63, 63, mortar)
            for y in range(wy-1, wy+2):
                for x in range(wx-1, wx+2):
                    gate = (x, y) == wall
                    solid = bool(grid[y][x]) and not (opening and gate)
                    rect = (394+(x-wx+1)*20, top+(y-wy+1)*20, 19, 19)
                    tint = wall_tint if solid else floor_tint
                    if (x, y) in (near, far):
                        tint = (139, 134, 117)
                    if gate:
                        self.rectangle(*rect, accent)
                        left, tile_top, width, height = rect
                        rect = (left+1, tile_top+1, width-2, height-2)
                        tint = (241, 203, 152) if solid else (133, 169, 134)
                    stone(rect, x, y, solid, tint)

    def room_rect(self, x, y, w, h, color, lift=0):
        corners = [self.world(x,y),self.world(x+w,y),self.world(x+w,y+h),self.world(x,y+h)]
        packed = b''.join(VERTEX.pack(corners[i][0],corners[i][1]-lift,*color[:3],
                                     color[3] if len(color) == 4 else 255,0.,0.)
                          for i in (0,1,2,0,2,3))
        buffer = ctypes.create_string_buffer(packed)
        p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
        assert p.SDL_RenderGeometry(p.renderer,None,ctypes.cast(buffer,ctypes.POINTER(p.SDL_Vertex)),6,None,0) == 0

    def room_outline(self, cell, color, lift=0):
        x,y = cell
        corners = [self.world(x,y),self.world(x+1,y),self.world(x+1,y+1),self.world(x,y+1)]
        for a,b in zip(corners,(*corners[1:],corners[0])):
            self.line(a[0],a[1]-lift,b[0],b[1]-lift,color)

    def room_piece(self, index, piece, center, completed=False, selected=False, lift=0):
        cx,cy = center
        sx,sy = self.world(cx,cy)
        self.atlas(sx,sy+3,'terrain',f'floor_{index%4}',(42,39,31))
        tint = (226,213,182) if completed else (167,162,139)
        self.atlas(sx,sy-lift,'terrain',f'floor_{index%4}',tint)
        for width,color in ((.34,(45,35,23)),(.23,(210,171,100)),(.045,(249,218,148))):
            self.room_rect(cx-width/2,cy-width/2,width,width,color,lift)
            for port in piece.ports:
                dx,dy = CONNECTION_DIRECTIONS[port]
                if dx:
                    self.room_rect(cx+min(0,dx*.5),cy-width/2,.5,width,color,lift)
                else:
                    self.room_rect(cx-width/2,cy+min(0,dy*.5),width,.5,color,lift)
        if selected:
            self.room_outline((cx-.5,cy-.5),(253,220,141),lift)

    def room_rune(self, index, x, y, reached):
        background = (18,23,24)
        color = ((250,209,116),(144,218,240))[index] if reached else ((197,155,89),(110,165,190))[index]
        self.rectangle(x-9,y-8,18,16,(*background,255))
        self.rectangle(x-9,y-8,18,1,(151,210,157) if reached else (80,87,80))
        if index == 0:
            for dx,dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
                self.line(x+dx*4,y+dy*4,x+dx*6,y+dy*6,color)
            for dy in range(-2,3):
                half = 3-abs(dy)
                self.line(x-half,y+dy,x+half,y+dy,color)
        else:
            for dy in range(-5,6):
                half = math.sqrt(25-dy*dy)
                self.line(x-half,y+dy,x+half,y+dy,color)
            for dy in range(-4,5):
                half = math.sqrt(16-dy*dy)
                self.line(x+3-half,y-1+dy,x+3+half,y-1+dy,background)

    def path_room_scene(self, game):
        self.clear((0,0,0,255))
        self.origin,self.world_scale = ROOM_ORIGIN,ROOM_SCALE
        puzzle = game.connection
        for x,y in sorted(FIXED_FLOOR,key=lambda c:sum(c)):
            self.atlas(*self.world(x+.5,y+.5),'terrain',f'floor_{(x+y)%4}',(151,150,130))
        reverse = game.world_path.reverse
        self.room_rect(-2.6,1.4,2.6,.2,(129,172,135) if reverse else (154,130,82))
        self.room_rect(4,2.4,1.5,.2,(154,130,82) if reverse else (129,172,135))
        for y in range(4):
            for x in range(4):
                self.room_outline((x,y),(48,53,46))
        for index,piece in enumerate(puzzle.pieces):
            if puzzle.held == index:continue
            center = (piece.cell[0]+.5,piece.cell[1]+.5) if piece.cell is not None else LOOSE_POSITIONS[index]
            self.room_piece(index,piece,center,puzzle.completed,puzzle.selected == index)
        for left,top,right,bottom in game.world_path.barriers:
            ax,ay = self.world(left,top)
            bx,by = self.world(right,bottom)
            self.line(ax,ay+1,bx,by+1,(47,41,32))
            self.line(ax,ay-2,bx,by-2,(100,91,70))
            self.line(ax,ay-4,bx,by-4,(174,161,126))
            self.line(ax,ay+1,ax,ay-4,(100,91,70))
            self.line(bx,by+1,bx,by-4,(100,91,70))
        scene = [(-1.5,self.atlas,(*self.world(-3,1.5),'shortcuts','trap_entry_east',(172,180,151))),
                 (8.5,self.atlas,(*self.world(6,2.5),'shortcuts','trap_arrival_west',(160,197,166))),
                 (game.player.x+game.player.y,self.player,(*self.world(game.player.x,game.player.y),game))]
        for _,draw,args in sorted(scene,key=lambda item:item[0]):draw(*args)
        ex,ey = self.world(-3,1.5)
        ox,oy = self.world(5.7,2.5)
        self.text('출구' if reverse else '입구 · 후퇴',ex,ey-84,
                  (161,215,177) if reverse else (207,194,155),size='font',center=True)
        self.text('입구 · 후퇴' if reverse else '출구',ox+30,oy+18,
                  (207,194,155) if reverse else (161,215,177),size='font',center=True)
        self.text('끊긴 길의 방',320,56,(226,211,172),size='hud_font',center=True)
        self.text('입구 → 두 문양 모두 → 출구 · 문양 순서는 자유',320,319,(189,194,175),size='font',center=True)
        status = '석판을 끌어 빈틈에 놓기 · R 회전'
        point = self.connection_pointer
        if puzzle.dragging and point is not None:
            cell = connection_cell(point)
            floor = on_loose_floor(point)
            valid = floor or (cell is not None and puzzle.piece_at(cell) is None)
            color = (160,224,178) if valid else (230,118,92)
            if cell is not None:self.room_outline(cell,color)
            status = '원래 바닥 자리로 돌려놓기' if floor else '놓기 · R 회전' if valid else '놓으면 원위치로 복구'
            self.room_piece(puzzle.held,puzzle.pieces[puzzle.held],room_point(point),False,True,8)
        elif puzzle.completed:
            status = 'WASD로 완성된 길을 걸어 맞은편 문까지'
        elif puzzle.exit_connected:
            status = '출구까지 닿았지만 문양이 빠졌습니다 · 두 문양을 지나 연결'
        elif len(puzzle.reached_runes) == len(RUNES):
            status = '두 문양 연결됨 · 길을 출구까지 이어 주세요'
        for index,cell in enumerate(RUNES):
            reached = cell in puzzle.reached_runes
            sx,sy = self.world(cell[0]+.5,cell[1]+.5)
            self.room_rune(index,sx,sy-11,reached)
            x = 215+index*150
            self.room_rune(index,x,337,reached)
            self.text(('태양' if index == 0 else '초승달')+(' · 연결됨' if reached else ' · 미연결'),
                      x+15,337,(174,222,180) if reached else (185,187,170),size='font')
        self.text(status,350,364,(231,211,167),size='font',center=True)
        self.text('Esc 들어온 문으로 후퇴 · 맞은편 문을 지나 통과',350,383,(177,180,160),center=True)

    def path_entry_fade(self, game):
        t = min(1.,game.world_path.elapsed/ENTER_SECONDS)
        x,y = self.world(game.player.x,game.player.y)
        y -= 24
        radius = max(24,round(700*(1-t)))
        left,right = max(0,round(x-radius)),min(LW,round(x+radius))
        top,bottom = max(0,round(y-radius*.65)),min(LH,round(y+radius*.65))
        for rect in ((0,0,LW,top),(0,bottom,LW,LH-bottom),(0,top,left,bottom-top),(right,top,LW-right,bottom-top)):
            if rect[2] > 0 and rect[3] > 0:self.rectangle(*rect,(0,0,0))
        if t > .78:self.rectangle(0,0,LW,LH,(0,0,0,round(255*(t-.78)/.22)))

    def puzzle_route(self, game):
        puzzle = game.puzzle
        gold = (241, 198, 123)
        edge = (107, 70, 39)
        nodes = [cell_center(*cell) for cell in puzzle.retained_path]
        for (x, y), (nx, ny) in zip(nodes, [*nodes[1:], puzzle.cursor]):
            if (x, y) == (nx, ny):
                continue
            self.rectangle(min(x, nx)-1, min(y, ny)-1, abs(nx-x)+3, abs(ny-y)+3, edge)
            self.line(x, y, nx, ny, gold)
        for x, y in nodes:
            self.rectangle(x-2, y-2, 5, 5, gold)
        x, y = puzzle.cursor
        self.rectangle(x-3, y-3, 7, 7, edge)
        self.rectangle(x-2, y-2, 5, 5, (255, 235, 182))

    def map_overlay(self, game):
        self.rectangle(0,0,LW,LH,(8,12,14,250))
        self.text(f'{PHASES[game.phase]} 방문 지도',320,44,(234,216,177),size='title',center=True)
        self.text('지나간 통로만 표시 · M / Esc 닫기 · 세계 시간은 계속 진행',320,68,center=True)
        step,ox,oy=11,(LW-COLS*11)//2,88
        self.hud_panel((ox-10,oy-10,COLS*step+20,ROWS*step+20))
        for x,y in game.visited:
            self.rectangle(ox+x*step,oy+y*step,step-1,step-1,(145,143,119))
        if game.trap_discovered:
            ax,ay=game.trap_cell
            self.badge('A',ox+(ax+.5)*step,oy+(ay+.5)*step,(218,175,107))
        if game.trap_completed:
            bx,by=game.trap_exit
            self.badge('B',ox+(bx+.5)*step,oy+(by+.5)*step,(127,197,183))
        if game.boulder_discovered:
            cx,cy = game.boulder_entry
            self.badge('C',ox+(cx+.5)*step+9,oy+(cy+.5)*step,(218,175,107))
        if game.boulder_completed:
            dx,dy = game.boulder_exit
            self.badge('D',ox+(dx+.5)*step+9,oy+(dy+.5)*step,(127,197,183))
        for cell,shown in ((game.path_entry,game.path_discovered),(game.path_exit,game.path_completed)):
            if cell is not None and shown:
                self.badge('L',ox+(cell[0]+.5)*step,oy+(cell[1]+.5)*step,(151,210,174))
        x,y=game.player.x,game.player.y
        self.rectangle(ox+x*step-2,oy+y*step-2,5,5,(231,214,156))
        self.text('노랑: 플레이어    A/B: 칼날 입구·도착점',320,365,center=True)
        self.text('C/D: 돌 입구·도착점 · L: 길의 방',320,383,center=True)
        if game.guard_attack_at is not None:
            self.text('수호자 공격 예고',459,37,(255,204,112),size='font')

    def draw(self, game, fps=0):
        p.canvas_width,p.canvas_height=LW,LH
        native_trap = game.state == 'trap'
        path_active = game.state == 'path_room' and game.world_path.stage == 'active'
        path_entering = game.state == 'path_room' and game.world_path.stage == 'entering'
        if native_trap:
            p.SDL_SetRenderTarget(p.renderer,self.display)
            self.trap(game)
            p.SDL_SetRenderTarget(p.renderer,self.logical)
            self.clear((0,0,0,0))
        else:
            p.SDL_SetRenderTarget(p.renderer,self.logical)
            if path_active:
                self.path_room_scene(game)
            else:
                self.quarter(game)
            if path_entering:
                self.path_entry_fade(game)
        if native_trap:
            self.hud_boulder(game) if game.trap_kind == 'boulder' else self.hud_trap(game)
        else:
            self.hud(game,fps)
        if game.map_open and game.state=='explore':
            self.map_overlay(game)
        if game.state == 'puzzle':
            self.puzzle_overlay(game)
        if game.state=='clear':
            self.rectangle(0,0,LW,LH,(0,0,0,240))
            self.text('CLEAR',225,180,(226,213,171),size='big')
            self.text('중앙 탈출구에 도달했습니다 · R 새 회차',200,236,size='font')
        elif game.state=='failed':
            self.rectangle(0,0,LW,LH,(0,0,0,240))
            self.text('실패',275,180,(218,126,109),size='big')
            self.text('체력이 0이 됐습니다 · R 새 회차',230,236,size='font')
        # 탐색↔변형에는 전체 암전을 넣지 않아 벽 연출과 고정 HUD가 보이게 한다.
        display_mode = 'explore' if game.state in ('shifting', 'puzzle') or path_entering else game.state
        kind = game.trap_kind if native_trap else None
        if self.mode_game is not game or self.last_mode != display_mode or self.last_trap_kind != kind:
            returning = self.mode_game is game and self.last_mode in ('trap','path_room') and display_mode == 'explore'
            # Show the landing point even on the first frame of the return fade.
            self.mode_fade_strength = .5 if returning else 1.
            self.mode_game = game
            self.last_mode, self.mode_changed = display_mode, game.ui_time
            self.last_trap_kind = kind
        fade=max(0,1-(game.ui_time-self.mode_changed)/.28)
        if fade:
            self.rectangle(0,0,LW,LH,(0,0,0,round(255*fade*self.mode_fade_strength)))
        if native_trap:
            p.SDL_SetRenderTarget(p.renderer, self.display)
            p.SDL_RenderCopy(p.renderer, self.logical, None, None)
        self.display_ready = native_trap
        p.SDL_SetRenderTarget(p.renderer, None)
        p.SDL_RenderCopy(p.renderer, self.display if native_trap else self.logical, None, None)

    def select_readback_target(self):
        """Select the current frame as a 1280×800 texture for pixel readback."""
        p.SDL_SetRenderTarget(p.renderer, self.display)
        if not self.display_ready:
            p.SDL_RenderCopy(p.renderer, self.logical, None, None)
            self.display_ready = True

    def capture(self, path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        self.select_readback_target()
        w,h=LW*SCALE,LH*SCALE
        pixels=(ctypes.c_ubyte*(w*h*4))()
        try:
            assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,pixels,w*4)==0
            surface=p.SDL_CreateRGBSurfaceWithFormatFrom(pixels,w,h,32,w*4,p.SDL_PIXELFORMAT_RGBA32)
            assert surface
            try:
                assert p.IMG_SavePNG(surface,str(path).encode('utf-8'))==0
            finally:
                p.SDL_FreeSurface(surface)
        finally:
            p.SDL_SetRenderTarget(p.renderer,None)

    def close(self):
        if self.boulder_scene is not None:
            self.boulder_scene.close()
        self.atlases.clear()
        self.images.clear()
        self.effects.clear()
        self.text_cache.clear()
        self.small=self.font=self.hud_font=self.title=self.big=None
        for texture in (self.logical,self.display):
            p.SDL_DestroyTexture(texture)
