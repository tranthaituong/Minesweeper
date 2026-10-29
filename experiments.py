"""Fixed inputs, a public-observation adapter, and one-round measurements.

The two upstream solver files in src/ are consumed without modification.
"""
import gc
import itertools
import json
import multiprocessing as mp
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from config import ROWS, COLS, MINES
from minesweeper_game import MinesweeperGame
from hill_climbing import HillClimbingSolver  # Preload both algorithms before timing.

ALGORITHMS = ("DFS", "HillClimbing")


def load_cases():
    data = json.loads((ROOT / "inputs.json").read_text(encoding="utf-8"))
    if (data["rows"], data["cols"], data["mines"]) != (ROWS, COLS, MINES):
        raise ValueError("Cấu hình đã đổi. Chạy python prepare_inputs.py để tạo lại bộ input.")
    return data["cases"]


def make_game(seed=0):
    """Initial clues belong to the input; they are not AI moves."""
    cases = load_cases()
    case = cases[seed % len(cases)]
    game = MinesweeperGame()
    engine = game.engine
    engine.mine_positions = {tuple(c) for c in case["mine_positions"]}
    engine.revealed = {tuple(c) for c in case["initial_revealed"]}
    engine.flags = {tuple(c) for c in case["initial_flags"]}
    engine._numbers = {
        (r, c): sum(n in engine.mine_positions for n in engine._neighbors((r, c)))
        for r in range(ROWS) for c in range(COLS)
    }
    return game


def public_observation(game):
    return {
        "rows": ROWS, "cols": COLS, "mines": MINES,
        "numbers": [[r, c, game.engine.get_number((r, c))]
                    for r, c in sorted(game.revealed)
                    if game.engine.get_number((r, c)) is not None],
        "flags": [list(c) for c in sorted(game.flags)],
    }


class ObservationEngine:
    """Solver view containing only visible clues and flags."""
    def __init__(self, observation):
        self._rows = observation["rows"]
        self._cols = observation["cols"]
        self._mines_count = observation["mines"]
        self.total_mines = observation["mines"]
        self._visible = {(r, c): n for r, c, n in observation["numbers"]}
        self.revealed = set(self._visible)
        self.flags = {tuple(c) for c in observation["flags"]}
        self.game_over = False
        self.won = False

    def get_number(self, cell):
        return self._visible.get(cell) if cell in self.revealed else None

    @property
    def mine_positions(self):
        raise RuntimeError("Solver đã yêu cầu vị trí mìn ẩn.")


def compute_plan(observation, algorithm):
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Thuật toán không hợp lệ: {algorithm}")
    game = MinesweeperGame()
    game.engine = ObservationEngine(observation)
    started = time.perf_counter()
    actions, unknown, seen = [], [], set()
    for tag, cell in game.start_ai(algorithm):
        if cell is not None:
            cell = tuple(cell)
        if tag in ("safe", "mine", "guess") and (tag, cell) not in seen:
            seen.add((tag, cell))
            actions.append((tag, cell))
        elif tag == "unknown":
            unknown.append(cell)
    # Facade statistics are finalized after exhausting its generator.
    elapsed = (time.perf_counter() - started) * 1000
    return {"actions": actions, "unknown": unknown, "planning_ms": elapsed,
            "stats": dict(game.stats)}


def plan_worker(connection, observation, algorithm):
    try:
        connection.send({"ok": True, "plan": compute_plan(observation, algorithm)})
    except Exception as exc:
        connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()


def forced_cells(observation):
    """Reference enumeration runs outside the measured solver calls."""
    engine = ObservationEngine(observation)
    all_cells = {(r, c) for r in range(engine._rows) for c in range(engine._cols)}
    hidden = sorted(all_cells - engine.revealed - engine.flags)
    target = engine.total_mines - len(engine.flags)
    always_mine, sometimes_mine = set(hidden), set()
    configurations = 0
    for combination in itertools.combinations(hidden, target):
        mines = set(combination) | engine.flags
        valid = True
        for (r, c), number in engine._visible.items():
            adjacent = sum((r+dr, c+dc) in mines for dr in (-1, 0, 1)
                           for dc in (-1, 0, 1) if (dr, dc) != (0, 0))
            if adjacent != number:
                valid = False
                break
        if valid:
            configurations += 1
            always_mine.intersection_update(mines)
            sometimes_mine.update(mines)
    if not configurations:
        raise ValueError("Các số và cờ của input mâu thuẫn.")
    return set(hidden) - sometimes_mine, always_mine, configurations


def _measure_local(case_index, algorithm):
    game = make_game(case_index)
    observation = public_observation(game)
    gc.collect()
    plan = compute_plan(observation, algorithm)
    gc.collect()
    tracemalloc.start()
    try:
        memory_plan = compute_plan(observation, algorithm)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if plan["actions"] != memory_plan["actions"]:
        raise RuntimeError("Hai lượt đo cùng input trả về các hành động khác nhau.")
    safe = {tuple(c) for tag, c in plan["actions"] if tag == "safe"}
    mines = {tuple(c) for tag, c in plan["actions"] if tag == "mine"}
    guesses = {tuple(c) for tag, c in plan["actions"] if tag == "guess"}
    expected_safe, expected_mines, models = forced_cells(observation)
    correct = safe <= expected_safe and mines <= expected_mines
    cases = load_cases()
    case = cases[case_index % len(cases)]
    return {
        "case_id": case["id"], "seed": case["seed"], "hidden_cells": case["hidden_cells"],
        "algorithm": algorithm, "status": "ok" if correct else "deduction_error",
        "planning_ms": plan["planning_ms"], "python_peak_kib": peak / 1024,
        "expanded_nodes": plan["stats"].get("expanded_nodes", 0),
        "generated_nodes": plan["stats"].get("generated_nodes", 0),
        "safe_deductions": len(safe), "mine_deductions": len(mines),
        "guesses": len(guesses), "guess_hits_mine": len(guesses & game.mine_positions),
        "forced_safe_total": len(expected_safe), "forced_mine_total": len(expected_mines),
        "missed_forced_safe": len(expected_safe - safe),
        "missed_forced_mines": len(expected_mines - mines),
        "consistent_layouts": models, "deductions_correct": correct,
        "search_truncated": plan["stats"].get("search_truncated", False),
    }


def _trial_worker(connection, case_index, algorithm):
    try:
        connection.send({"ok": True, "row": _measure_local(case_index, algorithm)})
    except Exception as exc:
        connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()


def measure_once(seed, algorithm, timeout=10):
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_trial_worker, args=(sender, seed, algorithm))
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise TimeoutError(f"{algorithm}: vượt {timeout:g} giây cho một lượt đo.")
        result = receiver.recv()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result["row"]
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        receiver.close()


def run_trials(seeds, repeats=3, timeout=10, progress=None):
    if repeats < 1:
        raise ValueError("repeats phải >= 1")
    rows = []
    for seed in seeds:
        for algorithm in ALGORITHMS:
            for repeat in range(1, repeats + 1):
                row = measure_once(seed, algorithm, timeout)
                row["repeat"] = repeat
                rows.append(row)
                if progress:
                    progress(row)
    return rows


def summarize(rows):
    return [{
        "algorithm": algorithm, "runs": len(samples),
        "median_planning_ms": statistics.median(r["planning_ms"] for r in samples),
        "median_python_peak_kib": statistics.median(r["python_peak_kib"] for r in samples),
        "correct_deduction_runs": sum(r["deductions_correct"] for r in samples),
        "runs_with_guess": sum(r["guesses"] > 0 for r in samples),
    } for algorithm in ALGORITHMS
       if (samples := [r for r in rows if r["algorithm"] == algorithm])]
