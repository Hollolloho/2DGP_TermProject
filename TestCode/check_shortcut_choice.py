"""경로 선택의 임시 선택·확정·예약 경계. SDL 없이 실행한다."""
from SourceCode.shortcut_choice import ShortcutChoice


def check_reservation():
    for phase in range(3):
        target = (phase+1)%3
        for index in (0,1):
            choice = ShortcutChoice()
            assert not choice.confirm(target) and not choice.apply_phase(target)
            for invalid in (None,True,-1,2,'0'):
                assert not choice.select(invalid)
            assert choice.select(1-index) and choice.select(index)
            assert choice.cancel() and choice.preview is None
            assert choice.select(index)
            for invalid in (None,True,-1,3,'1'):
                assert not choice.confirm(invalid)
            assert choice.confirm(target)
            assert choice.selected == index and choice.reserved_phase == target and not choice.opened
            assert not choice.select(1-index) and not choice.cancel() and not choice.confirm(target)
            for _ in range(3):
                assert choice.route_for_phase(phase) is None
                assert choice.route_for_phase(target) == index
                assert not choice.opened, '지형 미리보기가 예약을 적용했다'
            assert not choice.apply_phase(phase) and not choice.opened
            assert choice.apply_phase(target) and choice.opened
            assert choice.reserved_phase is None and not choice.apply_phase(target)
            assert all(choice.route_for_phase(later) == index for later in range(3))
            choice.reset()
            assert choice.preview is choice.selected is choice.reserved_phase is None
            assert not choice.opened and all(choice.route_for_phase(later) is None for later in range(3))
    print('PASS: both choices across all 3 starting phases; preview/cancel, confirm lock, pure layout query, one-time next-phase opening, later-phase persistence and reset.')


def run():
    check_reservation()


if __name__ == '__main__':
    run()
