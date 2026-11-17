"""타이틀 배경의 바닥을 따라 흐르는 먼지."""
import math

import pico2d.pico2d as p


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
