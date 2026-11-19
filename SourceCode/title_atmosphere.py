"""타이틀 배경의 횃불, 먼지, 쥐 연출."""
import json
import math

import pico2d.pico2d as p


class TitleTorch:
    def __init__(self, ui, background):
        self.wall = p.load_image(str(ui / 'title-wood-torch-patch.png'))
        self.wall_rect = p.SDL_Rect(1170, 238, self.wall.w, self.wall.h)
        p.SDL_SetTextureBlendMode(self.wall.texture, p.SDL_BLENDMODE_BLEND)

        atlas = p.load_image(str(ui / 'title-wood-torch-flame.png'))
        p.SDL_SetTextureBlendMode(atlas.texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(atlas.texture, p.SDL_ScaleModeLinear)
        self.frames = [p.SDL_Rect(col*self.wall.w, row*self.wall.h, self.wall.w, self.wall.h)
                       for row in range(3) for col in range(4)]
        self.fps = 6
        # 셀 피벗 (32, 90)을 탄 천 머리의 접점 (1203, 334)에 맞춘다.
        self.flame_rect = p.SDL_Rect(1171, 244, 64, 104)
        self.flame = self.compose_frames(background, atlas)

    def compose_frames(self, background, atlas):
        # 같은 벽 위에 합성한 불투명 프레임끼리 섞어 불꽃의 중간 밝기를 유지한다.
        texture = p.SDL_CreateTexture(p.renderer, p.SDL_PIXELFORMAT_RGBA8888,
                                      p.SDL_TEXTUREACCESS_TARGET, self.wall.w*4, self.wall.h*3)
        assert texture, p.SDL_GetError()
        image = p.Image(texture)
        p.SDL_SetTextureBlendMode(texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(texture, p.SDL_ScaleModeLinear)
        previous = p.SDL_GetRenderTarget(p.renderer)
        if p.SDL_SetRenderTarget(p.renderer, texture) != 0:
            raise RuntimeError(p.SDL_GetError())
        try:
            for index, frame in enumerate(self.frames):
                source = p.SDL_Rect(index % 4*64, index // 4*104, 64, 104)
                flame = p.SDL_Rect(frame.x+self.flame_rect.x-self.wall_rect.x,
                                   frame.y+self.flame_rect.y-self.wall_rect.y, 64, 104)
                # 패치 안의 벽과 손잡이만 약 1% 폭으로 빛이 변한다.
                phase = math.tau*index/len(self.frames)
                light = 251+round(2*math.sin(phase)+math.sin(3*phase+.7))
                p.SDL_SetTextureColorMod(self.wall.texture, light, light, light)
                p.SDL_RenderSetClipRect(p.renderer, frame)
                p.SDL_RenderCopy(p.renderer, background.texture, self.wall_rect, frame)
                p.SDL_RenderCopy(p.renderer, self.wall.texture, None, frame)
                p.SDL_RenderCopy(p.renderer, atlas.texture, source, flame)
        finally:
            p.SDL_SetTextureColorMod(self.wall.texture, 255, 255, 255)
            p.SDL_SetRenderTarget(p.renderer, previous)
        return image

    def draw(self, seconds):
        position = seconds*self.fps
        step = int(position)
        frame = self.frames[step % len(self.frames)]
        p.SDL_RenderCopy(p.renderer, self.flame.texture, frame, self.wall_rect)
        mix = round((position-step)*255)
        if mix:
            following = self.frames[(step+1) % len(self.frames)]
            p.SDL_SetTextureAlphaMod(self.flame.texture, mix)
            p.SDL_RenderCopy(p.renderer, self.flame.texture, following, self.wall_rect)
            p.SDL_SetTextureAlphaMod(self.flame.texture, 255)


class TitleMouse:
    def __init__(self, ui):
        data = json.loads((ui / 'title-mouse-grounded.json').read_text(encoding='utf-8'))
        self.atlas = p.load_image(str(ui / data['image']))
        width, height = data['cell']
        columns = data['columns']
        self.pivot = data['pivot']
        self.clips = data['clips']
        self.frames = [p.SDL_Rect(index % columns*width, index // columns*height, width, height)
                       for index in range(sum(len(clip['indices']) for clip in self.clips.values()))]
        p.SDL_SetTextureBlendMode(self.atlas.texture, p.SDL_BLENDMODE_BLEND)
        p.SDL_SetTextureScaleMode(self.atlas.texture, p.SDL_ScaleModeLinear)
        self.side_length = math.hypot(176, 12)
        self.rear_length = math.hypot(92, 246)
        self.side_distance = self.side_length*math.log(1/.94)/.06
        self.rear_distance = self.rear_length*math.log(.94/.38)/.56
        self.side_seconds = self.side_distance/144
        self.rear_seconds = self.rear_distance/90
        self.turn_seconds = .36

    @staticmethod
    def ground_shadow(x, y, scale, heading, opacity):
        angle = math.radians(heading)
        dx, dy = math.cos(angle), math.sin(angle)
        for row in range(-3, 4):
            half = 24*scale*math.sqrt(1-(row/4)**2)
            across = row*scale
            cx, cy = x-dy*across, y-1+dx*across
            alpha = round(opacity*.15*(1-abs(row)/4))
            p.SDL_SetRenderDrawColor(p.renderer, 12, 8, 4, alpha)
            p.SDL_RenderDrawLine(p.renderer, round(cx-dx*half), round(cy-dy*half),
                                 round(cx+dx*half), round(cy+dy*half))

    def draw(self, seconds):
        if seconds < 4.7:
            return
        # 등장 간격은 14.2초, 17.8초, 12.9초, 18.6초를 반복한다.
        cycle = (seconds-4.7) % 63.5
        start = next(at for at in (44.9, 32.0, 14.2, 0.0) if cycle >= at)
        age = cycle-start
        rear_age = age-self.side_seconds-self.turn_seconds
        if rear_age >= self.rear_seconds:
            return

        offset_x = offset_y = 0.0
        fade = min(1.0, age/.14)
        if age < self.side_seconds:
            distance = age*144
            scale = math.exp(-.06*distance/self.side_length)
            progress = (1-scale)/.06
            x, y = 1124-176*progress, 688-12*progress
            heading = math.degrees(math.atan2(12, 176))
            clip = self.clips['side_left']
            index = int(distance/clip['cycle_distance_px']*len(clip['indices'])) % len(clip['indices'])
            frame_id = clip['indices'][index]
            angle = heading-clip['heading_degrees_above_left']
        elif rear_age < 0:
            progress = (age-self.side_seconds)/self.turn_seconds
            clip = self.clips['turn_upper_left']
            index = min(len(clip['indices'])-1, int(progress*len(clip['indices'])))
            frame_id = clip['indices'][index]
            heading = clip['headings_degrees_above_left'][index]
            x, y, scale, angle = 948, 676, .94, 0.0
        else:
            distance = rear_age*90
            scale = .94*math.exp(-.56*distance/self.rear_length)
            progress = (.94-scale)/.56
            x, y = 948-92*progress, 676-246*progress
            heading = math.degrees(math.atan2(246, 92))
            clip = self.clips['rear_upper_left']
            index = int(distance/clip['cycle_distance_px']*len(clip['indices'])) % len(clip['indices'])
            frame_id = clip['indices'][index]
            angle = heading-clip['heading_degrees_above_left']
            # 후방 1~3번 접지 포즈의 뒷발 (55,84)→(55,86)→(55.5,86)을 등록 보정한다.
            if index == 2:
                offset_x, offset_y = 1.25, .17
            elif index == 3:
                offset_x, offset_y = 2.0, 2.33
            elif index == 4:
                offset_x, offset_y = 1.0, 1.17
            fade *= min(1.0, (1-progress)/.24)

        opacity = round(255*fade)
        self.ground_shadow(x, y, scale, heading, opacity)
        frame = self.frames[frame_id]
        width, height = round(frame.w*scale), round(frame.h*scale)
        pivot = p.SDL_Point(round((self.pivot[0]-offset_x)*width/frame.w),
                            round((self.pivot[1]-offset_y)*height/frame.h))
        destination = p.SDL_Rect(round(x)-pivot.x, round(y)-pivot.y, width, height)
        shade = round(255-90*(1-scale)/.62)
        p.SDL_SetTextureColorMod(self.atlas.texture, shade, shade, shade)
        p.SDL_SetTextureAlphaMod(self.atlas.texture, opacity)
        p.SDL_RenderCopyEx(p.renderer, self.atlas.texture, frame, destination,
                           angle, pivot, p.SDL_FLIP_NONE)


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
