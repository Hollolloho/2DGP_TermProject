"""Pack generated material crops into connected tiles using native SDL2."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import ctypes
import json
from pathlib import Path
import pico2d.pico2d as p

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'sprite/topdown/terrain_v2'
SIZE=32

def target(w,h):
    t=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,w,h)
    assert t
    assert p.SDL_SetRenderTarget(p.renderer,t)==0
    p.SDL_SetRenderDrawColor(p.renderer,0,0,0,0)
    p.SDL_RenderClear(p.renderer)
    return t

def rect(x,y,w,h,color):
    p.SDL_SetRenderDrawBlendMode(p.renderer,p.SDL_BLENDMODE_BLEND)
    p.SDL_SetRenderDrawColor(p.renderer,*color)
    p.SDL_RenderFillRect(p.renderer,p.SDL_Rect(x,y,w,h))

def save(t,w,h,name):
    p.SDL_SetRenderTarget(p.renderer,t)
    data=(ctypes.c_ubyte*(w*h*4))()
    assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,w*4)==0
    surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,w,h,32,w*4,p.SDL_PIXELFORMAT_RGBA32)
    try: assert p.IMG_SavePNG(surface,str(OUT/name).encode())==0
    finally: p.SDL_FreeSurface(surface)

def main():
    p.open_canvas(32,32)
    if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    source=p.load_image(str(OUT/'material_source.png'))
    p.SDL_SetTextureScaleMode(source.texture,p.SDL_ScaleModeLinear)
    p.SDL_SetTextureBlendMode(source.texture,p.SDL_BLENDMODE_NONE)
    q=source.w//2
    assert source.w==source.h and source.w%2==0
    span=q//2
    def material(quadrant,variant,dst,tint):
        # Reuse full quadrant crops; finite variants deliberately aren't claimed seamless.
        sx=(quadrant%2)*q+(variant%2)*span
        sy=(quadrant//2)*q+((variant//2)%2)*span
        p.SDL_SetTextureColorMod(source.texture,*tint)
        assert p.SDL_RenderCopy(p.renderer,source.texture,p.SDL_Rect(sx,sy,span,span),p.SDL_Rect(*dst))==0
    sheet=target(512,160)
    for variant in range(4):
        for mask in range(16):
            x,y=mask*32,variant*32
            cap_h=32 if mask&4 else 22
            material(0,variant,(x,y,32,cap_h),(186,196,199))
            if not mask&1:
                rect(x,y,32,1,(181,180,162,180))
                rect(x,y+1,32,1,(146,148,135,85))
            if not mask&8:
                rect(x,y,1,cap_h,(164,167,151,170))
                rect(x+1,y+1,1,cap_h-1,(127,133,119,70))
            if not mask&2:
                rect(x+30,y,2,cap_h,(16,22,24,100))
                rect(x+31,y,1,cap_h,(14,20,22,150))
            if not mask&4:
                material(1,variant,(x,y+22,32,10),(151,155,153))
                rect(x,y+21,32,1,(164,158,138,170))
                rect(x,y+22,32,1,(19,22,22,140))
                rect(x,y+30,32,1,(12,17,19,95))
                rect(x,y+31,32,1,(10,15,17,170))
                if not mask&2:rect(x+31,y+22,1,10,(9,14,16,170))
    for variant in range(8):
        x=variant*32
        material(2+variant//4,variant%4,(x,128,32,32),(137,144,145))
    save(sheet,512,160,'terrain.png')
    # Readable contact sheet, actual atlas sampling, no illustration substitute.
    contact=target(1024,384)
    rect(0,0,1024,384,(15,20,22,255))
    p.SDL_SetTextureScaleMode(sheet,p.SDL_ScaleModeNearest)
    for row in range(4):
        p.SDL_RenderCopy(p.renderer,sheet,p.SDL_Rect(0,row*32,512,32),p.SDL_Rect(0,row*64,1024,64))
    p.SDL_RenderCopy(p.renderer,sheet,p.SDL_Rect(0,128,256,32),p.SDL_Rect(0,288,768,96))
    save(contact,1024,384,'tiles_contact.png')
    catalog={'version':2,'tile_size':32,'sheet':'terrain.png','sheet_size':[512,160],
        'wall':{'variants':4,'masks':16,'connected_bits':{'N':1,'E':2,'S':4,'W':8},
                'rect_top_left':'[mask*32, variant*32, 32, 32]','south_face_height':10},
        'floor':{'variants':8,'rect_top_left':'[variant*32, 128, 32, 32]'},
        'source':'material_source.png','source_size':[source.w,source.h],
        'style':'weathered limestone, warm grey neutral stone, lower-contrast flagstone floor',
        'packing':'native SDL texture resampling, directional bevels and face shading',
        'notes':'Finite material crops; not claimed mathematically seamless. Props/actors remain original separate assets.'}
    catalog['frames']=[{'kind':'wall','variant':v,'mask':m,'rect_top_left':[m*32,v*32,32,32],
                        'pico2d_clip':[m*32,160-v*32-32,32,32]} for v in range(4) for m in range(16)]
    catalog['frames'] += [{'kind':'floor','variant':v,'rect_top_left':[v*32,128,32,32],
                           'pico2d_clip':[v*32,0,32,32]} for v in range(8)]
    (OUT/'catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    p.SDL_SetRenderTarget(p.renderer,None)
    p.SDL_DestroyTexture(contact);p.SDL_DestroyTexture(sheet)
    del source
    p.close_canvas()
    print('Packed 64 connected wall tiles + 8 floor tiles; native SDL2.')

if __name__=='__main__':main()
