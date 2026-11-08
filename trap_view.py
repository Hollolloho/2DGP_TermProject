"""Moving 2D texture planes for one known corridor, with billboard hazards.

No maze ray traversal or arbitrary 3D engine: textures scroll on fixed wall,
floor and ceiling planes, whose depth/UVs share the gameplay metre coordinates.
"""
import math
import struct
import ctypes
import pico2d.pico2d as p
from maze_model import TRAP_LENGTH, TRAP_HALF_WIDTH, TRAP_HEIGHT, TRAP_LATERAL, BLADE_RADIUS, TRAP_PLANES, blade_position

WIDTH, HEIGHT, TOP = 1280, 800, 60
FOCAL = 790.0
VERTEX=struct.Struct('<ffBBBBff')
assert VERTEX.size==ctypes.sizeof(p.SDL_Vertex)


def camera(game):
    amount=min(1,abs(game.trap_velocity)/1.8)
    eye=1.55+math.sin(game.trap_stride*9)*.012*amount
    hit=max(0,1-(game.time-game.trap_hit_at)/.22)
    cx=WIDTH/2+math.sin(game.time*75)*hit*4
    return game.trap_x*TRAP_LATERAL,game.trap_progress*TRAP_LENGTH,eye,cx,400.0


def project(game, x, y, world_z):
    camera_x,camera_z,eye,cx,horizon=camera(game)
    z=world_z-camera_z
    if z<=.06:
        return None
    return cx+(x-camera_x)*FOCAL/z,horizon+(eye-y)*FOCAL/z


class Corridor:
    def __init__(self, view):
        self.view=view
        for name,path in [('raw_wall','sprite/wall/materials/base_a.png'),
                          ('raw_floor','sprite/surfaces/materials/floor_flagstone.png'),
                          ('raw_ceiling','sprite/surfaces/materials/ceiling_damp.png'),
                          ('blade','sprite/traps/iron_blade.png')]:
            view.images[name]=view.load(path)

    def draw_planes(self,game):
        """Batch small textured 2D quads; shared edges avoid raster gaps."""
        v=self.view
        camera_x,camera_z,eye,cx,horizon=camera(game)
        end_z=TRAP_LENGTH+1.1-camera_z

        def vertex(x,y,u,t,z,base):
            shade=math.exp(-.065*max(0,z))
            return VERTEX.pack(x,y,int(base[0]*shade+.5),int(base[1]*shade+.5),int(base[2]*shade+.5),255,
                               0 if u<0 else 1 if u>1 else u,0 if t<0 else 1 if t>1 else t)

        def submit(name,vertices):
            if not vertices: return
            # Pack the documented SDL vertex layout directly instead of creating
            # thousands of nested Python SDL_FPoint/SDL_Color wrappers per frame.
            packed=b''.join(vertices)
            buffer=ctypes.create_string_buffer(packed)
            array=ctypes.cast(buffer,ctypes.POINTER(p.SDL_Vertex))
            texture=v.images[name].texture
            p.SDL_SetTextureColorMod(texture,255,255,255)
            assert p.SDL_RenderGeometry(p.renderer,texture,array,len(vertices),None,0)==0

        def quad(output,corners):
            output.extend(corners[i] for i in (0,1,2,0,2,3))

        # Cut precisely at texture repeats so UVs never interpolate across a wrap.
        wraps=[k*3.2-camera_z for k in range(math.floor(camera_z/3.2),math.ceil((camera_z+end_z)/3.2)+1)
               if .05<k*3.2-camera_z<end_z]
        for floor in (True,False):
            height=eye if floor else TRAP_HEIGHT-eye
            sign=1 if floor else -1
            edge=horizon+sign*height*FOCAL/end_z
            low,high=(max(TOP,edge),HEIGHT) if floor else (TOP,min(HEIGHT,edge))
            if high<=low: continue
            nodes={low,high}
            nodes.update(float(y) for y in range(math.ceil(low),math.floor(high)+1,2))
            nodes.update(horizon+sign*height*FOCAL/z for z in wraps if low<horizon+sign*height*FOCAL/z<high)
            nodes=sorted(nodes)
            output=[]
            base=(196,187,170) if floor else (153,165,163)
            for y1,y2 in zip(nodes,nodes[1:]):
                z1=height*FOCAL/abs(y1-horizon)
                z2=height*FOCAL/abs(y2-horizon)
                tile=math.floor((camera_z+(z1+z2)/2)/3.2)
                uv1=(camera_z+z1)/3.2-tile
                uv2=(camera_z+z2)/3.2-tile
                x11=cx+(-TRAP_HALF_WIDTH-camera_x)*FOCAL/z1
                x12=cx+(TRAP_HALF_WIDTH-camera_x)*FOCAL/z1
                x21=cx+(-TRAP_HALF_WIDTH-camera_x)*FOCAL/z2
                x22=cx+(TRAP_HALF_WIDTH-camera_x)*FOCAL/z2
                quad(output,[vertex(x11,y1,0,uv1,z1,base),vertex(x12,y1,1,uv1,z1,base),
                             vertex(x22,y2,1,uv2,z2,base),vertex(x21,y2,0,uv2,z2,base)])
            submit('raw_floor' if floor else 'raw_ceiling',output)

        for side in (-1,1):
            wall_x=side*TRAP_HALF_WIDTH
            far=cx+(wall_x-camera_x)*FOCAL/end_z
            low,high=(0,min(WIDTH,far)) if side<0 else (max(0,far),WIDTH)
            if high<=low: continue
            nodes={low,high}
            nodes.update(float(x) for x in range(math.ceil(low),math.floor(high)+1,2))
            nodes.update(cx+(wall_x-camera_x)*FOCAL/z for z in wraps
                         if low<cx+(wall_x-camera_x)*FOCAL/z<high)
            nodes=sorted(nodes)
            output=[]
            base=(161,170,166) if side<0 else (190,187,175)
            for x1,x2 in zip(nodes,nodes[1:]):
                z1=(wall_x-camera_x)*FOCAL/(x1-cx)
                z2=(wall_x-camera_x)*FOCAL/(x2-cx)
                tile=math.floor((camera_z+(z1+z2)/2)/3.2)
                uv1=(camera_z+z1)/3.2-tile
                uv2=(camera_z+z2)/3.2-tile
                top1=horizon-(TRAP_HEIGHT-eye)*FOCAL/z1
                top2=horizon-(TRAP_HEIGHT-eye)*FOCAL/z2
                bottom1=horizon+eye*FOCAL/z1
                bottom2=horizon+eye*FOCAL/z2
                quad(output,[vertex(x1,top1,uv1,0,z1,base),vertex(x2,top2,uv2,0,z2,base),
                             vertex(x2,bottom2,uv2,1,z2,base),vertex(x1,bottom1,uv1,1,z1,base)])
            submit('raw_wall',output)

    def draw(self, game):
        v=self.view
        v.clear((12,14,16,255))
        camera_x,camera_z,eye,cx,horizon=camera(game)
        end=TRAP_LENGTH+1.1
        end_z=end-camera_z
        a=project(game,-TRAP_HALF_WIDTH,TRAP_HEIGHT,end)
        b=project(game,TRAP_HALF_WIDTH,0,end)
        if a and b:
            v.image('raw_wall',(a[0],a[1],b[0]-a[0],b[1]-a[1]),tint=(160,165,158))
            # A real opening at the end, framed in masonry, rather than a text-only finish.
            door_a=project(game,-.62,2.25,end-.01)
            door_b=project(game,.62,0,end-.01)
            v.rectangle(door_a[0]-6,door_a[1]-6,door_b[0]-door_a[0]+12,door_b[1]-door_a[1]+6,(50,51,45))
            v.rectangle(door_a[0],door_a[1],door_b[0]-door_a[0],door_b[1]-door_a[1],(107,119,99))
            v.rectangle(door_a[0]+5,door_a[1]+5,max(1,door_b[0]-door_a[0]-10),door_b[1]-door_a[1]-5,(146,154,126))

        self.draw_planes(game)
        door_a=project(game,-.62,2.25,end-.01)
        door_b=project(game,.62,0,end-.01)
        if door_a and door_b:
            v.rectangle(door_a[0],door_a[1],door_b[0]-door_a[0],door_b[1]-door_a[1],(126,137,112))
        # Wall-mounted ribs provide world-anchored depth landmarks as we pass them.
        for z in (9.6,6.4,3.2):
            if z-camera_z<.15:
                continue
            shade=math.exp(-.07*(z-camera_z))
            tint=tuple(round(c*shade) for c in (170,172,161))
            for side in (-1,1):
                x0=side*TRAP_HALF_WIDTH
                x1=x0-side*.12
                a,b=project(game,min(x0,x1),TRAP_HEIGHT,z),project(game,max(x0,x1),0,z)
                if a and b:
                    v.image('raw_wall',(a[0],a[1],b[0]-a[0],b[1]-a[1]),(300,100,120,1050),tint=tint)
            a,b=project(game,-TRAP_HALF_WIDTH,TRAP_HEIGHT,z),project(game,TRAP_HALF_WIDTH,TRAP_HEIGHT-.12,z)
            if a and b:
                v.image('raw_wall',(a[0],a[1],b[0]-a[0],b[1]-a[1]),(0,0,1254,90),tint=tint)

        for index,plane in reversed(list(enumerate(TRAP_PLANES))):
            world_z=plane*TRAP_LENGTH
            z=world_z-camera_z
            if z<=.10:
                continue
            world_x=blade_position(game.time,index)*TRAP_LATERAL
            center=project(game,world_x,1.45,world_z)
            ceiling=project(game,world_x,TRAP_HEIGHT,world_z)
            radius=BLADE_RADIUS*FOCAL/z
            tint=tuple(round(c*math.exp(-.035*z)) for c in (238,234,218))
            # The unrotated support and contact shadow share the same anchor.
            v.line(ceiling[0],ceiling[1],center[0],center[1]-radius,(86,83,71))
            v.line(ceiling[0]+2,ceiling[1],center[0]+2,center[1]-radius,(136,128,107))
            ground=project(game,world_x,.015,world_z)
            if ground:
                v.rectangle(ground[0]-radius*.6,ground[1]-3,radius*1.2,6,(8,10,10,100))
            v.image('blade',(center[0]-radius,center[1]-radius,radius*2,radius*2),
                    (100,100,1045,1045),tint=tint,angle=game.time*140+index*45)
            v.rectangle(center[0]-2,center[1]-2,4,4,(63,60,51))
