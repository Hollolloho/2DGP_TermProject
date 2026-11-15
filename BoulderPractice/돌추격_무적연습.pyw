"""Double-click to launch the separate playable practice room."""
import ctypes
import sys
import traceback
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
try:
    from BoulderPractice.boulder_practice import main

    main()
except Exception:
    text=traceback.format_exc()
    folder=root/'output/boulder_practice'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'error.log').write_text(text,encoding='utf-8')
    ctypes.windll.user32.MessageBoxW(None,'실행 오류가 발생했습니다.\noutput/boulder_practice/error.log를 확인해 주세요.','돌 추격 무적 연습',16)
