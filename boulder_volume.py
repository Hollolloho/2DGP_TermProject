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
