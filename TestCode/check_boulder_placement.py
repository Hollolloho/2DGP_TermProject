"""Check both trap shortcuts on every phase, mouse gate and choice gate."""
from SourceCode.maze_model import Game, distances, landmark_area


def run():
    totals = [0,0]
    for seed in (*range(20),117,120):
        for run_number in range(3):
            game = Game(seed,run_number)
            layouts = game.maze_layouts
            if (seed,run_number)==(117,0):
                assert (game.trap_cell,game.trap_exit,game.boulder_entry,game.boulder_exit)==(
                    (9,3),(20,11),(9,6),(11,13))
            pairs = [(game.trap_cell,game.trap_exit,15)]
            if game.boulder_entry is not None:
                pairs.append((game.boulder_entry,game.boulder_exit,26))
                totals[0] += 1
            else:
                assert game.boulder_exit is None
            for entry,end,_ in pairs:
                assert entry != end and landmark_area((entry,end)) <= layouts.protected_cells
            source = [[row[:] for row in grid] for grid in layouts.grids]
            for phase in range(3):
                for opened in (False,True):
                    game.puzzle_open = opened
                    for selected in (None,*range(len(game.route_options))):
                        game.shortcut_choice.reset()
                        if selected is not None:
                            choice = game.shortcut_choice
                            assert choice.select(selected) and choice.confirm(phase) and choice.apply_phase(phase)
                        grid = game.layout_for_phase(phase)
                        goal,guard = (distances(grid,pt) for pt in (game.exit,game.guard_home))
                        assert layouts.is_valid(grid)
                        for entry,end,minimum in pairs:
                            assert distances(grid,entry)[end] >= minimum
                            assert goal[entry] > goal[end] >= 10
                            for x,y in (entry,end):
                                assert guard[x,y]>=4 and game.can_stand(x+.5,y+.5,grid)
                            assert all(grid[y][x]==source[0][y][x] for x,y in landmark_area((entry,end)))
                        totals[1] += 1
            assert layouts.grids == source
    print(f'PASS: C/D on {totals[0]}/66 maps; both trap endpoints, gain, guard clearance, stable landing and remaining distance across {totals[1]} layouts.')


if __name__=='__main__':
    run()
