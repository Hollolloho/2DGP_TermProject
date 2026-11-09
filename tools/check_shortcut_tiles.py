"""Check native wall texture preservation, opacity and cache reuse with SDL2."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import ctypes
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PROJECT=ROOT
sys.path.append(str(PROJECT))
from game_view import View,p
OUT=ROOT/'output/shortcut_character';OUT.mkdir(parents=True,exist_ok=True)
p.open_canvas(1280,800)
if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
v=View(PROJECT)
def read(texture):
    p.SDL_SetRenderTarget(p.renderer,texture)
    data=(ctypes.c_ubyte*(32*32*4))()
    assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,32*4)==0
    return bytes(data)
cases=debris_cases=0
try:
    for frame in range(4):
        for facing in ('south','east','north','west'):
            design=v.shortcut_design(frame,facing)
            parts={(a[0]//32,a[1]//32) for a in design}
            mask=10 if facing in ('south','north') else 5
            for variant in range(4):
                base=v.target(32,32)
                p.SDL_SetRenderTarget(p.renderer,base);p.SDL_RenderSetClipRect(p.renderer,None)
                v.image('terrain_v2',(0,0,32,32),(mask*32,variant*32,32,32))
                original=read(base)
                for part in parts:
                    debris=all(a[2].startswith('debris-') for a in design if (a[0]//32,a[1]//32)==part)
                    tile_mask=15 if debris else mask
                    composed=v.shortcut_tile(tile_mask,variant,frame,facing,part,design,debris)
                    assert v.shortcut_tile(tile_mask,variant,frame,facing,part,design,debris) is composed
                    pixels=read(composed.texture)
                    allowed={(x%32,y%32) for x,y,*_ in design if (x//32,y//32)==part}
                    for y in range(32):
                        for x in range(32):
                            offset=(y*32+x)*4
                            if not debris:assert pixels[offset+3]==255
                            if (x,y) not in allowed:
                                if debris:assert pixels[offset:offset+4]==bytes(4)
                                else:assert pixels[offset:offset+4]==original[offset:offset+4]
                    cases+=1
                    debris_cases+=int(debris)
                p.SDL_SetRenderTarget(p.renderer,None);p.SDL_DestroyTexture(base)
    # A contact atlas of actual composed wall tiles, not a separately drawn illustration.
    sheet=v.target(256,128)
    p.SDL_SetRenderTarget(p.renderer,sheet);p.SDL_RenderSetClipRect(p.renderer,None)
    for frame in range(4):
        design=v.shortcut_design(frame,'south')
        for variant in range(4):
            for offset,part in enumerate(((1,1),(2,1))):
                tile=v.shortcut_tile(10,(variant+offset*3)%4,frame,'south',part,design)
                p.SDL_SetRenderTarget(p.renderer,sheet)
                p.SDL_SetTextureColorMod(tile.texture,255,255,255)
                p.SDL_RenderCopy(p.renderer,tile.texture,None,p.SDL_Rect(frame*64+offset*32,variant*32,32,32))
    p.SDL_SetRenderTarget(p.renderer,sheet)
    buf=(ctypes.c_ubyte*(256*128*4))()
    p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,buf,256*4)
    surf=p.SDL_CreateRGBSurfaceWithFormatFrom(buf,256,128,32,256*4,p.SDL_PIXELFORMAT_RGBA32)
    assert p.IMG_SavePNG(surf,str(OUT/'09-wall-tiles-native.png').encode())==0
    p.SDL_FreeSurface(surf);p.SDL_SetRenderTarget(p.renderer,None);p.SDL_DestroyTexture(sheet)
    result={'native_tile_size':32,'checked_tiles':cases,'debris_tiles':debris_cases,
            'preserved_original_pixels_outside_edit':True,'wall_tiles_opaque':True,
            'debris_surroundings_transparent':True,'cache_reused':True,'separately_drawn_generated_rim':False}
    (OUT/'wall_tile_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS',json.dumps(result))
finally:
    composed=tile=None
    p.SDL_SetRenderTarget(p.renderer,None);v.close();p.close_canvas()
