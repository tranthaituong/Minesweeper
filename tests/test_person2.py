"""Integration checks for the frontend and measurement boundary."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import pygame
from experiments import (ObservationEngine, compute_plan, forced_cells, load_cases,
                         make_game, public_observation, _measure_local)
from minesweeper_gui import MinesweeperGUI
from rendering import app_icon, enable_real_highdpi


class MeasurementTests(unittest.TestCase):
    def test_solver_view_has_only_visible_numbers(self):
        game = make_game(0)
        observation = public_observation(game)
        view = ObservationEngine(observation)
        self.assertEqual(set(view._visible), game.revealed)
        self.assertNotIn("mine_positions", observation)
        self.assertIsNone(view.get_number(next(iter(game.mine_positions))))
        with self.assertRaises(RuntimeError):
            _ = view.mine_positions

    def test_reads_final_statistics_after_generator_completion(self):
        observation = {"rows": 1, "cols": 3, "mines": 1,
                       "numbers": [[0, 1, 1]], "flags": []}
        plan = compute_plan(observation, "DFS")
        self.assertEqual(plan["stats"]["expanded_nodes"], 8)
        self.assertEqual(plan["stats"]["generated_nodes"], 12)

    def test_guess_is_separate_from_deductions(self):
        row = _measure_local(0, "HillClimbing")
        self.assertEqual(row["safe_deductions"], 2)
        self.assertEqual(row["guesses"], 1)
        self.assertLessEqual(row["guess_hits_mine"], row["guesses"])
        self.assertGreaterEqual(row["guess_hits_mine"], 0)
        self.assertTrue(row["deductions_correct"])

    def test_all_inputs_have_consistent_clues_and_sound_deductions(self):
        for index, case in enumerate(load_cases()):
            observation = public_observation(make_game(index))
            expected_safe, expected_mines, layouts = forced_cells(observation)
            self.assertGreater(layouts, 0)
            for algorithm in ("DFS", "HillClimbing"):
                plan = compute_plan(observation, algorithm)
                for tag, cell in plan["actions"]:
                    if tag == "safe":
                        self.assertIn(cell, expected_safe, (case["id"], algorithm, cell))
                    elif tag == "mine":
                        self.assertIn(cell, expected_mines, (case["id"], algorithm, cell))


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.app = MinesweeperGUI(seed=0)
        self.app.draw()

    def tearDown(self):
        self.app.close()

    def finish_plan(self):
        deadline = time.monotonic() + 4
        while self.app.pending is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertIsNone(self.app.pending, "Solver process did not finish")

    def test_step_performs_one_action_even_when_reveal_cascades(self):
        self.app.step()
        self.finish_plan()
        self.assertEqual(len(self.app.history), 1)
        self.assertFalse(self.app.playing)
        self.assertIsNotNone(self.app.plan_ms)
        self.assertGreater(self.app.game.stats["expanded_nodes"], 0)

    def test_reset_restores_exact_initial_observation(self):
        before = public_observation(self.app.game)
        mines = set(self.app.game.mine_positions)
        self.app.step()
        self.finish_plan()
        self.app.reset_board()
        self.assertEqual(public_observation(self.app.game), before)
        self.assertEqual(self.app.game.mine_positions, mines)
        self.assertEqual(self.app.history, [])
        self.assertIsNone(self.app.started_at)

    def test_pause_during_planning_does_not_execute_action(self):
        self.app.toggle_play()
        self.assertEqual(self.app.pending_action, "play")
        self.app.toggle_play()
        self.finish_plan()
        self.assertEqual(self.app.history, [])
        self.assertFalse(self.app.playing)
        self.assertTrue(self.app.plan_remaining)

    def test_reset_cancels_running_plan(self):
        self.app.step()
        process = self.app.pending
        self.app.reset_board()
        self.assertIsNone(self.app.pending)
        self.assertFalse(process.is_alive())
        self.assertEqual(self.app.history, [])

    def test_manual_flag_invalidates_old_plan(self):
        self.app.step()
        self.finish_plan()
        if self.app.game.game_over:
            self.app.reset_board()
        cell = next(c for c in self.app.game.numbers if c not in self.app.game.revealed)
        self.app.toggle_flag(cell)
        self.assertEqual(self.app.game.ai_path, [])
        self.assertIn(cell, self.app.game.flags)

    def test_mine_action_is_visible_as_its_own_step(self):
        cell = next(iter(self.app.game.mine_positions))
        self.app.plan_actions = [("mine", cell)]
        self.app.game.ai_path = [cell]
        self.app._advance()
        self.assertIn(cell, self.app.game.flags)
        self.assertEqual(self.app.history[-1][1], "AI cắm cờ")

    def test_guess_action_keeps_guess_label(self):
        self.app.choose_algorithm("HillClimbing")
        cell = next(iter(self.app.game.mine_positions))
        self.app.plan_actions = [("guess", cell)]
        self.app.game.ai_path = [cell]
        self.app._advance()
        self.assertEqual(self.app.history[-1][1], "AI đoán")
        self.assertTrue(self.app.game.game_over)

    def test_benchmark_button_targets_root_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.app.benchmark_dir = Path(temporary)
            with patch("minesweeper_gui.subprocess.Popen") as popen:
                self.app.start_benchmark()
                command = popen.call_args.args[0]
                self.assertEqual(Path(command[1]), ROOT / "benchmark.py")
                self.assertTrue(Path(command[1]).is_file())
                self.assertEqual(command[command.index("--cases")+1], "9")
                self.app.benchmark_process = None
                self.app.benchmark_log.close()
                self.app.benchmark_log = None

    def test_resize_keeps_board_coordinates_and_retina_pixels(self):
        self.app.draw(drawable_size=(2320, 1640), present=False)
        self.assertEqual(self.app.canvas.get_size(), (2320, 1640))
        board, tile = self.app.board_geometry()
        self.assertEqual(self.app.cell_at((board.x+tile/2, board.y+tile/2)), (0, 0))
        self.assertIn("hill", self.app.buttons)
        self.assertNotIn("astar", self.app.buttons)

    def test_new_input_wraps_and_restores_its_clues(self):
        self.app.new_board(8)
        self.assertEqual(self.app.seed, 8)
        self.app.new_board()
        self.assertEqual(self.app.seed, 0)
        self.assertEqual(public_observation(self.app.game), public_observation(make_game(0)))

    def test_highdpi_flag_and_large_icon(self):
        class Window:
            _kwarg_to_flag = {"allow_highdpi": 0}
        enable_real_highdpi(Window)
        self.assertEqual(Window._kwarg_to_flag["allow_highdpi"], 0x2000)
        self.assertEqual(app_icon().get_size(), (512, 512))


if __name__ == "__main__":
    unittest.main()
