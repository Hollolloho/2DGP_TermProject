"""Pixel top-down exploration and fixed-front 2D-perspective trap rendering."""
import ctypes
import json
import math
from pathlib import Path
import pico2d.pico2d as p
from maze_model import COLS, ROWS, PHASES, DIRECTIONS, TRAP_LENGTH
from trap_view import Corridor

LW, LH, SCALE = 640, 400, 2
TILE, MAP_X, MAP_Y = 16, 8, 32


class View:
    def __init__(self, root):
        self.root = Path(root)
        self.images, self.effects = {}, {}
        self.text_cache={}
        self.atlases, self.pending_assets = {}, []
        self.small = p.load_font('C:/Windows/Fonts/malgun.ttf', 10)
        self.font = p.load_font('C:/Windows/Fonts/malgun.ttf', 12)
        self.title = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 17)
        self.big = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 46)
        player = Path('sprite/quarter/player_explorer_v1')
        self.player_catalog = json.loads((self.root/player/'explorer.json').read_text(encoding='utf-8'))
        self.images['player'] = self.load(player/self.player_catalog['image'], pixel=True)
        for name, folder in (('props', 'props_v1'), ('guardian', 'guardian_v1'),
                             ('shortcuts', 'shortcuts_v1')):
            directory = Path('sprite/quarter')/folder
            catalog = self.root/directory/'catalog.json'
            if not catalog.is_file():
                self.pending_assets.append(name)
                continue
            data = json.loads(catalog.read_text(encoding='utf-8'))
            self.images[name] = self.load(directory/data['image'], pixel=True)
            self.atlases[name] = data['frames']
        for name in ('torch', 'sword-slash'):
            data = json.loads((self.root/f'sprite/topdown/effects/{name}.json').read_text())
            self.images[name] = self.load(f'sprite/topdown/effects/{name}.png', pixel=True)
            self.effects[name] = data
        self.logical = self.target(LW, LH)
        self.display = self.target(LW*SCALE, LH*SCALE)
        self.corridor = Corridor(self)
        self.origin, self.world_scale = (MAP_X,MAP_Y), 1
        self.last_mode, self.mode_changed = None, -10

    def load(self, path, pixel=False):
        image = p.load_image(str(self.root/path))
        p.SDL_SetTextureScaleMode(image.texture, p.SDL_ScaleModeNearest if pixel else p.SDL_ScaleModeLinear)
        p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND)
        return image

    def atlas(self, name, frame, x, y, scale=1, tint=(255, 255, 255)):
        if name not in self.atlases:
            return False
        item = self.atlases[name][frame]
        sx, sy, w, h = item['rect']
        px, py = item['pivot']
        self.image(name, (x-px*scale, y-py*scale, w*scale, h*scale),
                   (sx, sy, w, h), tint)
        return True

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

    def tile(self, index, x, y, tint=(255, 255, 255), size=16, variant=0):
        if index<24:
            # ponytail: keep square material cells until the quarter-view coordinate change;
            # placing diamond terrain on this grid would show gaps at solid boundaries.
            self.image('raw_wall' if index<16 else 'raw_floor', (x,y,size,size), tint=tint)
            if index<16:
                self.rectangle(x,y+size-2,size,2,(6,10,11,180))
        else:
            frame = {34:'fountain_full', 35:'fountain_empty', 36:'rope_exit'}[index]
            if not self.atlas('props', frame, x+size/2, y+size/2, size/64, tint):
                color = (90,170,186) if index==34 else (75,80,83) if index==35 else (222,197,126)
                self.rectangle(x+size*.2,y+size*.2,size*.6,size*.6,color)
                if index==36:
                    self.line(x+size/2,y-size/2,x+size/2,y+size*.7,(230,211,167))

    def actor(self, x, y, direction, step=0, guardian=False, tint=(255, 255, 255)):
        scale=self.world_scale
        if guardian:
            facing=('sw','nw','se','ne')[direction]
            if not self.atlas('guardian', 'idle_'+facing, x, y, scale*.5, tint):
                self.rectangle(x-6*scale,y-16*scale,12*scale,16*scale,(123,130,125))
                self.rectangle(x-4*scale,y-21*scale,8*scale,6*scale,(176,152,111))
        else:
            # ponytail: idle art only here; state/timing integration is the next task.
            facing=('sw','nw','se','ne')[direction]
            frame=self.player_catalog['clips']['idle-'+facing]['frames'][0]['rect']
            px,py=self.player_catalog['pivot']
            self.image('player',(x-px*scale*.5,y-py*scale*.5,32*scale,32*scale),tuple(frame),tint)

    def world(self, x, y):
        return self.origin[0]+x*TILE*self.world_scale,self.origin[1]+y*TILE*self.world_scale

    def badge(self, label, x, y, color):
        self.rectangle(x-5,y-6,11,12,(17,22,23,230))
        self.rectangle(x-5,y-6,11,1,color)
        self.text(label,x-3,y,color)

    @staticmethod
    def shortcut_mount(game, cell):
        # Anchor the threshold on the adjacent wall, preserving the floor/interaction cell.
        for dx,dy,facing in ((0,-1,'south'),(-1,0,'east'),(1,0,'west'),(0,1,'north')):
            if game.solid(cell[0]+dx,cell[1]+dy):
                return cell[0]+.5+dx*.48,cell[1]+.5+dy*.48,facing
        return cell[0]+.5,cell[1]+.5,'south'

    def shortcut(self, game, cell, kind='trap', state='entry', arrival=False):
        _, _, facing = self.shortcut_mount(game, cell)
        frame = ('puzzle_' + ('open' if state == 'open' else 'closed') if kind == 'puzzle'
                 else 'trap_' + ('arrival' if arrival else 'entry')) + '_' + facing
        x, y = self.world(cell[0]+.5, cell[1]+.5)
        scale = self.world_scale*.5
        if not self.atlas('shortcuts', frame, x, y, scale):
            size = TILE*self.world_scale
            self.rectangle(x-size*.35,y-size*.45,size*.7,size*.8,(24,29,28))
            color = (127,197,183) if arrival else (218,175,107)
            self.rectangle(x-size*.35,y-size*.45,size*.7,2,color)

    @staticmethod
    def tile_tint(game,x,y):
        visible=(x,y) in game.visible
        brightness=1.0 if visible else .80 if game.reveal_all else .32
        phase_tint=((.94,.96,1.),(.70,.79,.94),(.82,.90,.96))[game.phase]
        if visible and game.player.torch:
            glow=max(0.,1.-math.hypot(x+.5-game.player.x,y+.5-game.player.y)/7.)
            phase_tint=tuple(min(1.,c+warm*glow) for c,warm in zip(phase_tint,(.30,.13,0.)))
        return brightness,tuple(round(255*brightness*c) for c in phase_tint)

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

    def topdown(self, game):
        self.clear()
        self.world_scale=1 if game.reveal_all else 2
        if game.reveal_all:
            self.origin=(MAP_X,MAP_Y)
        else:
            self.origin=(round(max(8-(COLS*32-496),min(8,256-game.player.x*32))),
                         round(max(32-(ROWS*32-368),min(32,216-game.player.y*32))))
        size=TILE*self.world_scale
        p.SDL_RenderSetClipRect(p.renderer,p.SDL_Rect(8,32,496,368))
        for y in range(ROWS):
            for x in range(COLS):
                known = (x,y) in game.observed
                visible = (x,y) in game.visible
                if not (game.reveal_all or known):
                    continue
                if game.grid[y][x]:
                    mask = sum(bit for dx,dy,bit in ((0,-1,1),(1,0,2),(0,1,4),(-1,0,8)) if game.solid(x+dx,y+dy))
                    index = mask
                else:
                    index = 16+((x*7+y*11+game.seed)%8)
                brightness,tint=self.tile_tint(game,x,y)
                sx,sy=self.world(x,y)
                if sx+size<8 or sx>504 or sy+size<32 or sy>400:
                    continue
                self.tile(index,sx,sy,tint,size=size,variant=(x*3+y*5+game.seed)%4)
                if not game.grid[y][x]:
                    # Contact shadows stay within floor cells and do not change collision.
                    alpha=round(90*brightness)
                    if game.solid(x,y-1):
                        for depth,weight in enumerate((1.,.72,.42,.2)):
                            self.rectangle(sx,sy+depth*self.world_scale,size,self.world_scale,(8,12,14,round(alpha*weight)))
                    if game.solid(x-1,y):
                        self.rectangle(sx,sy,2*self.world_scale,size,(8,12,14,round(alpha*.45)))
        for cell, index in [(game.exit,36),(game.fountain,35 if game.fountain_used else 34)]:
            if cell in game.visible or game.reveal_all:
                sx,sy=self.world(*cell)
                self.tile(index,sx-2*self.world_scale,sy-2*self.world_scale,size=20*self.world_scale)
        for cell,arrival in ((game.trap_cell,False),(game.trap_exit,True)):
            if cell in game.visible or game.reveal_all:
                self.shortcut(game,cell,state='arrival' if arrival else 'entry',arrival=arrival)
                sx,sy=self.world(*cell)
                self.badge('B' if arrival else 'A',sx+size+6,sy+size/2,(127,197,183) if arrival else (218,175,107))
        if not game.player.torch and (game.torch_cell in game.visible or game.reveal_all):
            x,y = game.torch_cell
            sx,sy=self.world(x+.5,y+.8)
            self.effect('torch',sx,sy,game.time,.23*self.world_scale)
        x,y = self.world(game.player.x,game.player.y)
        step = (int(game.time*8)%3) if game.player.state in ('walk','sprint') else 0
        actors=[(game.player.y,False)]
        if game.guard_hp and (game.guard in game.visible or game.reveal_all):
            actors.append((game.guard[1]+.5,True))
        for _,guardian in sorted(actors):
            if guardian:
                sx,sy=self.world(game.guard[0]+.5,game.guard[1]+.5)
                self.actor(sx,sy,game.guard_direction,guardian=True)
                if game.time<game.guard_alert_until:
                    self.rectangle(sx-7*self.world_scale,sy-27*self.world_scale,14*self.world_scale,self.world_scale,(36,29,26))
                    self.rectangle(sx-7*self.world_scale,sy-27*self.world_scale,14*self.world_scale*game.guard_hp/3,self.world_scale,(155,75,59))
            else:
                self.actor(x,y,game.player.direction,step)
                if game.player.torch:
                    self.effect('torch',x-5*self.world_scale,y-2*self.world_scale,game.time,.17*self.world_scale)
        if game.attack_time < .75:
            angle = (90,180,0,270)[game.player.direction]
            dx,dy = DIRECTIONS[game.player.direction]
            self.effect('sword-slash',x+dx*7*self.world_scale,y+dy*7*self.world_scale,game.attack_time,.42*self.world_scale,angle)
        if game.time<game.landing_until:
            bx,by=self.world(game.trap_exit[0]+.5,game.trap_exit[1]+.5)
            radius=(12+math.sin(game.time*5)*3)*self.world_scale
            color=(127,197,183,round(100+40*math.sin(game.time*5)))
            self.rectangle(bx-radius,by+size*.4,radius*2,2,color)
        p.SDL_RenderSetClipRect(p.renderer,None)

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
        self.text('탑뷰 검사 · 쿼터뷰 미연결',365,14,(156,156,128))
        self.rectangle(512,30,128,370,(16,23,27))
        self.rectangle(512,30,1,370,(71,77,70))
        self.text('함정방 · 1인칭' if game.state=='trap' else '미궁 탐색 · 탑뷰',523,49,size='font')
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
            self.topdown(game)
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
