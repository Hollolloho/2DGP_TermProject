"""키보드·마우스 입력을 현재 게임에 전달하는 플레이 모드."""
import json
import pico2d.pico2d as p
from maze_model import Game
from game_view import View
from game_audio import Audio


class PlayMode:
    def __init__(self, project, args):
        self.seed, self.smoke = args.seed, args.smoke
        self.output = project / "output/topdown"
        self.output.mkdir(parents=True, exist_ok=True)
        self.game = Game(args.seed)
        self.game.reveal_all = args.overview
        if args.trap_preview:
            self.game.player.x,self.game.player.y=self.game.trap_cell[0]+.5,self.game.trap_cell[1]+.5
            self.game.player.torch=True
            self.game.interact()
        self.held = set()
        self.running = True
        self.view = View(project)
        self.audio = Audio(project)

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
                    self.game = Game(self.seed, self.game.run_number+1)
                    self.held.clear()
                elif event.key == p.SDLK_F10:
                    self.view.capture(self.output/'manual.png')
                    self.game.message('output/topdown/manual.png 저장')
            elif event.type == p.SDL_MOUSEBUTTONDOWN and event.button == p.SDL_BUTTON_LEFT:
                self.game.attack()

        if not self.smoke and not p.SDL_GetWindowFlags(p.window) & p.SDL_WINDOW_INPUT_FOCUS:
            self.held.clear()

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
        if not self.smoke:
            self.audio.update(self.game)

    def save_status(self):
        self.output.mkdir(parents=True,exist_ok=True)
        g=self.game
        (self.output/'session.json').write_text(json.dumps({'mode':g.state,'player':[round(g.player.x,3),round(g.player.y,3)],
            'spawn':g.spawn,'trap':g.trap_cell,'phase':g.phase,'run':g.run_number,'torch':g.player.torch,
            'map_open':g.map_open,'full_view':g.reveal_all,'visited':len(g.visited),
            'player_fsm':g.player.state,'time':round(g.time,2)},indent=2),encoding='utf-8')

    def render(self, dt):
        self.view.draw(self.game, 1 / max(.001, dt))
        p.SDL_RenderPresent(p.renderer)

    def finish(self):
        self.audio.close()
        self.view.close()
