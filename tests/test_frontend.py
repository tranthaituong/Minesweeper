"""State-transition and benchmark checks; no desktop window is opened."""

import csv
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
from benchmark import run_benchmark
from experiments import make_game
from minesweeper_gui import MinesweeperGUI
from rendering import enable_real_highdpi, app_icon


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.app = MinesweeperGUI(seed=7)
        self.app.draw()

    def tearDown(self):
        self.app.close()

    def finish_planning(self):
        deadline = time.monotonic() + 3
        while self.app.pending is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.002)
        self.assertIsNone(self.app.pending, "Planning did not finish")

    def test_step_opens_exactly_one_cell(self):
        self.app.step()
        self.finish_planning()
        self.assertEqual(self.app.safe_opened, 1)
        self.assertFalse(self.app.playing)
        self.app.step()
        self.assertEqual(self.app.safe_opened, 2)

    def test_pause_stops_and_step_stays_paused(self):
        self.app.step()
        self.finish_planning()
        self.app.toggle_play()
        self.app.update()
        self.app.toggle_play()
        count = self.app.safe_opened
        self.app.next_tick = 0
        self.app.update()
        self.assertEqual(self.app.safe_opened, count)
        self.app.step()
        self.assertEqual(self.app.safe_opened, count+1)
        self.assertFalse(self.app.playing)

    def test_reset_keeps_mines_and_clears_flags_clock_and_plan(self):
        original = set(self.app.game.mine_positions)
        self.app.toggle_flag(min(original))
        self.app.step()
        self.finish_planning()
        self.app.reset_board()
        self.assertEqual(self.app.game.mine_positions, original)
        self.assertEqual(len(self.app.game.revealed), 0)
        self.assertEqual(len(self.app.game.flags), 0)
        self.assertEqual(self.app.game.ai_path, [])
        self.assertEqual(self.app.elapsed(), 0)

    def test_new_board_can_return_to_identical_seed(self):
        original = set(self.app.game.mine_positions)
        self.app.new_board()
        self.assertEqual(self.app.seed, 8)
        self.app.new_board(7)
        self.assertEqual(self.app.game.mine_positions, original)

    def test_flags_block_manual_reveal_and_ai_without_consuming_step(self):
        self.app.step()
        self.finish_planning()
        index = self.app.game.ai_index
        target = self.app.game.ai_path[index]
        self.app.toggle_flag(target)
        self.app.player_reveal(target)
        self.assertNotIn(target, self.app.game.revealed)
        self.app.step()
        self.assertEqual(self.app.game.ai_index, index)
        self.assertNotIn(target, self.app.game.revealed)
        self.app.toggle_flag(target)
        self.app.step()
        self.assertIn(target, self.app.game.revealed)

    def test_ai_solver_finds_safe_cells(self):
        """AI suy luận phải tìm được ít nhất 1 ô an toàn sau khi mở ô đầu tiên."""
        for algorithm in ("DFS", "HillClimbing"):
            self.app.reset_board()
            self.app.choose_algorithm(algorithm)
            self.app.step()
            self.finish_planning()
            # AI phải tìm được ít nhất 1 ô
            self.assertGreater(len(self.app.game.ai_path), 0, f"{algorithm} should find at least 1 safe cell")
            # Ô đầu tiên phải an toàn (đã được mở)
            self.assertGreater(self.app.safe_opened, 0)
            self.app.draw()

    def test_manual_mine_stops_playback(self):
        self.app.player_reveal(min(self.app.game.mine_positions))
        self.assertTrue(self.app.game.game_over)
        self.assertFalse(self.app.game.won)
        self.assertFalse(self.app.playing)
        self.assertIsNotNone(self.app.finished_seconds)
        self.app.draw()

    def test_manual_open_invalidates_ai_plan(self):
        self.app.step()
        self.finish_planning()
        target = self.app.game.ai_path[self.app.game.ai_index]
        self.app.player_reveal(target)
        self.assertEqual(self.app.game.ai_path, [])
        self.assertIn(target, self.app.game.revealed)
        self.app.step()
        self.finish_planning()
        self.assertGreaterEqual(self.app.safe_opened, 1)

    def test_reset_discards_inflight_plan(self):
        release, started = threading.Event(), threading.Event()
        compute = self.app._compute_plan
        def delayed(snapshot, algorithm):
            started.set()
            release.wait(2)
            return compute(snapshot, algorithm)
        self.app._compute_plan = delayed
        self.app.step()
        future = self.app.pending
        try:
            self.assertTrue(started.wait(1))
            self.app.reset_board()
        finally:
            release.set()
        future.result(timeout=3)
        self.app.update()
        self.assertEqual(len(self.app.game.revealed), 0)
        self.assertEqual(self.app.game.ai_path, [])

    def test_mouse_mapping_after_resize(self):
        self.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=640, h=480))
        self.app.draw()
        safe = next(cell for cell in self.app.game.numbers if cell not in self.app.game.mine_positions)
        board, tile = self.app.board_geometry()
        virtual = board.x+(safe[1]+.5)*tile, board.y+(safe[0]+.5)*tile
        position = (round(self.app.viewport.x+virtual[0]*self.app.scale),
                    round(self.app.viewport.y+virtual[1]*self.app.scale))
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=3))
        self.assertIn(safe, self.app.game.flags)
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=3))
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=1))
        self.assertIn(safe, self.app.game.revealed)

    def test_retina_rasterizes_fonts_at_physical_pixel_size(self):
        base_height = self.app.font(20).get_height()
        self.app.draw(drawable_size=(2320, 1640), present=False)
        self.assertEqual(self.app.canvas.get_size(), (2320, 1640))
        self.assertEqual(self.app.render_scale, 2)
        self.assertAlmostEqual(self.app.font(20).get_height(), base_height*2, delta=2)

    def test_retina_mouse_coordinates_remain_in_window_points(self):
        self.app.draw(drawable_size=(2320, 1640), present=False)
        board, tile = self.app.board_geometry()
        position = board.x+tile//2, board.y+tile//2
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=3))
        self.assertIn((0, 0), self.app.game.flags)

    def test_render_does_not_upscale_a_finished_frame(self):
        with patch("pygame.transform.smoothscale", side_effect=AssertionError("Bitmap upscaling")):
            self.app.display.resize((1370, 920))
            self.app.draw(drawable_size=(2740, 1840), present=False)
        self.assertEqual(self.app.canvas.get_size(), (2740, 1840))
        self.assertAlmostEqual(self.app.render_scale, 1840/820)

    def test_ui_benchmark_finishes_and_writes_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.app.benchmark_dir = Path(temporary)
            self.app.start_benchmark()
            deadline = time.monotonic()+15
            while self.app.benchmark_process is not None and time.monotonic() < deadline:
                self.app.update()
                time.sleep(.01)
            self.assertIsNone(self.app.benchmark_process)
            self.assertTrue((Path(temporary)/"by_input.csv").is_file())


class BenchmarkTests(unittest.TestCase):
    def test_seed_generation_preserves_global_random_state(self):
        state = random.getstate()
        first = make_game(9)
        self.assertEqual(state, random.getstate())
        self.assertEqual(first.mine_positions, make_game(9).mine_positions)

    def test_benchmark_produces_valid_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_benchmark(temporary, seeds=2, repeats=2, start_seed=11)
            with (Path(temporary)/"raw.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 8)
            self.assertEqual({row["seed"] for row in rows}, {"11", "12"})
            # AI reasoning mode - results depend on board state
            self.assertTrue(all(row["valid_result"] == "True" for row in rows))
            # expanded_nodes and generated_nodes should be available
            self.assertTrue(all(row["expanded_nodes"] != "" for row in rows))
            self.assertTrue(all(row["generated_nodes"] != "" for row in rows))
            self.assertTrue(all(float(row["planning_ms"]) >= 0 for row in rows))
            self.assertTrue(all(row["valid_results"] == 4 for row in summary))
            with (Path(temporary)/"by_input.csv").open(encoding="utf-8-sig") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)
            metadata = json.loads((Path(temporary)/"metadata.json").read_text())
            self.assertIn("ai_reasoning", metadata.get("backend_mode", ""))


class DisplayRegressionTests(unittest.TestCase):
    def test_zero_enum_in_pygame_wheel_is_repaired(self):
        class BrokenWindow:
            _kwarg_to_flag = {"allow_highdpi": 0, "resizable": 32}
        enable_real_highdpi(BrokenWindow)
        self.assertEqual(BrokenWindow._kwarg_to_flag["allow_highdpi"], 0x2000)
        self.assertEqual(BrokenWindow._kwarg_to_flag["resizable"], 32)

    def test_existing_valid_highdpi_flag_is_preserved(self):
        class WorkingWindow:
            _kwarg_to_flag = {"allow_highdpi": 0x2000}
        flags = WorkingWindow._kwarg_to_flag
        enable_real_highdpi(WorkingWindow)
        self.assertIs(WorkingWindow._kwarg_to_flag, flags)
        self.assertEqual(flags["allow_highdpi"], 0x2000)

    def test_icon_has_large_native_bitmap(self):
        pygame.font.init()
        try:
            self.assertEqual(app_icon().get_size(), (512, 512))
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
