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
        self.shortcut_cache,self.shortcut_designs={},{}
        self.small = p.load_font('C:/Windows/Fonts/malgun.ttf', 10)
        self.font = p.load_font('C:/Windows/Fonts/malgun.ttf', 12)
        self.title = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 17)
        self.big = p.load_font('C:/Windows/Fonts/malgunbd.ttf', 46)
        for name, path in {
            'terrain': 'sprite/topdown/terrain.png', 'actors': 'sprite/topdown/actors.png',
            'terrain_v2': 'sprite/topdown/terrain_v2/terrain.png',
            'guardian': 'sprite/topdown/guardian_v2/guardian.png',
            'shortcuts': 'sprite/topdown/shortcuts_v2/shortcuts.png',
            'walls': 'sprite/wall/sheets/base_a.png',
            'ceiling': 'sprite/surfaces/parts/ceiling/Limestone_Top-2048x512.png',
            'floor': 'sprite/surfaces/parts/floor/Limestone_Bottom-2048x512.png',
        }.items():
            self.images[name] = self.load(path, pixel=name in ('terrain','terrain_v2','actors','guardian','shortcuts'))
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
            source=(index*32,(variant%4)*32,32,32) if index<16 else ((index-16)*32,128,32,32)
            self.image('terrain_v2',(x,y,size,size),source,tint)
        else:
            self.image('terrain', (x, y, size, size), ((index%16)*16, (index//16)*16, 16, 16), tint)

    def actor(self, x, y, direction, step=0, guardian=False, tint=(255, 255, 255)):
        scale=self.world_scale
        if guardian:
            self.image('guardian',(x-16*scale,y-28*scale,32*scale,32*scale),
                       (direction*64,0,64,64),tint)
        else:
            self.image('actors',(x-16*scale,y-24*scale,32*scale,32*scale),
                       ((direction*3+step)*32,0,32,32),tint)

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
        _,_,facing=self.shortcut_mount(game,cell)
        dx,dy={'south':(0,-1),'east':(-1,0),'west':(1,0),'north':(0,1)}[facing]
        wx,wy=cell[0]+dx,cell[1]+dy
        if not game.solid(wx,wy):
            return
        opened=state in ('open','arrival')
        frame=int(opened)+(0 if kind=='puzzle' else 2)
        design_key=frame,facing
        if design_key not in self.shortcut_designs:
            self.shortcut_designs[design_key]=self.shortcut_design(frame,facing)
        design=self.shortcut_designs[design_key]
        parts={(action[0]//32,action[1]//32) for action in design}
        tile=TILE*self.world_scale
        # Compose opaque native-resolution wall tiles once; use exactly the wall grid/filter.
        for y in range(wy-1,wy+2):
            for x in range(wx-1,wx+2):
                part=x-wx+1,y-wy+1
                if part not in parts:
                    continue
                if not game.solid(x,y) or not (game.reveal_all or (x,y) in game.visible):
                    continue
                tx,ty=self.world(x,y)
                left,top=max(8,tx),max(32,ty)
                right,bottom=min(504,tx+tile),min(400,ty+tile)
                if right<=left or bottom<=top:
                    continue
                p.SDL_RenderSetClipRect(p.renderer,p.SDL_Rect(round(left),round(top),round(right-left),round(bottom-top)))
                mask=sum(bit for dx,dy,bit in ((0,-1,1),(1,0,2),(0,1,4),(-1,0,8)) if game.solid(x+dx,y+dy))
                variant=(x*3+y*5+game.seed)%4
                image=self.shortcut_tile(mask,variant,frame,facing,part,design)
                _,tint=self.tile_tint(game,x,y)
                p.SDL_SetTextureColorMod(image.texture,*tint)
                p.SDL_RenderCopy(p.renderer,image.texture,None,p.SDL_Rect(round(tx),round(ty),round(tile),round(tile)))
        p.SDL_RenderSetClipRect(p.renderer,p.SDL_Rect(8,32,496,368))

    @staticmethod
    def shortcut_design(frame,facing):
        """Only reuse the door interior. The generated masonry rim is intentionally excluded."""
        puzzle=frame<2
        def inside(x,y):
            if puzzle:
                if not 8<=y<32:return False
                half=math.sqrt(max(0,8**2-(y-16)**2)) if y<16 else 8
                return 48-half<=x<48+half
            if not 12<=y<32:return False
            left=(39,39,40,38,39)[min(4,int(y-12)//4)]
            right=(57,58,58,57,58)[min(4,int(y-12)//4)]
            return left<=x<right
        coverage={}
        for y in range(7,32):
            for x in range(36,61):
                count=sum(inside(x+ox,y+oy) for ox in (.25,.75) for oy in (.25,.75))
                if count:coverage[x,y]=round(255*count/4)
        actions=[]
        for (x,y),alpha in coverage.items():
            if puzzle:
                u=43+min(10,max(0,int((x-40)*11/16)))
                v=43+min(19,max(0,int((y-8)*20/24)))
            else:
                u=41+min(14,max(0,int((x-38)*15/20)))
                v=48+min(15,max(0,int((y-12)*16/20)))
            actions.append((x,y+32,'fill',frame*96+u,v,alpha))
        if puzzle:
            # Carve a compact stone arch out of the existing wall texture; no facade decal.
            for y in range(5,32):
                for x in range(36,61):
                    if (x,y) in coverage:continue
                    radius=math.hypot(x+.5-48,y+.5-16)
                    ring=(y<16 and 8<=radius<11.5) or (y>=16 and (37<=x<40 or 56<=x<59))
                    if not ring:continue
                    if y<16:
                        sector=math.atan2(16-y-.5,x+.5-48)/(math.pi/7)
                        joint=abs(sector-round(sector))<.075
                    else:
                        joint=y in (20,26)
                    # Each arch stone uses the original wall's stone grain at native 1:1 scale.
                    if not joint:
                        actions.append((x,y+32,'stone',5+(x%4),3+(y%4),255))
                        if y<16 and radius>10.2:
                            actions.append((x,y+32,'shade',255,255,28))
                    else:
                        actions.append((x,y+32,'shade',0,0,120))
            # Small central keystone with the selected three-notch motif.
            for y in range(4,9):
                for x in range(45,52):
                    notch=x in (46,48,50) and y in (5,6)
                    edge=x in (45,51) or y==8
                    dark=notch or edge
                    if not dark:actions.append((x,y+32,'stone',5+x%4,3+y%4,255))
                    actions.append((x,y+32,'shade',0 if dark else 255,0 if dark else 255,
                                    125 if notch else 52 if edge else 24))
            if frame==0:
                # Two stone leaves and a narrow central seam distinguish the closed slab.
                for y in range(14,31):
                    actions.append((48,y+32,'shade',0,0,85))
                    actions.append((47,y+32,'shade',255,255,24))
        # A one-pixel bevel shades the existing wall texture, preserving its mortar and grain.
        for y in range(6,32):
            for x in range(35,62):
                if (x,y) in coverage:continue
                if (x+1,y) in coverage:
                    actions.append((x,y+32,'shade',255,255,13))
                elif (x-1,y) in coverage or (x,y+1) in coverage:
                    actions.append((x,y+32,'shade',0,0,42))
        if puzzle:
            for y in range(15,22):
                for x in range(66,73):
                    border=x in (66,72) or y in (15,21)
                    if not border:
                        actions.append((x,y+32,'stone',5+x%4,3+y%4,255 if frame==0 else 190))
                        actions.append((x,y+32,'shade',255 if frame==0 else 0,255 if frame==0 else 0,24))
                    else:
                        actions.append((x,y+32,'shade',0,0,125))
        turned=[]
        for x,y,*action in actions:
            if facing=='east':x,y=y,95-x
            elif facing=='west':x,y=95-y,x
            elif facing=='north':x,y=95-x,95-y
            turned.append((x,y,*action))
        return turned

    def shortcut_tile(self,mask,variant,frame,facing,part,design):
        key=mask,variant,frame,facing,part
        if key in self.shortcut_cache:return self.shortcut_cache[key]
        previous=p.SDL_GetRenderTarget(p.renderer)
        clipped=p.SDL_RenderIsClipEnabled(p.renderer)
        clip=p.SDL_Rect();p.SDL_RenderGetClipRect(p.renderer,ctypes.byref(clip))
        texture=self.target(32,32)
        try:
            p.SDL_SetRenderTarget(p.renderer,texture);p.SDL_RenderSetClipRect(p.renderer,None)
            self.image('terrain_v2',(0,0,32,32),(mask*32,variant*32,32,32))
            for x,y,action,a,b,c in design:
                if (x//32,y//32)!=part:continue
                x,y=x%32,y%32
                if action=='fill':
                    p.SDL_SetTextureAlphaMod(self.images['shortcuts'].texture,c)
                    self.image('shortcuts',(x,y,1,1),(a,b,1,1))
                elif action=='stone':
                    self.image('terrain_v2',(x,y,1,1),(mask*32+a,variant*32+b,1,1),(c,c,c))
                else:
                    self.rectangle(x,y,1,1,(a,a,b,c))
            p.SDL_SetTextureBlendMode(texture,p.SDL_BLENDMODE_NONE)
            image=p.Image(texture)
            self.shortcut_cache[key]=image
            return image
        except Exception:
            p.SDL_DestroyTexture(texture)
            raise
        finally:
            p.SDL_SetTextureAlphaMod(self.images['shortcuts'].texture,255)
            p.SDL_SetRenderTarget(p.renderer,previous)
            p.SDL_RenderSetClipRect(p.renderer,ctypes.byref(clip) if clipped else None)

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
                known = (x,y) in game.visited
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
        self.text('HYBRID VIEW · 시제품',383,14,(156,156,128))
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
        self.text('확인한 지형만 표시 · M / Esc 닫기 · 세계 시간은 계속 진행',40,64)
        step,ox,oy=11,145,100
        for x,y in game.visited:
            self.rectangle(ox+x*step,oy+y*step,step-1,step-1,
                           (51,61,61) if game.grid[y][x] else (145,143,119))
        if game.trap_discovered:
            ax,ay=game.trap_cell
            bx,by=game.trap_exit
            length=math.hypot(bx-ax,by-ay)*step
            for i in range(0,max(1,round(length)),7):
                t=i/max(1,length)
                self.rectangle(ox+(ax+.5+(bx-ax)*t)*step,oy+(ay+.5+(by-ay)*t)*step,2,2,(119,141,133))
            self.badge('A',ox+(ax+.5)*step,oy+(ay+.5)*step,(218,175,107))
            self.badge('B',ox+(bx+.5)*step+8,oy+(by+.5)*step-8,(127,197,183))
            self.text(f'A → B : 함정방 연결 · 일반 통로 {game.shortcut_distance}칸 우회',145,80,(195,184,147))
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
        self.shortcut_cache.clear()
        self.shortcut_designs.clear()
        self.images.clear()
        self.effects.clear()
        self.text_cache.clear()
        self.small=self.font=self.title=self.big=None
        for texture in (self.logical,self.display):
            p.SDL_DestroyTexture(texture)
