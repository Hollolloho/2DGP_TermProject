"""타이틀 배경을 움직이는 횃불과 먼지."""
import ctypes
import json
import math

import pico2d.pico2d as p


class TitleTorch:
    def __init__(self, project):
        self.wall = p.load_image(str(project / 'sprite/ui/title-torch-wall-patch.png'))
        self.wall_rect = p.SDL_Rect(1176, 240, self.wall.w, self.wall.h)
        p.SDL_SetTextureBlendMode(self.wall.texture, p.SDL_BLENDMODE_BLEND)

        directory = project / 'sprite/topdown/effects'
        data = json.loads((directory / 'torch.json').read_text(encoding='utf-8'))
        self.fps = data['meta']['pixelfx']['fps']
        self.frames = [p.SDL_Rect(frame['x'], frame['y'], frame['w'], 76)
                       for frame in (entry['frame'] for entry in data['frames'])]
        self.flame = self.load_flame(directory / data['meta']['image'])
        p.SDL_SetTextureBlendMode(self.flame.texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(self.flame.texture, p.SDL_ScaleModeLinear)
        p.SDL_SetTextureAlphaMod(self.flame.texture, 207)
        # 기존 받침은 배경 그림을 쓰고, 불꽃의 밑변만 심지에 맞춘다.
        self.flame_rect = p.SDL_Rect(1109, 167, 192, 166)

    def load_flame(self, path):
        source = p.IMG_Load(str(path).encode('utf-8'))
        assert source, p.SDL_GetError()
        try:
            surface = p.SDL_ConvertSurfaceFormat(source, p.SDL_PIXELFORMAT_RGBA32, 0)
        finally:
            p.SDL_FreeSurface(source)
        assert surface, p.SDL_GetError()
        try:
            if p.SDL_LockSurface(surface) != 0:
                raise RuntimeError(p.SDL_GetError())
            try:
                self.feather_flame(surface.contents)
            finally:
                p.SDL_UnlockSurface(surface)
            texture = p.SDL_CreateTextureFromSurface(p.renderer, surface)
            assert texture, p.SDL_GetError()
            return p.Image(texture)
        finally:
            p.SDL_FreeSurface(surface)

    def feather_flame(self, surface):
        pitch = surface.pitch
        pixels = (ctypes.c_ubyte * (pitch*surface.h)).from_address(surface.pixels)
        width, height = self.frames[0].w, self.frames[0].h
        wick = [max(0.0, min(1.0, (10-abs(x-(width-1)/2))/7)) for x in range(width)]
        for y in range(height):
            sparks = min(1.0, .36 + max(0, y-27)*.025)
            edge = min(1.0, (height-1-y)/15)
            # 심지와 닿는 중심부를 남기고 잘린 바깥쪽 빛과 위쪽 불티를 약하게 한다.
            for x, core in enumerate(wick):
                opacity = sparks * (edge + (1.0-edge)*core)
                if opacity < 1.0:
                    for frame in self.frames:
                        alpha = (frame.y+y)*pitch + (frame.x+x)*4+3
                        pixels[alpha] = round(pixels[alpha]*opacity)

    def draw(self, seconds):
        frame = self.frames[int(seconds*self.fps) % len(self.frames)]
        p.SDL_RenderCopy(p.renderer, self.wall.texture, None, self.wall_rect)
        p.SDL_RenderCopy(p.renderer, self.flame.texture, frame, self.flame_rect)


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
