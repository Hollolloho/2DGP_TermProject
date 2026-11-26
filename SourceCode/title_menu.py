"""게임 시작 전 타이틀과 조작법 화면."""
import ctypes
from .window_input import disable_text_input
from time import perf_counter

import pico2d.pico2d as p
from .title_atmosphere import TitleTorch, draw_dust


BUTTON_ART = ('title-button-start.png', 'title-button-controls.png', 'title-button-exit.png')
CREAM = (249, 232, 204)
GOLD = (228, 180, 114)
MUTED = (211, 190, 162)
CONTROLS = (
    ('W / A / S / D', '통로 이동  ↖ / ↙ / ↘ / ↗'),
    ('Shift + 이동', '달리기'),
    ('좌클릭', '단검 2연타'),
    ('좌클릭 드래그', '누른 채 움직여 마우스 미로 풀기'),
    ('F', '상호작용'),
    ('M', '방문 지도'),
    ('Esc', '지도·퍼즐 닫기 / 함정방 입장 전 복귀'),
    ('R', '새 회차 시작'),
)


def contains(rect, x, y):
    return rect.x <= x < rect.x + rect.w and rect.y <= y < rect.y + rect.h


def discard_startup_input():
    # 로딩 중 누른 키·버튼은 비우고 창 닫기 이벤트는 남긴다.
    p.SDL_PumpEvents()
    p.SDL_FlushEvents(p.SDL_KEYDOWN, p.SDL_KEYUP)
    p.SDL_FlushEvents(p.SDL_MOUSEBUTTONDOWN, p.SDL_MOUSEBUTTONUP)


def show_title_menu(project):
    ui = project / 'sprite/ui'
    background = p.load_image(str(ui / 'title-background.png'))
    torch = TitleTorch(ui)
    heading = p.load_image(str(ui / 'title-heading.png'))
    plates = [p.load_image(str(ui / name)) for name in BUTTON_ART]
    for image in (heading, *plates):
        p.SDL_SetTextureBlendMode(image.texture, p.SDL_BLENDMODE_BLEND)
    heading_rect = p.SDL_Rect(84, 167, heading.w, heading.h)
    fonts = {size: p.load_font(f'C:/Windows/Fonts/{face}.ttf', size)
             for size, face in ((20, 'malgun'), (27, 'malgunbd'), (47, 'malgunbd'))}
    labels = {}

    def text(value, x, y, size, color=CREAM):
        key = (value, size, color)
        if key not in labels:
            surface = p.TTF_RenderUTF8_Blended(fonts[size].font, value.encode('utf-8'), p.SDL_Color(*color, 255))
            assert surface, p.SDL_GetError()
            try:
                texture = p.SDL_CreateTextureFromSurface(p.renderer, surface)
                assert texture, p.SDL_GetError()
                labels[key] = p.Image(texture)
            finally:
                p.SDL_FreeSurface(surface)
        label = labels[key]
        p.SDL_RenderCopy(p.renderer, label.texture, None, p.SDL_Rect(x, y, label.w, label.h))

    def draw_back(rect):
        p.SDL_SetRenderDrawColor(p.renderer, 72, 46, 29, 245)
        p.SDL_RenderFillRect(p.renderer, rect)
        p.SDL_SetRenderDrawColor(p.renderer, 190, 131, 71, 255)
        p.SDL_RenderDrawRect(p.renderer, rect)
        text('›', rect.x+18, rect.y+(rect.h-35)//2, 27, GOLD)
        text('뒤로', rect.x+48, rect.y+(rect.h-35)//2, 27)

    def draw_focus(rect):
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        # 테두리를 버튼 이미지의 잘린 모서리에 맞춘다.
        corners = ((7, 1), (w-8, 1), (w-2, 7), (w-2, h-8), (w-8, h-2),
                   (7, h-2), (1, h-8), (1, 7), (7, 1))
        points = (p.SDL_Point * len(corners))(*(p.SDL_Point(x+dx, y+dy) for dx, dy in corners))
        p.SDL_SetRenderDrawColor(p.renderer, *GOLD, 255)
        p.SDL_RenderDrawLines(p.renderer, points, len(points))
        p.SDL_RenderDrawLine(p.renderer, x+19, y+23, x+25, y+28)
        p.SDL_RenderDrawLine(p.renderer, x+25, y+28, x+19, y+33)

    buttons = [p.SDL_Rect(86, 354+index*70, plate.w, plate.h) for index, plate in enumerate(plates)]
    back = p.SDL_Rect(86, 688, 196, 54)
    selected = 0
    help_open = False
    event = p.SDL_Event()
    discard_startup_input()
    started = perf_counter()

    while True:
        choice = None
        # 화면 전환을 고른 뒤 같은 입력 묶음은 소비하고, 창 닫기는 끝까지 처리한다.
        while p.SDL_PollEvent(ctypes.byref(event)):
            if event.type == p.SDL_WINDOWEVENT and event.window.event == p.SDL_WINDOWEVENT_FOCUS_GAINED:
                disable_text_input(p)
            if event.type == p.SDL_QUIT or (event.type == p.SDL_WINDOWEVENT and
                                            event.window.event == p.SDL_WINDOWEVENT_CLOSE):
                return False
            if choice is not None:
                continue
            if event.type == p.SDL_KEYDOWN and not event.key.repeat:
                key = event.key.keysym.sym
                if key == p.SDLK_ESCAPE:
                    choice = 'back' if help_open else 'quit'
                elif key in (p.SDLK_RETURN, p.SDLK_KP_ENTER):
                    choice = 'back' if help_open else selected
                elif not help_open and key in (p.SDLK_UP, p.SDLK_DOWN):
                    selected = (selected + (1 if key == p.SDLK_DOWN else -1)) % len(buttons)
            elif event.type == p.SDL_MOUSEMOTION and not help_open:
                for index, rect in enumerate(buttons):
                    if contains(rect, event.motion.x, event.motion.y):
                        selected = index
                        break
            elif event.type == p.SDL_MOUSEBUTTONDOWN and event.button.button == p.SDL_BUTTON_LEFT:
                if help_open:
                    if contains(back, event.button.x, event.button.y):
                        choice = 'back'
                else:
                    for index, rect in enumerate(buttons):
                        if contains(rect, event.button.x, event.button.y):
                            choice = index
                            break

        if choice == 0:
            return True
        if choice in (2, 'quit'):
            return False
        if choice == 1:
            help_open = True
            selected = 1
        elif choice == 'back':
            help_open = False

        p.SDL_RenderCopy(p.renderer, background.texture, None, None)
        elapsed = perf_counter() - started
        torch.draw(elapsed)
        p.SDL_SetRenderDrawBlendMode(p.renderer, p.SDL_BLENDMODE_BLEND)
        draw_dust(elapsed)
        if help_open:
            p.SDL_SetRenderDrawColor(p.renderer, 19, 13, 9, 210)
            p.SDL_RenderFillRect(p.renderer, p.SDL_Rect(60, 52, 524, 710))
            text('조작법', 86, 67, 47)
            text('미로 탐색', 86, 150, 27, GOLD)
            for index, (keys, description) in enumerate(CONTROLS):
                y = 197+index*42
                text(keys, 86, y, 20, GOLD)
                text(description, 240, y, 20)
            text('탐색 중 Esc는 게임 종료', 240, 533, 20, MUTED)
            text('함정방 · 칼날 A → B / 여섯 줄 돌방 C → D', 86, 563, 27, GOLD)
            text('W / S', 86, 610, 20, GOLD)
            text('전진·후진', 170, 610, 20)
            text('A / D', 305, 610, 20, GOLD)
            text('좌우 이동', 389, 610, 20)
            text('마우스 좌우로 시선 회전', 550, 610, 20)
            draw_back(back)
            text('Enter / Esc', 306, 702, 20, MUTED)
        else:
            p.SDL_RenderCopy(p.renderer, heading.texture, None, heading_rect)
            for plate, rect in zip(plates, buttons):
                p.SDL_RenderCopy(p.renderer, plate.texture, None, rect)
            draw_focus(buttons[selected])
            text('↑ ↓ 이동    Enter 선택    Esc 종료', 86, 575, 20, MUTED)

        p.SDL_RenderPresent(p.renderer)
        p.delay(.01)
