"""Invulnerable, playable boulder trap. python boulder_practice.py [--smoke]."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import struct
import time
from transitions import Machine

ROOT=Path(os.environ.get('MAZE_PROJECT',Path(__file__).resolve().parent))
ASSETS=ROOT/'sprite/traps/boulder_chase_v1'
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
    def __init__(self):
        Machine(model=self,states=['ready','chasing','clear'],initial='ready',auto_transitions=False,
                transitions=[['release','ready','chasing'],['finish',['ready','chasing'],'clear'],['restart','*','ready']])
        self.reset()

    def reset(self):
        self.restart()
        self.time=self.x=self.z=self.vx=self.vz=self.stride=0.0
        self.stamina=100.0
        self.hp=100
        self.ball_z=-3.0
        self.ball_speed=self.ball_distance=0.0
        self.contacts=0
        self.hit_until=self.notice_until=0.0
        self.look_back=self.blocked=self.running=False
        self.paused=False
        self.exit_used=None

    @property
    def gap(self):return self.z-self.ball_z-RADIUS-PLAYER_RADIUS

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

    def update(self,dt,dx=0,forward=0,sprint=False,look_back=False):
        dt=max(0,min(.05,dt))
        self.look_back=look_back
        if self.state=='clear' or not dt:return
        self.time+=dt
        if self.state=='ready' and self.time>=5:self.release()
        # Pushing along a side wall should not waste forward velocity.
        if abs(self.x)>=1.47 and dx*self.x>0:dx=0
        magnitude=math.hypot(dx,forward)
        fraction=min(1,self.stamina/(25*dt)) if sprint and magnitude else 0
        speed=2.55+(4.70-2.55)*fraction
        tx,tz=(dx/magnitude*speed,forward/magnitude*speed) if magnitude else (0,0)
        self.vx+=max(-15*dt,min(15*dt,tx-self.vx))
        self.vz+=max(-15*dt,min(15*dt,tz-self.vz))
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
        if self.running:self.stamina=max(0,self.stamina-25*dt*fraction)
        if self.state=='chasing':
            self.ball_speed=min(3.7,self.ball_speed+1.8*dt)
            movement=self.ball_speed*dt
            self.ball_z+=movement
            self.ball_distance+=movement
            if self.gap<=0:
                self.contacts+=1
                self.hit_until=self.time+.45
                self.notice_until=self.time+2.2
                # Practice-only: retain player position/resources, put the rock
                # behind again so contact never becomes a death/soft-lock.
                self.ball_z=self.z-RADIUS-PLAYER_RADIUS-8
        for name,side,z,half in EXITS:
            if side*self.x>1.32 and abs(self.z-z)<half:
                self.exit_used=name;self.finish();self.vx=self.vz=0
                break


class View:
    def __init__(self,p,w,h):
        self.p,self.w,self.h=p,w,h
        self.focal=w*.62
        self.images={}
        for name,path in [('raw_wall',ROOT/'sprite/wall/materials/base_a.png'),
                          ('raw_floor',ROOT/'sprite/surfaces/materials/floor_flagstone.png'),
                          ('raw_ceiling',ROOT/'sprite/surfaces/materials/ceiling_damp.png'),
                          ('boulder',ASSETS/'boulder.png'),('props',ASSETS/'obstacles.png'),
                          ('exits',ASSETS/'exits.png'),('dust',ASSETS/'dust.png')]:
            im=p.load_image(str(path));self.images[name]=im
            p.SDL_SetTextureScaleMode(im.texture,p.SDL_ScaleModeLinear)
            p.SDL_SetTextureBlendMode(im.texture,p.SDL_BLENDMODE_BLEND)
        self.catalog=json.loads((ASSETS/'catalog.json').read_text())
        self.font=p.load_font('C:/Windows/Fonts/malgun.ttf',20)
        self.big=p.load_font('C:/Windows/Fonts/malgunbd.ttf',42)
        self.text_cache={}
        self.canvas=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,w,h)
        assert self.canvas,p.SDL_GetError()
        p.SDL_SetTextureScaleMode(self.canvas,p.SDL_ScaleModeLinear)
        # Reuse the existing corridor planes in this dedicated process only.
        import trap_view as corridor
        corridor.WIDTH,corridor.HEIGHT,corridor.TOP=w,h,72
        corridor.FOCAL=self.focal
        corridor.TRAP_LENGTH=LENGTH+30
        corridor.TRAP_HALF_WIDTH=HALF_WIDTH
        corridor.camera=self.camera
        self.planes=corridor.Corridor.__new__(corridor.Corridor)
        self.planes.view=self
        self.vertex=struct.Struct('<ffBBBBff')

    def camera(self,g):
        speed=min(1,math.hypot(g.vx,g.vz)/4.7)
        eye=1.55+math.sin(g.stride*7)*(.024 if g.running else .014)*speed
        hit=max(0,(g.hit_until-g.time)/.45)
        pressure=max(0,1-g.gap/7) if g.state=='chasing' else 0
        cx=self.w/2+math.sin(g.time*66)*(hit*5+pressure*1.8)
        return (-g.x,LENGTH-g.z,eye,cx,self.h*.46) if g.look_back else (g.x,g.z,eye,cx,self.h*.46)

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
        p=self.p
        camera_x,camera_z,eye,cx,horizon=self.camera(g)
        poly=[]
        for (x,y,z),(u,v) in zip(points,uv):
            if g.look_back:x,z=-x,LENGTH-z
            poly.append([x,y,z-camera_z,u,v])
        clipped=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            inside_a,inside_b=a[2]>=.09,b[2]>=.09
            if inside_a:clipped.append(a)
            if inside_a!=inside_b:
                t=(.09-a[2])/(b[2]-a[2])
                clipped.append([a[i]+(b[i]-a[i])*t for i in range(5)])
        if len(clipped)<3:return
        vertices=[]
        for index in range(1,len(clipped)-1):
            for x,y,z,u,v in (clipped[0],clipped[index],clipped[index+1]):
                vertices.append(self.vertex.pack(cx+(x-camera_x)*self.focal/z,horizon+(eye-y)*self.focal/z,
                                                *tint[:3],tint[3] if len(tint)>3 else 255,u,v))
        raw=b''.join(vertices);buf=ctypes.create_string_buffer(raw)
        ptr=ctypes.cast(buf,ctypes.POINTER(p.SDL_Vertex))
        tex=self.images[name].texture if name else None
        p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
        assert p.SDL_RenderGeometry(p.renderer,tex,ptr,len(vertices),None,0)==0

    def billboard(self,g,name,rect,pivot,size,x,z,tint):
        im=self.images[name];rx,ry,rw,rh=rect;w,h=size
        left=x-w*pivot[0]/rw;bottom=-h*(rh-pivot[1])/rh
        points=[(left,bottom+h,z),(left+w,bottom+h,z),(left+w,bottom,z),(left,bottom,z)]
        uv=[(rx/im.w,ry/im.h),((rx+rw)/im.w,ry/im.h),((rx+rw)/im.w,(ry+rh)/im.h),(rx/im.w,(ry+rh)/im.h)]
        self.quad(g,name,points,uv,tint)

    def exit(self,g,name,side,z):
        im=self.images['exits'];entry=self.catalog['exits'][name]
        rx,_,rw,rh=entry['rect_top_left'];w,h=entry['world_frame_size_metres']
        floor=-h*24/1024;top=floor+h
        x=side*HALF_WIDTH
        il,ir,it=(.344,.66,.212) if name=='narrow' else (.155,.852,.25)
        za,zb=z-w/2+w*il,z-w/2+w*ir
        def corners(a,b,y0,y1,xpos=x):return [(xpos,y1,a),(xpos,y1,b),(xpos,y0,b),(xpos,y0,a)]
        self.quad(g,None,corners(za,zb,0,top-h*it),[(0,0)]*4,(13,17,16))
        self.quad(g,None,corners(za+.02,zb-.02,0,.12),[(0,0)]*4,(31,33,27))
        shade=math.exp(-.04*abs(z-g.z))
        tint=tuple(round(c*shade) for c in (195,194,178))
        for index in range(24):
            a,b=index/24,(index+1)/24
            self.quad(g,'exits',corners(z-w/2+w*a,z-w/2+w*b,floor,top,x-side*.004),
                      [((rx+rw*a)/im.w,0),((rx+rw*b)/im.w,0),((rx+rw*b)/im.w,1),((rx+rw*a)/im.w,1)],tint)

    def draw(self,g):
        p=self.p;w,h=self.w,self.h
        p.SDL_SetRenderTarget(p.renderer,self.canvas)
        p.SDL_SetRenderDrawColor(p.renderer,8,11,11,255);p.SDL_RenderClear(p.renderer)
        self.planes.draw_planes(g)
        # A real end wall keeps the last side exit from looking like an infinite corridor.
        end_shade=math.exp(-.065*abs(LENGTH+1.3-g.z))
        self.quad(g,'raw_wall',[(-1.8,3,LENGTH+1.3),(1.8,3,LENGTH+1.3),(1.8,0,LENGTH+1.3),(-1.8,0,LENGTH+1.3)],
                  [(0,0),(1,0),(1,1),(0,1)],tuple(round(c*end_shade) for c in (160,166,151)))
        for name,side,z,_ in sorted(EXITS,key=lambda entry:abs(entry[2]-g.z),reverse=True):self.exit(g,name,side,z)
        objects=[('obstacle',entry[2],entry) for entry in OBSTACLES]
        objects.append(('boulder',g.ball_z,None))
        direction=-1 if g.look_back else 1
        objects.sort(key=lambda item:direction*(item[1]-g.z),reverse=True)
        for kind,z,entry in objects:
            if direction*(z-g.z)<.10:continue
            shade=math.exp(-.045*abs(z-g.z))
            tint=tuple(round(c*shade) for c in (220,215,197))
            if kind=='obstacle':
                name,x,z,_,_=entry;prop=self.catalog['props'][name]
                self.billboard(g,'props',prop['rect_top_left'],prop['pivot'],prop['world_frame_size_metres'],x,z,tint)
            else:
                index=int(g.ball_distance/RADIUS/math.tau*24)%24
                size=RADIUS*2*512/472
                self.billboard(g,'boulder',self.catalog['boulder']['frames'][index]['rect_top_left'],[256,492],
                               [size,size],0,z,tint)
                if g.state=='chasing':
                    dust=self.catalog['dust']['frames'][int(g.time*16)%12]
                    self.billboard(g,'dust',dust['rect_top_left'],[256,230],[2.6,1.3],0,z+direction*.02,(185,177,155))
        if g.hit_until>g.time:self.rect(0,72,w,h-72,(160,28,19,round(70*(g.hit_until-g.time)/.45)))
        self.rect(0,0,w,72,(12,17,18,245));self.rect(0,h-100,w,100,(12,17,18,235))
        self.text('돌 추격 · 무적 연습',24,10,big=False)
        if g.state=='ready':status=f'{max(0,5-g.time):.1f}초 후 돌 출발 · 먼저 이동하세요'
        else:status='뒤를 보는 중 · 이동 방향은 그대로' if g.look_back else '좌우로 장애물을 피하고 측면 출구로 탈출'
        self.text(status,285,10)
        self.text('WASD / 방향키 이동   Shift 달리기   Q 누르는 동안 뒤 보기   F 출구 이용   R 재시작   Esc 종료',24,41,(162,174,166))
        self.text(f'스태미너 {g.stamina:03.0f}',24,h-92)
        self.rect(24,h-59,250,12,(44,47,43));self.rect(24,h-59,250*g.stamina/100,12,(171,177,104))
        gap=max(0,g.gap)
        self.text(f'후방 여유 {gap:.1f} m',320,h-92,(226,149,110) if gap<5 else (205,198,173))
        self.rect(320,h-59,220,12,(44,47,43));self.rect(320,h-59,220*min(1,gap/18),12,(186,117,78))
        self.text(f'진행 {g.z:.1f} / {LENGTH:.0f} m   돌 접촉 {g.contacts}회 · HP 100 고정',580,h-92)
        self.text('왼쪽 46m 좁은 출구 / 오른쪽 52m 넓은 출구',580,h-59,(166,184,174))
        if g.exit_nearby() and g.state!='clear':self.text('F  출구 통과',w/2-100,h*.63,(235,218,146),big=True)
        elif g.notice_until>g.time:self.text('돌 접촉 · 무적 적용 / 돌 간격 재설정',w/2-240,h*.28,(244,167,126))
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

    def capture(self,path):
        p=self.p;path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        p.SDL_SetRenderTarget(p.renderer,self.canvas)
        data=(ctypes.c_ubyte*(self.w*self.h*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,self.w*4)==0
        surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,self.w,self.h,32,self.w*4,p.SDL_PIXELFORMAT_RGBA32)
        try:assert p.IMG_SavePNG(surface,str(path).encode())==0
        finally:p.SDL_FreeSurface(surface);p.SDL_SetRenderTarget(p.renderer,None)

    def close(self):
        self.images.clear();self.text_cache.clear();self.font=self.big=None
        self.p.SDL_DestroyTexture(self.canvas)


class App:
    def __init__(self,p,w,h):
        self.p=p;self.g=Practice();self.view=View(p,w,h)
        self.held=set();self.running=True
    def events(self):
        p=self.p
        for event in p.get_events():
            if event.type==p.SDL_QUIT:self.running=False
            elif event.type==p.SDL_KEYUP:self.held.discard(event.key)
            elif event.type==p.SDL_KEYDOWN:
                self.held.add(event.key)
                if event.key==p.SDLK_ESCAPE:self.running=False
                elif event.key==p.SDLK_r:self.g.reset();self.held.clear()
                elif event.key==p.SDLK_f:self.g.use_exit()
                elif event.key==p.SDLK_F10:self.view.capture(OUTPUT/'manual.png')
    def update(self,dt):
        p=self.p;keys=self.held
        dx=int(bool(keys&{p.SDLK_d,p.SDLK_RIGHT}))-int(bool(keys&{p.SDLK_a,p.SDLK_LEFT}))
        forward=int(bool(keys&{p.SDLK_w,p.SDLK_UP}))-int(bool(keys&{p.SDLK_s,p.SDLK_DOWN}))
        self.g.update(dt,dx,forward,bool(keys&{p.SDLK_LSHIFT,p.SDLK_RSHIFT}),p.SDLK_q in keys)
    def status(self):
        g=self.g
        data={'mode':g.state,'time':round(g.time,2),'position':[round(g.x,3),round(g.z,3)],
              'stamina':round(g.stamina,2),'hp':g.hp,'contacts':g.contacts,'gap':round(g.gap,2),
              'look_back':g.look_back,'exit':g.exit_used,'paused':g.paused,
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
    inject(p,p.SDLK_q);app.events();app.update(.025)
    assert g.look_back
    app.view.draw(g);app.view.capture(OUTPUT/'02-look-back.png')
    for _ in range(500):app.update(.025)
    assert g.contacts>0 and g.hp==100 and g.state=='chasing'
    app.view.draw(g);app.view.capture(OUTPUT/'03-invulnerable.png')
    inject(p,p.SDLK_r);app.events()
    assert g.state=='ready' and g.stamina==100 and g.contacts==0
    g.x,g.z=-1,46
    inject(p,p.SDLK_f);app.events()
    assert g.state=='clear' and g.exit_used=='narrow'
    app.view.draw(g);app.view.capture(OUTPUT/'04-complete.png')
    app.status()
    (OUTPUT/'smoke.json').write_text(json.dumps({'passed':True,'native_sdl_inputs':['W','Shift','Q','R','F'],
        'movement':True,'stamina_consumes':True,'rear_view':True,'contact_never_kills':True,
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
    if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    assert p.renderer,p.SDL_GetError()
    p.print_fps=lambda:None
    p.SDL_SetWindowTitle(p.window,'돌 추격 · 무적 연습 · pico2d'.encode())
    if not args.smoke:
        p.SDL_HideWindow(p.window);p.SDL_ShowWindow(p.window);p.SDL_RaiseWindow(p.window)
    app=None
    try:
        app=App(p,args.width,args.height)
        if args.smoke:smoke(app);return
        last=time.perf_counter();next_status=0
        while app.running:
            now=time.perf_counter();dt=min(.05,now-last);last=now
            app.events()
            app.g.paused=not bool(p.SDL_GetWindowFlags(p.window)&p.SDL_WINDOW_INPUT_FOCUS)
            if app.g.paused:app.held.clear()
            else:app.update(dt)
            app.view.draw(app.g);p.SDL_RenderPresent(p.renderer)
            if now>=next_status:
                app.status()
                if not (OUTPUT/'launched.png').exists():app.view.capture(OUTPUT/'launched.png')
                next_status=now+1
            p.delay(.001)
    finally:
        if app:app.view.close()
        p.close_canvas()


if __name__=='__main__':main()
