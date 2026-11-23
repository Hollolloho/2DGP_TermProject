"""구판 좌표를 전제로 한 조작 기하·픽셀 회귀를 그대로 보존하는 검사용 판."""
from contextlib import ExitStack
from functools import wraps
import sys
from unittest.mock import patch
from SourceCode import mouse_maze

LEGACY = dict(BOARD=(66,134,34),START_CELL=(1,1),GOAL_CELL=(7,1),WAYPOINTS=(),
              MAZE=('#########','#S..#..G#','###.#.###','#.....###','#########'))


def legacy_mouse_maze(function):
    @wraps(function)
    def run(*args,**kwargs):
        modules = [mouse_maze,sys.modules[function.__module__]]
        if 'SourceCode.game_view' in sys.modules:
            modules.append(sys.modules['SourceCode.game_view'])
        with ExitStack() as stack:
            for module in modules:
                for key,value in LEGACY.items():
                    if hasattr(module,key):stack.enter_context(patch.object(module,key,value))
            return function(*args,**kwargs)
    return run
