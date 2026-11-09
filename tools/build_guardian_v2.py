"""Native SDL packing of four generated directional idle poses."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import ctypes
import json
from pathlib import Path
import pico2d.pico2d as p
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'sprite/topdown/guardian_v2'
p.open_canvas(32,32)
if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
source=p.load_image(str(OUT/'source.png'))
assert source.w==source.h and source.w%2==0
q=source.w//2
sheet=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,256,64)
assert sheet
p.SDL_SetRenderTarget(p.renderer,sheet)
p.SDL_SetRenderDrawColor(p.renderer,0,0,0,0);p.SDL_RenderClear(p.renderer)
p.SDL_SetTextureBlendMode(source.texture,p.SDL_BLENDMODE_NONE)
p.SDL_SetTextureScaleMode(source.texture,p.SDL_ScaleModeLinear)
for i in range(4):
    assert p.SDL_RenderCopy(p.renderer,source.texture,p.SDL_Rect((i%2)*q,(i//2)*q,q,q),p.SDL_Rect(i*64,0,64,64))==0
data=(ctypes.c_ubyte*(256*64*4))()
assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,256*4)==0
surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,256,64,32,256*4,p.SDL_PIXELFORMAT_RGBA32)
assert p.IMG_SavePNG(surface,str(OUT/'guardian.png').encode())==0
p.SDL_FreeSurface(surface);p.SDL_SetRenderTarget(p.renderer,None);p.SDL_DestroyTexture(sheet)
del source
p.close_canvas()
(OUT/'catalog.json').write_text(json.dumps({'version':2,'sheet':'guardian.png','size':[256,64],
    'frame_size':[64,64],'directions':['down','left','right','up'],'frames_per_direction':1,
    'pivot_top_left':[32,56],'poses':'directional idle only; not a walking or attack animation',
    'source':'source.png','method':'OpenAI generated source, native SDL2 crop/resample',
    'frames':[{'direction':d,'rect_top_left':[i*64,0,64,64],'pico2d_clip':[i*64,0,64,64]}
              for i,d in enumerate(['down','left','right','up'])]},indent=2),encoding='utf-8')
print('Packed four 64px guardian idle directions, RGBA.')
