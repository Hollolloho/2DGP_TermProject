"""Check retained assets and new atlas contracts; --require-complete rejects pending art."""
import argparse
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
DIRECTIONS = ('sw', 'nw', 'se', 'ne')
ATTACK_DIRECTIONS = (*DIRECTIONS, 'n', 's', 'w', 'e')
QUARTER = {
    'terrain_v1': {*(f'floor_{n}' for n in range(4)), *(f'wall_{n}' for n in range(16))},
    'props_v1': {'fountain_full', 'fountain_empty', 'rope_exit',
                 *(f'torch_wall_{side}_{state}' for side in ('left', 'right') for state in ('full', 'empty'))},
    'shortcuts_v1': {f'{state}_{side}' for state in
                     ('puzzle_closed', 'puzzle_open', 'trap_entry', 'trap_arrival')
                     for side in ('south', 'east', 'north', 'west')},
    'guardian_v1': {'idle_'+direction for direction in DIRECTIONS},
}


def png_size(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n', path
    return struct.unpack('>II', header[16:24])


def frame_check(size, rect, pivot):
    x, y, w, h = rect
    assert all(isinstance(n, int) for n in rect)
    assert x >= 0 and y >= 0 and w > 0 and h > 0
    assert x+w <= size[0] and y+h <= size[1], (size, rect)
    assert len(pivot) == 2 and 0 <= pivot[0] <= w and 0 <= pivot[1] <= h


def check_dagger(clips):
    directory = ROOT/'sprite/quarter/effects'
    effect = json.loads((directory/'dagger-slash.json').read_text(encoding='utf-8'))
    size = png_size(directory/effect['image'])
    assert set(effect['frames']) == set(ATTACK_DIRECTIONS)
    assert effect['frame_size'] == [24, 24]
    start, end = effect['window_ms']
    assert (start, end) == (233, 350)
    opacity = effect['opacity_by_attack_frame']
    assert set(opacity) == {'3', '4'} and all(0 < value <= 1 for value in opacity.values())
    for direction in ATTACK_DIRECTIONS:
        frame = effect['frames'][direction]
        assert frame['rect'][2:] == effect['frame_size'] and frame['pivot'] == [12, 12]
        frame_check(size, frame['rect'], frame['pivot'])
        clip = clips[f'attack-{direction}']
        durations, frames = clip['durations_ms'], clip['frames']
        assert clip['direction'] == direction and not clip['loop']
        assert len(frames) == len(durations) == 6 and sum(durations) == 533
        assert all(frame['rect'][2:] == [64, 64] for frame in frames)
        hit = [event for event in clip['events'] if event['name'] == 'hit']
        assert len(hit) == 1 and hit[0]['frame'] == 3
        assert hit[0]['at_ms'] == start == sum(durations[:3])
        active, tips = clip['fx_active_frames'], clip['blade_tips_px']
        assert active == [3, 4] and sum(durations[:4]) < end <= sum(durations[:5])
        assert len(tips) == len(frames)
        for index, tip in enumerate(tips):
            if tip is None:
                assert index not in active
            else:
                assert len(tip) == 2 and all(type(value) is int and 0 <= value < 64 for value in tip)


def run(require_complete=False):
    for relative in ('sprite/wall/materials/base_a.png',
                     'sprite/surfaces/materials/floor_flagstone.png',
                     'sprite/surfaces/materials/ceiling_damp.png',
                     'sprite/traps/iron_blade.png',
                     'sprite/traps/boulder_volume_v2/stone_material.png'):
        png_size(ROOT/relative)
    directory = ROOT/'sprite/topdown/effects'
    data = json.loads((directory/'torch.json').read_text(encoding='utf-8'))
    size = png_size(directory/data['meta']['image'])
    for frame in data['frames']:
        r = frame['frame']
        frame_check(size, [r[key] for key in ('x','y','w','h')], data['meta']['pixelfx']['pivot'])
    player_dir = ROOT/'sprite/quarter/player_explorer_v1'
    player = json.loads((player_dir/'explorer.json').read_text(encoding='utf-8'))
    size = png_size(player_dir/player['image'])
    for state in ('idle', 'walk', 'run', 'hurt'):
        for direction in DIRECTIONS:
            assert f'{state}-{direction}' in player['clips']
    # 선택적인 정면 4방향도 포함해 실제 프레임 수와 보행 메타를 검사한다.
    for name, clip in player['clips'].items():
        assert clip['frames'] and len(clip['frames']) == len(clip['durations_ms'])
        assert all(duration > 0 for duration in clip['durations_ms'])
        for frame in clip['frames']:
            frame_check(size, frame['rect'], player['pivot'])
        if name.startswith(('walk-', 'run-')):
            if 'cycle_distance_px' in clip:
                cycle = clip['cycle_distance_px']
                assert math.isfinite(cycle) and cycle > 0, name
            if 'phase_offset_frames' in clip:
                assert type(clip['phase_offset_frames']) is int, name
    check_dagger(player['clips'])
    dust_dir = ROOT/'sprite/traps/boulder_chase_v1'
    dust = json.loads((dust_dir/'catalog.json').read_text(encoding='utf-8'))['dust']
    size = png_size(dust_dir/dust['image'])
    for frame in dust['frames']:
        frame_check(size, frame['rect_top_left'], dust['pivot'])
    ready, pending = ['dagger-slash'], []
    for folder, names in QUARTER.items():
        directory = ROOT/'sprite/quarter'/folder
        catalog = directory/'catalog.json'
        if not catalog.is_file():
            pending.append(folder)
            continue
        data = json.loads(catalog.read_text(encoding='utf-8'))
        size = png_size(directory/data['image'])
        assert names <= data['frames'].keys(), (folder, names-data['frames'].keys())
        for frame in data['frames'].values():
            frame_check(size, frame['rect'], frame['pivot'])
        if folder == 'props_v1':
            for side in ('left', 'right'):
                full = data['frames'][f'torch_wall_{side}_full']
                empty = data['frames'][f'torch_wall_{side}_empty']
                assert full['pivot'] == empty['pivot']
                frame_check(size, full['rect'], full['wick_anchor'])
        ready.append(folder)
    room_dir = ROOT/'sprite/traps/boulder_room_v2'
    if (room_dir/'catalog.json').is_file():
        room = json.loads((room_dir/'catalog.json').read_text(encoding='utf-8'))
        for group, names in (('props', ('fallen_column','rubble')), ('exits', ('narrow','wide'))):
            assert len({entry['image'] for entry in room[group].values()}) == 1
            for name in names:
                entry = room[group][name]
                frame_check(png_size(room_dir/entry['image']), entry['rect_top_left'], entry['pivot'])
                assert len(entry['world_frame_size_metres']) == 2
                assert all(n > 0 for n in entry['world_frame_size_metres'])
                if group == 'exits':
                    left, top, right, bottom = entry['opening_uv']
                    assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
        ready.append('boulder_room_v2')
    else:
        pending.append('boulder_room_v2')
    print(json.dumps({'retained_assets_valid': True, 'ready': ready, 'pending': pending}))
    if require_complete and pending:
        raise SystemExit('Assets still pending: '+', '.join(pending))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete', action='store_true')
    run(parser.parse_args().require_complete)
