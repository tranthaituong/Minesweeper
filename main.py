"""Pygame entry point. Run: python main.py"""

try:
    from minesweeper_gui import MinesweeperGUI
except ModuleNotFoundError as exc:
    if exc.name != "pygame":
        raise
    raise SystemExit("Chưa có Pygame. Chạy: python -m pip install -r requirements.txt") from exc


if __name__ == "__main__":
    MinesweeperGUI().run()
