"""Horizontal camera controls and world-space SDL triangle projection."""
import ctypes
import math


def turned_yaw(yaw, relative_x):
    return math.remainder(yaw + relative_x * math.radians(.15), math.tau)


def view_axes(yaw):
    return math.cos(yaw), math.sin(yaw)


def rotate_movement(right, forward, yaw):
    cosine, sine = view_axes(yaw)
    return right*cosine + forward*sine, forward*cosine - right*sine


def walk_velocity(right, forward, yaw, previous_yaw, vx, vz, speed, acceleration, dt):
    """Resolve view-relative input in metres, preserving sub-unit analog input."""
    magnitude = math.hypot(right, forward)
    scale = speed / max(1., magnitude)
    target_x, target_z = rotate_movement(right*scale, forward*scale, yaw)
    if magnitude and yaw != previous_yaw:
        # Carry held movement around with the camera on this very tick.
        vx, vz = rotate_movement(vx, vz, yaw-previous_yaw)
    dx, dz = target_x-vx, target_z-vz
    change = math.hypot(dx, dz)
    if change <= acceleration*dt:
        return target_x, target_z
    fraction = acceleration*dt/change
    return vx+dx*fraction, vz+dz*fraction


class MouseLook:
    def __init__(self, sdl):
        self.sdl = sdl
        self.restore = None
        self.skip_delta = False

    def capture(self, active):
        p = self.sdl
        if active and self.restore is None:
            self.restore = p.SDL_GetRelativeMouseMode(), p.SDL_ShowCursor(p.SDL_QUERY)
            if p.SDL_SetRelativeMouseMode(p.SDL_TRUE) == 0:
                p.SDL_ShowCursor(p.SDL_DISABLE)
            self.skip_delta = True
        elif not active and self.restore is not None:
            relative, cursor = self.restore
            p.SDL_SetRelativeMouseMode(relative)
            p.SDL_ShowCursor(cursor)
            self.restore = None

    def delta(self, motion):
        if self.restore is None or self.skip_delta:
            self.skip_delta = False
            return 0
        return motion.xrel


def submit_mesh(v,g,texture,vertices,indices,cull=False):
    """Batch triangles; clip near-plane crossings before projection."""
    p=v.p
    camera_x,camera_z,eye,cx,horizon=v.camera(g)
    cosine,sine=v.view_axes
    clip_view = getattr(v, 'clip_to_view', False)
    planes = [lambda a: a[2]-.075]
    if clip_view:
        # SDL software raster cost can follow the enormous bounding box of
        # a near-plane triangle, even when only a few pixels are on screen.
        planes += [lambda a: cx*a[2]+v.focal*a[0],
                   lambda a: (v.w-cx)*a[2]-v.focal*a[0],
                   lambda a: horizon*a[2]-v.focal*a[1],
                   lambda a: (v.h-horizon)*a[2]+v.focal*a[1]]
    camera=[];screen=[];packed=[];codes=[]
    for x,y,z,u,t,r,green,b,alpha in vertices:
        dx,dz=x-camera_x,z-camera_z
        x,y,z=cosine*dx-sine*dz,y-eye,sine*dx+cosine*dz
        camera.append((x,y,z,u,t,r,green,b,alpha))
        if z>=.075:
            px,py=cx+x*v.focal/z,horizon-y*v.focal/z
            code = 0
            if clip_view:
                code = (2 if px < 0 else 4 if px > v.w else 0) | (8 if py < 0 else 16 if py > v.h else 0)
            codes.append(code)
            screen.append((px,py));packed.append(v.vertex.pack(px,py,r,green,b,alpha,u,t))
        else:screen.append(None);packed.append(None);codes.append(1)
    output=[];count=0
    for triangle in indices:
        i,j,k=triangle
        if codes[i] & codes[j] & codes[k]:
            continue
        mask = codes[i] | codes[j] | codes[k]
        if not mask:
            a,b,c=screen[i],screen[j],screen[k]
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if (clip_view and abs(area)<1e-6) or (cull and area<=0):continue
            output.extend(packed[i] for i in triangle);count+=1
            continue
        clipped=[camera[i] for i in triangle]
        for bit, plane in enumerate(planes):
            if not clipped or not (mask & (1 << bit) or mask & 1):
                continue
            poly, clipped = clipped, []
            for a,b in zip(poly,poly[1:]+poly[:1]):
                da, db = plane(a), plane(b)
                if da >= 0:
                    clipped.append(a)
                if (da >= 0) != (db >= 0):
                    t=da/(da-db)
                    clipped.append(tuple(a[i]+(b[i]-a[i])*t for i in range(9)))
        if clip_view and v.software and texture and len(clipped) >= 4:
            # The SDL software rectangle fast path discards rotated UVs when
            # clipping yields a screen-aligned quad. Retain triangle sampling.
            point = clipped[0]
            clipped[0] = (*point[:5], round(point[5]) ^ 1, *point[6:])
        for i in range(1,len(clipped)-1):
            tri=[clipped[0],clipped[i],clipped[i+1]]
            projected=[(cx+a[0]*v.focal/a[2],horizon-a[1]*v.focal/a[2]) for a in tri]
            a,b,c=projected
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if (clip_view and abs(area)<1e-6) or (cull and area<=0):continue
            for (x,y),point in zip(projected,tri):
                output.append(v.vertex.pack(x,y,*(round(max(0,min(255,value))) for value in point[5:]),point[3],point[4]))
            count+=1
    if output:
        raw=b''.join(output);buffer=ctypes.create_string_buffer(raw)
        ptr=ctypes.cast(buffer,ctypes.POINTER(p.SDL_Vertex))
        p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
        assert p.SDL_RenderGeometry(p.renderer,texture,ptr,len(output),None,0)==0,p.SDL_GetError()
    return count
