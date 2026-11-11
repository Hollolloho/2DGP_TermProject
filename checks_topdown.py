"""Small model checks: python checks_topdown.py; no SDL window required."""
import math
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


def run():
    check_visibility()
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
    combat=Game()
    combat.player.x,combat.player.y=combat.guard[0]+.5,combat.guard[1]+.5
    combat.attack()
    assert combat.guard_hp==2 and combat.guard_alert_until>combat.time
    game.interact()
    assert game.player.torch and len(game.visible)>=before
    game.player.x,game.player.y=game.trap_cell[0]+.5,game.trap_cell[1]+.5
    saved=game.player.x,game.player.y
    game.interact()
    assert game.state=='trap'
    game.phase_time=59.99
    game.update(.02,1,-1)
    assert game.state=='explore' and (game.player.x,game.player.y)==saved
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
    assert TRAP_LENGTH/1.8+.56 < demo.shortcut_distance/2.5
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
