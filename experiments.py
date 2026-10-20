"""Reproducible inputs and measurements for AI solver evaluation."""

import gc
import random
import statistics
import time
import tracemalloc

from config import ROWS, COLS, MINES
from minesweeper_game import MinesweeperGame


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


def validate_result(game, cells):
    """
    Kiểm tra kết quả AI:
    - Tất cả ô được trả về phải thực sự an toàn
    - Không có ô an toàn nào bị bỏ sót trong phạm vi suy luận
    """
    if not cells:
        return True
    
    # Kiểm tra tất cả ô đều an toàn
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
    - safe_cells_found: số ô an toàn tìm được
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
    
    for result in game.start_ai(algorithm):
        # start_ai có thể yield:
        #   - (cell): ô chắc chắn an toàn.
        #   - ("mine", cell): cờ mìn.
        #   - ("guess", cell): đoán của HillClimbing.
        #   - ("unknown", cell): không đủ bằng chứng (DFS).
        # Chỉ tính những ô thực sự là "safe" (yield dạng thuần tuple).
        if isinstance(result, tuple) and len(result) == 2 and result[0] in ("mine", "guess", "unknown"):
            continue
        safe_cells.append(result)
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
    
    for algorithm in ("DFS", "A*"):
        samples = [row for row in rows if row["algorithm"] == algorithm]
        if samples:
            valid_count = sum(1 for row in samples if row["valid_result"])
            expanded_list = [row["expanded_nodes"] for row in samples if row["expanded_nodes"]]
            generated_list = [row["generated_nodes"] for row in samples if row["generated_nodes"]]
            
            summaries.append({
                "algorithm": algorithm,
                "runs": len(samples),
                "valid_results": valid_count,
                "median_planning_ms": statistics.median(row["planning_ms"] for row in samples),
                "median_python_peak_kib": statistics.median(row["python_peak_kib"] for row in samples),
                "median_expanded_nodes": statistics.median(expanded_list) if expanded_list else None,
                "median_generated_nodes": statistics.median(generated_list) if generated_list else None,
                "total_safe_cells": sum(row["safe_cells_found"] for row in samples),
            })
    
    return summaries
