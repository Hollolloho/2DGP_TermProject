"""타이틀 배경의 횃불과 먼지 연출."""
import ctypes
import json
import math

import pico2d.pico2d as p


class TitleTorch:
    def __init__(self, ui):
        self.wall = p.load_image(str(ui / 'title-wood-torch-patch.png'))
        self.wall_rect = p.SDL_Rect(1170, 238, self.wall.w, self.wall.h)
        p.SDL_SetTextureBlendMode(self.wall.texture, p.SDL_BLENDMODE_BLEND)

        data = json.loads((ui / 'title-torch-fire-motion.json').read_text(encoding='utf-8'))
        self.flame = p.load_image(str(ui / data['image']))
        p.SDL_SetTextureBlendMode(self.flame.texture, p.SDL_BLENDMODE_BLEND)
        width, height = data['cell']
        self.frames = [p.SDL_Rect(index % data['columns']*width,
                                  index // data['columns']*height, width, height)
                       for index in range(data['frames'])]
        self.fps = data['fps']
        self.light_levels = data['light_levels']
        # 셀 피벗을 탄 천 머리의 접점 (1203, 334)에 고정한다.
        x, y = (world-local for world, local in zip(data['world_pivot'], data['pivot']))
        self.flame_rect = p.SDL_Rect(x, y, width, height)
        self.glow_rect = p.SDL_Rect(1033, 184, 340, 216)
        self.glow = self.make_glow()

    def make_glow(self):
        # 기존 패치 경계 밖에서도 벽 무늬를 유지하며 빛이 부드럽게 사라진다.
        width, height = self.glow_rect.w, self.glow_rect.h
        tint = bytearray(width*height*4)
        for y in range(height):
            for x in range(width):
                radius = ((x-width/2)/(width/2))**2 + ((y-height/2)/(height/2))**2
                alpha = round(26*max(0., 1.-radius)**2)
                offset = (y*width+x)*4
                tint[offset:offset+4] = bytes((255, 170, 80, alpha))
        buffer = (ctypes.c_ubyte*len(tint)).from_buffer(tint)
        surface = p.SDL_CreateRGBSurfaceWithFormatFrom(buffer, width, height, 32, width*4,
                                                     p.SDL_PIXELFORMAT_RGBA32)
        assert surface, p.SDL_GetError()
        try:
            texture = p.SDL_CreateTextureFromSurface(p.renderer, surface)
            assert texture, p.SDL_GetError()
        finally:
            p.SDL_FreeSurface(surface)
        p.SDL_SetTextureBlendMode(texture, p.SDL_BLENDMODE_ADD)
        return p.Image(texture)

    def draw(self, seconds):
        index = int(seconds*self.fps+1e-7) % len(self.frames)
        p.SDL_RenderCopy(p.renderer, self.wall.texture, None, self.wall_rect)
        p.SDL_SetTextureAlphaMod(self.glow.texture, round(255*self.light_levels[index]))
        p.SDL_RenderCopy(p.renderer, self.glow.texture, None, self.glow_rect)
        # 24fps 고유 프레임을 한 장씩 그려 불길의 이중 윤곽을 피한다.
        p.SDL_RenderCopy(p.renderer, self.flame.texture, self.frames[index], self.flame_rect)


# 시작 위상, 이동 시간(초), 통로 안 좌우 위치, 가까운 쪽 반경, 최대 불투명도.
DUST = (
    (.06, 7.6, -24, 1.28, 166),
    (.21, 9.8, 19, 1.39, 192),
    (.31, 8.6, -8, 1.42, 185),
    (.44, 10.4, 8, 1.16, 146),
    (.57, 7.1, 22, 1.32, 176),
    (.70, 9.2, -19, 1.19, 160),
    (.87, 8.1, 1, 1.36, 179),
    (.95, 10.9, -4, 1.04, 137),
)


def draw_dust(seconds):
    for offset, duration, lane, radius, opacity in DUST:
        age = (seconds / duration + offset) % 1.0
        depth = 1.0 - (1.0 - age)**1.45
        near = 1.0 - depth
        perspective = .25 + .75*near
        spread = lane*perspective
        # 기둥 앞의 바닥에서 출발해 아치 안쪽으로 휘는 이차 베지어 곡선.
        middle = 2*near*depth
        x = 1141*near**2 + 956*middle + 859*depth**2 + spread
        drift = math.sin(math.tau*(1.5*age + offset))*5*perspective
        y = 679*near**2 + 642*middle + 441*depth**2 - .48*spread + drift

        fade = min(1.0, age/.13, (1.0-age)/.27)
        light = min(1.0, .58 + 1.65*depth)*(1.0 - .68*depth)
        alpha = opacity*fade*light
        radius *= .36 + .64*near
        # 가장자리 픽셀의 알파를 거리로 가중해 1~3px 입자의 이동을 부드럽게 한다.
        for py in range(round(y)-1, round(y)+2):
            for px in range(round(x)-1, round(x)+2):
                coverage = min(1.0, radius - math.hypot(px-x, py-y))
                shaded = round(alpha*coverage)
                if shaded > 0:
                    p.SDL_SetRenderDrawColor(p.renderer, 225, 169, 104, shaded)
                    p.SDL_RenderDrawPoint(p.renderer, px, py)
