"""Perspective rendering for six adjacent sloped stone lanes."""
import ctypes
import json
import math
from pathlib import Path
import struct
import time

from BoulderPractice.boulder_volume import Boulder, normalize, sloped_rolled_pose, stone_mesh
from .first_person import view_axes
from .six_lane_trap import (
    BEVEL_DEPTH, HALF_WIDTH, LANE_COUNT, LANE_DEPTH, LANE_START, LENGTH,
    RADIUS, ROLL_LIMIT, connection_width, row_height,
)


class SixLaneView:
    clip_to_view = True

    def __init__(self, p, w, h, *, top=60, render_scale=None):
        self.p = p
        info = p.SDL_RendererInfo()
        assert p.SDL_GetRendererInfo(p.renderer, ctypes.byref(info)) == 0
        self.software = bool(info.flags & p.SDL_RENDERER_SOFTWARE)
        if render_scale is None:
            render_scale = 1. if info.flags & p.SDL_RENDERER_ACCELERATED else .75
        self.w, self.h = round(w*render_scale), round(h*render_scale)
        self.top = round(top*render_scale)
        self.focal = self.w*.70
        self.vertex = struct.Struct('<ffBBBBff')
        self.canvas = p.SDL_CreateTexture(p.renderer, p.SDL_PIXELFORMAT_RGBA8888,
                                          p.SDL_TEXTUREACCESS_TARGET, self.w, self.h)
        assert self.canvas, p.SDL_GetError()
        p.SDL_SetTextureScaleMode(self.canvas, p.SDL_ScaleModeLinear)
        root = Path(__file__).resolve().parents[1]
        self.images = {}
        self.lane_inlays = {}
        for name, path in (
                ('wall', 'sprite/wall/materials/base_a.png'),
                ('floor', 'sprite/surfaces/materials/floor_flagstone.png'),
                ('ceiling', 'sprite/surfaces/materials/ceiling_damp.png'),
                ('stone', 'sprite/traps/boulder_volume_v2/stone_material.png'),
                ('dust', 'sprite/traps/boulder_chase_v1/dust.png')):
            image = p.load_image(str(root/path))
            p.SDL_SetTextureScaleMode(image.texture, p.SDL_ScaleModeLinear)
            p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND if name == 'dust' else p.SDL_BLENDMODE_NONE)
            self.images[name] = image
        directory = root/'sprite/traps/boulder_room_v2'
        catalog = json.loads((directory/'catalog.json').read_text(encoding='utf-8'))
        self.exit_frame = catalog['exits']['wide']
        image = p.load_image(str(directory/self.exit_frame['image']))
        p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(image.texture, p.SDL_ScaleModeLinear)
        self.images['exit'] = image
        dust_catalog = root/'sprite/traps/boulder_chase_v1/catalog.json'
        self.dust = json.loads(dust_catalog.read_text(encoding='utf-8'))['dust']
        # Old fracture planes truncate the round core. The same planes survive LOD changes.
        fractures = [(*normalize(*normal), depth) for normal,depth in (
            ((-.75,.55,-.5),.81), ((.32,.8,-.48),.86), ((.87,-.30,-.39),.78),
            ((-.22,-.85,-.46),.86), ((.65,.26,.7),.83), ((-.6,-.43,.67),.86))]
        self.rock = Boulder(self, self.images['stone'], RADIUS, rings=16, segments=28, fractures=fractures)
        self.mineral_veins()
        p.SDL_SetTextureBlendMode(self.rock.texture, p.SDL_BLENDMODE_NONE)
        self.meshes = {
            'near': (self.rock.vertices, self.rock.indices),
            'middle': stone_mesh(RADIUS, 10, 20, fractures),
            'far': stone_mesh(RADIUS, 6, 12, fractures),
        }
        self.fracture_faces = {}
        self.port_meshes = {}
        for level,(vertices, _) in self.meshes.items():
            self.fracture_faces[level] = []
            for vertex in vertices:
                nx,ny,nz = vertex[5:]
                # Keep the planar normal across a broken face and its chipped rim.
                exposed = False
                for fx,fy,fz,depth in fractures:
                    if abs(fx*vertex[0]+fy*vertex[1]+fz*vertex[2]-RADIUS*depth)<1e-6:
                        vertex[5:] = normalize(.15*nx+.85*fx, .15*ny+.85*fy, .15*nz+.85*fz)
                        exposed = True
                        break
                self.fracture_faces[level].append(exposed)
        self.light = normalize(-.8, 1., -.55)
        self.last_triangles = 0
        self.last_draw_ms = 0.
        self.visible_stones = []
        self.stone_contacts = {}

    def mineral_veins(self):
        """Deposit branching, grain-textured inclusions on the rock's private UV atlas."""
        p, source = self.p, self.images['stone']
        target = p.SDL_GetRenderTarget(p.renderer)
        p.SDL_SetRenderTarget(p.renderer,self.rock.texture)
        p.SDL_SetTextureBlendMode(source.texture,p.SDL_BLENDMODE_ADD)
        try:
            width,height = 2*source.w,source.h
            def trace(u):
                angle = math.tau*u
                return (.49+.19*math.cos(angle-.45)+.052*math.sin(3*angle+.7)
                        +.013*math.sin(9*angle)+.006*math.sin(23*angle))
            for start,end,branch in ((0.,1.,0.),(.12,.34,.12),(.47,.65,-.09),(.7,.94,.13)):
                packed = []
                previous = None
                steps = math.ceil((end-start)*400)
                for i in range(steps+1):
                    t = i/steps
                    u = start+(end-start)*t
                    v = trace(u)+branch*t**1.4
                    grain = .55+.24*math.sin(math.tau*7*u)+.15*math.cos(math.tau*17*u)
                    half = (.018 if not branch else .008*(1-t))*grain
                    opacity = 235*min(1.,1.6*grain)*(1.-t if branch else 1.)
                    section = []
                    for offset, strength in ((-1.,0.),(-.48,.9),(.25,1.),(1.,0.)):
                        uv_y = v+half*offset
                        section.append(self.vertex.pack(u*width,uv_y*height,215,235,245,
                                                       round(opacity*strength),abs(1-2*u),uv_y))
                    if previous:
                        for j in range(3):
                            packed.extend((previous[j],section[j],section[j+1],
                                           previous[j],section[j+1],previous[j+1]))
                    previous = section
                buf = ctypes.create_string_buffer(b''.join(packed))
                ptr = ctypes.cast(buf,ctypes.POINTER(p.SDL_Vertex))
                assert p.SDL_RenderGeometry(p.renderer,source.texture,ptr,len(packed),None,0)==0,p.SDL_GetError()
        finally:
            p.SDL_SetTextureBlendMode(source.texture,p.SDL_BLENDMODE_NONE)
            p.SDL_SetRenderTarget(p.renderer,target)

    def camera(self, room):
        eye = room.floor_height(room.x, room.z)+1.55
        speed = min(1., math.hypot(room.vx, room.vz)/4.7)
        eye += math.sin(room.stride*7)*.012*speed
        return room.x, room.z, eye, self.w/2, self.h*.43

    @staticmethod
    def quad_mesh(faces, uv_at=None):
        vertices, indices = [], []
        for points, tint in faces:
            offset = len(vertices)
            for (x, y, z), (u, v) in zip(points, ((0, 0), (1, 0), (1, 1), (0, 1))):
                if uv_at is not None:
                    u, v = uv_at(x, z)
                vertices.append((x, y, z, u, v, *tint, 255))
            for triangle in ((0,1,2), (0,2,3)):
                a,b,c = (points[index] for index in triangle)
                ab,ac = [b[index]-a[index] for index in range(3)], [c[index]-a[index] for index in range(3)]
                area = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
                if sum(component*component for component in area) > 1e-16:
                    indices.append(tuple(offset+index for index in triangle))
        return vertices,indices

    def quads(self, room, name, faces, uv_at=None):
        vertices,indices = self.quad_mesh(faces,uv_at)
        texture = self.images[name].texture if name is not None else None
        self.last_triangles += self.rock.submit(room, texture, vertices, indices)

    @staticmethod
    def floor_uv(x, z):
        # One continuous outcrop. The same world point always samples the same
        # grain, even on two independently drawn faces or in the rear view.
        u = .5+.081*x+.052*math.sin(z*.47)
        v = .05+.9*(1.-abs(z % 16.-8.)/8.)
        return u, v

    def row(self, room, index, start, end):
        lane = index if 0 <= index < LANE_COUNT else None
        shade = max(.53, math.exp(-.016*abs((start+end)/2-room.z)))
        floor_tint = tuple(round(c*shade) for c in (214, 207, 185))
        ceiling = 4.8
        floors, walls = [], []
        # Split on every terrain crease and UV fold. Extra depth slices limit
        # affine texture distortion on the foreground floor in SDL_RenderGeometry.
        depths = {start, end, start+.75, start+1.5, start+2.25}
        depths.update(z for z in (8.,16.) if start < z < end)
        if lane is not None:
            depths.update((start+BEVEL_DEPTH, end-BEVEL_DEPTH))
        depths = sorted(depths)
        if lane is not None:
            self.ports(room,lane,depths)
        for za, zb in zip(depths, depths[1:]):
            edges = []
            for z in (za, zb):
                wedge = connection_width(lane, z)
                edges.append((-HALF_WIDTH, -2.55, -wedge, wedge, 2.55, HALF_WIDTH))
            for left_a,right_a,left_b,right_b in zip(edges[0],edges[0][1:],edges[1],edges[1][1:]):
                corners = ((left_a,za),(right_a,za),(right_b,zb),(left_b,zb))
                points = [(x,row_height(lane,x,z),z) for x,z in corners]
                floors.append((points, floor_tint))
        # Render the bedrock beneath the side ports at the same slope as the floor.
        for side in (-1, 1):
            walls.extend(self.side_wall(lane,start,end,side,shade))
        self.quads(room, 'floor', floors, self.floor_uv)
        if lane is not None:
            if lane not in self.lane_inlays:
                self.lane_inlays[lane]=self.inlay_mesh(lane,(start+end)/2)
            self.last_triangles+=self.rock.submit(room,None,*self.lane_inlays[lane])
        self.quads(room, 'wall', walls)
        self.quads(room, 'ceiling', [
            ([(-HALF_WIDTH,ceiling,start), (HALF_WIDTH,ceiling,start),
              (HALF_WIDTH,ceiling,end), (-HALF_WIDTH,ceiling,end)], (80,79,69))])

    @staticmethod
    def inlay_mesh(lane,center_z):
        # Inlaid bronze feathers point downhill. The wide crossing in the
        # middle stays clear; all corners sit on the same surface as the rock.
        direction=1 if lane%2==0 else -1
        faces=[]
        for side in (-1,1):
            center_x=side*3.15
            for offset in (-.35,.35):
                for wing in (-1,1):
                    outline=((offset+.23,0),(offset-.31,wing*.64),
                             (offset-.49,wing*.64),(offset+.05,0))
                    points=[]
                    for run,along in outline:
                        x,z=center_x+direction*run,center_z+along
                        points.append((x,row_height(lane,x,z)+.012,z))
                    color=(189,121,79) if wing<0 else (128,96,76)
                    faces.append((points,color))
        return SixLaneView.quad_mesh(faces)

    @staticmethod
    def side_wall(lane,start,end,side,shade):
        walls = []
        ceiling = 4.8
        x = side*HALF_WIDTH
        tint = tuple(round(c*shade) for c in ((139,132,113) if side < 0 else (167,155,131)))
        port = 3.05 if lane is not None else 0.
        walls.append(([(x,ceiling,start), (x,ceiling,end),
                       (x,row_height(lane,x,end)+port,end),
                       (x,row_height(lane,x,start)+port,start)], tint))
        if lane is not None:
            for a,b in ((start,start+.10), (end-.10,end)):
                walls.append(([(x,ceiling,a), (x,ceiling,b),
                               (x,row_height(lane,x,b),b), (x,row_height(lane,x,a),a)], tint))
        return walls

    def ports(self,room,lane,depths):
        # Continue the track beneath the offstage roll. A side-on view sees the
        # recess behind the mouth, including the bed under the stone's shadow.
        start,end = depths[0],depths[-1]
        c,s = self.view_axes
        _,_,eye,cx,horizon = self.camera(room)
        for side in (-1,1):
            lip = side*HALF_WIDTH
            dx = lip-room.x
            depth = [dx*s+(z-room.z)*c for z in (start,end)]
            if max(depth) <= .075:
                continue
            clip = None
            if min(depth) > .075:
                px = [cx+self.focal*(dx*c-(z-room.z)*s)/d for z,d in zip((start,end),depth)]
                # Bound the whole mouth, including the bevel's highest and lowest points.
                heights = [row_height(lane,lip,z) for z in (start,(start+end)/2,end)]
                py = [horizon-self.focal*(y-eye)/d for d in depth for y in (min(heights),max(heights)+3.3)]
                l,r = max(0,math.floor(min(px))),min(self.w,math.ceil(max(px)))
                t,b = max(0,math.floor(min(py))),min(self.h,math.ceil(max(py)))
                if r <= l or b <= t:
                    continue
                clip = self.p.SDL_Rect(l,t,r-l,b-t)
            key = lane,side
            if key not in self.port_meshes:
                self.port_meshes[key] = self.build_port(lane,depths,side)
            self.p.SDL_RenderSetClipRect(self.p.renderer,clip)
            try:
                for name,(vertices,indices) in self.port_meshes[key]:
                    self.last_triangles += self.rock.submit(room,self.images[name].texture,vertices,indices)
            finally:
                self.p.SDL_RenderSetClipRect(self.p.renderer,None)

    def build_port(self,lane,depths,side):
        start,end = depths[0],depths[-1]
        lip,back = side*HALF_WIDTH,side*(HALF_WIDTH+3.5)
        def bed(x,z):
            return row_height(lane,x,z)
        shell = []
        for z in (start,end):
            shell.append(([(lip,bed(lip,z),z),(back,bed(back,z),z),
                           (back,bed(back,z)+3.3,z),(lip,bed(lip,z)+3.3,z)], (73,69,60)))
        shell.append(([(back,bed(back,start),start),(back,bed(back,end),end),
                       (back,bed(back,end)+3.3,end),(back,bed(back,start)+3.3,start)], (36,34,31)))

        floor = []
        roof = []
        for za,zb in zip(depths,depths[1:]):
            points = [(x,bed(x,z),z) for x,z in ((lip,za),(back,za),(back,zb),(lip,zb))]
            floor.append((points,(140,134,120)))
            roof.append(([(x,y+3.3,z) for x,y,z in points],(58,54,46)))
        return [('wall',self.quad_mesh(shell)), ('ceiling',self.quad_mesh(roof)),
                ('floor',self.quad_mesh(floor,lambda x,z: self.floor_uv(2*lip-x,z)))]

    def seam(self, room, z, before, after):
        width = max(connection_width(before, z), connection_width(after, z))
        faces = []
        for left, right in ((-HALF_WIDTH, -width), (width, HALF_WIDTH)):
            faces.append(([(left,row_height(before,left,z),z), (right,row_height(before,right,z),z),
                           (right,row_height(after,right,z),z), (left,row_height(after,left,z),z)],
                          (137,126,106)))
        self.quads(room, 'wall', faces)

    def end_wall(self, room):
        ceiling = 4.8
        self.quads(room, 'wall', [
            ([(-HALF_WIDTH,ceiling,LENGTH), (-1.55,ceiling,LENGTH),
              (-1.55,0,LENGTH), (-HALF_WIDTH,0,LENGTH)], (151,139,115)),
            ([(1.55,ceiling,LENGTH), (HALF_WIDTH,ceiling,LENGTH),
              (HALF_WIDTH,0,LENGTH), (1.55,0,LENGTH)], (151,139,115)),
            ([(-1.55,ceiling,LENGTH), (1.55,ceiling,LENGTH),
              (1.55,2.7,LENGTH), (-1.55,2.7,LENGTH)], (151,139,115)),
        ])
        self.quads(room, None, [
            ([(-1.55,2.7,LENGTH+.02), (1.55,2.7,LENGTH+.02),
              (1.55,0,LENGTH+.02), (-1.55,0,LENGTH+.02)], (7,12,12))])
        image = self.images['exit']
        rx, ry, rw, rh = self.exit_frame['rect_top_left']
        width, height = 3.95, 3.3
        bottom = -height*(rh-self.exit_frame['pivot'][1])/rh
        points = [(-width/2,bottom+height,LENGTH-.01), (width/2,bottom+height,LENGTH-.01),
                  (width/2,bottom,LENGTH-.01), (-width/2,bottom,LENGTH-.01)]
        vertices = [(x,y,z,u,v,221,204,163,255) for (x,y,z),(u,v) in zip(points, (
            (rx/image.w,ry/image.h), ((rx+rw)/image.w,ry/image.h),
            ((rx+rw)/image.w,(ry+rh)/image.h), (rx/image.w,(ry+rh)/image.h)))]
        self.last_triangles += self.rock.submit(room, image.texture, vertices, ((0,1,2), (0,2,3)))

    def shadow(self, room, stone, contact, opacity):
        x, _, z = contact
        vertices = [(x,room.floor_height(x,z)+.008,z,0,0,4,5,5,round(155*opacity))]
        indices = []
        segments = 20
        for radius, alpha in ((.2,140), (.6,76), (1.05,0)):
            for index in range(segments):
                angle = index/segments*math.tau
                px = x+math.cos(angle)*RADIUS*radius
                pz = z+math.sin(angle)*RADIUS*radius*.75
                vertices.append((px,room.floor_height(px,pz)+.008,pz,0,0,4,5,5,round(alpha*opacity)))
        for index in range(segments):
            indices.append((0,1+index,1+(index+1) % segments))
        for ring in range(2):
            a, b = 1+ring*segments, 1+(ring+1)*segments
            for index in range(segments):
                after = (index+1) % segments
                indices.extend(((a+index,b+index,b+after), (a+index,b+after,a+after)))
        self.last_triangles += self.rock.submit(room, None, vertices, indices)

    def stone(self, room, stone):
        depth = math.hypot(stone.x-room.x,stone.z-room.z)
        level = 'near' if depth < 6 else 'middle' if depth < 12 else 'far'
        mesh, indices = self.meshes[level]
        world, _, contact = sloped_rolled_pose(mesh, stone.radius, stone.distance,
                                               stone.x, stone.z, stone.slope, stone.direction)
        self.stone_contacts[stone.lane] = contact
        opacity = min(1.,max(0.,(ROLL_LIMIT-abs(stone.x))/.48))
        self.shadow(room, stone, contact, opacity)
        frame = self.dust['frames'][int(room.time*12+stone.lane) % len(self.dust['frames'])]
        image = self.images['dust']
        rx,ry,rw,rh = frame['rect_top_left']
        x,z = contact[0]-stone.direction*.45, contact[2]+.03
        y = room.floor_height(x,z)
        c,s = self.view_axes
        points = [(x+c*offset,y+height,z-s*offset)
                  for offset,height in ((-.4,.42),(.4,.42),(.4,0.),(-.4,0.))]
        vertices = [(px,py,pz,u,v,185,169,138,round(145*opacity)) for (px,py,pz),(u,v) in zip(points, (
            (rx/image.w,ry/image.h), ((rx+rw)/image.w,ry/image.h),
            ((rx+rw)/image.w,(ry+rh)/image.h), (rx/image.w,(ry+rh)/image.h)))]
        self.last_triangles += self.rock.submit(room, image.texture, vertices, ((0,1,2), (0,2,3)))
        fade = max(.60, math.exp(-.014*depth))
        vertices = []
        for (x,y,z,u,v,nx,ny,nz),exposed in zip(world,self.fracture_faces[level]):
            diffuse = max(0., nx*self.light[0]+ny*self.light[1]+nz*self.light[2])
            fill = max(0., .8*nx+.36*ny+.44*nz)
            shade = min(1., .26+.63*diffuse+.13*fill+.095*exposed)*fade
            shade *= .76+.24*min(1., max(0., (y-stone.slope*x)/.5))
            vertices.append((x,y,z,u,v,round(246*shade),round((233+7*exposed)*shade),round((207+17*exposed)*shade),round(255*opacity)))
        if opacity < 1.:
            self.p.SDL_SetTextureBlendMode(self.rock.texture,self.p.SDL_BLENDMODE_BLEND)
        self.last_triangles += self.rock.submit(room, self.rock.texture, vertices, indices, cull=True)
        if opacity < 1.:
            self.p.SDL_SetTextureBlendMode(self.rock.texture,self.p.SDL_BLENDMODE_NONE)
        self.visible_stones.append(stone.lane)

    def draw_scene(self, room):
        started = time.perf_counter()
        p = self.p
        target = p.SDL_GetRenderTarget(p.renderer)
        p.SDL_SetRenderTarget(p.renderer, self.canvas)
        self.last_triangles = 0
        self.visible_stones = []
        self.stone_contacts = {}
        p.SDL_SetRenderDrawColor(p.renderer, 7, 10, 11, 255)
        p.SDL_RenderClear(p.renderer)
        c,s = self.view_axes = view_axes(room.yaw)
        self.end_wall(room)
        entrance_z = -3.
        self.quads(room, 'wall', [
            ([(-HALF_WIDTH,4.8,entrance_z),(HALF_WIDTH,4.8,entrance_z),
              (HALF_WIDTH,0.,entrance_z),(-HALF_WIDTH,0.,entrance_z)], (137,128,110))])
        stones = {stone.lane: stone for stone in room.stones}
        rows = [(-2,entrance_z,0.),(-1,0.,LANE_START)]
        rows.extend((i,LANE_START+i*LANE_DEPTH,LANE_START+(i+1)*LANE_DEPTH) for i in range(LANE_COUNT))
        rows.append((LANE_COUNT,LANE_START+LANE_COUNT*LANE_DEPTH,LENGTH))
        # The parallel row boundaries partition all geometry, including each rock.
        # Along any sight ray a farther slab precedes a nearer slab, at every yaw.
        rows.sort(key=lambda row: max(row[1]-room.z,room.z-row[2],0.), reverse=True)
        tangent = self.w/(2*self.focal)
        for index,start,end in rows:
            extent = HALF_WIDTH+3.5
            mid = (start+end)/2-room.z
            depth = c*mid-s*room.x
            reach = abs(s)*extent+abs(c)*(end-start)/2
            right = -s*mid-c*room.x
            side_reach = abs(c)*extent+abs(s)*(end-start)/2
            if depth+reach <= .075 or abs(right)-side_reach > tangent*(depth+reach):
                continue
            self.row(room,index,start,end)
            stone = stones.get(index)
            if stone is not None:
                dx,dz = stone.x-room.x,stone.z-room.z
                depth,right = s*dx+c*dz,c*dx-s*dz
                radius = self.rock.max_radius
                if depth+radius > .075 and abs(right) <= tangent*depth+radius*math.hypot(1,tangent):
                    self.stone(room,stone)
                    if abs(stone.x) > HALF_WIDTH:
                        shade = max(.53, math.exp(-.016*abs(stone.z-room.z)))
                        self.quads(room,'wall',self.side_wall(index,start,end,1 if stone.x>0 else -1,shade))
            # Finish the nearer edge before drawing the adjoining foreground row.
            if room.z < start and 0 <= index <= LANE_COUNT:
                self.seam(room,start,index-1 if index else None,index if index<LANE_COUNT else None)
            elif room.z >= end and -1 <= index < LANE_COUNT:
                self.seam(room,end,index if index>=0 else None,index+1 if index+1<LANE_COUNT else None)
        p.SDL_SetRenderTarget(p.renderer, target)
        p.SDL_RenderCopy(p.renderer, self.canvas, None, None)
        self.last_draw_ms = (time.perf_counter()-started)*1000

    def close(self):
        self.rock.close()
        self.p.SDL_DestroyTexture(self.canvas)
        self.images.clear()
