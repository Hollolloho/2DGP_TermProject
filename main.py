"""Run the first hybrid-view maze prototype: python main.py."""
import argparse
import json
import os
from pathlib import Path
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed', type=int, default=117)
parser.add_argument('--smoke', action='store_true', help='Export native frames and exercise SDL input headlessly')
parser.add_argument('--overview', action='store_true', help='Start in full-view asset inspection mode; V restores normal vision')
parser.add_argument('--trap-preview',action='store_true',help='Start in the trap room to review movement immediately')
args = parser.parse_args()
if args.smoke and args.trap_preview:
    parser.error('--smoke and --trap-preview are separate review modes')
if args.smoke:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pico2d.pico2d as p
from maze_model import Game
from game_view import View, LW, LH, SCALE
from game_audio import Audio

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'output/topdown'


class App:
    def __init__(self):
        self.game = Game(args.seed)
        self.game.reveal_all = args.overview
        if args.trap_preview:
            self.game.player.x,self.game.player.y=self.game.trap_cell[0]+.5,self.game.trap_cell[1]+.5
            self.game.player.torch=True
            self.game.interact()
        self.held = set()
        self.running = True
        self.view = View(ROOT)
        self.audio = Audio(ROOT)

    def handle_events(self):
        for event in p.get_events():
            if event.type == p.SDL_QUIT:
                self.running = False
            elif event.type == p.SDL_KEYUP:
                self.held.discard(event.key)
            elif event.type == p.SDL_KEYDOWN:
                self.held.add(event.key)
                if event.key == p.SDLK_ESCAPE:
                    if self.game.map_open:
                        self.game.map_open = False
                    elif self.game.state == 'trap':
                        self.game.return_from_trap()
                    else:
                        self.running = False
                elif event.key == p.SDLK_f:
                    self.game.interact()
                    self.held.clear()
                elif event.key == p.SDLK_m and self.game.state == 'explore':
                    self.game.map_open = not self.game.map_open
                    self.held.clear()
                elif event.key == p.SDLK_v and self.game.state == 'explore':
                    self.game.reveal_all = not self.game.reveal_all
                elif event.key == p.SDLK_r:
                    self.game = Game(args.seed, self.game.run_number+1)
                    self.held.clear()
                elif event.key == p.SDLK_F10:
                    self.view.capture(OUTPUT/'manual.png')
                    self.game.message('output/topdown/manual.png 저장')
            elif event.type == p.SDL_MOUSEBUTTONDOWN and event.button == p.SDL_BUTTON_LEFT:
                self.game.attack()

    def update(self, dt):
        dx = int(bool(self.held & {p.SDLK_d,p.SDLK_RIGHT}))-int(bool(self.held & {p.SDLK_a,p.SDLK_LEFT}))
        dy = int(bool(self.held & {p.SDLK_s,p.SDLK_DOWN}))-int(bool(self.held & {p.SDLK_w,p.SDLK_UP}))
        previous=self.game.state
        self.game.update(dt,dx,dy,bool(self.held & {p.SDLK_LSHIFT,p.SDLK_RSHIFT}))
        if previous!=self.game.state:
            self.held.clear()
        if not args.smoke:
            self.audio.update(self.game)

    def save_status(self):
        OUTPUT.mkdir(parents=True,exist_ok=True)
        g=self.game
        (OUTPUT/'session.json').write_text(json.dumps({'mode':g.state,'player':[round(g.player.x,3),round(g.player.y,3)],
            'spawn':g.spawn,'trap':g.trap_cell,'phase':g.phase,'run':g.run_number,'torch':g.player.torch,
            'map_open':g.map_open,'full_view':g.reveal_all,'visited':len(g.visited),
            'player_fsm':g.player.state,'time':round(g.time,2)},indent=2),encoding='utf-8')


def inject_key(key, down=True):
    event=p.SDL_Event()
    event.type=p.SDL_KEYDOWN if down else p.SDL_KEYUP
    event.key.keysym.sym=key
    event.key.repeat=0
    assert p.SDL_PushEvent(event)==1


def smoke(app):
    g=app.game
    def snapshot(name):
        # Draw once to start a mode transition, then capture after its fade.
        app.view.draw(g)
        for _ in range(16): app.update(.025)
        app.view.draw(g)
        app.view.capture(OUTPUT/name)

    for _ in range(20):
        app.update(.025)
    snapshot('01-directional-view.png')
    # F is routed through the same SDL event handler as the visible app.
    inject_key(p.SDLK_f)
    app.handle_events()
    assert g.player.torch
    for _ in range(12): app.update(.025)
    inject_key(p.SDLK_v)
    app.handle_events()
    assert g.reveal_all
    snapshot('02-topdown-overview.png')
    inject_key(p.SDLK_m)
    app.handle_events()
    app.update(.025)
    assert g.map_open
    snapshot('03-visited-map.png')
    inject_key(p.SDLK_m)
    app.handle_events()
    # Arrange entry proximity in this automated test; no teleport key is shipped.
    g.player.x,g.player.y=g.trap_cell[0]+.5,g.trap_cell[1]+.5
    before=g.player.x,g.player.y
    inject_key(p.SDLK_f)
    app.handle_events()
    assert g.state=='trap'
    for _ in range(20): app.update(.025)
    snapshot('04-first-person-trap.png')
    inject_key(p.SDLK_ESCAPE)
    app.handle_events()
    assert g.state=='explore' and (g.player.x,g.player.y)==before
    app.save_status()
    (OUTPUT/'render_checks.json').write_text(json.dumps({'native_renderer':'pico2d + SDL2',
        'window_size':[LW*SCALE,LH*SCALE],'logical_topdown':[LW,LH],
        'sdl_F_torch':True,'sdl_V_overview':True,'sdl_M_map':True,
        'sdl_F_trap':True,'sdl_Esc_exact_return':True},indent=2),encoding='utf-8')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    p.open_canvas(LW*SCALE,LH*SCALE,sync=not args.smoke)
    if not p.renderer:
        p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    assert p.renderer
    p.print_fps=lambda: None
    p.SDL_SetWindowTitle(p.window,'Maze · Top-down / First-person trap · pico2d'.encode())
    if not args.smoke:
        # The launcher hides only the Python host; show the SDL game window explicitly.
        p.SDL_HideWindow(p.window)
        p.SDL_ShowWindow(p.window)
        p.SDL_RaiseWindow(p.window)
    app=None
    try:
        app=App()
        if args.smoke:
            smoke(app)
            return
        previous=time.perf_counter()
        next_status=0
        while app.running:
            now=time.perf_counter()
            dt=min(.05,now-previous)
            previous=now
            app.handle_events()
            if not p.SDL_GetWindowFlags(p.window)&p.SDL_WINDOW_INPUT_FOCUS:
                app.held.clear()
            app.update(dt)
            app.view.draw(app.game,1/max(.001,dt))
            p.SDL_RenderPresent(p.renderer)
            if now>=next_status:
                app.save_status()
                next_status=now+1
            p.delay(.002)
    finally:
        if app:
            app.audio.close()
            app.view.close()
        p.close_canvas()


if __name__=='__main__':
    main()
