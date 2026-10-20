"""Reproducible inputs and measurements for AI solver evaluation."""

import gc
import os
import random
import statistics
import sys
import time
import tracemalloc

# Make sure src/ is on the path regardless of cwd
_THIS = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_THIS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from config import ROWS, COLS, MINES
from minesweeper_game import MinesweeperGame
# Ensure HillClimbingSolver is registered so start_ai("HillClimbing") works
from hill_climbing import HillClimbingSolver  # noqa: F401


def make_game(seed):
    """
    Tạo bàn cờ có thể lặp lại (deterministic).
    Giữ nguyên global random state.
    """
    if ROWS <= 0 or COLS <= 0 or not 0 <= MINES < ROWS * COLS:
        raise ValueError("Cần ROWS, COLS > 0 và 0 <= MINES < ROWS * COLS.")

    saved = random.getstate()
    try:
        random.seed(seed)
        game = MinesweeperGame()
        game.new_game()
        return game
    finally:
        random.setstate(saved)


def validate_result(game, cells, allow_guesses=False):
    """
    Kiểm tra kết quả AI:
    - Tất cả ô được trả về phải thực sự an toàn
    - Không có ô an toàn nào bị bỏ sót trong phạm vi suy luận

    ``allow_guesses=False`` (mặc định): tất cả cell phải là safe.
    ``allow_guesses=True``: cho phép guess có thể sai (hill climbing).
    """
    if not cells:
        return True

    for cell in cells:
        if cell in game.engine.mine_positions:
            return False

    return True


def measure_once(seed, algorithm):
    """
    Đo lường một lần chạy thuật toán.

    Trả về:
    - seed, rows, cols, mines
    - algorithm
    - planning_ms: thời gian lập kế hoạch (ms)
    - expanded_nodes: số trạng thái đã mở rộng
    - generated_nodes: số trạng thái đã sinh
    - safe_cells_found: số ô an toàn tìm được (chỉ từ propagation, không tính guess)
    - guesses_made: số nước đoán (Hill Climbing)
    - steps_taken: số ô đã mở thực sự
    - valid_result: kết quả có hợp lệ không
    - status: trạng thái cuối cùng
    """
    game = make_game(seed)

    # Chạy solver và đo thời gian
    gc.collect()
    start = time.perf_counter()

    safe_cells = []
    expanded = 0
    generated = 0
    guesses_made = 0
    propagated_safe = 0

    for result in game.start_ai(algorithm):
        # start_ai yield:
        #   - ("safe", cell): ô an toàn (từ propagation hoặc DFS).
        #   - ("mine", cell): cờ mìn.
        #   - ("guess", cell): nước đoán (Hill Climbing).
        #   - ("unknown", cell): không đủ bằng chứng (DFS).
        #   - ("prop_done", None): propagation kết thúc.
        if isinstance(result, tuple) and len(result) == 2:
            tag, val = result
            if tag == "mine":
                continue
            elif tag == "guess":
                guesses_made += 1
                safe_cells.append(val)
            elif tag == "unknown":
                continue
            elif tag == "prop_done":
                continue
            elif tag == "safe":
                safe_cells.append(val)
                propagated_safe += 1
            else:
                # tag is not a recognized string, val might be cell
                if isinstance(val, tuple):
                    safe_cells.append(val)
        else:
            # Bare cell tuple (legacy fallback)
            safe_cells.append(result)
            propagated_safe += 1

        expanded = game.stats.get("expanded_nodes", 0)
        generated = game.stats.get("generated_nodes", 0)

    elapsed_ms = (time.perf_counter() - start) * 1000
    valid = validate_result(game, safe_cells)

    # Đo bộ nhớ (tách riêng để không ảnh hưởng timing)
    memory_game = make_game(seed)
    gc.collect()
    tracemalloc.start()
    try:
        for _ in memory_game.start_ai(algorithm):
            pass
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return {
        "seed": seed,
        "rows": ROWS,
        "cols": COLS,
        "mines": MINES,
        "algorithm": algorithm,
        "planning_ms": elapsed_ms,
        "python_peak_kib": peak / 1024,
        "expanded_nodes": expanded,
        "generated_nodes": generated,
        "safe_cells_found": len(safe_cells),
        "guesses_made": guesses_made,
        "propagated_safe": propagated_safe,
        "valid_result": valid,
        "status": "valid" if valid else "invalid",
        "backend_mode": "ai_reasoning",
    }


def run_trials(seeds, repeats=3):
    """Chạy nhiều lần thí nghiệm."""
    if repeats < 1:
        raise ValueError("repeats phải >= 1")

    rows = []
    for seed in seeds:
        for algorithm in ("DFS", "HillClimbing"):
            for repeat in range(repeats):
                row = measure_once(seed, algorithm)
                row["repeat"] = repeat + 1
                rows.append(row)

    return rows


def summarize(rows):
    """Tổng hợp kết quả theo thuật toán."""
    summaries = []

    for algorithm in ("DFS", "HillClimbing"):
        samples = [row for row in rows if row["algorithm"] == algorithm]
        if samples:
            valid_count = sum(1 for row in samples if row["valid_result"])
            expanded_list = [row["expanded_nodes"] for row in samples if row["expanded_nodes"]]
            generated_list = [row["generated_nodes"] for row in samples if row["generated_nodes"]]
            guesses_list = [row.get("guesses_made", 0) for row in samples if row["algorithm"] == "HillClimbing"]

            summaries.append({
                "algorithm": algorithm,
                "runs": len(samples),
                "valid_results": valid_count,
                "median_planning_ms": statistics.median(row["planning_ms"] for row in samples),
                "median_python_peak_kib": statistics.median(row["python_peak_kib"] for row in samples),
                "median_expanded_nodes": statistics.median(expanded_list) if expanded_list else None,
                "median_generated_nodes": statistics.median(generated_list) if generated_list else None,
                "total_safe_cells": sum(row["safe_cells_found"] for row in samples),
                "total_guesses": sum(row.get("guesses_made", 0) for row in samples),
                "valid_runs": valid_count,
            })

    return summaries
