"""World-space textured corridor and suspended blades."""
import math
import struct
import ctypes
import pico2d.pico2d as p
from .first_person import submit_mesh, view_axes
from .maze_model import TRAP_LENGTH, TRAP_HALF_WIDTH, TRAP_HEIGHT, TRAP_LATERAL, BLADE_RADIUS, TRAP_PLANES, blade_position

WIDTH, HEIGHT, TOP = 1280, 800, 60
FOCAL = 790.0
VERTEX=struct.Struct('<ffBBBBff')
assert VERTEX.size==ctypes.sizeof(p.SDL_Vertex)


def camera(game):
    amount=min(1,math.hypot(game.trap_side_velocity,game.trap_velocity)/1.8)
    eye=1.55+math.sin(game.trap_stride*9)*.012*amount
    hit=max(0,1-(game.time-game.trap_hit_at)/.22)
    cx=WIDTH/2+math.sin(game.time*75)*hit*4
    return game.trap_x*TRAP_LATERAL,game.trap_progress*TRAP_LENGTH,eye,cx,400.0


def project(game, x, y, world_z):
    camera_x,camera_z,eye,cx,horizon=camera(game)
    cosine,sine=view_axes(game.trap_yaw)
    dx,dz=x-camera_x,world_z-camera_z
    depth=sine*dx+cosine*dz
    if depth<=.075:
        return None
    return cx+(cosine*dx-sine*dz)*FOCAL/depth,horizon+(eye-y)*FOCAL/depth


UV = ((0,0),(1,0),(1,1),(0,1))
QUAD = ((0,1,2),(0,2,3))


class CorridorPlanes:
    """The shell and its UVs stay fixed as the camera translates and turns."""
    def __init__(self, view, *, width=WIDTH, height=HEIGHT, top=TOP, focal=FOCAL,
                 length=TRAP_LENGTH+1.1, start=-1.6, half_width=TRAP_HALF_WIDTH, camera=camera):
        self.view=view
        self.w,self.h,self.top=width,height,top
        self.focal,self.length,self.half_width=focal,length,half_width
        self.camera,self.start=camera,start
        self.p,self.vertex=p,VERTEX
        info=p.SDL_RendererInfo()
        p.SDL_GetRendererInfo(p.renderer,info)
        self.software=bool(info.flags & p.SDL_RENDERER_SOFTWARE)
        self.clip_to_view=self.software
        self.view_axes=(1.,0.)
        self.tiles=[]
        for tile in range(math.floor(start/3.2), math.ceil(length/3.2)):
            low=max(start,tile*3.2)
            high=min(length,(tile+1)*3.2)
            if high-low<1e-6:
                continue
            self.tiles.append((low,high,[self.tile_mesh(tile,low,high,n) for n in (2,8)]))

    def tile_mesh(self,tile,low,high,n):
        # Subdivide nearby surfaces for perspective-correct-looking SDL affine UVs.
        sections=[]
        indices=[]
        for row in range(n):
            for col in range(n):
                i=row*(n+1)+col
                indices.extend(((i,i+1,i+n+2),(i,i+n+2,i+n+1)))
        for name,side,base in (('raw_floor',0,(196,187,170)),('raw_ceiling',0,(153,165,163)),
                               ('raw_wall',-1,(161,170,166)),('raw_wall',1,(190,187,175))):
            vertices=[]
            for row in range(n+1):
                z=low+(high-low)*row/n
                repeat=max(0.,min(1.,z/3.2-tile))
                for col in range(n+1):
                    t=col/n
                    if side:
                        vertices.append((side*self.half_width,TRAP_HEIGHT*(1-t),z,repeat,t))
                    else:
                        vertices.append(((2*t-1)*self.half_width,TRAP_HEIGHT if name=='raw_ceiling' else 0.,z,t,repeat))
            sections.append((name,vertices,base))
        return sections,indices

    def quad(self,game,name,points,tint,uv=UV):
        texture=self.view.images[name].texture if name else None
        alpha=tint[3] if len(tint)==4 else 255
        vertices=[(*pos,*tex,*tint[:3],alpha) for pos,tex in zip(points,uv)]
        return submit_mesh(self,game,texture,vertices,QUAD if len(points)==4 else ((0,1,2),))

    def draw_planes(self,game):
        x,z,_,cx,_=self.camera(game)
        cosine,sine=self.view_axes
        for low,high,levels in self.tiles:
            dx,dz=-x,(low+high)*.5-z
            depth=sine*dx+cosine*dz
            lateral=cosine*dx-sine*dz
            radius=math.hypot(self.half_width,(high-low)*.5)
            if depth+radius<=.075 or abs(lateral)>radius+(depth+radius)*max(cx,self.w-cx)/self.focal:
                continue
            far_mesh,near_mesh=levels
            sections,indices=near_mesh if abs(dz)<6. else far_mesh
            for name,mesh,base in sections:
                vertices=[]
                # Cross-sections repeat z for each row. Share their fog calculation.
                previous=None
                for vx,y,vz,u,t in mesh:
                    if vz!=previous:
                        fade=math.exp(-.065*abs(vz-z))
                        color=tuple(round(c*fade) for c in base)
                        previous=vz
                    vertices.append((vx,y,vz,u,t,*color,255))
                submit_mesh(self,game,self.view.images[name].texture,vertices,indices)
        for end in (self.start,self.length):
            wall=self.half_width
            tint=tuple(round(c*math.exp(-.065*abs(end-z))) for c in (160,165,158))
            # Split across the wall to keep its UVs anchored at oblique angles.
            for i in range(12):
                u,v=i/12,(i+1)/12
                left,right=(2*u-1)*wall,(2*v-1)*wall
                self.quad(game,'raw_wall',[(left,TRAP_HEIGHT,end),(right,TRAP_HEIGHT,end),
                          (right,0,end),(left,0,end)],tint,[(u,0),(v,0),(v,1),(u,1)])


class Corridor(CorridorPlanes):
    def __init__(self, view):
        super().__init__(view)
        for name,path in [('raw_wall','sprite/wall/materials/base_a.png'),
                          ('raw_floor','sprite/surfaces/materials/floor_flagstone.png'),
                          ('raw_ceiling','sprite/surfaces/materials/ceiling_damp.png'),
                          ('blade','sprite/traps/iron_blade.png')]:
            view.images[name]=view.load(path)

    def draw(self,game):
        self.view.clear((12,14,16,255))
        self.view_axes=view_axes(game.trap_yaw)
        self.draw_planes(game)
        def panel(name,z,left,right,bottom,top,tint,uv=UV):
            self.quad(game,name,[(left,top,z),(right,top,z),(right,bottom,z),(left,bottom,z)],tint,uv)
        # A bronze-stepped portal frames the same traversable exit.
        end=self.length-.025
        panel(None,end,-.77,.77,0,2.40,(38,39,52))
        panel(None,end-.012,-.54,.54,0,2.17,(43,72,74))
        for side in (-1,1):
            l,r=sorted((side*.57,side*.71))
            panel(None,end-.025,l,r,0,2.21,(174,132,84))
            l,r=sorted((side*.53,side*.75))
            panel(None,end-.03,l,r,2.10,2.25,(215,177,107))
        panel(None,end-.035,-.77,.77,2.24,2.32,(200,157,98))
        self.quad(game,None,[(-.76,2.34,end),(0,2.70,end),(.76,2.34,end)],(125,84,65))
        self.quad(game,None,[(-.29,2.40,end-.04),(0,2.54,end-.04),(.29,2.40,end-.04)],(105,192,172))
        camera_z=game.trap_progress*TRAP_LENGTH
        objects=[(z,None) for z in (3.2,6.4,9.6)]
        objects.extend((plane*TRAP_LENGTH,i) for i,plane in enumerate(TRAP_PLANES))
        for z,index in sorted(objects,key=lambda item:abs(item[0]-camera_z),reverse=True):
            if index is None:
                tint=tuple(round(c*math.exp(-.07*abs(z-camera_z))) for c in (170,172,161))
                for side in (-1,1):
                    outer=side*TRAP_HALF_WIDTH
                    inner=outer-side*.12
                    panel('raw_wall',z,min(inner,outer),max(inner,outer),0,TRAP_HEIGHT,tint,
                          ((.24,.08),(.34,.08),(.34,.92),(.24,.92)))
                panel('raw_wall',z,-TRAP_HALF_WIDTH,TRAP_HALF_WIDTH,TRAP_HEIGHT-.12,TRAP_HEIGHT,tint,
                      ((0,0),(1,0),(1,.07),(0,.07)))
                continue
            x=blade_position(game.time,index)*TRAP_LATERAL
            r=BLADE_RADIUS
            for side in (-1,1):
                # Vitreous red inlay identifies the sweep plane on the floor.
                edge=side*(TRAP_HALF_WIDTH-.10)
                self.quad(game,None,[(edge,.008,z-.12),(edge-side*.40,.008,z),
                          (edge,.008,z+.12)],(203,88,64))
            panel(None,z,-TRAP_HALF_WIDTH,TRAP_HALF_WIDTH,TRAP_HEIGHT-.13,TRAP_HEIGHT,(66,52,53))
            panel(None,z,x-.10,x+.10,TRAP_HEIGHT-.14,TRAP_HEIGHT-.055,(199,146,82))
            axle_y=1.45
            panel(None,z,x-.009,x+.009,axle_y,TRAP_HEIGHT,(123,118,99))
            pin=r*.055
            panel(None,z,x-pin,x+pin,axle_y-pin,axle_y+pin,(87,59,43))
            panel(None,z,x-.65*pin,x+.65*pin,axle_y-.65*pin,axle_y+.65*pin,(189,143,81))
            self.quad(game,None,[(x-r*.6,.015,z-.04),(x+r*.6,.015,z-.04),
                      (x+r*.6,.015,z+.04),(x-r*.6,.015,z+.04)],(8,10,10,100))
            angle=math.radians(game.time*140+index*45)
            c,s=math.cos(angle),math.sin(angle)
            points=[(x+r*(c*dx+s*dy),axle_y+r*(c*dy-s*dx),z) for dx,dy in ((-1,1),(1,1),(1,-1),(-1,-1))]
            im=self.view.images['blade']
            uv=[((100+u*1045)/im.w,(100+v*1045)/im.h) for u,v in UV]
            tint=tuple(round(v*math.exp(-.035*abs(z-camera_z))) for v in (238,234,218))
            self.quad(game,'blade',points,tint,uv)
