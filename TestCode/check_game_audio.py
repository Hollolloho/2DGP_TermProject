"""방 종류 전환·발걸음·칼날 근접음과 공통 시간대 예고음의 재생 호출 검사."""
from pathlib import Path
from unittest.mock import patch

import pico2d.pico2d as p
from SourceCode.game_audio import Audio
from SourceCode.maze_model import Game, TRAP_PLANES


class SoundCount:
    def __init__(self):
        self.calls = 0

    def play(self):
        self.calls += 1


def run():
    with patch.object(p, 'audio_on', False):
        audio = Audio(Path(__file__).resolve().parents[1])
    step, shared_sample = SoundCount(), SoundCount()
    audio.step, audio.blade = step, shared_sample
    game = Game(117)
    assert game.trap_kind == 'blade'
    audio.update(game)
    game.player.x, game.player.y = game.trap_cell[0]+.5, game.trap_cell[1]+.5
    game.interact()
    assert game.state == 'trap' and game.trap_kind == 'blade'
    audio.update(game)
    assert step.calls == shared_sample.calls == 0
    game.trap_stride = .63
    game.trap_progress = TRAP_PLANES[0]
    for _ in range(4):
        audio.update(game)
    assert step.calls == shared_sample.calls == 1
    assert audio.whoosh_index == 0

    # 방 연결 전에도 같은 Game의 종류 메타데이터를 바꿔 오디오 경계를 검사한다.
    game.trap_kind = 'boulder'
    game.trap_stride = 10.
    audio.update(game)
    assert audio.step_index == audio.whoosh_index == -1
    for index, plane in enumerate(TRAP_PLANES):
        game.trap_progress, game.trap_stride = plane, 20.+index
        audio.update(game)
    assert step.calls == shared_sample.calls == 1, 'boulder emitted blade/stride sounds'

    # 동일한 blade_pass.wav라도 공통 시간대 예고는 한 번 재생해야 한다.
    game.phase_warning = True
    for _ in range(4):
        audio.update(game)
    assert shared_sample.calls == 2 and audio.whoosh_index == -1
    assert step.calls == 1
    game.trap_kind = 'blade'
    game.trap_progress, game.trap_stride = TRAP_PLANES[0], 30.
    for _ in range(4):
        audio.update(game)
    assert shared_sample.calls == 3, 'blade re-entry must reset proximity, not replay phase warning'
    assert step.calls == 1 and audio.step_index == int(30./.62)
    game.trap_stride += .63
    game.trap_progress = TRAP_PLANES[2]
    audio.update(game)
    assert step.calls == 2 and shared_sample.calls == 4
    print('PASS: blade -> boulder -> blade resets stride/proximity; same sample keeps warning and blade events separate.')

    game.trap_kind = 'boulder'
    audio.update(game)
    assert audio.step_index == audio.whoosh_index == -1
    game.phase_warning = False
    audio.update(game)
    game.phase_warning = True
    for _ in range(3):
        audio.update(game)
    assert shared_sample.calls == 5 and step.calls == 2
    game.start_shift()
    for _ in range(3):
        audio.update(game)
    assert step.calls == 3 and shared_sample.calls == 5
    assert audio.step_index == audio.whoosh_index == -1

    fresh = Game(117, 1)
    audio.update(fresh)
    assert not audio.warning_played and audio.step_index == audio.whoosh_index == -1
    fresh.player.x, fresh.player.y = fresh.trap_cell[0]+.5, fresh.trap_cell[1]+.5
    fresh.interact()
    fresh.trap_progress = TRAP_PLANES[0]
    fresh.phase_warning = True
    for _ in range(4):
        audio.update(fresh)
    assert step.calls == 3 and shared_sample.calls == 7, 'new game must emit warning and blade entry once each'
    fresh.return_from_trap()
    audio.update(fresh)
    assert audio.step_index == audio.whoosh_index == -1
    fresh.trap_kind = 'boulder'
    fresh.interact()
    assert fresh.trap_kind == 'blade', 'normal A entry must select blade after a different room'
    audio.update(fresh)
    assert step.calls == 3 and shared_sample.calls == 7
    audio.close()
    fresh.trap_progress = TRAP_PLANES[1]
    fresh.trap_stride = 10.
    audio.update(fresh)
    assert audio.step is audio.blade is None
    print('PASS: repeated warnings, shifting sound, new game, normal A entry and muted audio preserve event boundaries.')


if __name__ == '__main__':
    run()
