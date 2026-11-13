"""Small model checks: python checks_topdown.py; no SDL window required."""
import json
import math
from pathlib import Path
from checks_phase_changes import check_phase_changes, finish_shift
from checks_gait import SCHEDULES, check_gait
from maze_model import WALK_SPEED, project as project_ground
from maze_model import Game, COLS, ROWS, DIRECTIONS, distances, TRAP_LENGTH, TRAP_PLANES, TRAP_LATERAL, BLADE_RADIUS, PLAYER_RADIUS, blade_position


def check_visibility():
    game = Game()
    game.grid = [[0] * COLS for _ in range(ROWS)]
    game.player.x = game.player.y = 10.5
    game.grid[10][12] = 1
    game.torch_cell = (10, 11)
    game.update_visibility()
    base = game.visible
    for direction in range(len(DIRECTIONS)):
        game.player.direction = direction
        game.update_visibility()
        assert game.visible == base, 'Turning in place must not change visibility.'

    # Check cardinal and diagonal distances and the wall directly east of the player.
    assert {(5, 10), (10, 5), (10, 15), (13, 14), (12, 10)} <= base
    assert {(10, 16), (14, 14), (13, 10)}.isdisjoint(base)

    game.interact()
    assert game.player.torch and base < game.visible
    assert {(10, 16), (10, 17), (14, 14)} <= game.visible
    assert {(10, 18), (17, 11), (13, 10), (16, 10)}.isdisjoint(game.visible)


def check_dagger():
    player_atlases = Path(__file__).parent/'sprite/quarter'
    catalog = player_atlases/'player_explorer_attack_v2/explorer.json'
    clips = json.loads(catalog.read_text(encoding='utf-8'))['clips']
    game = Game(player_clips=clips)
    game.grid = [[0]*COLS for _ in range(ROWS)]
    player = game.player
    directions = (('n', -1, -1), ('s', 1, 1), ('w', -1, 1), ('e', 1, -1),
                  ('nw', -1, 0), ('ne', 0, -1), ('sw', 0, 1), ('se', 1, 0))

    def begin(facing, target):
        player.x, player.y = 15.5, 11.5
        player.screen_facing = facing
        game.guard, game.guard_hp = target, 3
        game.phase_time, game.attack_time = 0., 10.
        game.attack()
        assert game.attack_facing == facing and game.attack_clip == 'attack-'+facing
        assert game.guard_hp == 3
        assert game.attack_hits_ms == (233, 466)

    for facing, dx, dy in directions:
        for sign in (1, -1):
            for times in SCHEDULES:
                begin(facing, (15+sign*dx, 11+sign*dy))
                for dt in times:
                    game.update(dt)
                    expected = 3 - sum(game.attack_time >= hit_at for hit_at in (.233, .466)) if sign == 1 else 3
                    assert game.guard_hp == expected, (facing, sign, game.attack_time)

    # 이동 방향을 바꿔도 두 타격은 시작 방향을 따른다.
    begin('sw', (15, 12))
    game.update(.025, 0, -1)
    assert player.screen_facing == 'ne' and game.attack_facing == 'sw'
    for _ in range(10):
        game.update(.025)
    assert game.guard_hp == 2 and game.guard_alert_until > game.time
    for _ in range(8):
        game.update(.025)
    assert game.guard_hp == 1

    # 첫 베기가 빗나가도 되베기에서 사거리와 시야를 새로 확인한다.
    begin('e', (18, 11))
    for _ in range(10):
        game.update(.025)
    assert game.guard_hp == 3
    game.guard = (16, 11)
    for _ in range(9):
        game.update(.025)
    assert game.guard_hp == 2

    # 1.8칸 안에 있어도 벽 뒤나 정확히 옆에 있는 대상은 맞지 않는다.
    game.grid[11][16] = 1
    begin('e', (17, 11))
    player.x = 15.75
    assert game.can_stand(player.x, player.y)
    assert math.hypot(game.guard[0]+.5-player.x, game.guard[1]+.5-player.y) < 1.8
    for _ in range(20):
        game.update(.025)
    assert game.guard_hp == 3
    game.grid[11][16] = 0
    begin('n', (16, 10))
    for _ in range(20):
        game.update(.025)
    assert game.guard_hp == 3

    begin('sw', (15, 12))
    game.map_open = True
    for _ in range(20):
        game.update(.025)
    game.map_open = False
    game.update(.05)
    assert game.guard_hp == 3

    # 함정방에 들어가면 남아 있던 되베기가 복귀 뒤에 적용되지 않는다.
    begin('sw', (15, 12))
    for _ in range(10):
        game.update(.025)
    assert game.guard_hp == 2
    game.trap_cell = (15, 11)
    player.torch = True
    game.interact()
    assert game.state == 'trap' and not game.attack_hits_ms
    game.return_from_trap()
    for _ in range(10):
        game.update(.025)
    assert game.guard_hp == 2

    legacy_catalog = player_atlases/'player_explorer_v1/explorer.json'
    game.player_clips = json.loads(legacy_catalog.read_text(encoding='utf-8'))['clips']
    game.guard_hp, game.attack_time = 3, 10.
    game.attack()
    assert game.attack_hits_ms == (233,)
    for _ in range(20):
        game.update(.025)
    assert game.guard_hp == 2
    print('PASS: 8-way dagger double hit at 30/60/120/variable dt, direction lock, wall, map, trap and legacy single hit.')


def run():
    check_gait()
    check_phase_changes()
    check_visibility()
    check_dagger()
    for seed in range(32):
        game=Game(seed)
        reachable=distances(game.grid,game.exit)
        floors=sum(not v for row in game.grid for v in row)
        assert len(reachable)==floors
        assert game.spawn!=game.exit and reachable[game.spawn]>25
        assert all(game.grid[0]) and all(game.grid[-1])
        assert all(row[0] and row[-1] for row in game.grid)
        assert not game.solid(*game.guard)
        protected=(game.spawn,game.torch_cell,game.trap_cell,game.trap_exit,game.fountain,game.exit)
        assert all(distances(game.grid,cell)[game.guard]>=4 for cell in protected), 'Guardian must not camp on arrival/service cells.'
        x,y=game.spawn
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if game.solid(x+dx,y+dy):
                    assert not game.can_stand(x+dx+.5,y+dy+.5)
    game=Game()
    assert game.torch_cell in game.visible
    assert game.visited=={game.spawn} and game.torch_cell not in game.visited
    assert any(game.grid[y][x] for x,y in game.visible), 'The nearest blocking walls must be visible themselves.'
    before=len(game.visible)
    assert game.guard_alert_until<=game.time
    game.interact()
    assert game.player.torch and len(game.visible)>=before
    game.player.x,game.player.y=game.trap_cell[0]+.5,game.trap_cell[1]+.5
    saved=game.player.x,game.player.y
    game.interact()
    assert game.state=='trap'
    game.phase_time=59.99
    game.update(.02,1,-1)
    assert game.state=='shifting' and (game.player.x,game.player.y)==saved
    finish_shift(game)
    assert game.state=='explore' and (game.player.x,game.player.y)==saved and game.player.torch
    game.interact()
    game.trap_progress=1
    game.update(.01)
    assert game.state=='explore' and (game.player.x,game.player.y)==(game.trap_exit[0]+.5,game.trap_exit[1]+.5)
    assert game.trap_exit in game.visited
    game.map_open=True
    position=game.player.x,game.player.y
    world=game.phase_time
    game.update(.02,1,0)
    assert (game.player.x,game.player.y)==position and game.phase_time>world
    game.map_open=False
    for _ in range(200): game.update(.05,0,-1)
    assert game.can_stand(game.player.x,game.player.y)
    assert Game(117,1).phase==1 and Game(117,2).phase==2 and Game(117,3).phase==0
    # The room creates a separate graph edge between A and B, not a corridor
    # suddenly carved through unrelated grid walls.
    demo=Game()
    assert demo.shortcut_distance>=15 and distances(demo.grid,demo.exit)[demo.trap_exit]>=10
    assert TRAP_LENGTH/1.8+.56 < demo.shortcut_distance*math.hypot(*project_ground(1, 0))/WALK_SPEED
    demo.player.x,demo.player.y=demo.trap_cell[0]+.5,demo.trap_cell[1]+.5
    demo.interact()
    demo.trap_progress=TRAP_PLANES[0]
    demo.trap_x=blade_position(demo.time+.01,0)
    demo.update(.01)
    assert demo.player.hp==80
    demo.update(.01)
    assert demo.player.hp==80, 'Hit cooldown must prevent repeated damage every frame.'
    fatal=Game()
    fatal.player.x,fatal.player.y=fatal.trap_cell[0]+.5,fatal.trap_cell[1]+.5
    fatal.interact()
    fatal.player.hp=20
    fatal.trap_progress=TRAP_PLANES[0]
    fatal.trap_x=blade_position(fatal.time+.01,0)
    fatal.update(.01)
    assert fatal.state=='failed' and fatal.player.hp==0
    fatal.update(.05,dy=-1)
    assert fatal.state=='failed' and fatal.player.hp==0
    demo.trap_progress=1;demo.trap_velocity=0
    demo.update(.01)
    assert demo.trap_completed and demo.landing_until>demo.time
    # Projection of a fixed landmark approaches smoothly and responds laterally.
    from trap_view import project
    demo.enter_room()
    demo.trap_progress=0;demo.trap_x=0;demo.trap_velocity=0;demo.trap_hit_at=-10
    a=project(demo,1.3,0,7)
    demo.trap_progress=.2
    b=project(demo,1.3,0,7)
    assert b[0]>a[0] and b[1]>a[1]
    demo.trap_x=.5
    c=project(demo,1.3,0,7)
    assert c[0]<b[0]
    print('PASS: circular visibility, wall occlusion, torch radius; 32 mazes; collision, FSM, moving-phase exact return, visited map, A/B benefit, fatal blade hits and perspective.')


if __name__=='__main__': run()
