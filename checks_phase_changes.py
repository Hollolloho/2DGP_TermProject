"""시간대 변형의 연결성·충돌·안전 복귀·기록·자원 유지 검사. SDL 창 없이 실행한다."""
import math
from maze_model import (Game, COLS, ROWS, DIRECTIONS, PHASE_SECONDS,
                        PHASE_WARNING_SECONDS, SHIFT_SWAP_AT, distances)


def finish_shift(game):
    for _ in range(20):
        if game.state != 'shifting':
            return
        game.update(.05, 1, -1, True)
    raise AssertionError('변형 상태가 종료되지 않음')


def start_shift(game):
    game.phase_time = PHASE_SECONDS-.01
    game.update(.02)
    assert game.state == 'shifting'


def check_phase_changes():
    for seed in range(32):
        for run in range(3):
            game = Game(seed, run)
            layouts = game.maze_layouts
            assert game.phase == game.layout_phase == run
            assert game.grid == layouts.grids[run] and game.grid is not layouts.grids[run]
            copied = layouts.copy_for_phase(run)
            copied[game.spawn[1]][game.spawn[0]] = 1
            assert layouts.grids[run][game.spawn[1]][game.spawn[0]] == 0
            base = layouts.grids[0]
            for phase, grid in enumerate(layouts.grids):
                assert layouts.is_valid(grid)
                assert all(grid[0]) and all(grid[-1]) and all(row[0] and row[-1] for row in grid)
                changes = {(x, y) for y in range(ROWS) for x in range(COLS) if grid[y][x] != base[y][x]}
                assert len(changes) == (0 if phase == 0 else 6)
                assert not changes & layouts.protected_cells
                tx, ty = game.torch_cell
                wx, wy = game.torch_wall
                assert (wx-tx, wy-ty) in ((-1, 0), (0, -1))
                assert grid[ty][tx] == 0 and grid[wy][wx] == 1
                assert (tx, ty) in distances(grid, game.spawn)
                assert game.torch_wall_contact == ((tx+wx+1)/2, (ty+wy+1)/2)

            # 모든 시작 시간대에서 한 바퀴 돈다. 이전 시간대 기록으로 새 지형을 공개하지 않는다.
            game.player.hp, game.player.stamina = 61, 37.
            game.fountain_used = game.player.torch = True
            game.observed = game.observed_by_phase[run]
            game.observed.update((x, y) for y in range(ROWS) for x in range(COLS))
            game.visited.update(distances(game.grid, game.spawn))
            saved_observed, saved_visited = set(game.observed), set(game.visited)
            game.attack()
            locked_facing = game.attack_facing
            for index in range(3):
                old_phase = game.phase
                old_grid = game.grid
                previous_time = game.time
                previous_position = game.player.x, game.player.y
                old_resources = game.player.hp, game.player.stamina, game.fountain_used, game.player.torch
                start_shift(game)
                assert game.grid is old_grid and game.phase == old_phase
                assert game.time == previous_time
                assert game.attack_time == 0 and game.attack_facing == locked_facing
                for _ in range(4):
                    game.update(.05, 1, 1, True)
                assert game.shift_elapsed < SHIFT_SWAP_AT and game.grid is old_grid
                game.attack()
                game.interact()
                assert (game.player.x, game.player.y) == previous_position
                finish_shift(game)
                assert game.phase == game.layout_phase == (old_phase+1) % 3
                assert game.layout_revision == index+1
                assert game.phase_time == 0 and not game.phase_warning
                assert game.grid == layouts.grids[game.phase]
                assert game.grid != old_grid
                assert game.time == previous_time
                assert (game.player.hp, game.player.stamina, game.fountain_used, game.player.torch) == old_resources
                assert game.can_stand(game.player.x, game.player.y)
                assert len(distances(game.grid, game.exit)) == sum(row.count(0) for row in game.grid)
                for y in range(ROWS):
                    for x in range(COLS):
                        assert game.can_stand(x+.5, y+.5) == (game.grid[y][x] == 0)
                if index < 2:
                    assert game.observed == game.visible
                    assert game.visited == {game.spawn}
                else:
                    assert saved_observed <= game.observed and saved_visited <= game.visited

            # 각 시작 시간대에서 닫히는 모든 칸과 몸 일부가 걸치는 경계도 확인한다.
            next_grid = layouts.grids[(game.phase+1) % 3]
            for y in range(1, ROWS-1):
                for x in range(1, COLS-1):
                    if game.grid[y][x] or not next_grid[y][x]:
                        continue
                    positions = [(x+.5, y+.5)]
                    for dx, dy in DIRECTIONS:
                        if not game.solid(x+dx, y+dy):
                            positions.append((x+.5+dx*.6, y+.5+dy*.6))
                    for px, py in positions:
                        game.player.x, game.player.y = px, py
                        assert game.can_stand(px, py) and not game.can_stand(px, py, next_grid)
                        safe = game.safe_position(next_grid)
                        assert game.can_stand(*safe) and game.can_stand(*safe, next_grid)
                        route = distances(game.grid, (math.floor(px), math.floor(py)))
                        assert (math.floor(safe[0]), math.floor(safe[1])) in route
            # 실제 교체에서도 좌표가 보정되는지 확인한다.
            closed = next((x, y) for y in range(ROWS) for x in range(COLS)
                          if not game.grid[y][x] and next_grid[y][x])
            game.player.x, game.player.y = closed[0]+.5, closed[1]+.5
            start_shift(game)
            finish_shift(game)
            assert game.can_stand(game.player.x, game.player.y)
            assert (math.floor(game.player.x), math.floor(game.player.y)) != closed

            # 보호된 입구 주변에서 정확한 소수 좌표·방향으로 복귀한다.
            x, y = game.trap_cell
            game.player.x, game.player.y = x+.4, y+.6
            game.player.direction = 2
            saved = game.player.x, game.player.y, game.player.direction
            before = game.grid
            game.interact()
            assert game.state == 'trap'
            game.trap_velocity, game.trap_side_velocity = 1.5, .8
            game.trap_progress = .4
            start_shift(game)
            assert (game.player.x, game.player.y, game.player.direction) == saved
            finish_shift(game)
            assert (game.player.x, game.player.y, game.player.direction) == saved
            assert game.trap_velocity == game.trap_side_velocity == 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    assert before[y+dy][x+dx] == game.grid[y+dy][x+dx]

    game = Game()
    game.phase_time = PHASE_SECONDS-PHASE_WARNING_SECONDS-.01
    game.update(.02)
    assert game.phase_warning and game.state == 'explore'
    for phase in range(3):
        game = Game(117, phase)
        game.player.stamina = 20.
        game.update(.05)
        assert math.isclose(game.player.stamina, 20.4 if phase == 2 else 20.)
    print('PASS: 96 starts, 288 layouts, 480 transitions; routes, one swap, frozen world, safe relocation, exact trap return, phase maps and resources.')


if __name__ == '__main__':
    check_phase_changes()
