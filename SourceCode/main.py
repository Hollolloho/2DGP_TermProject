"""게임 실행: python -m SourceCode.main."""

if __package__:
    from .game_framework import run
else:
    # Allow launching this file directly from outside the project directory.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from SourceCode.game_framework import run


if __name__ == '__main__':
    run()
