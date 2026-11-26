"""경로 선택의 임시 선택·확정·예약 경계. SDL 없이 실행한다."""
from SourceCode.shortcut_choice import ShortcutChoice
from SourceCode.shortcut_choice import CHOICE_START, CHOICE_GOAL
from SourceCode.maze_model import Game, distances, shortest_path, GUARD_NOTICE_RADIUS, PHASE_SECONDS
from SourceCode.mouse_maze import START_CELL,cell_center
from .checks_phase_changes import finish_shift
from .check_waypoint_maze import SOLUTION_CORNERS
import math


def check_reservation():
    for phase in range(3):
        target = (phase+1)%3
        for index in (0,1):
            choice = ShortcutChoice()
            assert not choice.confirm(target) and not choice.apply_phase(target)
            for invalid in (None,True,-1,2,'0'):
                assert not choice.select(invalid)
            assert choice.select(1-index) and choice.select(index)
            assert choice.cancel() and choice.preview is None
            assert choice.select(index)
            for invalid in (None,True,-1,3,'1'):
                assert not choice.confirm(invalid)
            assert choice.confirm(target)
            assert choice.selected == index and choice.reserved_phase == target and not choice.opened
            assert not choice.select(1-index) and not choice.cancel() and not choice.confirm(target)
            for _ in range(3):
                assert choice.route_for_phase(phase) is None
                assert choice.route_for_phase(target) == index
                assert not choice.opened, '지형 미리보기가 예약을 적용했다'
            assert not choice.apply_phase(phase) and not choice.opened
            assert choice.apply_phase(target) and choice.opened
            assert choice.reserved_phase is None and not choice.apply_phase(target)
            assert all(choice.route_for_phase(later) == index for later in range(3))
            choice.reset()
            assert choice.preview is choice.selected is choice.reserved_phase is None
            assert not choice.opened and all(choice.route_for_phase(later) is None for later in range(3))
    print('PASS: both choices across all 3 starting phases; preview/cancel, confirm lock, pure layout query, one-time next-phase opening, later-phase persistence and reset.')


def check_candidates():
    game = Game(117,0)
    assert len(game.route_options) == 2
    saved = tuple(tuple(tuple(row) for row in grid) for grid in game.maze_layouts.grids)
    for phase,base in enumerate(game.maze_layouts.grids):
        for p_open in (False,True):
            original = [row[:] for row in base]
            x,y = game.puzzle_gate[0];original[y][x] = int(not p_open)
            assert distances(original,CHOICE_START)[CHOICE_GOAL] == 16
            assert CHOICE_GOAL in distances(original,game.spawn) and game.exit in distances(original,game.spawn)
            for index,option in enumerate(game.route_options):
                grid = [row[:] for row in original]
                x,y = option.gate;assert grid[y][x] == 1;grid[y][x] = 0
                other = game.route_options[1-index].gate
                assert grid[other[1]][other[0]] == 1
                assert game.can_stand(x+.5,y+.5,grid) and not game.can_stand(other[0]+.5,other[1]+.5,grid)
                assert option.path[0] == CHOICE_START and option.path[-1] == CHOICE_GOAL
                assert all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a,b in zip(option.path,option.path[1:]))
                assert all(not grid[y][x] for x,y in option.path)
                assert distances(grid,CHOICE_START)[CHOICE_GOAL] == option.distance == (12,14)[index]
                assert distances(grid,CHOICE_GOAL)[game.exit] == 20 and game.maze_layouts.is_valid(grid)
                # 같은 게임의 LOS 판정으로 초기 수호자 시야에 드는 경로 중심을 재측정한다.
                game.grid = grid
                game.player.x,game.player.y = game.guard_home[0]+.5,game.guard_home[1]+.5
                exposed = tuple(cell for cell in option.path
                                if math.dist(cell,game.guard_home) <= GUARD_NOTICE_RADIUS and game.line_of_sight(*cell))
                assert exposed == option.exposed_cells and len(exposed) == (5,0)[index],(phase,p_open,index,exposed)
    assert saved == tuple(tuple(tuple(row) for row in grid) for grid in game.maze_layouts.grids)
    generated = []
    for seed in (0,2,5,9,12,16,18,117):
        for run in range(3):
            other = Game(seed,run)
            if not other.route_options:
                continue
            generated.append((seed,run))
            start,goal = other.choice_start,other.choice_goal
            protected = other.maze_layouts.protected_cells | set(other.puzzle_gate or ())
            assert start not in protected and goal not in protected
            for phase,base in enumerate(other.maze_layouts.grids):
                for p_open in (False,True):
                    grid = [row[:] for row in base]
                    if other.puzzle_gate:
                        x,y = other.puzzle_gate[0]
                        grid[y][x] = int(not p_open)
                    original = distances(grid,start)
                    assert other.exit in original and other.spawn in original
                    for index,route in enumerate(other.route_options):
                        x,y = route.gate
                        ox,oy = other.route_options[1-index].gate
                        assert route.gate not in protected and grid[y][x] == 1
                        grid[y][x] = 0
                        assert grid[oy][ox] == 1 and other.maze_layouts.is_valid(grid)
                        assert (route.path[0],route.path[-1]) == (start,goal)
                        assert route.gate in route.path and route.distance < original[goal]
                        assert distances(grid,start)[goal] == route.distance
                        assert distances(grid,goal)[other.exit] >= 8
                        assert all(other.can_stand(cx+.5,cy+.5,grid) for cx,cy in route.path)
                        assert all(math.dist(a,b)==1 for a,b in zip(route.path,route.path[1:]))
                        grid[y][x] = 1
    assert len(set(seed for seed,_ in generated)) >= 3 and {run for _,run in generated}=={0,1,2}
    print(f'PASS: generated independent route pairs on {len(generated)}/24 seed/runs; both gates checked in all six terrains.')
    print('PASS: seed 117/run 0, all 6 phase/P-gate layouts: ordinary 16, exposure route 12/5 centres, cover route 14/0; selected gate walkable, other gate closed, ordinary exit retained, 20 cells remain and source layouts unchanged.')


def opened(phase=0):
    game = Game(117,0)
    game.phase = game.layout_phase = phase
    game.grid = game.layout_for_phase(phase)
    game.observed,game.visited = game.observed_by_phase[phase],game.visited_by_phase[phase]
    game.player.x,game.player.y = CHOICE_START[0]+.5,CHOICE_START[1]+.5
    game.guard_hp = 0
    game.update_visibility();game.interact()
    assert game.state == 'puzzle' and game.puzzle_tab == 'choice'
    return game


def walk_cells(game, route):
    game.player.x,game.player.y = route[0][0]+.5,route[0][1]+.5
    for cell in route[1:]:
        for _ in range(100):
            dx,dy = cell[0]+.5-game.player.x,cell[1]+.5-game.player.y
            if max(abs(dx),abs(dy)) < 1e-6:break
            if abs(dx) > 1e-6:axis,distance = (1 if dx > 0 else -1,0),abs(dx)
            else:axis,distance = (0,1 if dy > 0 else -1),abs(dy)
            game.update(min(.02,distance/2.5),*axis)
            assert game.state == 'explore'
        else:raise AssertionError(('blocked walk',cell,game.player.x,game.player.y))
        assert game.can_stand(game.player.x,game.player.y)


def check_game_cycle():
    for phase in range(3):
        for index in (0,1):
            game = opened(phase)
            source = tuple(tuple(tuple(row) for row in grid) for grid in game.maze_layouts.grids)
            selected,other = game.route_options[index],game.route_options[1-index]
            assert not game._complete_puzzle() and game.puzzle_reserved_phase is None
            assert game.select_shortcut(index)
            game.close_puzzle();game.interact()
            assert game.shortcut_choice.preview == index and game.puzzle_tab == 'choice'
            assert game.request_shortcut_confirmation() and game.shortcut_choice.selected is None
            game.update(.02)
            assert game.state == 'explore' and game.shortcut_choice.selected == index
            assert not game.shortcut_available() and not game.select_shortcut(1-index)
            target = (phase+1)%3
            assert game.shortcut_choice.reserved_phase == target and not game.shortcut_choice.opened
            assert all(game.grid[o.gate[1]][o.gate[0]] for o in game.route_options)
            assert game.layout_for_phase(target)[selected.gate[1]][selected.gate[0]] == 0
            assert not game.shortcut_choice.opened
            # 실제 P 풀이로 같은 전환에 두 예약을 만들며 서로의 기록을 덮지 않는다.
            near = game.puzzle_gate[1]
            game.player.x,game.player.y = near[0]+.5,near[1]+.5
            game.update_visibility();game.interact()
            assert game.state == 'puzzle' and game.puzzle_tab == 'maze'
            game.puzzle.press(cell_center(*START_CELL))
            for cell in SOLUTION_CORNERS:game.drag_puzzle(cell_center(*cell))
            assert game.state == 'explore' and game.puzzle_reserved_phase == target
            assert game.shortcut_choice.selected == index and game.shortcut_choice.reserved_phase == target
            game.phase_time = PHASE_SECONDS-.01;game.update(.02)
            assert game.state == 'shifting' and not game.shortcut_choice.opened
            for _ in range(5):game.update(.05)
            assert not game.shift_applied and game.grid[selected.gate[1]][selected.gate[0]] == 1
            game.update(.05);game.update(.01)
            assert game.shift_applied and game.shortcut_choice.opened
            assert game.grid[selected.gate[1]][selected.gate[0]] == 0
            assert game.grid[other.gate[1]][other.gate[0]] == 1
            assert game.puzzle_open and game.grid[game.puzzle_gate[0][1]][game.puzzle_gate[0][0]] == 0
            finish_shift(game)
            walk_cells(game,selected.path);walk_cells(game,tuple(reversed(selected.path)))
            assert selected.gate in game.visited
            before = other.path[other.path.index(other.gate)-1]
            game.player.x,game.player.y = before[0]+.5,before[1]+.5
            dx,dy = other.gate[0]-before[0],other.gate[1]-before[1]
            game.move_straight(dx*20,dy*20)
            assert math.dist((game.player.x,game.player.y),(before[0]+.5,before[1]+.5)) <= .290001
            # 기존 일반 경로도 같은 충돌·이동 코드로 여전히 걸을 수 있다.
            walk_cells(game,shortest_path(game.maze_layouts.grids[game.phase],CHOICE_START,CHOICE_GOAL))
            for _ in range(3):
                game.phase_time = PHASE_SECONDS-.01;game.update(.02);finish_shift(game)
                assert game.shortcut_choice.opened and game.shortcut_choice.selected == index
                assert game.grid[selected.gate[1]][selected.gate[0]] == 0 and game.grid[other.gate[1]][other.gate[0]] == 1
            walk_cells(game,shortest_path(game.maze_layouts.grids[game.phase],game.spawn,game.exit))
            game.interact();assert game.state == 'clear'
            assert source == tuple(tuple(tuple(row) for row in grid) for grid in game.maze_layouts.grids)
            fresh = Game(117,0)
            assert fresh.shortcut_choice.preview is fresh.shortcut_choice.selected is fresh.shortcut_choice.reserved_phase is None
            assert not fresh.shortcut_choice.opened and all(fresh.grid[o.gate[1]][o.gate[0]] for o in fresh.route_options)
    print('PASS: both routes/all 3 phases through Game: queued confirmation, independent real P reservation, exact swap, selected two-way movement, rejected other gate, original walking/normal exit, later phases and fresh run.')


def check_interruptions():
    game = opened()
    assert game.select_shortcut(0) and game.request_shortcut_confirmation()
    assert not game.select_shortcut(1) and game.shortcut_choice.preview == 0
    game.cancel_puzzle_drag()  # 버튼을 놓은 일반 포인터 이동은 확정 요청과 무관하다.
    assert game.choice_confirm_requested
    game.update(.02)
    assert game.shortcut_choice.selected == 0 and game.state == 'explore'
    for cause in ('escape','hit','fatal','phase','already_dead'):
        game = opened()
        game.select_shortcut(1)
        assert game.request_shortcut_confirmation()
        if cause == 'escape':game.close_puzzle()
        elif cause == 'phase':game.phase_time = PHASE_SECONDS-.01
        elif cause == 'already_dead':game.player.hp = 0
        else:
            game.guard = CHOICE_START
            game.guard_hp = 3
            game.guard_attack_at = game.time+.01
            if cause == 'fatal':game.player.hp = 15
        game.update(.02)
        assert game.shortcut_choice.selected is None and game.shortcut_choice.reserved_phase is None
        assert not game.choice_confirm_requested and not game.shortcut_choice.opened
        if cause == 'phase':
            assert game.shortcut_choice.preview is None and game.state == 'shifting'
            finish_shift(game)
        else:
            assert game.shortcut_choice.preview == 1
            assert game.state == ('failed' if cause in ('fatal','already_dead') else 'explore')
        if cause in ('escape','hit','phase'):
            game.guard_hp = 0;game.interact()
            assert game.state == 'puzzle' and game.shortcut_choice.preview == (None if cause == 'phase' else 1)
    print('PASS: Esc, same-update nonfatal/fatal hit, pre-existing failure and phase beat queued confirm; same-phase draft resumes, phase clears only an unconfirmed draft.')
    print('PASS: pending confirmation locks its clicked candidate and survives ordinary pointer/drag release.')


def run():
    check_reservation();check_candidates();check_game_cycle();check_interruptions()


if __name__ == '__main__':
    run()
