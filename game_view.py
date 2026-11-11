"""Quarter-view exploration and fixed-front 2D-perspective trap rendering."""
import ctypes
import json
import math
from pathlib import Path
import pico2d.pico2d as p
from maze_model import COLS, ROWS, PHASES, DIRECTIONS, TRAP_LENGTH
from trap_view import Corridor

LW, LH, SCALE = 640, 400, 2
MAP_RECT = (8, 32, 496, 368)
HALF_TILE_W, HALF_TILE_H = 32, 16
WALL_NEIGHBORS = ((0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8))


def project(x, y):
    return HALF_TILE_W*(x-y), HALF_TILE_H*(x+y)


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
        player = Path('sprite/quarter/player_explorer_v1')
        self.player_catalog = json.loads((self.root/player/'explorer.json').read_text(encoding='utf-8'))
        directions = self.player_catalog['world_direction_to_screen']
        self.facing = tuple(directions[name] for name in ('down', 'left', 'right', 'up'))
        self.images['player'] = self.load(player/self.player_catalog['image'], pixel=True)
        for name, folder in (('terrain', 'terrain_v1'), ('props', 'props_v1'),
                             ('guardian', 'guardian_v1'), ('shortcuts', 'shortcuts_v1')):
            directory = Path('sprite/quarter')/folder
            data = json.loads((self.root/directory/'catalog.json').read_text(encoding='utf-8'))
            self.images[name] = self.load(directory/data['image'], pixel=True)
            self.atlases[name] = data['frames']
        for name in ('torch', 'sword-slash'):
            data = json.loads((self.root/f'sprite/topdown/effects/{name}.json').read_text())
            self.images[name] = self.load(f'sprite/topdown/effects/{name}.png', pixel=True)
            self.effects[name] = data
        self.logical = self.target(LW, LH)
        self.display = self.target(LW*SCALE, LH*SCALE)
        self.corridor = Corridor(self)
        self.origin, self.world_scale = (0, 0), 1
        self.camera, self.camera_game = None, None
        self.animated_player, self.animation_state, self.animation_started = None, None, 0
        self.last_mode, self.mode_changed = None, -10

    def load(self, path, pixel=False):
        image = p.load_image(str(self.root/path))
        p.SDL_SetTextureScaleMode(image.texture, p.SDL_ScaleModeNearest if pixel else p.SDL_ScaleModeLinear)
        p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND)
        return image

    def atlas(self, x, y, name, frame, tint=(255, 255, 255)):
        item = self.atlases[name][frame]
        sx, sy, w, h = item['rect']
        px, py = item['pivot']
        scale = self.world_scale
        self.image(name, (x-px*scale, y-py*scale, w*scale, h*scale),
                   (sx, sy, w, h), tint)

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

    def image(self, name, rect, source=None, tint=(255, 255, 255), angle=0, flip=False):
        image = self.images[name]
        p.SDL_SetTextureColorMod(image.texture, *tint)
        dst = p.SDL_Rect(*(round(v) for v in rect))
        src = p.SDL_Rect(*source) if source else None
        if angle or flip:
            p.SDL_RenderCopyEx(p.renderer, image.texture, src, dst, angle, None, p.SDL_FLIP_HORIZONTAL if flip else p.SDL_FLIP_NONE)
        else:
            p.SDL_RenderCopy(p.renderer, image.texture, src, dst)

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

    def player_frame(self, game):
        player = game.player
        clips = self.player_catalog['clips']
        facing = self.facing[player.direction]
        attack = clips['attack-'+facing]
        attack_ms = game.attack_time*1000
        if attack_ms < sum(attack['durations_ms']):
            clip, elapsed_ms = attack, attack_ms
        else:
            state = {'walk': 'walk', 'sprint': 'run'}.get(player.state, 'idle')
            if player is not self.animated_player or state != self.animation_state:
                self.animated_player, self.animation_state = player, state
                self.animation_started = game.time
            clip = clips[state+'-'+facing]
            elapsed_ms = (game.time-self.animation_started)*1000
        durations = clip['durations_ms']
        if clip['loop']:
            elapsed_ms %= sum(durations)
        for frame, duration in zip(clip['frames'], durations):
            if elapsed_ms < duration:
                return frame['rect']
            elapsed_ms -= duration
        return clip['frames'][-1]['rect']

    def player(self, x, y, game):
        scale = self.world_scale
        frame = self.player_frame(game)
        px, py = self.player_catalog['pivot']
        self.image('player', (x-px*scale, y-py*scale, frame[2]*scale, frame[3]*scale), frame)
        if game.player.torch:
            self.effect('torch', x-8*scale, y-23*scale, game.time, .22*scale)
        if game.attack_time < .75:
            dx, dy = project(*DIRECTIONS[game.player.direction])
            angle = math.degrees(math.atan2(dy, dx))
            self.effect('sword-slash', x+dx*.5*scale, y+(dy*.5-22)*scale,
                        game.attack_time, .55*scale, angle)

    def guardian(self, x, y, game, tint):
        self.atlas(x, y, 'guardian', 'idle_'+self.facing[game.guard_direction], tint)
        if game.time < game.guard_alert_until:
            scale = self.world_scale
            self.rectangle(x-12*scale, y-56*scale, 24*scale, 2*scale, (36,29,26))
            self.rectangle(x-12*scale, y-56*scale, 8*game.guard_hp*scale, 2*scale, (155,75,59))

    def prop(self, x, y, frame, tint, game):
        self.atlas(x, y, 'props', frame, tint)
        if frame == 'torch_stand' and not game.player.torch:
            scale = self.world_scale
            self.effect('torch', x, y-43*scale, game.time, .26*scale)

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

    @staticmethod
    def tile_tint(game,x,y):
        visible=(x,y) in game.visible
        brightness=1.0 if visible else .80 if game.reveal_all else .32
        phase_tint=((.94,.96,1.),(.70,.79,.94),(.82,.90,.96))[game.phase]
        if visible and game.player.torch:
            glow=max(0.,1.-math.hypot(x+.5-game.player.x,y+.5-game.player.y)/7.)
            phase_tint=tuple(min(1.,c+warm*glow) for c,warm in zip(phase_tint,(.30,.13,0.)))
        return tuple(round(255*brightness*c) for c in phase_tint)

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
        self.clear()
        self.position_camera(game)
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
            tint = self.tile_tint(game, x, y)
            variant = (x*3+y*5+game.seed) % 4
            self.atlas(sx, sy, 'terrain', f'floor_{variant}', tint)
            if game.grid[y][x]:
                # Close the exposed wall face at the edge of explored terrain.
                mask = sum(bit for dx, dy, bit in WALL_NEIGHBORS
                           if (x+dx, y+dy) in drawn_cells and game.grid[y+dy][x+dx])
                place(self.atlas, x+.5, y+.5, 'terrain', f'wall_{mask}', tint)

        for (x, y), frame in ((game.exit, 'rope_exit'), (game.torch_cell, 'torch_stand'),
                              (game.fountain, 'fountain_empty' if game.fountain_used else 'fountain_full')):
            if (x, y) in game.visible or game.reveal_all:
                place(self.prop, x+.5, y+.5, frame, self.tile_tint(game, x, y), game)

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
        self.text('칼날의 통로',272,15,(217,198,154),size='font')
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

    def hud(self, game, fps=0):
        self.rectangle(0,0,640,30,(12,18,22))
        self.text('초보자를 위한 미로 탈출 안내서',10,14,size='font')
        self.rectangle(512,30,128,370,(16,23,27))
        self.rectangle(512,30,1,370,(71,77,70))
        self.text('미궁 탐색 · 쿼터뷰',523,49,size='font')
        self.text(f'{PHASES[game.phase]}  {60-int(game.phase_time):02d}s',523,73,(217,190,131),size='font')
        self.text('현재는 조명만 전환',523,91,(129,139,137))
        for y,label,value,color in [(115,'HP',game.player.hp,(158,77,66)),(148,'ST',game.player.stamina,(113,143,106))]:
            self.text(f'{label}  {int(value):3d}',523,y,(194,198,182))
            self.rectangle(523,y+10,104,6,(36,43,44))
            self.rectangle(523,y+10,value*1.04,6,color)
        self.text('횃불: 획득' if game.player.torch else '횃불: 미획득',523,187,(217,185,111))
        if game.state=='trap':
            lines=['W / S  전진·후진','A / D  칼날 회피','Esc  입장 전 복귀',f'진행 {int(game.trap_progress*100)}%']
        else:
            lines=['WASD / 방향키 이동','Shift  달리기','좌클릭  검 공격','F  상호작용','M  방문 지도','V  시야 / 전체 보기','R  새 회차','F10  화면 저장','Esc  창 닫기']
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
        self.text('방문 지도',40,37,size='title')
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
        if self.last_mode != game.state:
            self.last_mode,self.mode_changed=game.state,game.time
        fade=max(0,1-(game.time-self.mode_changed)/.28)
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
