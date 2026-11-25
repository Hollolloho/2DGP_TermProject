"""경로 선택의 임시 선택·확정·예약 경계. SDL 없이 실행한다."""
from SourceCode.shortcut_choice import ShortcutChoice
from SourceCode.shortcut_choice import CHOICE_START, CHOICE_GOAL
from SourceCode.maze_model import Game, distances, GUARD_NOTICE_RADIUS
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
                exposed = sum(math.dist(cell,game.guard_home) <= GUARD_NOTICE_RADIUS and game.line_of_sight(*cell)
                              for cell in option.path)
                assert exposed == option.exposure_centres == (5,0)[index],(phase,p_open,index,exposed)
    assert saved == tuple(tuple(tuple(row) for row in grid) for grid in game.maze_layouts.grids)
    assert all(not Game(seed,run).route_options for seed,run in ((118,0),(117,1),(117,2)))
    print('PASS: seed 117/run 0, all 6 phase/P-gate layouts: ordinary 16, exposure route 12/5 centres, cover route 14/0; selected gate walkable, other gate closed, ordinary exit retained, 20 cells remain and source layouts unchanged.')


def run():
    check_reservation();check_candidates()


if __name__ == '__main__':
    run()
