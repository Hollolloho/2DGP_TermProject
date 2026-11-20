"""돌 C/D 후보의 여섯 지형 조건·주변 보존·안전한 생략을 검사한다."""
from copy import deepcopy
from unittest.mock import patch

from SourceCode.maze_model import Game, distances


def run():
    game = Game(117, 0)
    entry, arrival = (9, 6), (11, 13)
    assert (game.boulder_entry, game.boulder_exit) == (entry, arrival)
    assert (game.spawn, game.trap_cell, game.trap_exit, game.puzzle_gate) == (
        (10, 1), (9, 3), (20, 11), ((17, 6), (17, 5), (17, 7)))
    layouts = game.maze_layouts
    original = deepcopy(layouts.grids)
    areas = {(x+dx, y+dy) for x,y in (entry,arrival)
             for dx in (-1,0,1) for dy in (-1,0,1)}
    assert areas <= layouts.protected_cells
    assert layouts.landmarks['boulder_entry'] == entry
    assert layouts.landmarks['boulder_exit'] == arrival
    assert game.valid_boulder_shortcut(entry, arrival)
    assert game.choose_boulder_shortcut() == (entry, arrival)

    for phase, base in enumerate(layouts.grids):
        for opened in (False, True):
            grid = deepcopy(base)
            wall = game.puzzle_gate[0]
            grid[wall[1]][wall[0]] = int(not opened)
            ds, dc, dr = (distances(grid, cell) for cell in (game.spawn, entry, game.exit))
            assert (ds[game.exit],ds[entry],dc[arrival],dr[arrival],ds[entry]+dr[arrival]) == (39,8,41,10,18)
            assert len(ds) == sum(row.count(0) for row in grid) == (348 if opened else 347)
            assert distances(grid,game.trap_cell)[game.trap_exit] == 19
            assert dr[game.trap_exit] == 15
            assert layouts.is_valid(grid)
            for x,y in areas:
                assert grid[y][x] == original[0][y][x]
            for x,y in (entry,arrival):
                assert game.can_stand(x+.5,y+.5,grid)
                for ox in (-.4,0.,.4):
                    for oy in (-.4,0.,.4):
                        assert game.can_stand(x+.5+ox,y+.5+oy,grid) == game.can_stand(x+.5+ox,y+.5+oy,original[0])
            print(f'PASS: phase {phase}, puzzle open={opened}: central route 39, C/D 41, D/center 10; A/B and bodies preserved.')
    assert layouts.grids == original
    assert not game.valid_boulder_shortcut(entry, entry)
    assert not game.valid_boulder_shortcut(game.trap_cell, arrival)
    assert not game.valid_boulder_shortcut(entry, game.exit)
    assert not game.valid_boulder_shortcut((0, 0), arrival)
    assert not game.valid_boulder_shortcut(game.puzzle_gate[1], arrival)

    x,y = entry
    layouts.grids[2][y][x] = 1
    assert game.choose_boulder_shortcut() is None
    layouts.grids = deepcopy(original)
    layouts.grids[1][y-1][x-1] = 1-layouts.grids[1][y-1][x-1]
    assert game.choose_boulder_shortcut() is None
    layouts.grids = deepcopy(original)
    original_valid = layouts.is_valid
    def closed_only(grid):
        wx,wy = game.puzzle_gate[0]
        return bool(grid[wy][wx]) and original_valid(grid)
    with patch.object(layouts, 'is_valid', side_effect=closed_only):
        assert game.choose_boulder_shortcut() is None, 'open-puzzle failure must reject the pair'
    assert layouts.grids == original

    with patch.object(Game, 'valid_boulder_shortcut', return_value=False):
        omitted = Game(117, 0)
    assert omitted.boulder_entry is omitted.boulder_exit is None
    assert 'boulder_entry' not in omitted.maze_layouts.landmarks
    assert not areas & omitted.maze_layouts.protected_cells
    assert omitted.maze_layouts.grids == original
    for base in omitted.maze_layouts.grids:
        assert len(distances(base,omitted.exit)) == sum(row.count(0) for row in base)
    for seed,run in ((117,1),(117,2),(0,0),(120,0)):
        other = Game(seed,run)
        assert other.boulder_entry is other.boulder_exit is None
    print('PASS: overlap, blocked center, changed return area and open-puzzle failures omit C/D without altering terrain.')


if __name__ == '__main__':
    run()
