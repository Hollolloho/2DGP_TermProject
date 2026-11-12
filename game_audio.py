"""Optional local sound effects; no sound is required for the game rules."""
from pathlib import Path
import pico2d.pico2d as p


class Audio:
    def __init__(self,root):
        self.step=self.blade=None
        self.previous_mode=None
        self.step_index=-1
        self.whoosh_index=-1
        self.game = None
        self.warning_played = False
        if p.audio_on:
            self.step=p.load_wav(str(Path(root)/'sound/stone_step.wav'))
            self.blade=p.load_wav(str(Path(root)/'sound/blade_pass.wav'))
            self.step.set_volume(28)
            self.blade.set_volume(20)

    def update(self,game):
        if self.game is not game:
            self.game = game
            self.previous_mode = None
            self.warning_played = False
        if not game.phase_warning:
            self.warning_played = False
        if game.phase_warning and not self.warning_played:
            self.warning_played = True
            # 전용 음향 연결 전에는 기존 효과음을 예고·돌 움직임에 재사용한다.
            if self.blade:
                self.blade.play()
        if game.state == 'shifting' and self.previous_mode != 'shifting' and self.step:
            self.step.play()
        if game.state!='trap':
            self.previous_mode=game.state
            return
        if self.previous_mode!='trap':
            self.step_index=int(game.trap_stride/.62)
            self.whoosh_index=-1
        index=int(game.trap_stride/.62)
        if index!=self.step_index and self.step:
            self.step.play()
        self.step_index=index
        from maze_model import TRAP_PLANES,TRAP_LENGTH
        near=[i for i,z in enumerate(TRAP_PLANES) if abs(z-game.trap_progress)*TRAP_LENGTH<.8]
        if near and near[0]!=self.whoosh_index:
            self.whoosh_index=near[0]
            if self.blade: self.blade.play()
        self.previous_mode=game.state

    def close(self):
        self.step=self.blade=None
