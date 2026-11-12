"""Headless SDL input and rendering checks."""
import json
import pico2d.pico2d as p
from maze_model import DIRECTIONS, TRAP_LENGTH, Game
from game_view import LW, LH, SCALE
from trap_view import project as project_trap


def inject_key(key, down=True):
    event=p.SDL_Event()
    event.type=p.SDL_KEYDOWN if down else p.SDL_KEYUP
    event.key.keysym.sym=key
    event.key.repeat=0
    assert p.SDL_PushEvent(event)==1


def run(app):
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
        app.view.capture(app.output/name)

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
    app.view.capture(app.output/'01b-quarter-moved.png')

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
    (app.output/'render_checks.json').write_text(json.dumps({'native_renderer':'pico2d + SDL2',
        'window_size':[LW*SCALE,LH*SCALE],'logical_quarter_view':[LW,LH],
        'sdl_F_torch':True,'sdl_V_overview':True,'sdl_M_map':True,
        'sdl_WASD_move':True,'sdl_WASD_diagonal_walk_run':True,
        'sdl_opposite_keys_cancel':True,'sdl_arrows_inactive':True,'sdl_corridor_collision_facing':True,
        'sdl_trap_WASD':True,
        'sdl_F_trap':True,'sdl_W_fixed_first_person':True,
        'sdl_Esc_exact_return':True,'sdl_W_shortcut_arrival':True},indent=2),encoding='utf-8')
