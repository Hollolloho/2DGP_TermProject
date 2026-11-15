"""One continuously rotating stone, projected with pico2d/SDL 2D triangles.

No 3D engine, ray casting or gameplay rules. Geometry/UVs stay attached to the
stone; camera translation and forward/rear views project the same world surface.
"""
import ctypes
import math


def normalize(x,y,z):
    length=math.sqrt(x*x+y*y+z*z) or 1
    return x/length,y/length,z/length


def stone_mesh(radius,rings=36,segments=80):
    vertices=[];indices=[]
    for row in range(rings+1):
        lat=(row/rings-.5)*math.pi
        for col in range(segments+1):
            angle=col/segments*math.tau
            x,y,z=math.sin(lat),math.cos(lat)*math.cos(angle),math.cos(lat)*math.sin(angle)
            # Broad rounded facets and small stable chips, rather than a perfect
            # billiard sphere or per-frame/random silhouette wobble.
            broad=(abs(x)**2.18+abs(y)**2.18+abs(z)**2.18)**(-1/2.18)
            rough=1+.024*math.sin(3*x+1.2)*math.sin(4*y-.4)*math.sin(3*z+2)+.007*math.cos(9*x-5*y+6*z)
            r=radius*broad*rough
            vertices.append([x*r,y*r,z*r,col/segments,row/rings,0.,0.,0.])
    stride=segments+1
    for row in range(rings):
        for col in range(segments):
            a=row*stride+col;b=a+stride
            for triangle in ((a,b,b+1),(a,b+1,a+1)):
                va,vb,vc=(vertices[i] for i in triangle)
                ab=[vb[i]-va[i] for i in range(3)];ac=[vc[i]-va[i] for i in range(3)]
                normal=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
                if sum(n*n for n in normal)<1e-16:continue
                if sum(normal[i]*va[i] for i in range(3))<0:
                    triangle=(triangle[0],triangle[2],triangle[1]);normal=tuple(-n for n in normal)
                indices.append(triangle)
                for index in triangle:
                    for axis in range(3):vertices[index][5+axis]+=normal[axis]
    # The UV wrap duplicates a position. Merge its normals for seamless light.
    for row in range(rings+1):
        a,b=vertices[row*stride],vertices[row*stride+segments]
        normal=normalize(*(a[5+i]+b[5+i] for i in range(3)))
        a[5:]=b[5:]=normal
    for row in (0,rings):
        points=vertices[row*stride:(row+1)*stride]
        normal=normalize(*(sum(vertex[5+i] for vertex in points) for i in range(3)))
        for vertex in points:vertex[5:]=normal
    for vertex in vertices:vertex[5:]=normalize(*vertex[5:])
    return vertices,indices


def rolled_pose(vertices,radius,distance,centre_z):
    a=distance/radius;c,s=math.cos(a),math.sin(a)
    rotated=[(x,c*y-s*z,s*y+c*z,u,v,nx,c*ny-s*nz,s*ny+c*nz)
             for x,y,z,u,v,nx,ny,nz in vertices]
    lowest=min(rotated,key=lambda vertex:vertex[1])
    centre_y=-lowest[1]
    world=[(x,y+centre_y,z+centre_z,u,v,nx,ny,nz) for x,y,z,u,v,nx,ny,nz in rotated]
    return world,centre_y,(lowest[0],0,lowest[2]+centre_z)


class Boulder:
    def __init__(self,view,material,radius):
        self.view=view;self.p=view.p;self.radius=radius
        self.vertices,self.indices=stone_mesh(radius)
        self.max_radius=max(math.sqrt(x*x+y*y+z*z) for x,y,z,*_ in self.vertices)
        p=self.p
        # Mirrored wrapping makes the source edge continuous without editing the
        # generated original or letting a long UV triangle cross a texture seam.
        old_target=p.SDL_GetRenderTarget(p.renderer)
        self.texture=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,material.w*2,material.h)
        assert self.texture,p.SDL_GetError()
        p.SDL_SetTextureScaleMode(self.texture,p.SDL_ScaleModeLinear)
        p.SDL_SetTextureBlendMode(self.texture,p.SDL_BLENDMODE_BLEND)
        p.SDL_SetRenderTarget(p.renderer,self.texture)
        p.SDL_SetRenderDrawColor(p.renderer,0,0,0,0);p.SDL_RenderClear(p.renderer)
        p.SDL_RenderCopy(p.renderer,material.texture,None,p.SDL_Rect(0,0,material.w,material.h))
        p.SDL_RenderCopyEx(p.renderer,material.texture,None,p.SDL_Rect(material.w,0,material.w,material.h),0,None,p.SDL_FLIP_HORIZONTAL)
        p.SDL_SetRenderTarget(p.renderer,old_target)
        self.cache_key=None;self.world=[];self.centre_y=radius
        self.contact=(0,0,0);self.last_triangles=0

    def pose(self,g):
        key=g.ball_distance,g.ball_z
        if self.cache_key==key:return self.world
        self.world,self.centre_y,self.contact=rolled_pose(self.vertices,self.radius,g.ball_distance,g.ball_z)
        self.cache_key=key
        return self.world

    def submit(self,g,texture,vertices,indices,cull=False):
        """Batch triangles; clip near-plane crossings before projection."""
        v=self.view;p=self.p
        _,_,eye,cx,horizon=v.camera(g);direction=-1 if g.look_back else 1
        camera=[];screen=[];packed=[]
        for x,y,z,u,t,r,green,b,alpha in vertices:
            x,y,z=direction*(x-g.x),y-eye,direction*(z-g.z)
            camera.append((x,y,z,u,t,r,green,b,alpha))
            if z>=.075:
                px,py=cx+x*v.focal/z,horizon-y*v.focal/z
                screen.append((px,py));packed.append(v.vertex.pack(px,py,r,green,b,alpha,u,t))
            else:screen.append(None);packed.append(None)
        output=[];count=0
        for triangle in indices:
            points=[screen[i] for i in triangle]
            if all(point is not None for point in points):
                a,b,c=points
                if cull and (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<=0:continue
                output.extend(packed[i] for i in triangle);count+=1
                continue
            poly=[camera[i] for i in triangle];clipped=[]
            for a,b in zip(poly,poly[1:]+poly[:1]):
                inside_a,inside_b=a[2]>=.075,b[2]>=.075
                if inside_a:clipped.append(a)
                if inside_a!=inside_b:
                    t=(.075-a[2])/(b[2]-a[2]);clipped.append(tuple(a[i]+(b[i]-a[i])*t for i in range(9)))
            for i in range(1,len(clipped)-1):
                tri=[clipped[0],clipped[i],clipped[i+1]]
                projected=[(cx+a[0]*v.focal/a[2],horizon-a[1]*v.focal/a[2]) for a in tri]
                a,b,c=projected
                if cull and (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<=0:continue
                for (x,y),point in zip(projected,tri):
                    output.append(v.vertex.pack(x,y,*(round(max(0,min(255,value))) for value in point[5:]),point[3],point[4]))
                count+=1
        if output:
            raw=b''.join(output);buffer=ctypes.create_string_buffer(raw)
            ptr=ctypes.cast(buffer,ctypes.POINTER(p.SDL_Vertex))
            p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
            assert p.SDL_RenderGeometry(p.renderer,texture,ptr,len(output),None,0)==0,p.SDL_GetError()
        return count

    def shadow(self,g):
        self.pose(g)
        x,_,z=self.contact
        vertices=[(x,.008,z,0,0,4,5,5,155)];indices=[]
        # Continuous penumbra plus a small, dense contact patch.
        levels=((.13,132),(.44,92),(.84,35),(1.20,0))
        segments=48
        for radius,alpha in levels:
            for i in range(segments):
                a=i/segments*math.tau
                vertices.append((x+math.cos(a)*self.radius*radius,.008,z+math.sin(a)*self.radius*radius*.77,0,0,4,5,5,alpha))
        for i in range(segments):indices.append((0,1+i,1+(i+1)%segments))
        for ring in range(len(levels)-1):
            a,b=1+ring*segments,1+(ring+1)*segments
            for i in range(segments):
                j=(i+1)%segments
                indices.extend(((a+i,b+i,b+j),(a+i,b+j,a+j)))
        self.submit(g,None,vertices,indices)

    def body(self,g):
        world=self.pose(g)
        # Light is attached to the viewer's overhead lamp, not baked into the
        # rotating image. Facet normals rotate with the rock under that light.
        light=normalize(g.x-.65,3.5-self.centre_y,g.z-g.ball_z)
        fade=math.exp(-.035*abs(g.z-g.ball_z))
        vertices=[]
        for x,y,z,u,t,nx,ny,nz in world:
            diffuse=max(0,nx*light[0]+ny*light[1]+nz*light[2])
            shade=(.29+.65*diffuse+.08*max(0,ny))*fade
            # Ground-side ambient occlusion adds weight without black bands.
            shade*=.72+.28*min(1,max(0,y/.5))
            vertices.append((x,y,z,u,t,round(248*shade),round(246*shade),round(235*shade),255))
        self.last_triangles=self.submit(g,self.texture,vertices,self.indices,cull=True)

    def dust(self,g,front):
        if g.state!='chasing' or g.ball_speed<.1:return
        v=self.view;direction=-1 if g.look_back else 1
        latest=int(g.ball_distance/.38)
        for i in range(12):
            event=latest-i
            if event<0:continue
            delta=g.ball_distance-event*.38
            age=delta/max(1,g.ball_speed)
            if age>1.1:continue
            z=g.ball_z-delta-.10
            if (direction*(z-g.ball_z)<=0)!=front:continue
            side=-1 if event%2 else 1
            x=side*(self.radius*.74+age*.24)+math.sin(event*2.3)*.06
            dust=v.catalog['dust']['frames'][min(11,max(1,int(age/1.1*12)))]
            width=.35+age*.65
            v.billboard(g,'dust',dust['rect_top_left'],[256,230],[width,width*.5],x,z,(188,179,157))
            if age<.55 and event%2==0:
                y=max(.018,.02+age*1.2-age*age*3)
                size=.018
                v.quad(g,None,[(x-size,y+size,z),(x+size,y,z),(x,y-size,z)],[(0,0)]*3,(127,117,96))

    def inside_overlay(self,g):
        _,_,eye,_,_=self.view.camera(g)
        distance=math.sqrt(g.x*g.x+(eye-self.centre_y)**2+(g.z-g.ball_z)**2)
        if distance<self.radius:
            opacity=round(210*max(0,1-distance/self.radius))
            self.view.rect(0,72,self.view.w,self.view.h-172,(26,22,18,opacity))

    def close(self):self.p.SDL_DestroyTexture(self.texture)
