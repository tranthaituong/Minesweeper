"""Generate fixed partially revealed puzzles, stored for reproducibility."""
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from config import ROWS, COLS, MINES
from minesweeper_game import MinesweeperGame


def prepare():
    if ROWS * COLS - MINES < 4:
        raise ValueError("Bộ demo cần ít nhất bốn ô an toàn.")
    saved = random.getstate()
    cases = []
    try:
        for seed in range(9):
            random.seed(seed)
            game = MinesweeperGame()
            game.new_game()
            safe = sorted(set(game.numbers) - game.mine_positions)
            random.Random(seed + 500).shuffle(safe)
            hidden = min(ROWS * COLS - 1, MINES + (3, 6, 8)[seed % 3])
            revealed = sorted(safe[:ROWS * COLS - hidden])
            cases.append({"id": f"T{seed+1:02d}", "seed": seed,
                          "hidden_cells": ROWS * COLS - len(revealed),
                          "mine_positions": [list(c) for c in sorted(game.mine_positions)],
                          "initial_revealed": [list(c) for c in revealed], "initial_flags": []})
    finally:
        random.setstate(saved)
    data = {"rows": ROWS, "cols": COLS, "mines": MINES,
            "task": "One inference round on fixed clues; guesses labeled separately.",
            "cases": cases}
    (ROOT / "inputs.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n",
                                      encoding="utf-8")
    print(f"Đã tạo {len(cases)} input trong inputs.json")


if __name__ == "__main__":
    prepare()
