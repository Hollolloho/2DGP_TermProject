"""타이틀 배경을 움직이는 횃불과 먼지."""
import math

import pico2d.pico2d as p


class TitleTorch:
    def __init__(self, ui, background):
        self.wall = p.load_image(str(ui / 'title-torch-wall-patch.png'))
        self.wall_rect = p.SDL_Rect(1176, 240, self.wall.w, self.wall.h)
        p.SDL_SetTextureBlendMode(self.wall.texture, p.SDL_BLENDMODE_BLEND)

        atlas = p.load_image(str(ui / 'title-torch-flame.png'))
        p.SDL_SetTextureBlendMode(atlas.texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(atlas.texture, p.SDL_ScaleModeLinear)
        self.frames = [p.SDL_Rect(col*72, row*96, 72, 96) for row in range(3) for col in range(4)]
        self.fps = 6
        # 셀 피벗 (36, 86)을 배경 심지 (1205, 333)에 맞춘다.
        self.flame_rect = p.SDL_Rect(1169, 247, 72, 96)
        self.flame = self.compose_frames(background, atlas)

    def compose_frames(self, background, atlas):
        # 같은 벽 위에 합성한 불투명 프레임끼리 섞어 불꽃의 중간 밝기를 유지한다.
        texture = p.SDL_CreateTexture(p.renderer, p.SDL_PIXELFORMAT_RGBA8888,
                                      p.SDL_TEXTUREACCESS_TARGET, atlas.w, atlas.h)
        assert texture, p.SDL_GetError()
        image = p.Image(texture)
        p.SDL_SetTextureBlendMode(texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(texture, p.SDL_ScaleModeLinear)
        previous = p.SDL_GetRenderTarget(p.renderer)
        if p.SDL_SetRenderTarget(p.renderer, texture) != 0:
            raise RuntimeError(p.SDL_GetError())
        try:
            for frame in self.frames:
                patch = p.SDL_Rect(frame.x+self.wall_rect.x-self.flame_rect.x,
                                   frame.y+self.wall_rect.y-self.flame_rect.y,
                                   self.wall_rect.w, self.wall_rect.h)
                p.SDL_RenderSetClipRect(p.renderer, frame)
                p.SDL_RenderCopy(p.renderer, background.texture, self.flame_rect, frame)
                p.SDL_RenderCopy(p.renderer, self.wall.texture, None, patch)
                p.SDL_RenderCopy(p.renderer, atlas.texture, frame, frame)
        finally:
            p.SDL_SetRenderTarget(p.renderer, previous)
        return image

    def draw(self, seconds):
        position = seconds*self.fps
        step = int(position)
        frame = self.frames[step % len(self.frames)]
        p.SDL_RenderCopy(p.renderer, self.wall.texture, None, self.wall_rect)
        p.SDL_RenderCopy(p.renderer, self.flame.texture, frame, self.flame_rect)
        mix = round((position-step)*255)
        if mix:
            following = self.frames[(step+1) % len(self.frames)]
            p.SDL_SetTextureAlphaMod(self.flame.texture, mix)
            p.SDL_RenderCopy(p.renderer, self.flame.texture, following, self.flame_rect)
            p.SDL_SetTextureAlphaMod(self.flame.texture, 255)


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
