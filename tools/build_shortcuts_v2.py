"""Extract local door edits; never include a replacement wall collar."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import ctypes
import json
import math
from pathlib import Path
import pico2d.pico2d as p
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'sprite/topdown/shortcuts_v2'

def target(w,h):
 t=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,w,h)
 assert t;p.SDL_SetRenderTarget(p.renderer,t)
 p.SDL_SetRenderDrawColor(p.renderer,0,0,0,0);p.SDL_RenderClear(p.renderer)
 return t

def save(t,w,h,path):
 p.SDL_SetRenderTarget(p.renderer,t);buf=(ctypes.c_ubyte*(w*h*4))()
 assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,buf,w*4)==0
 surf=p.SDL_CreateRGBSurfaceWithFormatFrom(buf,w,h,32,w*4,p.SDL_PIXELFORMAT_RGBA32)
 try:assert p.IMG_SavePNG(surf,str(path).encode())==0
 finally:p.SDL_FreeSurface(surf)

def main():
 p.open_canvas(32,32)
 if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
 images=[];normalized=[];patches=[]
 for kind in ('puzzle','trap'):
  im=p.load_image(str(OUT/'sources'/f'{kind}_edit.png'));images.append(im)
  p.SDL_SetTextureScaleMode(im.texture,p.SDL_ScaleModeLinear)
  p.SDL_SetTextureBlendMode(im.texture,p.SDL_BLENDMODE_NONE)
  small=target(160,192);p.SDL_RenderCopy(p.renderer,im.texture,None,None);normalized.append(small)
  for state in range(2):
   # The edit put the threshold at the original cap/face join. Align it to the wall foot.
   patch=target(96,32)
   p.SDL_SetTextureScaleMode(small,p.SDL_ScaleModeLinear)
   p.SDL_SetTextureBlendMode(small,p.SDL_BLENDMODE_NONE)
   p.SDL_RenderCopy(p.renderer,small,p.SDL_Rect(32,state*96+32,96,22),None)
   patches.append(patch)
 sheet=target(384,96)
 for i,patch in enumerate(patches):
  p.SDL_SetTextureBlendMode(patch,p.SDL_BLENDMODE_NONE)
  p.SDL_SetTextureScaleMode(patch,p.SDL_ScaleModeNearest)
  for y in range(2,32):
   if i<2:
    half=math.sqrt(max(0,14**2-(y-15)**2)) if y<15 else 14
    left,right=math.ceil(48-half),math.floor(48+half)
   else:
    half=10+(y//3)%3 if y<10 else 12+(0,1,-1,0)[y%4]
    left,right=48-half,48+half
   # One-pixel alpha edges; everything outside the compact edit stays transparent.
   for x,width,alpha in ((left,1,100),(left+1,right-left-1,255),(right,1,100)):
    if width>0:
     p.SDL_SetTextureAlphaMod(patch,alpha)
     p.SDL_RenderCopy(p.renderer,patch,p.SDL_Rect(x,y,width,1),p.SDL_Rect(i*96+x,32+y,width,1))
  if i<2:
   p.SDL_SetTextureAlphaMod(patch,255)
   p.SDL_RenderCopy(p.renderer,patch,p.SDL_Rect(66,15,8,10),p.SDL_Rect(i*96+66,47,8,10))
 save(sheet,384,96,OUT/'shortcuts.png')
 contact=target(1152,360)
 p.SDL_SetRenderDrawColor(p.renderer,15,21,23,255);p.SDL_RenderClear(p.renderer)
 p.canvas_width,p.canvas_height=1152,360
 p.SDL_SetTextureScaleMode(sheet,p.SDL_ScaleModeNearest)
 p.SDL_SetTextureBlendMode(sheet,p.SDL_BLENDMODE_BLEND)
 font=p.load_font('C:/Windows/Fonts/malgun.ttf',19)
 for i,label in enumerate(('퍼즐 · 닫힘','퍼즐 · 개방','함정 · 입구','함정 · 도착')):
  p.SDL_RenderCopy(p.renderer,sheet,p.SDL_Rect(i*96,0,96,96),p.SDL_Rect(i*288,32,288,288))
  font.draw(i*288+20,330,label,(217,208,186))
 font.draw(18,20,'문과 틈 부분만 포함 · 주변 벽은 기존 타일 그대로', (169,176,168))
 save(contact,1152,360,OUT/'overlay_preview.png')
 frames=[{'kind':'puzzle' if i<2 else 'trap','state':('closed','open','entry','arrival')[i],
          'rect_top_left':[i*96,0,96,96],'pico2d_clip':[i*96,0,96,96],
          'pivot':[48,48]} for i in range(4)]
 (OUT/'catalog.json').write_text(json.dumps({'version':2,'sheet':'shortcuts.png','size':[384,96],
    'frame_size':[96,96],'native_wall_tile':32,'frames':frames,
    'method':'Existing wall tile strip edited with imagegen; local opening-only alpha masks packed with SDL2.',
    'placement':'Three-by-three tile canvas. Only compact wall band has alpha. Runtime clips to existing solid visible tiles.',
    'states':'Four states, 90-degree 2D rotations for wall direction; no replacement wall collar.'},indent=2),encoding='utf-8')
 p.SDL_SetRenderTarget(p.renderer,None)
 for t in [sheet,contact,*normalized,*patches]:p.SDL_DestroyTexture(t)
 images.clear();del font;p.close_canvas()
 print('Packed four compact wall edits; outside aperture/button is transparent.')

if __name__=='__main__':main()
