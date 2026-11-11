"""Current boulder visual checks; --native uses and measures the GPU renderer.

The scenes are scripted fixtures, not recorded human playthroughs.
"""
import argparse,ctypes,json,math,os,statistics,sys,time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    project=next(parent for parent in (root,*root.parents) if (parent/'boulder_practice.py').exists())
    os.environ.setdefault('MAZE_PROJECT',str(project));sys.path.insert(0,str(project))
    if not args.native:os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    import pico2d.pico2d as p
    import boulder_practice as current
    from boulder_volume import stone_mesh
    out=current.OUTPUT/'visuals';out.mkdir(parents=True,exist_ok=True)
    w,h=1440,900
    p.open_canvas(w,h,sync=False)
    if not p.renderer:p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    p.SDL_HideWindow(p.window)
    new=current.View(p,w,h)
    g=current.Practice();g.release();g.time=9;g.z=12;g.ball_z=5;g.ball_speed=3.7;g.ball_distance=8;g.look_back=True
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
        new.draw(g);new.capture(out/'current.png')
        for frame in range(48):
            t=frame/30
            g.time=9+t;g.z=12+2.55*t;g.ball_z=5+3.7*t;g.ball_distance=8+3.7*t
            g.x=math.sin(t*2)*.8;g.look_back=True
            begin=time.perf_counter();new.draw(g);p.SDL_RenderPresent(p.renderer)
            durations.append((time.perf_counter()-begin)*1000)
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
                'room_assets_ready':new.room_ready,'native_scene_size':[w,h],
                'scripted_frames':48,
                'render_submit_ms_median':statistics.median(durations),
                'render_submit_ms_p95':sorted(durations)[int(len(durations)*.95)],
                'measurement':'CPU frame draw plus present; not an end-to-end FPS guarantee'}
        (out/('checks-native.json' if args.native else 'checks.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        new.close()
        p.SDL_SetRenderTarget(p.renderer,None);p.close_canvas()

if __name__=='__main__':main()
