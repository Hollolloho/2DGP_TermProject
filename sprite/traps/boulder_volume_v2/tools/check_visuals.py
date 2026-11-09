"""Native before/after visual checks; --native uses and measures the GPU renderer.

The comparison is a scripted fixture, not a recorded human playthrough.
"""
import argparse,ctypes,importlib.util,json,math,os,statistics,sys,time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',action='store_true')
    parser.add_argument('--gif',action='store_true',help='Also encode the comparison GIF; requires Pillow')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    project=next(parent for parent in (root,*root.parents) if (parent/'boulder_practice.py').exists())
    os.environ.setdefault('MAZE_PROJECT',str(project));sys.path.insert(0,str(project))
    if not args.native:os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    import pico2d.pico2d as p
    import boulder_practice as current
    from boulder_volume import stone_mesh
    out=current.OUTPUT/'visuals';out.mkdir(parents=True,exist_ok=True)
    before_path=Path(os.environ.get('BOULDER_BEFORE',root/'before_practice.py'))
    spec=importlib.util.spec_from_file_location('before_practice',before_path)
    before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
    # Rendering-only task: all movement, resource, collision and exit code remains identical.
    def rules(path):return path.read_text(encoding='utf-8').split('class Practice:',1)[1].split('class View:',1)[0]
    assert rules(before_path)==rules(Path(current.__file__))
    w,h=1440,900
    p.open_canvas(w,h,sync=False)
    if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    p.SDL_HideWindow(p.window)
    old=before.View(p,w,h);new=current.View(p,w,h)
    g=current.Practice();g.release();g.time=9;g.z=12;g.ball_z=5;g.ball_speed=3.7;g.ball_distance=8;g.look_back=True
    font=p.load_font('C:/Windows/Fonts/malgun.ttf',25)
    def target(width,height):
        tex=p.SDL_CreateTexture(p.renderer,p.SDL_PIXELFORMAT_RGBA8888,p.SDL_TEXTUREACCESS_TARGET,width,height)
        assert tex;p.SDL_SetTextureScaleMode(tex,p.SDL_ScaleModeLinear);return tex
    board=target(1920,660);animation=target(1152,360)
    def read(tex,width,height,path=None):
        p.SDL_SetRenderTarget(p.renderer,tex);data=(ctypes.c_ubyte*(width*height*4))()
        assert p.SDL_RenderReadPixels(p.renderer,None,p.SDL_PIXELFORMAT_RGBA32,data,width*4)==0
        if path:
            surface=p.SDL_CreateRGBSurfaceWithFormatFrom(data,width,height,32,width*4,p.SDL_PIXELFORMAT_RGBA32)
            try:assert p.IMG_SavePNG(surface,str(path).encode())==0
            finally:p.SDL_FreeSurface(surface)
        return bytes(data)
    durations=[]
    try:
        ground_errors=[]
        for step in range(96):
            g.ball_distance=step/96*math.tau*current.RADIUS
            vertices=new.rock.pose(g)
            ground_errors.append(abs(min(vertex[1] for vertex in vertices)))
        assert max(ground_errors)<1e-12
        g.ball_distance=0;start=new.rock.pose(g)
        g.ball_distance=math.tau*current.RADIUS;end=new.rock.pose(g)
        assert max(abs(a-b) for va,vb in zip(start,end) for a,b in zip(va,vb))<1e-11
        g.ball_distance=2;start=new.rock.pose(g)
        g.ball_distance=2.005;end=new.rock.pose(g)
        assert 0<max(abs(a-b) for va,vb in zip(start,end) for a,b in zip(va[:3],vb[:3]))<.02
        for x in (-1.2,0,1.2):
            g.x=x;g.ball_distance=8
            new.draw(g);assert new.rock.last_triangles>100
            new.capture(out/f'new-side-{x:+.1f}.png')
        g.x=.9
        old.draw(g);old.capture(out/'before.png')
        new.draw(g);new.capture(out/'after.png')
        p.SDL_SetRenderTarget(p.renderer,board)
        p.SDL_SetRenderDrawColor(p.renderer,15,20,20,255);p.SDL_RenderClear(p.renderer)
        p.SDL_RenderCopy(p.renderer,old.canvas,None,p.SDL_Rect(0,60,960,600))
        p.SDL_RenderCopy(p.renderer,new.canvas,None,p.SDL_Rect(960,60,960,600))
        p.canvas_width,p.canvas_height=1920,660
        font.draw(24,620,'이전 · 회전 시트 / 평면 사물',(217,204,180))
        font.draw(984,620,'개선 · 연속 회전 / 시점에 따른 표면 / 접지 그림자',(217,204,180))
        read(board,1920,660,out/'comparison.png')
        raws=[]
        for frame in range(48):
            t=frame/30
            g.time=9+t;g.z=12+2.55*t;g.ball_z=5+3.7*t;g.ball_distance=8+3.7*t
            g.x=math.sin(t*2)*.8;g.look_back=True
            old.draw(g)
            begin=time.perf_counter();new.draw(g);p.SDL_RenderPresent(p.renderer)
            durations.append((time.perf_counter()-begin)*1000)
            p.SDL_SetRenderTarget(p.renderer,animation)
            p.SDL_RenderCopy(p.renderer,old.canvas,None,p.SDL_Rect(0,0,576,360))
            p.SDL_RenderCopy(p.renderer,new.canvas,None,p.SDL_Rect(576,0,576,360))
            if args.gif:raws.append(read(animation,1152,360))
        # Explicit near/crossing cases must clip without invalid geometry.
        for back in (False,True):
            g.look_back=back
            for delta in (-1.4,-.05,0,.05,1.4):
                g.ball_z=g.z+delta;new.draw(g)
        info=p.SDL_RendererInfo();p.SDL_GetRendererInfo(p.renderer,info)
        report={'passed':True,'renderer':info.name.decode(),'native_gpu_requested':args.native,
                'mesh_vertices':len(new.rock.vertices),'mesh_triangles':len(new.rock.indices),
                'fixed_floor_contact_max_error_metres':max(ground_errors),
                'continuous_rotation_5mm_step':True,'full_rotation_returns_same_surface':True,
                'side_views':[-1.2,0,1.2],'front_rear_near_plane_cases':10,
                'game_rules_identical':True,'native_scene_size':[w,h],
                'comparison_png_size':[1920,660],'scripted_comparison_frames':48,
                'render_submit_ms_median':statistics.median(durations),
                'render_submit_ms_p95':sorted(durations)[int(len(durations)*.95)],
                'measurement':'CPU frame draw plus present; not an end-to-end FPS guarantee'}
        (out/('checks-native.json' if args.native else 'checks.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        if args.gif:
            from PIL import Image
            images=[Image.frombytes('RGBA',(1152,360),raw).convert('RGB') for raw in raws]
            palette=images[0].quantize(colors=256)
            frames=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in images]
            frames[0].save(out/'comparison.gif',save_all=True,append_images=frames[1:],duration=[30,30,40]*16,loop=0,disposal=2,optimize=False)
        print(json.dumps(report,indent=2))
    finally:
        old.close();new.close();font=None
        p.SDL_SetRenderTarget(p.renderer,None);p.SDL_DestroyTexture(board);p.SDL_DestroyTexture(animation);p.close_canvas()

if __name__=='__main__':main()
