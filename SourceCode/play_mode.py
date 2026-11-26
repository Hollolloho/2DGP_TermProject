"""키보드·마우스 입력을 현재 게임에 전달하는 플레이 모드."""
import ctypes
import json
import pico2d.pico2d as p
from .maze_model import Game
from .game_view import View, LW, LH, PUZZLE_OFFSET_X, CHOICE_CARD_RECTS, CHOICE_CONFIRM_RECT
from .game_audio import Audio
from .first_person import MouseLook, turned_yaw
from .window_input import disable_text_input
from .puzzle_layout import connection_cell, connection_piece_at, on_loose_floor


class PlayMode:
    def __init__(self, project, args, *, output=None):
        self.seed, self.smoke = args.seed, args.smoke
        self.test_course = getattr(args, 'test_course', False)
        self.output = project / "output/topdown" if output is None else output
        self.output.mkdir(parents=True, exist_ok=True)
        self.view = View(project)
        self.game = self.new_game()
        self.game.reveal_all = args.overview
        if args.trap_preview:
            self.game.player.x,self.game.player.y=self.game.trap_cell[0]+.5,self.game.trap_cell[1]+.5
            self.game.player.torch=True
            self.game.interact()
        self.held = set()
        self.puzzle_mouse_held = False
        self.focused = self.smoke or bool(p.SDL_GetWindowFlags(p.window) & p.SDL_WINDOW_INPUT_FOCUS)
        self.mouse_inside = self.smoke or bool(p.SDL_GetWindowFlags(p.window) & p.SDL_WINDOW_MOUSE_FOCUS)
        self.mouse = MouseLook(p)
        self.running = True
        self.audio = Audio(project)

    def new_game(self, run_number=0):
        return Game(self.seed, run_number, self.view.player_catalog['clips'], test_course=self.test_course)

    def release_input(self):
        self.held.clear()
        self.game.cancel_puzzle_drag()
        self.game.choice_confirm_requested = False
        self.view.connection_pointer = None
        self.puzzle_mouse_held = False
        self.game.boulder_return_requested = self.game.boulder_exit_requested = False

    def sync_mouse(self):
        self.mouse.capture(self.running and self.focused and self.mouse_inside and self.game.state == 'trap')

    def handle_events(self):
        self.sync_mouse()
        event = p.SDL_Event()
        while p.SDL_PollEvent(ctypes.byref(event)):
            if event.type == p.SDL_QUIT:
                self.running = False
            elif event.type == p.SDL_WINDOWEVENT and event.window.event == p.SDL_WINDOWEVENT_FOCUS_LOST:
                self.focused = False
                self.sync_mouse()
                self.release_input()
            elif event.type == p.SDL_WINDOWEVENT and event.window.event == p.SDL_WINDOWEVENT_FOCUS_GAINED:
                disable_text_input(p)
                self.focused = True
                self.sync_mouse()
            elif event.type == p.SDL_WINDOWEVENT and event.window.event in (p.SDL_WINDOWEVENT_ENTER,p.SDL_WINDOWEVENT_LEAVE):
                self.mouse_inside = event.window.event == p.SDL_WINDOWEVENT_ENTER
                if not self.mouse_inside and self.game.state == 'trap':
                    self.release_input()
                self.sync_mouse()
            elif not self.focused:
                continue
            elif event.type == p.SDL_KEYUP:
                self.held.discard(event.key.keysym.sym)
            elif event.type == p.SDL_KEYDOWN:
                if event.key.repeat:
                    continue
                key = event.key.keysym.sym
                if key == p.SDLK_r and self.game.state == 'path_room':
                    self.game.rotate_connection()
                    continue
                if (self.game.state == 'path_room' and self.game.world_path.stage == 'entering'
                        and key not in (p.SDLK_ESCAPE,p.SDLK_F10)):
                    continue
                # 변형과 퍼즐 중 이동 키를 보관하지 않는다.
                if self.game.state in ('shifting', 'puzzle') and key not in (p.SDLK_r, p.SDLK_ESCAPE, p.SDLK_F10):
                    continue
                self.held.add(key)
                if key == p.SDLK_ESCAPE:
                    if self.game.map_open:
                        self.game.map_open = False
                    elif self.game.state == 'path_room':
                        self.game.return_from_path()
                    elif self.game.state == 'puzzle':
                        self.game.close_puzzle()
                    elif self.game.state == 'trap':
                        if self.game.trap_kind == 'boulder':
                            self.game.request_boulder_return()
                        else:
                            self.game.return_from_trap()
                            self.sync_mouse()
                    else:
                        self.running = False
                elif key == p.SDLK_f:
                    previous = self.game.state
                    self.game.interact()
                    self.sync_mouse()
                    if previous != 'explore' or self.game.state != 'explore':
                        self.held.clear()
                elif key == p.SDLK_m and self.game.state == 'explore':
                    self.game.map_open = not self.game.map_open
                    self.held.clear()
                elif key == p.SDLK_v and self.game.state == 'explore':
                    self.game.reveal_all = not self.game.reveal_all
                elif key == p.SDLK_r:
                    self.game = self.new_game(self.game.run_number+1)
                    self.release_input()
                    self.sync_mouse()
                elif key == p.SDLK_F10:
                    self.view.capture(self.output/'manual.png')
                    self.game.message('output/topdown/manual.png 저장')
            elif event.type == p.SDL_MOUSEBUTTONDOWN and event.button.button == p.SDL_BUTTON_LEFT:
                if self.game.state in ('puzzle','path_room'):
                    if not self.puzzle_mouse_held:
                        point = self.mouse_point(event.button)
                        if self.game.state == 'path_room':
                            self.view.connection_pointer = point
                            index = connection_piece_at(self.game.connection,point)
                            if index is not None:
                                self.game.pick_connection(index)
                        elif self.game.puzzle_tab == 'choice':
                            for index,(x,y,w,h) in enumerate(CHOICE_CARD_RECTS):
                                if x <= point[0] < x+w and y <= point[1] < y+h:
                                    self.game.select_shortcut(index)
                            x,y,w,h = CHOICE_CONFIRM_RECT
                            if x <= point[0] < x+w and y <= point[1] < y+h:
                                self.game.request_shortcut_confirmation()
                        else:
                            self.game.puzzle.press(point)
                    self.puzzle_mouse_held = True
                elif not self.puzzle_mouse_held:
                    self.game.attack()
            elif event.type == p.SDL_MOUSEBUTTONUP and event.button.button == p.SDL_BUTTON_LEFT:
                if self.game.state == 'path_room' and self.puzzle_mouse_held:
                    point = self.mouse_point(event.button)
                    self.game.drop_connection(connection_cell(point),shelf=on_loose_floor(point))
                self.game.puzzle.release()
                self.puzzle_mouse_held = False
            elif event.type == p.SDL_MOUSEMOTION:
                if self.game.state == 'trap':
                    delta = self.mouse.delta(event.motion)
                    if self.game.trap_kind == 'boulder':
                        room = self.game.boulder_room
                        room.yaw = turned_yaw(room.yaw, delta)
                    else:
                        self.game.trap_yaw = turned_yaw(self.game.trap_yaw, delta)
                elif not event.motion.state & p.SDL_BUTTON_LMASK:
                    self.game.cancel_puzzle_drag()
                    self.puzzle_mouse_held = False
                elif self.game.state in ('puzzle','path_room'):
                    point = self.mouse_point(event.motion)
                    if self.game.state == 'path_room':
                        self.view.connection_pointer = point
                    elif self.game.puzzle_tab == 'maze':
                        self.game.drag_puzzle(point)

        if not self.smoke and not p.SDL_GetWindowFlags(p.window) & p.SDL_WINDOW_INPUT_FOCUS:
            self.focused = False
            self.release_input()
        self.sync_mouse()

    def mouse_point(self, event):
        width, height = ctypes.c_int(), ctypes.c_int()
        p.SDL_GetWindowSize(p.window, ctypes.byref(width), ctypes.byref(height))
        offset = PUZZLE_OFFSET_X if self.game.state == 'puzzle' and self.game.puzzle_tab == 'maze' else 0
        return event.x*LW//max(1, width.value)-offset, event.y*LH//max(1, height.value)

    def update(self, dt):
        dx = int(p.SDLK_d in self.held)-int(p.SDLK_a in self.held)
        dy = int(p.SDLK_s in self.held)-int(p.SDLK_w in self.held)
        previous = self.game.state
        if previous in ('explore','path_room'):
            # 일반 미로에서는 W가 격자 -X 통로, D가 격자 -Y 통로 방향이다.
            dx, dy = dy, -dx
        self.game.update(dt,dx,dy,bool(self.held & {p.SDLK_LSHIFT,p.SDLK_RSHIFT}))
        if previous!=self.game.state:
            self.held.clear()
        self.sync_mouse()
        if not self.smoke:
            self.audio.update(self.game)

    def save_status(self):
        self.output.mkdir(parents=True,exist_ok=True)
        g=self.game
        (self.output/'session.json').write_text(json.dumps({'mode':g.state,'player':[round(g.player.x,3),round(g.player.y,3)],
            'spawn':g.spawn,'trap':g.trap_cell,'phase':g.phase,'layout_phase':g.layout_phase,
            'layout_revision':g.layout_revision,'run':g.run_number,'torch':g.player.torch,
            'map_open':g.map_open,'full_view':g.reveal_all,'visited':len(g.visited),
            'player_fsm':g.player.state,'time':round(g.time,2)},indent=2),encoding='utf-8')


    def render(self, dt):
        self.view.draw(self.game, 1 / max(.001, dt))
        p.SDL_RenderPresent(p.renderer)

    def finish(self):
        self.running = False
        self.sync_mouse()
        self.audio.close()
        self.view.close()
