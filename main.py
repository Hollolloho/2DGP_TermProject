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
from maze_model import DIRECTIONS, TRAP_LENGTH, Game
from game_view import View, LW, LH, SCALE
from game_audio import Audio
from trap_view import project as project_trap

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
        dx = int(p.SDLK_d in self.held)-int(p.SDLK_a in self.held)
        dy = int(p.SDLK_s in self.held)-int(p.SDLK_w in self.held)
        previous = self.game.state
        if previous == 'explore':
            # Invert the quarter-view axes before normalizing movement on the grid.
            dx, dy = dx+dy, dy-dx
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
    from math import hypot, isclose

    g=app.game
    player = g.player
    step = .025
    w, a, s, d = p.SDLK_w, p.SDLK_a, p.SDLK_s, p.SDLK_d
    diagonals = ((s, a), (w, a), (s, d), (w, d))  # DIRECTIONS order
    diagonal_facings = ('sw', 'nw', 'se', 'ne')

    def press(*keys, ticks=0):
        for key in keys:
            inject_key(key)
        app.handle_events()
        for _ in range(ticks):
            app.update(step)
        for key in keys:
            inject_key(key, down=False)
        app.handle_events()

    def check_controls():
        room = Game(g.seed)
        room.grid = [[0] * len(row) for row in room.grid]
        actor = room.player
        actor.x, actor.y = 15.5, 11.5
        app.game = room
        view = app.view
        view.position_camera(room)
        clips = view.player_catalog['clips']

        def check_move(keys, sx, sy, direction, running=False):
            grid_x, grid_y = actor.x, actor.y
            start_x, start_y = view.world(grid_x, grid_y)
            press(*keys, ticks=1)
            screen_x, screen_y = view.world(actor.x, actor.y)
            for delta, sign in ((screen_x-start_x, sx), (screen_y-start_y, sy)):
                if sign:
                    assert delta*sign > 0
                else:
                    assert isclose(delta, 0, abs_tol=1e-9)
            distance = hypot(actor.x-grid_x, actor.y-grid_y)
            assert isclose(distance, (4.1 if running else 2.5)*step)
            assert actor.direction == direction
            assert actor.state == ('sprint' if running else 'walk')
            clip = clips[('run-' if running else 'walk-')+diagonal_facings[direction]]
            assert view.player_frame(room) in [frame['rect'] for frame in clip['frames']]

        try:
            for keys, (sx, sy, facing) in zip(diagonals,
                    ((-1, 1, 0), (-1, -1, 1), (1, 1, 2), (1, -1, 3))):
                check_move(keys, sx, sy, facing)
                check_move((*keys, p.SDLK_LSHIFT), sx, sy, facing, running=True)
            for key, sx, sy, facing in ((w, 0, -1, 3), (a, -1, 0, 1),
                                         (s, 0, 1, 0), (d, 1, 0, 2)):
                actor.direction = facing
                check_move((key,), sx, sy, facing)
                check_move((key,), sx, sy, facing)

            # Releasing one key of an up-right chord retains the compatible facing.
            check_move((w, d), 1, -1, 3)
            check_move((d,), 1, 0, 3)
            check_move((w, s, d), 1, 0, 3)
            start = actor.x, actor.y, actor.direction
            for keys in ((w, s), (a, d), (p.SDLK_UP,), (p.SDLK_LEFT,),
                         (p.SDLK_DOWN,), (p.SDLK_RIGHT,)):
                press(*keys, ticks=4)
                assert (actor.x, actor.y, actor.direction) == start

            # Down slides along a one-cell corridor when its grid X component hits a wall.
            room.grid = [[int(x != 15) for x in range(len(row))] for row in room.grid]
            actor.x, actor.y = 15.76, 11.5
            actor.direction = 2
            press(s, ticks=1)
            assert actor.x == 15.76 and actor.y > 11.5 and actor.direction == 0
            start_y = actor.y
            press(s, ticks=8)
            assert actor.x == 15.76 and actor.y > start_y and actor.direction == 0
            assert room.can_stand(actor.x, actor.y)
            start = actor.x, actor.y, actor.direction
            press(s, d, ticks=4)
            assert (actor.x, actor.y, actor.direction) == start
        finally:
            app.game = g
            app.held.clear()

    def snapshot(name):
        # Draw once to start a mode transition, then capture after its fade.
        app.view.draw(g)
        for _ in range(16): app.update(.025)
        app.view.draw(g)
        app.view.capture(OUTPUT/name)

    if g.reveal_all:
        press(p.SDLK_v)
    for _ in range(20):
        app.update(.025)
    snapshot('01-directional-view.png')
    check_controls()
    app.view.draw(g)
    press(p.SDLK_f)
    assert player.torch

    forward = player.direction
    start_screen = app.view.world(player.x, player.y)
    press(*diagonals[forward], ticks=16)
    assert all(isclose(position, cell+.5) for position, cell in zip((player.x, player.y), g.torch_cell))
    assert player.state == 'walk'
    app.view.draw(g)
    assert app.view.world(player.x, player.y) != start_screen
    app.view.capture(OUTPUT/'01b-quarter-moved.png')

    press(p.SDLK_v)
    assert g.reveal_all
    snapshot('02-quarter-overview.png')
    press(p.SDLK_m)
    assert g.map_open
    snapshot('03-visited-map.png')
    press(p.SDLK_m)
    press(p.SDLK_v)
    assert not g.map_open and not g.reveal_all

    # Follow the real corridor from the torch to A using regular movement input.
    for (x, y), (nx, ny) in zip(g.path[1:5], g.path[2:6]):
        press(*diagonals[DIRECTIONS.index((nx-x, ny-y))], ticks=16)
    before = player.x, player.y
    assert all(isclose(position, cell+.5) for position, cell in zip(before, g.trap_cell))
    press(p.SDLK_f)
    assert g.state=='trap'
    fixed_center = project_trap(g, 0, 0, TRAP_LENGTH)
    press(w, ticks=20)
    closer = project_trap(g, 0, 0, TRAP_LENGTH)
    assert g.trap_progress > 0 and (player.x, player.y) == before
    assert closer[0] == fixed_center[0] and closer[1] > fixed_center[1]
    snapshot('04-first-person-trap.png')
    press(a, ticks=4)
    left_x = g.trap_x
    assert left_x < 0
    press(d, ticks=12)
    assert g.trap_x > left_x
    forward_progress = g.trap_progress
    press(s, ticks=12)
    assert g.trap_progress < forward_progress
    press(p.SDLK_ESCAPE)
    assert g.state=='explore' and (player.x, player.y) == before
    snapshot('05-quarter-return-a.png')

    press(p.SDLK_f)
    assert g.state == 'trap'
    app.view.draw(g)
    press(w, ticks=300)
    assert g.state == 'explore' and g.trap_completed and g.trap_exit in g.visited
    assert (player.x, player.y) == (g.trap_exit[0]+.5, g.trap_exit[1]+.5)
    snapshot('06-quarter-return-b.png')
    app.save_status()
    (OUTPUT/'render_checks.json').write_text(json.dumps({'native_renderer':'pico2d + SDL2',
        'window_size':[LW*SCALE,LH*SCALE],'logical_quarter_view':[LW,LH],
        'sdl_F_torch':True,'sdl_V_overview':True,'sdl_M_map':True,
        'sdl_WASD_move':True,'sdl_WASD_diagonal_walk_run':True,
        'sdl_opposite_keys_cancel':True,'sdl_arrows_inactive':True,'sdl_corridor_collision_facing':True,
        'sdl_trap_WASD':True,
        'sdl_F_trap':True,'sdl_W_fixed_first_person':True,
        'sdl_Esc_exact_return':True,'sdl_W_shortcut_arrival':True},indent=2),encoding='utf-8')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    p.open_canvas(LW*SCALE,LH*SCALE,sync=not args.smoke)
    if not p.renderer:
        p.renderer=p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
    assert p.renderer
    p.print_fps=lambda: None
    p.SDL_SetWindowTitle(p.window,'Maze · Quarter-view / First-person trap · pico2d'.encode())
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
