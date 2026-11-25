"""Invulnerable, playable boulder trap. python -m BoulderPractice.boulder_practice [--smoke]."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import struct
import time
from transitions import Machine
from SourceCode.first_person import MouseLook, turned_yaw, view_axes, walk_velocity
from SourceCode.window_input import disable_text_input

ROOT=Path(os.environ.get('MAZE_PROJECT',Path(__file__).resolve().parents[1]))
ASSETS=ROOT/'sprite/traps/boulder_chase_v1'
ROOM_ASSETS=ROOT/'sprite/traps/boulder_room_v2'
OUTPUT=Path(os.environ.get('BOULDER_OUTPUT',ROOT/'output/boulder_practice'))
LENGTH=52.0
HALF_WIDTH=1.8
RADIUS=1.35
PLAYER_RADIUS=.19
# x, forward metres, half width, half depth. Each leaves a walkable side.
OBSTACLES=(('fallen_column',-.78,11,.60,.28),('rubble',.72,21,.49,.34),
           ('fallen_column',-.62,31,.60,.28),('rubble',.72,39,.49,.34))
EXITS=(('narrow',-1,46,.38),('wide',1,52,.70))


class Practice:
    """Metre-based rules, independent of rendering. Contact counts, never kills."""
    def __init__(self, player=None):
        self.player=player
        Machine(model=self,states=['ready','chasing','clear'],initial='ready',auto_transitions=False,
                transitions=[['release','ready','chasing'],['finish',['ready','chasing'],'clear'],['restart','*','ready']])
        self.reset()

    def reset(self):
        self.restart()
        self.time=self.x=self.z=self.vx=self.vz=self.stride=0.0
        if self.player is None:
            self.stamina=100.0
            self.hp=100
        self.ball_z=-3.0
        self.ball_speed=self.ball_distance=0.0
        self.contacts=0
        self.ball_touching=False
        self.hit_until=self.notice_until=0.0
        self.yaw=self.movement_yaw=0.
        self.blocked=self.running=False
        self.paused=False
        self.exit_used=None

    @property
    def gap(self):return self.z-self.ball_z-RADIUS-PLAYER_RADIUS

    @property
    def stamina(self):return self.player.stamina if self.player is not None else self._stamina

    @stamina.setter
    def stamina(self,value):
        if self.player is None:self._stamina=value
        else:self.player.stamina=value

    @property
    def hp(self):return self.player.hp if self.player is not None else self._hp

    @hp.setter
    def hp(self,value):
        if self.player is None:self._hp=value
        else:self.player.hp=value

    @staticmethod
    def can_stand(x,z):
        return not any(abs(x-ox)<hw+PLAYER_RADIUS and abs(z-oz)<hd+PLAYER_RADIUS
                       for _,ox,oz,hw,hd in OBSTACLES)

    def exit_nearby(self):
        return next((name for name,side,z,half in EXITS if side*self.x>.65 and abs(self.z-z)<=half+.7),None)

    def use_exit(self):
        if self.state=='clear':return False
        name=self.exit_nearby()
        if name:
            self.exit_used=name
            self.finish()
            self.vx=self.vz=0
            return True
        return False

    def update(self,dt,dx=0,forward=0,sprint=False):
        dt=max(0,min(.05,dt))
        if self.state=='clear' or not dt:return
        fraction=min(1,self.stamina/(25*dt)) if sprint and math.hypot(dx,forward) else 0
        self.advance(dt,dx,forward,fraction)
        if self.running:self.stamina=max(0,self.stamina-25*dt*fraction)
        self.automatic_exit()

    def advance(self,dt,dx=0,forward=0,sprint_fraction=0):
        """이동과 돌 진행만 갱신한다. 자원·즉사·출구 확정은 호출자가 처리한다."""
        dt=max(0,min(.05,dt))
        if self.state=='clear' or not dt:return
        self.time+=dt
        if self.state=='ready' and self.time>=5:self.release()
        fraction=sprint_fraction if dx or forward else 0.
        speed=2.55+(4.70-2.55)*fraction
        self.vx,self.vz=walk_velocity(dx,forward,self.yaw,self.movement_yaw,
                                      self.vx,self.vz,speed,15.,dt)
        self.movement_yaw=self.yaw
        old_x,old_z=self.x,self.z
        nx=max(-1.48,min(1.48,self.x+self.vx*dt))
        nz=max(0,min(LENGTH+1.2,self.z+self.vz*dt))
        self.blocked=False
        if self.can_stand(nx,self.z):self.x=nx
        else:self.vx=0;self.blocked=True
        if self.can_stand(self.x,nz):self.z=nz
        else:self.vz=0;self.blocked=True
        travelled=math.hypot(self.x-old_x,self.z-old_z)
        self.stride+=travelled
        self.running=bool(fraction and travelled>.0001)
        if self.state=='chasing':
            self.ball_speed=min(3.7,self.ball_speed+1.8*dt)
            movement=self.ball_speed*dt
            self.ball_z+=movement
            self.ball_distance+=movement
            touching=abs(self.z-self.ball_z)<=RADIUS+PLAYER_RADIUS
            if touching and not self.ball_touching:
                self.contacts+=1
                self.hit_until=self.time+.45
                self.notice_until=self.time+2.2
            # Invulnerability changes the damage result, never the trajectory.
            # Count only entry into overlap, including a later genuine recontact.
            self.ball_touching=touching

    def automatic_exit(self):
        if self.state=='clear':return False
        for name,side,z,half in EXITS:
            if side*self.x>1.32 and abs(self.z-z)<half:
                self.exit_used=name;self.finish();self.vx=self.vz=0
                return True
        return False


class View:
    def __init__(self,p,w,h,*,top=72):
        self.p,self.w,self.h=p,w,h
        self.top=top
        self.focal=w*.62
        self.images={}
        for name,path in [('raw_wall',ROOT/'sprite/wall/materials/base_a.png'),
                          ('raw_floor',ROOT/'sprite/surfaces/materials/floor_flagstone.png'),
                          ('raw_ceiling',ROOT/'sprite/surfaces/materials/ceiling_damp.png'),
                          ('raw_boulder',Path(os.environ.get('BOULDER_MATERIAL',ROOT/'sprite/traps/boulder_volume_v2/stone_material.png'))),
                          ('dust',ASSETS/'dust.png')]:
            im=p.load_image(str(path));self.images[name]=im
            p.SDL_SetTextureScaleMode(im.texture,p.SDL_ScaleModeLinear)
            p.SDL_SetTextureBlendMode(im.texture,p.SDL_BLENDMODE_BLEND)
        self.catalog=json.loads((ASSETS/'catalog.json').read_text())
        self.room_ready=(ROOM_ASSETS/'catalog.json').is_file()
        if self.room_ready:
            room=json.loads((ROOM_ASSETS/'catalog.json').read_text(encoding='utf-8'))
            for name in ('props','exits'):
                entries=room[name]
                filenames={entry['image'] for entry in entries.values()}
                if len(filenames)!=1:
                    raise ValueError(f'{name}: one atlas image required')
                im=p.load_image(str(ROOM_ASSETS/filenames.pop()))
                self.images[name]=im
                p.SDL_SetTextureScaleMode(im.texture,p.SDL_ScaleModeLinear)
                p.SDL_SetTextureBlendMode(im.texture,p.SDL_BLENDMODE_BLEND)
                self.catalog[name]=entries
        self.font=p.load_font('C:/Windows/Fonts/malgun.ttf',20)
        self.big=p.load_font('C:/Windows/Fonts/malgunbd.ttf',42)
        self.text_cache={}
        self.canvas=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,w,h)
        assert self.canvas,p.SDL_GetError()
        p.SDL_SetTextureScaleMode(self.canvas,p.SDL_ScaleModeLinear)
        from SourceCode.trap_view import CorridorPlanes
        self.planes=CorridorPlanes(self,width=w,height=h,top=top,focal=self.focal,
                                   length=LENGTH+1.3,start=-5.0,half_width=HALF_WIDTH,camera=self.camera)
        self.software=self.planes.software
        self.clip_to_view=self.software
        self.view_axes=(1.,0.)
        self.vertex=struct.Struct('<ffBBBBff')
        from .boulder_volume import Boulder
        self.rock=Boulder(self,self.images['raw_boulder'],RADIUS)

    def camera(self,g):
        speed=min(1,math.hypot(g.vx,g.vz)/4.7)
        eye=1.55+math.sin(g.stride*7)*(.024 if g.running else .014)*speed
        hit=max(0,(g.hit_until-g.time)/.45)
        distance=max(0,abs(g.z-g.ball_z)-RADIUS-PLAYER_RADIUS)
        pressure=max(0,1-distance/7) if g.state=='chasing' else 0
        cx=self.w/2+math.sin(g.time*66)*(hit*5+pressure*1.8)
        return g.x,g.z,eye,cx,self.h*.46

    def rect(self,x,y,w,h,color):
        p=self.p
        p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
        p.SDL_SetRenderDrawColor(p.renderer,*color[:3],color[3] if len(color)>3 else 255)
        p.SDL_RenderFillRect(p.renderer,p.SDL_Rect(round(x),round(y),max(0,round(w)),max(0,round(h))))

    def text(self,string,x,y,color=(219,207,184),big=False):
        p=self.p;key=(string,color,big)
        image=self.text_cache.get(key)
        if image is None:
            font=self.big if big else self.font
            surf=p.TTF_RenderUTF8_Blended(font.font,string.encode(),p.SDL_Color(*color,255))
            assert surf
            try:image=p.Image(p.SDL_CreateTextureFromSurface(p.renderer,surf))
            finally:p.SDL_FreeSurface(surf)
            self.text_cache[key]=image
            if len(self.text_cache)>200:self.text_cache.pop(next(iter(self.text_cache)))
        p.SDL_RenderCopy(p.renderer,image.texture,None,p.SDL_Rect(round(x),round(y),image.w,image.h))

    def quad(self,g,name,points,uv,tint):
        return self.planes.quad(g,name,points,tint,uv)

    def billboard(self,g,name,rect,pivot,size,x,z,tint):
        im=self.images[name];rx,ry,rw,rh=rect;w,h=size
        left=-w*pivot[0]/rw;bottom=-h*(rh-pivot[1])/rh
        # A sprite faces the player position. Turning in place must not move its edges.
        distance=math.hypot(x-g.x,z-g.z)
        c,s=((z-g.z)/distance,(x-g.x)/distance) if distance>.001 else self.view_axes
        points=[(x+c*offset,y,z-s*offset) for offset,y in
                ((left,bottom+h),(left+w,bottom+h),(left+w,bottom),(left,bottom))]
        uv=[(rx/im.w,ry/im.h),((rx+rw)/im.w,ry/im.h),((rx+rw)/im.w,(ry+rh)/im.h),(rx/im.w,(ry+rh)/im.h)]
        self.quad(g,name,points,uv,tint)

    def exit(self,g,name,side,z):
        x=side*HALF_WIDTH
        def corners(a,b,y0,y1,xpos=x):return [(xpos,y1,a),(xpos,y1,b),(xpos,y0,b),(xpos,y0,a)]
        shade=math.exp(-.04*abs(z-g.z))
        tint=tuple(round(c*shade) for c in (195,194,178))
        if not self.room_ready:
            # ponytail: use retained stone and the real opening widths until art is ready.
            half=next(half for exit_name,_,_,half in EXITS if exit_name==name)
            self.quad(g,None,corners(z-half,z+half,0,1.9),[(0,0)]*4,(13,17,16))
            for a,b,y0,y1 in ((z-half-.16,z-half,0,2.06),
                              (z+half,z+half+.16,0,2.06),(z-half,z+half,1.9,2.06)):
                self.quad(g,'raw_wall',corners(a,b,y0,y1,x-side*.004),
                          [(0,0),(1,0),(1,1),(0,1)],tint)
            return
        im=self.images['exits'];entry=self.catalog['exits'][name]
        rx,ry,rw,rh=entry['rect_top_left'];w,h=entry['world_frame_size_metres']
        floor=-h*(rh-entry['pivot'][1])/rh;top=floor+h
        il,it,ir,ib=entry['opening_uv']
        za,zb=z-w/2+w*il,z-w/2+w*ir
        self.quad(g,None,corners(za,zb,top-h*ib,top-h*it),[(0,0)]*4,(13,17,16))
        for index in range(24):
            a,b=index/24,(index+1)/24
            self.quad(g,'exits',corners(z-w/2+w*a,z-w/2+w*b,floor,top,x-side*.004),
                      [((rx+rw*a)/im.w,ry/im.h),((rx+rw*b)/im.w,ry/im.h),
                       ((rx+rw*b)/im.w,(ry+rh)/im.h),((rx+rw*a)/im.w,(ry+rh)/im.h)],tint)

    def obstacle(self,g,entry,tint):
        name,x,z,half_width,half_depth=entry
        if self.room_ready:
            prop=self.catalog['props'][name]
            self.billboard(g,'props',prop['rect_top_left'],prop['pivot'],
                           prop['world_frame_size_metres'],x,z,tint)
            return
        left,right=x-half_width,x+half_width
        near,far=z-half_depth,z+half_depth
        height=.64 if name=='fallen_column' else .58
        faces=[[(left,height,near),(right,height,near),(right,height,far),(left,height,far)],
               [(left,height,far),(left,height,near),(left,0,near),(left,0,far)],
               [(right,height,near),(right,height,far),(right,0,far),(right,0,near)]]
        front,back=(far,near) if g.z>z else (near,far)
        for depth in (back,front):
            faces.append([(left,height,depth),(right,height,depth),(right,0,depth),(left,0,depth)])
        for points in sorted(faces,key=lambda face:sum((v[0]-g.x)**2+(v[2]-g.z)**2 for v in face),reverse=True):
            self.quad(g,'raw_wall',points,[(0,0),(1,0),(1,1),(0,1)],tint)

    def draw_scene(self,g):
        """현재 렌더 타깃에 장면만 그린다. HUD·화면 전환은 호출자가 담당한다."""
        p=self.p;w,h=self.w,self.h
        p.SDL_SetRenderDrawColor(p.renderer,8,11,11,255);p.SDL_RenderClear(p.renderer)
        self.view_axes=self.planes.view_axes=view_axes(g.yaw)
        self.planes.draw_planes(g)
        for name,side,z,_ in EXITS:
            self.exit(g,name,side,z)
        c,s=self.view_axes
        def depth(x,z):
            return s*(x-g.x)+c*(z-g.z)
        objects=[(depth(entry[1],entry[2]),'obstacle',entry[2],entry) for entry in OBSTACLES]
        if g.ball_z<LENGTH+1.3 and depth(0,g.ball_z)>-self.rock.max_radius:
            self.rock.shadow(g)
            objects.append((depth(0,g.ball_z),'boulder',g.ball_z,None))
        for distance,kind,z,entry in sorted(objects,reverse=True):
            if kind=='obstacle' and distance<-.9:continue
            shade=math.exp(-.045*abs(z-g.z))
            tint=tuple(round(c*shade) for c in (220,215,197))
            if kind=='obstacle':
                self.obstacle(g,entry,tint)
            else:
                self.rock.dust(g,front=False)
                self.rock.body(g)
                self.rock.dust(g,front=True)
        if g.ball_z<LENGTH+1.3:self.rock.inside_overlay(g)
        if g.hit_until>g.time:self.rect(0,self.top,w,h-self.top,(160,28,19,round(70*(g.hit_until-g.time)/.45)))

    def draw(self,g):
        draw_started=time.perf_counter()
        p=self.p;w,h=self.w,self.h
        p.SDL_SetRenderTarget(p.renderer,self.canvas)
        self.draw_scene(g)
        self.rect(0,0,w,72,(12,17,18,245));self.rect(0,h-100,w,100,(12,17,18,235))
        self.text('돌 추격 · 무적 연습' if self.room_ready else '돌 추격 · 임시 사물',24,10,big=False)
        if g.state=='ready':status=f'{max(0,5-g.time):.1f}초 후 돌 출발 · 먼저 이동하세요'
        elif g.ball_z>g.z+RADIUS+PLAYER_RADIUS:status='돌이 앞서갑니다 · 계속 이동해서 출구로 탈출'
        else:status='좌우로 장애물을 피하고 측면 출구로 탈출'
        self.text(status,285,10)
        self.text('WASD / 방향키 이동   Shift 달리기   마우스 좌우 회전   F 출구 이용   R 재시작   Esc 종료',24,41,(162,174,166))
        self.text(f'스태미너 {g.stamina:03.0f}',24,h-92)
        self.rect(24,h-59,250,12,(44,47,43));self.rect(24,h-59,250*g.stamina/100,12,(171,177,104))
        gap=max(0,abs(g.z-g.ball_z)-RADIUS-PLAYER_RADIUS)
        distance_label=('앞쪽 돌' if g.ball_z>g.z else '후방 여유') if gap>0 else '돌 통과 중'
        self.text(f'{distance_label} {gap:.1f} m',320,h-92,(226,149,110) if gap<5 else (205,198,173))
        self.rect(320,h-59,220,12,(44,47,43));self.rect(320,h-59,220*min(1,gap/18),12,(186,117,78))
        self.text(f'진행 {g.z:.1f} / {LENGTH:.0f} m   돌 접촉 {g.contacts}회 · HP 100 고정',580,h-92)
        self.text('왼쪽 46m 좁은 출구 / 오른쪽 52m 넓은 출구',580,h-59,(166,184,174))
        if g.exit_nearby() and g.state!='clear':self.text('F  출구 통과',w/2-100,h*.63,(235,218,146),big=True)
        elif g.notice_until>g.time:self.text('돌 접촉 · 무적 적용 / 돌은 계속 전진',w/2-240,h*.28,(244,167,126))
        elif g.blocked:self.text('장애물 · 옆으로 돌아가세요',w/2-180,h*.72,(217,182,130))
        if g.state=='clear':
            self.rect(w/2-360,h/2-130,720,240,(10,17,17,235))
            self.text('통과!',w/2-70,h/2-105,(231,216,170),big=True)
            name='좁은 출구' if g.exit_used=='narrow' else '넓은 출구'
            self.text(f'{name} · {g.time:.1f}초 · 돌 접촉 {g.contacts}회 · 남은 스태미너 {g.stamina:.0f}',w/2-300,h/2-30)
            self.text('R 다시 도전   /   Esc 종료',w/2-160,h/2+35,(169,194,182))
        elif g.paused:
            self.rect(w/2-330,h/2-60,660,125,(10,17,17,235))
            self.text('일시 정지 · 게임 창을 클릭하면 재개',w/2-215,h/2-15,(223,211,176))
        p.SDL_SetRenderTarget(p.renderer,None)
        p.SDL_RenderCopy(p.renderer,self.canvas,None,None)
        self.last_draw_ms=(time.perf_counter()-draw_started)*1000

    def capture(self,path):
        p=self.p;path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        p.SDL_SetRenderTarget(p.renderer,self.canvas)
        data=(ctypes.c_ubyte*(self.w*self.h*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,self.w*4)==0
        surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,self.w,self.h,32,self.w*4,p.SDL_PIXELFORMAT_RGBA32)
        try:assert p.IMG_SavePNG(surface,str(path).encode())==0
        finally:p.SDL_FreeSurface(surface);p.SDL_SetRenderTarget(p.renderer,None)

    def close(self):
        self.rock.close()
        self.images.clear();self.text_cache.clear();self.font=self.big=None
        self.p.SDL_DestroyTexture(self.canvas)


class App:
    def __init__(self,p,w,h,*,smoke=False):
        self.p=p;self.g=Practice();self.view=View(p,w,h)
        self.held=set();self.running=True
        self.focused=smoke or bool(p.SDL_GetWindowFlags(p.window)&p.SDL_WINDOW_INPUT_FOCUS)
        self.g.paused=not self.focused
        self.mouse_inside=smoke or bool(p.SDL_GetWindowFlags(p.window)&p.SDL_WINDOW_MOUSE_FOCUS)
        self.mouse=MouseLook(p)
        self.sync_mouse()

    def sync_mouse(self):
        self.mouse.capture(self.running and self.focused and self.mouse_inside and self.g.state!='clear')

    def events(self):
        p=self.p
        event=p.SDL_Event()
        while p.SDL_PollEvent(ctypes.byref(event)):
            if event.type==p.SDL_QUIT:
                self.running=False
            elif event.type==p.SDL_WINDOWEVENT:
                if event.window.event==p.SDL_WINDOWEVENT_FOCUS_LOST:
                    self.focused=False
                    self.held.clear()
                elif event.window.event==p.SDL_WINDOWEVENT_FOCUS_GAINED:
                    disable_text_input(p)
                    self.focused=True
                elif event.window.event in (p.SDL_WINDOWEVENT_ENTER,p.SDL_WINDOWEVENT_LEAVE):
                    self.mouse_inside=event.window.event==p.SDL_WINDOWEVENT_ENTER
                    if not self.mouse_inside:self.held.clear()
                self.g.paused=not self.focused
            elif event.type==p.SDL_MOUSEMOTION:
                self.g.yaw=turned_yaw(self.g.yaw,self.mouse.delta(event.motion))
            elif event.type==p.SDL_KEYUP:
                self.held.discard(event.key.keysym.sym)
            elif event.type==p.SDL_KEYDOWN and self.focused and not event.key.repeat:
                key=event.key.keysym.sym
                self.held.add(key)
                if key==p.SDLK_ESCAPE:self.running=False
                elif key==p.SDLK_r:
                    self.g.reset()
                    self.held.clear()
                    self.mouse.skip_delta=True
                elif key==p.SDLK_f:self.g.use_exit()
                elif key==p.SDLK_F10:self.view.capture(OUTPUT/'manual.png')
            self.sync_mouse()

    def update(self,dt):
        if not self.focused:return
        p=self.p;keys=self.held
        dx=int(bool(keys&{p.SDLK_d,p.SDLK_RIGHT}))-int(bool(keys&{p.SDLK_a,p.SDLK_LEFT}))
        forward=int(bool(keys&{p.SDLK_w,p.SDLK_UP}))-int(bool(keys&{p.SDLK_s,p.SDLK_DOWN}))
        self.g.update(dt,dx,forward,bool(keys&{p.SDLK_LSHIFT,p.SDLK_RSHIFT}))
        self.sync_mouse()

    def status(self):
        g=self.g
        data={'mode':g.state,'time':round(g.time,2),'position':[round(g.x,3),round(g.z,3)],
              'stamina':round(g.stamina,2),'hp':g.hp,'contacts':g.contacts,'gap':round(g.gap,2),
              'ball_z':round(g.ball_z,3),'ball_touching':g.ball_touching,
              'version':'volume-v3','yaw_degrees':round(math.degrees(g.yaw),2),'exit':g.exit_used,'paused':g.paused,
              'frame_draw_ms':round(getattr(self.view,'last_draw_ms',0),2),
              'window_flags':int(self.p.SDL_GetWindowFlags(self.p.window)),'pid':os.getpid()}
        OUTPUT.mkdir(parents=True,exist_ok=True)
        (OUTPUT/'session.json').write_text(json.dumps(data,indent=2),encoding='utf-8')


def inject(p,key,down=True):
    event=p.SDL_Event();event.type=p.SDL_KEYDOWN if down else p.SDL_KEYUP
    event.key.keysym.sym=key;event.key.repeat=0
    assert p.SDL_PushEvent(event)==1


def smoke(app):
    p=app.p;g=app.g
    inject(p,p.SDLK_w);inject(p,p.SDLK_LSHIFT);app.events()
    for _ in range(40):app.update(.025)
    assert g.z>4 and g.stamina<80
    app.view.draw(g);app.view.capture(OUTPUT/'01-moving.png')
    inject(p,p.SDLK_w,False);inject(p,p.SDLK_LSHIFT,False);app.events()
    for _ in range(200):app.update(.025)
    assert g.state=='chasing'
    def motion(dx):
        event=p.SDL_Event()
        event.type=p.SDL_MOUSEMOTION
        event.motion.xrel=dx
        assert p.SDL_PushEvent(event)==1
        app.events()
    motion(35)
    assert g.yaw==0
    motion(600)
    assert math.isclose(g.yaw,math.pi/2)
    def focus(kind):
        event=p.SDL_Event()
        event.type=p.SDL_WINDOWEVENT
        event.window.event=kind
        assert p.SDL_PushEvent(event)==1
        app.events()
    focus(p.SDL_WINDOWEVENT_FOCUS_LOST)
    assert app.mouse.restore is None and not app.held
    motion(-600)
    assert math.isclose(g.yaw,math.pi/2)
    focus(p.SDL_WINDOWEVENT_FOCUS_GAINED)
    motion(2500)
    assert math.isclose(g.yaw,math.pi/2)
    app.view.draw(g);app.view.capture(OUTPUT/'02-side.png')
    motion(600)
    assert math.isclose(g.yaw,math.pi)
    inject(p,p.SDLK_q);app.events()
    assert math.isclose(g.yaw,math.pi)
    app.view.draw(g);app.view.capture(OUTPUT/'02-look-back.png')
    while g.ball_z<g.z+3.5:app.update(.025)
    inject(p,p.SDLK_q,False);app.events();assert math.isclose(g.yaw,math.pi)
    motion(-1200);assert g.yaw==0
    assert g.contacts==1 and g.hp==100 and g.ball_z>g.z+RADIUS+PLAYER_RADIUS
    app.view.draw(g);app.view.capture(OUTPUT/'03-ball-passed-front.png')
    for _ in range(500):app.update(.025)
    assert g.contacts==1 and g.hp==100 and g.state=='chasing' and g.ball_z>g.z
    app.view.draw(g);app.view.capture(OUTPUT/'03-invulnerable.png')
    inject(p,p.SDLK_r);app.events()
    assert g.state=='ready' and g.stamina==100 and g.contacts==0
    # Walk around the first column, then follow the center to the side exit.
    def walk(key,until):
        inject(p,key);app.events()
        for _ in range(1200):
            app.update(.025)
            if until():break
        else:raise AssertionError((key,g.x,g.z))
        inject(p,key,False);app.events()
    motion(8000)  # First motion after restart is discarded.
    inject(p,p.SDLK_w);app.events()
    app.update(.025)
    before_x,before_z=g.x,g.z
    motion(600)
    app.update(.025)
    assert g.x>before_x and math.isclose(g.z,before_z,abs_tol=1e-9)
    walk(p.SDLK_w,lambda:g.x>.9)
    walk(p.SDLK_a,lambda:g.z>14)
    motion(-600)
    walk(p.SDLK_a,lambda:g.x<-.27)
    walk(p.SDLK_w,lambda:g.z>24)
    walk(p.SDLK_d,lambda:g.x>.8)
    walk(p.SDLK_w,lambda:g.z>34)
    walk(p.SDLK_a,lambda:g.x<-.9)
    walk(p.SDLK_w,lambda:g.z>45.8)
    inject(p,p.SDLK_f);app.events()
    assert g.state=='clear' and g.exit_used=='narrow' and app.mouse.restore is None
    app.view.draw(g);app.view.capture(OUTPUT/'04-complete.png')
    app.status()
    (OUTPUT/'smoke.json').write_text(json.dumps({'passed':True,'native_sdl_inputs':['W','Shift','mouse motion','R','F'],
        'movement':True,'stamina_consumes':True,'rear_view':True,'contact_never_kills':True,
        'ball_continues_past_player':True,'one_contact_per_overlap':True,
        'restart':True,'exit':True,'resolution':[app.view.w,app.view.h]},indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--width',type=int,default=1440)
    parser.add_argument('--height',type=int,default=900)
    args=parser.parse_args()
    if args.smoke:os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    import pico2d.pico2d as p
    p.open_canvas(args.width,args.height,sync=not args.smoke)
    disable_text_input(p)
    if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    assert p.renderer,p.SDL_GetError()
    p.print_fps=lambda:None
    p.SDL_SetWindowTitle(p.window,'돌 추격 · 무적 연습 · pico2d'.encode())
    if not args.smoke:
        p.SDL_HideWindow(p.window);p.SDL_ShowWindow(p.window);p.SDL_RaiseWindow(p.window)
    app=None
    try:
        app=App(p,args.width,args.height,smoke=args.smoke)
        if args.smoke:smoke(app);return
        last=time.perf_counter();next_status=0;captured_launch=False
        while app.running:
            now=time.perf_counter();dt=min(.05,now-last);last=now
            app.events()
            app.update(dt)
            app.view.draw(app.g);p.SDL_RenderPresent(p.renderer)
            if now>=next_status:
                app.status()
                if not captured_launch:app.view.capture(OUTPUT/'launched.png');captured_launch=True
                next_status=now+1
            p.delay(.001)
    finally:
        if app:
            app.mouse.capture(False)
            app.view.close()
        p.close_canvas()


if __name__=='__main__':main()
