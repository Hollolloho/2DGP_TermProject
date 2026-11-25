"""검수 코스를 스폰부터 중앙 로프까지 SDL 키·마우스 이벤트로 완주한다."""
import os
import ctypes
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from SourceCode.maze_model import distances, shortest_path
from SourceCode.world_path_room import TRAVERSE_CELLS, LOOSE_POSITIONS
from SourceCode.puzzle_layout import room_screen, connection_center
from SourceCode.mouse_maze import START_CELL, cell_center
from .runed_path_fixtures import ROUTES, placement
from .check_waypoint_maze import SOLUTION_CORNERS


def check_layout(g):
    original = [[row[:] for row in grid] for grid in g.maze_layouts.grids]
    points = [g.spawn, g.torch_cell, g.fountain, g.guard_home, g.exit, g.trap_cell, g.trap_exit,
              g.boulder_entry, g.boulder_exit, *g.puzzle_gate, g.path_entry, g.path_exit,
              g.choice_start, g.choice_goal, *(r.gate for r in g.route_options)]
    assert len(points) == len(set(points))
    assert len(g.route_options) == 2 and all(original[a] != original[b] for a,b in ((0,1),(1,2),(0,2)))
    for base in original:
        for mouse_open in (False, True):
            for choice in (None, 0, 1):
                grid = [row[:] for row in base]
                wall, near, far = g.puzzle_gate
                if mouse_open:
                    grid[wall[1]][wall[0]] = 0
                if choice is not None:
                    x, y = g.route_options[choice].gate
                    grid[y][x] = 0
                assert g.maze_layouts.is_valid(grid)
                goal = distances(grid, g.exit)
                assert (distances(grid, near)[far] == 2) == mouse_open
                for entry, end, minimum in ((g.trap_cell, g.trap_exit, 15),
                                            (g.boulder_entry, g.boulder_exit, 26),
                                            (g.path_entry, g.path_exit, TRAVERSE_CELLS+1)):
                    assert g.can_stand(entry[0]+.5, entry[1]+.5, grid)
                    assert g.can_stand(end[0]+.5, end[1]+.5, grid)
                    assert goal[entry] > goal[end] >= 8 and distances(grid, entry)[end] >= minimum
                for i, route in enumerate(g.route_options):
                    x, y = route.gate
                    assert (grid[y][x] == 0) == (i == choice)
                    if i == choice:
                        assert route.gate in shortest_path(grid, g.choice_start, g.choice_goal)
                        assert len(route.path)-1 == distances(grid, g.choice_start)[g.choice_goal]
                        exposure = g.route_exposure(route.path, grid)
                        assert bool(exposure) == (i == 0), (i, exposure)
    assert g.maze_layouts.grids == original



def check_arch(app, p, torch):
    from .check_boulder_render import keys, press
    g, view = app.game, app.view

    def walk(key, count):
        keys(app, (key,))
        for _ in range(count):
            app.update(1/60)
            view.draw(g, 60)
        keys(app)

    def coverage(skip_foreground=False):
        mount = view.shortcut_mount(g, g.trap_cell)
        sx, sy = view.world(*mount[:2])
        rect = p.SDL_Rect(round(sx)-64, round(sy)-96, 128, 128)
        original_door, original_wall = view.shortcut, view.shifting_wall
        frames = []

        def pixels():
            data = (ctypes.c_ubyte*(128*128*4))()
            assert p.SDL_RenderReadPixels(p.renderer, rect, p.SDL_PIXELFORMAT_RGBA32, data, 128*4) == 0
            return bytes(data)

        for tone in (0, 255):
            drawn = []
            def door(x, y, facing, arrival, tint):
                if (x, y, facing) == (sx, sy, mount[2]):
                    original_door(x, y, facing, arrival, (tone,)*3)
                    drawn.append(pixels())
                else:
                    original_door(x, y, facing, arrival, tint)

            def wall(x, y, frame, tint, brightness, cell, game):
                if not skip_foreground or sum(cell) <= sum(g.trap_cell):
                    original_wall(x, y, frame, tint, brightness, cell, game)

            with (patch.object(view, 'shortcut', door), patch.object(view, 'shifting_wall', wall),
                  patch.object(view, 'badge'), patch.object(view, 'player'),
                  patch.object(view, 'player_silhouette')):
                p.SDL_SetRenderTarget(p.renderer, view.logical)
                view.quarter(g)
                assert len(drawn) == 1
                frames.append((drawn[0], pixels()))
        p.SDL_SetRenderTarget(p.renderer, None)

        def changed(a, b):
            return sum(a[i:i+3] != b[i:i+3] for i in range(0, len(a), 4))
        return tuple(changed(a, b) for a, b in zip(*frames))

    if torch:
        press(app, p.SDLK_f)
    walk(p.SDLK_s, 18)
    edge = coverage()
    assert edge[0] > 2000 and edge[0] == edge[1], ('first approach', edge)
    # Walk past A and come back so the surrounding walls are remembered.
    walk(p.SDLK_s, 198)
    walk(p.SDLK_w, 142)
    for _ in range(18):
        app.update(1/60)
        view.draw(g, 60)
    assert g.trap_cell in g.visible and (9, 0) in g.observed-g.visible
    remembered = coverage()
    assert remembered[0] == remembered[1], ('remembered wall cut the arch', remembered)
    walk(p.SDLK_s, 46)
    rear = coverage(skip_foreground=True)
    foreground = coverage()
    assert (9, 0) in g.visible and rear[0] == rear[1], ('backing wall cut the arch', rear)
    assert 0 < foreground[1] < foreground[0], ('foreground occlusion lost', foreground)
    print(f'arch pixels (torch {torch}): approach {edge}, remembered {remembered}, backing {rear}, foreground {foreground}')
    press(app, p.SDLK_r)

def play(app, p, fps, option):
    from SourceCode.game_view import PUZZLE_OFFSET_X, CHOICE_CARD_RECTS, CHOICE_CONFIRM_RECT
    from .check_game_render import inject_mouse
    from .check_boulder_render import keys, press

    g = app.game
    dt = 1/fps
    mapping = {(-1,0):p.SDLK_w, (1,0):p.SDLK_s, (0,-1):p.SDLK_d, (0,1):p.SDLK_a}
    measuring = False
    guard_events = set()

    def tick(seconds):
        before = g.guard_x, g.guard_y
        app.update(seconds)
        if measuring:
            if g.guard_seen_until > g.time:
                guard_events.add('seen')
            if before != (g.guard_x, g.guard_y):
                guard_events.add('chase')
            if g.guard_attack_at is not None:
                guard_events.add('windup')


    def cell():
        return int(g.player.x), int(g.player.y)

    def advance(seconds):
        count = max(1, ceil(seconds/dt))
        for _ in range(count):
            tick(seconds/count)

    def until(condition, seconds):
        for _ in range(ceil(seconds/dt)+1):
            if condition():
                return
            tick(dt)
            assert g.state != 'failed', (g.banner, g.time, cell())
        raise AssertionError((g.state, g.time, cell(), g.banner))

    def walk_point(x, y):
        state = g.state
        for _ in range(6*fps):
            dx, dy = x-g.player.x, y-g.player.y
            if g.state != state or max(abs(dx), abs(dy)) < 1e-6:
                break
            axis = dx if abs(dx)>1e-6 else dy
            sign = 1 if axis>0 else -1
            direction = (sign,0) if abs(dx)>1e-6 else (0,sign)
            keys(app, (mapping[direction],))
            tick(min(dt, abs(axis)/2.5))
        else:
            raise AssertionError(('blocked', (x,y), cell(), g.banner))
        keys(app)

    def walk(target):
        assert g.state == 'explore'
        path = shortest_path(g.grid, cell(), target)
        if target != g.exit:
            assert g.exit not in path
        for x,y in path[1:]:
            walk_point(x+.5, y+.5)
        assert cell() == target
        return len(path)-1

    def mouse(kind, point):
        inject_mouse(kind, point)
        app.handle_events()

    def interact(state):
        press(app, p.SDLK_f)
        assert g.state == state, (g.state, state, g.banner, cell())
        app.render(dt)

    def click(rect):
        x,y,w,h = rect
        point = (x+w//2,y+h//2)
        mouse(p.SDL_MOUSEBUTTONDOWN, point)
        mouse(p.SDL_MOUSEBUTTONUP, point)

    def wait_gate(gate):
        assert g.solid(*gate)
        old_phase = g.phase
        until(lambda: g.phase != old_phase and g.state == 'explore', 64)
        assert not g.solid(*gate)

    assert g.test_course and cell() == g.spawn and not g.trap_completed and not g.puzzle_open
    press(app, p.SDLK_f)
    assert g.player.torch
    segments = [walk(g.trap_cell)]
    interact('trap')
    keys(app, (p.SDLK_w,))
    until(lambda: g.state == 'explore', 10)
    assert g.trap_completed and cell() == g.trap_exit
    blade_hp = g.player.hp
    segments.append(walk(g.boulder_entry))
    interact('trap')
    advance(.5)
    keys(app, (p.SDLK_w,))
    until(lambda: g.state == 'explore', 12)
    assert g.boulder_completed and cell() == g.boulder_exit

    wall, near, far = g.puzzle_gate
    segments.append(walk(near))
    interact('puzzle')
    assert g.puzzle_tab == 'maze'
    for i, node in enumerate((START_CELL, *SOLUTION_CORNERS)):
        x,y = cell_center(*node)
        point = (x+PUZZLE_OFFSET_X,y)
        mouse(p.SDL_MOUSEMOTION if i else p.SDL_MOUSEBUTTONDOWN, point)
        advance(.12)
    mouse(p.SDL_MOUSEBUTTONUP, point)
    assert g.puzzle_reserved_phase == g.next_phase and g.state == 'explore'
    wait_gate(wall)
    segments.append(walk(wall)+walk(far))
    segments.append(walk(g.path_entry))
    interact('path_room')
    until(lambda: g.world_path.stage == 'active', 2)
    route = ROUTES[0]
    for index, target, ports in placement(route):
        mouse(p.SDL_MOUSEBUTTONDOWN, room_screen(*LOOSE_POSITIONS[index]))
        assert g.connection.held == index
        for _ in range(4):
            if g.connection.pieces[index].ports == frozenset(ports):
                break
            press(app, p.SDLK_r)
        mouse(p.SDL_MOUSEMOTION, connection_center(target))
        advance(.15)
        mouse(p.SDL_MOUSEBUTTONUP, connection_center(target))
    assert g.connection.completed and not g.path_completed
    walk_point(-.5,1.5)
    for x,y in route:
        walk_point(x+.5,y+.5)
    walk_point(4.5,2.5)
    walk_point(5.6,2.5)
    assert g.state == 'explore' and g.path_completed and cell() == g.path_exit

    segments.append(walk(g.choice_start))
    interact('puzzle')
    assert g.puzzle_tab == 'choice'
    click(CHOICE_CARD_RECTS[option])
    click(CHOICE_CONFIRM_RECT)
    advance(dt)
    assert g.shortcut_choice.selected == option and g.shortcut_choice.reserved_phase == g.next_phase
    gate = g.route_options[option].gate
    wait_gate(gate)
    assert g.solid(*g.route_options[1-option].gate)
    route_hp = g.player.hp
    measuring = True
    segments.append(walk(gate)+walk(g.choice_goal))
    measuring = False
    damage = route_hp-g.player.hp
    if option == 0:
        assert guard_events == {'seen', 'chase', 'windup'} and damage >= 15, (guard_events, damage)
    else:
        assert not guard_events and damage == 0, (guard_events, damage)
    segments.append(walk(g.exit))
    interact('clear')
    assert app.game is g and g.layout_revision == 2 and g.player.hp > 0
    assert segments == [5,3,3,2,3,3,(16,20)[option],9], segments
    print(f'{fps} Hz / route {option+1}: {segments}, {g.time:.1f}s, route damage {damage}, guard {sorted(guard_events)}, final HP {g.player.hp}')


def main():
    os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pico2d.pico2d as p
    from SourceCode.play_mode import PlayMode
    from SourceCode.window_input import disable_text_input
    from .check_boulder_render import press
    p.open_canvas(1280, 800, sync=False)
    with TemporaryDirectory(prefix='maze-course-') as output:
        app = None
        try:
            if not p.renderer:
                p.renderer = p.SDL_CreateRenderer(p.window,-1,p.SDL_RENDERER_SOFTWARE)
            disable_text_input(p)
            args = SimpleNamespace(seed=117, test_course=True, smoke=True, overview=False, trap_preview=False)
            app = PlayMode(Path(__file__).resolve().parents[1], args, output=Path(output))
            check_layout(app.game)
            check_arch(app, p, False)
            check_arch(app, p, True)
            for i, (fps, option) in enumerate((fps, option) for fps in (30,60,120) for option in (0,1)):
                if i:
                    press(app, p.SDLK_r)
                play(app, p, fps, option)
        finally:
            if app:
                app.finish()
            p.close_canvas()


if __name__ == '__main__':
    main()
