"""구판 5개 조각의 기하 회귀를 문양 조건과 독립적으로 보존한다."""
from functools import wraps
from unittest.mock import patch
from SourceCode import path_connection


def legacy_path_connection(function):
    @wraps(function)
    def run(*args,**kwargs):
        pieces = (('straight',1),('straight',0),('straight',1),('corner',2),('corner',0))
        with patch.multiple(path_connection,INITIAL_PIECES=pieces,RUNES=()):
            return function(*args,**kwargs)
    return run
