"""Pygame entry point. Run: python main.py"""

import os
import sys

# Ensure src/ is importable no matter where we run from
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from minesweeper_gui import MinesweeperGUI
except ModuleNotFoundError as exc:
    if exc.name != "pygame":
        raise
    raise SystemExit("Chưa có Pygame. Chạy: python -m pip install -r requirements.txt") from exc


if __name__ == "__main__":
    MinesweeperGUI().run()
