"""Optional local sound effects; no sound is required for the game rules."""
from pathlib import Path
from array import array
import ctypes
import io
import math
import random
import wave
import pico2d.pico2d as p
from .first_person import view_axes


def rolling_sound():
    """A low stone rumble, kept in memory and looped on its own mixer channel."""
    samples = array('h')
    noise = random.Random(117)
    filtered = 0.
    rate = 22050
    for index in range(rate):
        time = index/rate
        filtered = .94*filtered+.06*noise.uniform(-1., 1.)
        envelope = math.sin(math.pi*time)**2
        value = (.34*math.sin(math.tau*45*time)+.16*math.sin(math.tau*79*time)+filtered*1.8)
        samples.append(round(12000*value*envelope))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())
    data = buffer.getvalue()
    raw = ctypes.create_string_buffer(data)
    stream = p.SDL_RWFromConstMem(raw, len(data))
    chunk = p.Mix_LoadWAV_RW(stream, 1)
    assert chunk, p.SDL_GetError()
    return p.Wav(chunk)


class Audio:
    def __init__(self,root):
        self.step=self.blade=None
        self.previous_mode=None
        self.step_index=-1
        self.whoosh_index=-1
        self.game = None
        self.warning_played = False
        self.roll = None
        self.roll_channel = -1
        if p.audio_on:
            self.step=p.load_wav(str(Path(root)/'sound/stone_step.wav'))
            self.blade=p.load_wav(str(Path(root)/'sound/blade_pass.wav'))
            self.step.set_volume(28)
            self.blade.set_volume(20)
            self.roll = rolling_sound()

    def stop_rolling(self):
        if self.roll_channel >= 0:
            p.Mix_HaltChannel(self.roll_channel)
            self.roll_channel = -1

    def update_rolling(self, game, kind):
        if kind != 'boulder' or game.boulder_room is None or self.roll is None:
            self.stop_rolling()
            return
        room = game.boulder_room
        stone = min(room.stones, key=lambda stone: math.hypot(stone.x-room.x, stone.z-room.z))
        distance = math.hypot(stone.x-room.x, stone.z-room.z)
        if self.roll_channel < 0 or not p.Mix_Playing(self.roll_channel):
            self.roll_channel = p.Mix_PlayChannel(-1, self.roll.wav, -1)
        if self.roll_channel >= 0:
            p.Mix_Volume(self.roll_channel, round(78/(1+distance*.3)))
            c,s = view_axes(room.yaw)
            right = (stone.x-room.x)*c-(stone.z-room.z)*s
            pan = right/max(1.,distance)
            p.Mix_SetPanning(self.roll_channel, round(255*(1-max(0., pan))),
                             round(255*(1+min(0., pan))))

    def update(self,game):
        if self.game is not game:
            self.stop_rolling()
            self.game = game
            self.previous_mode = None
            self.warning_played = False
        kind = game.trap_kind if game.state == 'trap' else None
        mode = game.state, kind
        changed = self.previous_mode != mode
        if changed:
            self.step_index = int(game.trap_stride/.62) if kind == 'blade' else -1
            self.whoosh_index = -1
        if not game.phase_warning:
            self.warning_played = False
        if game.phase_warning and not self.warning_played:
            self.warning_played = True
            # 시간대 예고는 칼날 근접 판정과 독립적으로 같은 효과음을 재사용한다.
            if self.blade:
                self.blade.play()
        if game.state == 'shifting' and changed and self.step:
            self.step.play()
        self.previous_mode = mode
        self.update_rolling(game, kind)
        if kind != 'blade':
            return
        index=int(game.trap_stride/.62)
        if index!=self.step_index and self.step:
            self.step.play()
        self.step_index=index
        from .maze_model import TRAP_PLANES,TRAP_LENGTH
        near=[i for i,z in enumerate(TRAP_PLANES) if abs(z-game.trap_progress)*TRAP_LENGTH<.8]
        if near and near[0]!=self.whoosh_index:
            self.whoosh_index=near[0]
            if self.blade: self.blade.play()

    def close(self):
        self.stop_rolling()
        self.roll = None
        self.step=self.blade=None
