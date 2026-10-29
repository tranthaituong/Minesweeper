"""Pygame frontend: fixed puzzles, tagged AI actions, and fair experiments."""

import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEO_HIGHDPI_DISABLED", "0")
import pygame

from config import ROWS, COLS, MINES
from experiments import ROOT, load_cases, make_game, public_observation, plan_worker
from rendering import NativeDisplay


W, H = 1160, 820
BG = "#F3F5F8"
INK = "#172B42"
MUTED = "#6C7D8F"
TEAL = "#087E83"
LINE = "#DFE6ED"
WHITE = "#FFFFFF"
NUMBER_COLORS = {1: "#2869B0", 2: "#167A60", 3: "#CC5A43", 4: "#7458A4",
                 5: "#A54F66", 6: "#087E83", 7: "#36495D", 8: "#536274"}


class MinesweeperGUI:
    def __init__(self, seed=0):
        pygame.display.init()
        pygame.font.init()
        self.display = NativeDisplay((W, H), "Minesweeper Lab | DFS & HillClimbing")
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.fonts = {}
        self.text_cache = {}
        self.render_scale = 1.0
        self.pixel_ratio = 1.0
        self.render_offset = (0, 0)
        self.buttons = {}
        self.viewport = pygame.Rect(0, 0, W, H)
        self.scale = 1.0
        self.hover = (-1, -1)
        self.running = True
        self.algorithm = "DFS"
        self.speed_index = 1
        self.intervals = (900, 450, 180)
        self.playing = False
        self.next_tick = 0
        self.plan_ms = None
        self.last_cell = None
        self.history = []
        self.notice = "Các số mở sẵn là dữ kiện của input. Chọn DFS hoặc Hill Climbing, rồi bấm Step."
        self.case_count = len(load_cases())
        self.seed = seed % self.case_count
        self.game = make_game(self.seed)
        self.plan_actions = []
        self.started_at = None
        self.finished_seconds = None
        self.generation = 0
        self.context = mp.get_context("spawn")
        self.plan_pipe = None
        self.plan_started = None
        self.pending = None
        self.pending_generation = None
        self.pending_action = None
        self.benchmark_process = None
        self.benchmark_log = None
        self.benchmark_notice = "9 input cố định · 3 lần / thuật toán"
        self.benchmark_dir = ROOT / "benchmark_results"
        self.benchmark_started = False

    def font(self, size=16, bold=False):
        pixel_size = max(1, round(size * self.render_scale))
        key = pixel_size, bold
        if key not in self.fonts:
            # Avoid scanning every installed font, which is slow on some Macs.
            suffix = "Arial Bold.ttf" if bold else "Arial.ttf"
            linux = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            windows = "arialbd.ttf" if bold else "arial.ttf"
            candidates = [Path("/System/Library/Fonts/Supplemental") / suffix,
                          Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / windows,
                          Path("/usr/share/fonts/truetype/dejavu") / linux]
            font_path = next((str(path) for path in candidates if path.is_file()), None)
            self.fonts[key] = pygame.font.Font(font_path, pixel_size)
            if font_path is None:
                self.fonts[key].set_bold(bold)
        return self.fonts[key]

    def text(self, text, pos, size=16, color=INK, bold=False, center=False):
        key = str(text), round(size * self.render_scale), color, bold
        if key not in self.text_cache:
            if len(self.text_cache) >= 512:
                self.text_cache.clear()
            self.text_cache[key] = self.font(size, bold).render(str(text), True, color)
        rendered = self.text_cache[key]
        point = self.pixel_point(pos)
        rect = rendered.get_rect(center=point) if center else rendered.get_rect(topleft=point)
        self.canvas.blit(rendered, rect)
        return rect

    def wrapped(self, text, rect, size=15, color=MUTED, line_height=22):
        words = text.split()
        line = ""
        y = rect.y
        for word in words:
            candidate = f"{line} {word}".strip()
            if self.font(size).size(candidate)[0] > rect.width * self.render_scale and line:
                self.text(line, (rect.x, y), size, color)
                y += line_height
                line = word
            else:
                line = candidate
        if line:
            self.text(line, (rect.x, y), size, color)
        return y + line_height

    def card(self, rect, color=WHITE, border=None, radius=16):
        rect = pygame.Rect(rect)
        pixel_rect = self.pixel_rect(rect)
        pixel_radius = max(0, round(radius * self.render_scale))
        pygame.draw.rect(self.canvas, color, pixel_rect, border_radius=pixel_radius)
        if border:
            pygame.draw.rect(self.canvas, border, pixel_rect,
                             width=max(1, round(self.render_scale)), border_radius=pixel_radius)
        return rect

    def pixel_point(self, pos):
        return (round(pos[0]*self.render_scale + self.render_offset[0]),
                round(pos[1]*self.render_scale + self.render_offset[1]))

    def pixel_rect(self, rect):
        rect = pygame.Rect(rect)
        x1, y1 = self.pixel_point(rect.topleft)
        x2, y2 = self.pixel_point(rect.bottomright)
        return pygame.Rect(x1, y1, max(1, x2-x1), max(1, y2-y1))

    def line(self, color, start, end, width=1):
        pygame.draw.line(self.canvas, color, self.pixel_point(start), self.pixel_point(end),
                         max(1, round(width*self.render_scale)))

    def circle(self, color, center, radius):
        pygame.draw.circle(self.canvas, color, self.pixel_point(center),
                           max(1, round(radius*self.render_scale)))

    def _prepare_frame(self, drawable_size=None):
        width, height = self.display.window_size
        self.scale = min(width / W, height / H)
        size = max(1, round(W*self.scale)), max(1, round(H*self.scale))
        self.viewport = pygame.Rect((width-size[0])//2, (height-size[1])//2, *size)
        pixel_width, pixel_height = drawable_size or self.display.pixel_size
        self.pixel_ratio = min(pixel_width/max(1, width), pixel_height/max(1, height))
        new_scale = min(pixel_width/W, pixel_height/H)
        if abs(new_scale-self.render_scale) > .0001:
            self.fonts.clear()
            self.text_cache.clear()
        self.render_scale = new_scale
        self.render_offset = ((pixel_width-W*new_scale)/2, (pixel_height-H*new_scale)/2)
        if self.canvas.get_size() != (pixel_width, pixel_height):
            self.canvas = pygame.Surface((pixel_width, pixel_height))

    def button(self, name, rect, label, callback, primary=False, enabled=True, active=False):
        rect = pygame.Rect(rect)
        hovered = rect.collidepoint(self.hover) and enabled
        if not enabled:
            fill, color = "#EDF0F3", "#9AA7B4"
        elif primary:
            fill, color = ("#066A6F" if hovered else TEAL), WHITE
        elif active:
            fill, color = "#E2F2F0", TEAL
        else:
            fill, color = ("#EAF0F5" if hovered else "#F1F4F7"), INK
        self.card(rect, fill, radius=9)
        self.text(label, rect.center, 15, color, True, center=True)
        self.buttons[name] = rect, callback, enabled

    @property
    def safe_opened(self):
        return len(self.game.revealed - self.game.mine_positions)

    @property
    def safe_total(self):
        return ROWS * COLS - MINES

    @property
    def plan_remaining(self):
        return self.game.ai_index < len(self.game.ai_path)

    def elapsed(self):
        if self.finished_seconds is not None:
            return self.finished_seconds
        return time.monotonic() - self.started_at if self.started_at is not None else 0

    def _start_clock(self):
        if self.started_at is None:
            self.started_at = time.monotonic()

    def _invalidate_plan(self):
        self.generation += 1
        if self.pending is not None:
            if self.pending.is_alive():
                self.pending.terminate()
            self.pending.join(timeout=1)
        if self.plan_pipe is not None:
            self.plan_pipe.close()
        self.pending = None
        self.plan_pipe = None
        self.pending_action = None
        self.game.ai_path = []
        self.game.ai_index = 0
        self.plan_actions = []
        self.plan_ms = None
        self.game.stats = {}
        self.playing = False

    def reset_board(self):
        """Restore the exact initial clues as well as the mine layout."""
        self._invalidate_plan()
        self.game = make_game(self.seed)
        self.last_cell = None
        self.history.clear()
        self.started_at = None
        self.finished_seconds = None
        self.notice = "Đã khôi phục dữ kiện ban đầu. Chọn thuật toán để chạy lại cùng input."

    def new_board(self, seed=None):
        self.seed = (self.seed + 1 if seed is None else seed) % self.case_count
        self.reset_board()
        self.notice = f"Input T{self.seed+1:02d}: các số mở sẵn là dữ kiện cho cả hai thuật toán."

    def choose_algorithm(self, algorithm):
        if algorithm == self.algorithm:
            return
        self._invalidate_plan()
        self.algorithm = algorithm
        self.notice = f"Đã chọn {algorithm}. Reset để so sánh từ cùng trạng thái ban đầu."

    def _request_plan(self, action):
        if self.pending is not None or self.game.game_over:
            return
        self.pending_action = action
        self.pending_generation = self.generation
        self.plan_pipe, sender = self.context.Pipe(duplex=False)
        self.pending = self.context.Process(target=plan_worker,
            args=(sender, public_observation(self.game), self.algorithm))
        self.pending.start()
        sender.close()
        self.plan_started = time.monotonic()
        self.notice = f"Đang suy luận bằng {self.algorithm}…"

    def step(self):
        if self.game.game_over or self.pending is not None:
            return
        self.playing = False
        if not self.plan_remaining:
            self._request_plan("step")
        else:
            self._advance()

    def toggle_play(self):
        if self.game.game_over:
            return
        if self.pending is not None:
            self.pending_action = "pause" if self.pending_action == "play" else "play"
            self.notice = "Đã tạm dừng." if self.pending_action == "pause" else "Sẽ chạy khi lập kế hoạch xong."
        elif self.playing:
            self.playing = False
            self.notice = "Đã tạm dừng. Bấm Step để xem từng hành động hoặc Play để tiếp tục."
        elif self.plan_remaining:
            self.playing = True
            self.next_tick = pygame.time.get_ticks() + self.intervals[self.speed_index]
        else:
            self._request_plan("play")

    def _advance(self):
        while self.plan_remaining:
            tag, cell = self.plan_actions[self.game.ai_index]
            if cell in self.game.revealed or (tag == "mine" and cell in self.game.flags):
                self.game.ai_index += 1
                continue
            if tag != "mine" and cell in self.game.flags:
                self.playing = False
                self.notice = f"Ô ({cell[0]+1}, {cell[1]+1}) đang có cờ. Bỏ cờ để mở ô này."
                return
            if tag == "mine" and len(self.game.flags) >= MINES:
                self.playing = False
                self.notice = "Đã hết cờ. Kiểm tra các cờ đang có trên bàn."
                return
            self.game.ai_index += 1
            self._start_clock()
            if tag == "mine":
                self.game.flags.add(cell)
                self.last_cell = cell
                self.history.append((cell, "AI cắm cờ", -1))
                self.notice = f"AI xác định mìn tại ({cell[0]+1}, {cell[1]+1}) và cắm cờ."
            else:
                self._reveal(cell, "AI đoán" if tag == "guess" else "AI suy luận")
            return
        self.playing = False
        if not self.game.game_over:
            self.notice = "Đã trình bày hết vòng suy luận. Bấm Step hoặc Play để phân tích trạng thái mới."

    def _reveal(self, cell, source):
        self.game.reveal(cell, source=source)
        self.last_cell = cell
        number = self.game.numbers[cell]
        self.history.append((cell, source, number))
        if self.game.game_over:
            self.playing = False
            self.finished_seconds = self.elapsed()
            if self.game.won:
                self.notice = "Hoàn thành! Đã mở toàn bộ ô an toàn. Reset để chạy lại cùng bàn."
            else:
                self.notice = "Trúng mìn! Các vị trí mìn đã được hiện. Reset để thử lại."
        else:
            self.notice = f"{source} mở ô ({cell[0]+1}, {cell[1]+1}) · {number} mìn xung quanh."

    def player_reveal(self, cell):
        if self.game.game_over or cell in self.game.revealed or cell in self.game.flags:
            return
        self._invalidate_plan()
        self._start_clock()
        self._reveal(cell, "Bạn")

    def toggle_flag(self, cell):
        if self.game.game_over or cell in self.game.revealed:
            return
        self._invalidate_plan()
        if cell in self.game.flags:
            self.game.flags.remove(cell)
            self.notice = f"Đã bỏ cờ ở ô ({cell[0]+1}, {cell[1]+1})."
        elif len(self.game.flags) < MINES:
            self.game.flags.add(cell)
            self._start_clock()
            self.notice = f"Đã cắm cờ ở ô ({cell[0]+1}, {cell[1]+1})."
        else:
            self.notice = "Đã dùng hết cờ. Bỏ một cờ trước khi đánh dấu ô khác."

    def cycle_speed(self):
        self.speed_index = (self.speed_index + 1) % len(self.intervals)

    def start_benchmark(self):
        if self.benchmark_process is not None:
            return
        self._invalidate_plan()
        self.benchmark_dir.mkdir(parents=True, exist_ok=True)
        self.benchmark_log = (self.benchmark_dir / "run.log").open("w", encoding="utf-8")
        command = [sys.executable, str(ROOT / "benchmark.py"), "--cases", "9",
                   "--repeats", "3", "--output", str(self.benchmark_dir)]
        try:
            self.benchmark_process = subprocess.Popen(command, cwd=ROOT,
                stdout=self.benchmark_log, stderr=subprocess.STDOUT)
        except OSError as exc:
            self.benchmark_log.close()
            self.benchmark_log = None
            self.notice = f"Không chạy được benchmark: {exc}"
            return
        self.benchmark_started = True
        self.benchmark_notice = "Đang đo 54 lượt · xem tiến độ trong run.log"

    def update(self):
        if self.pending is not None:
            if self.plan_pipe.poll():
                process, connection = self.pending, self.plan_pipe
                action, generation = self.pending_action, self.pending_generation
                self.pending = self.plan_pipe = None
                self.pending_action = None
                try:
                    result = connection.recv()
                except EOFError:
                    result = {"ok": False, "error": "Tiến trình giải đã dừng."}
                finally:
                    connection.close()
                    process.join(timeout=1)
                if generation == self.generation:
                    if not result["ok"]:
                        self.notice = "Lỗi xử lý thuật toán: " + result["error"]
                    else:
                        plan = result["plan"]
                        self.plan_actions = [(tag, tuple(cell)) for tag, cell in plan["actions"]]
                        self.game.ai_path = [cell for _, cell in self.plan_actions]
                        self.game.ai_index = 0
                        self.plan_ms = plan["planning_ms"]
                        self.game.stats = plan["stats"]
                        safe = sum(tag == "safe" for tag, _ in self.plan_actions)
                        mines = sum(tag == "mine" for tag, _ in self.plan_actions)
                        guesses = sum(tag == "guess" for tag, _ in self.plan_actions)
                        self.notice = f"{self.algorithm}: {safe} ô an toàn · {mines} mìn · {guesses} ô đoán."
                        if not self.plan_actions:
                            self.playing = False
                            self.notice = "Vòng suy luận đã kết thúc, chưa có hành động mới. Reset hoặc chọn input khác."
                        elif action == "step":
                            self._advance()
                        elif action == "play":
                            self.playing = True
                            self.next_tick = pygame.time.get_ticks() + self.intervals[self.speed_index]
            elif time.monotonic() - self.plan_started > 10:
                self._invalidate_plan()
                self.notice = "Lượt suy luận vượt 10 giây. Chọn input khác hoặc gửi trường hợp này cho bạn làm thuật toán."
            elif not self.pending.is_alive():
                # Poll once more next frame: the pipe may still have a final result.
                if not self.plan_pipe.poll():
                    self._invalidate_plan()
                    self.notice = "Tiến trình thuật toán đã dừng. Thử Reset để chạy lại."
        if self.playing and pygame.time.get_ticks() >= self.next_tick:
            self._advance()
            self.next_tick = pygame.time.get_ticks() + self.intervals[self.speed_index]
        if self.benchmark_process is not None:
            code = self.benchmark_process.poll()
            if code is not None:
                self.benchmark_process = None
                self.benchmark_log.close()
                self.benchmark_log = None
                self.benchmark_notice = ("Đã lưu CSV và báo cáo thực nghiệm" if code == 0
                                         else "Xem lỗi trong benchmark_results/run.log")

    def board_geometry(self):
        available = pygame.Rect(62, 280, 622, 355)
        tile = min(62, available.width // COLS, available.height // ROWS)
        tile = max(1, tile)
        x = available.centerx - COLS * tile // 2
        y = available.centery - ROWS * tile // 2 + 6
        return pygame.Rect(x, y, COLS * tile, ROWS * tile), tile

    def cell_at(self, pos):
        board, tile = self.board_geometry()
        if board.collidepoint(pos):
            return (int((pos[1] - board.y) // tile), int((pos[0] - board.x) // tile))
        return None

    def _draw_flag(self, rect):
        x, y = rect.center
        unit = min(rect.width, rect.height) / 54
        self.line("#EAF2F8", (x-5*unit, y-14*unit), (x-5*unit, y+13*unit), max(2, int(3*unit)))
        pygame.draw.polygon(self.canvas, "#F2BE60", [self.pixel_point(point) for point in
                            [(x-4*unit, y-14*unit), (x+15*unit, y-8*unit), (x-4*unit, y-1*unit)]])
        self.line("#EAF2F8", (x-13*unit, y+14*unit), (x+4*unit, y+14*unit), max(2, int(3*unit)))

    def _draw_mine(self, rect):
        x, y = rect.center
        radius = max(3, int(rect.width * .15))
        color = "#A9423A"
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            self.line(color, (x-dx*radius*1.6, y-dy*radius*1.6),
                      (x+dx*radius*1.6, y+dy*radius*1.6), 2)
        self.circle(color, (x, y), radius)
        self.circle("#FFD4C9", (x-radius//3, y-radius//3), max(1, radius//4))

    def draw_board(self):
        board, tile = self.board_geometry()
        self.card(board.inflate(16, 16), "#E3E9EE", radius=13)
        # The displayed coordinates are one-based; backend coordinates stay zero-based.
        if tile >= 24:
            for c in range(COLS):
                self.text(str(c+1), (board.x + c*tile + tile//2, board.y-20), 12, MUTED, center=True)
            for r in range(ROWS):
                self.text(str(r+1), (board.x-22, board.y + r*tile + tile//2), 12, MUTED, center=True)
        hovered_cell = self.cell_at(self.hover)
        for r in range(ROWS):
            for c in range(COLS):
                cell = r, c
                rect = pygame.Rect(board.x+c*tile+2, board.y+r*tile+2, max(1, tile-4), max(1, tile-4))
                revealed = cell in self.game.revealed
                flagged = cell in self.game.flags
                if revealed:
                    fill = "#F8DCD5" if cell in self.game.mine_positions else "#F5F8FA"
                else:
                    fill = "#3E536A" if flagged else "#415970"
                    if hovered_cell == cell and not self.game.game_over:
                        fill = "#506C85"
                self.card(rect, fill, radius=max(1, min(8, tile//7)))
                if revealed and cell in self.game.mine_positions:
                    self._draw_mine(rect)
                elif revealed:
                    number = self.game.numbers[cell]
                    if number:
                        self.text(str(number), rect.center, max(9, min(26, tile//2)),
                                  NUMBER_COLORS.get(number, INK), True, center=True)
                elif flagged:
                    self._draw_flag(rect)
                elif tile >= 20:
                    self.circle("#7690A7", rect.center, max(1, tile//22))
                if cell == self.last_cell:
                    pygame.draw.rect(self.canvas, TEAL, self.pixel_rect(rect),
                                     max(1, round(3*self.render_scale)),
                                     border_radius=max(1, round(min(8, tile//7)*self.render_scale)))

    def draw(self, *, drawable_size=None, present=True):
        self._prepare_frame(drawable_size)
        self.buttons.clear()
        self.canvas.fill(BG)
        self.card((28, 27, 44, 44), TEAL, radius=12)
        self.text("M", (50, 48), 26, WHITE, True, center=True)
        self.text("MINESWEEPER", (85, 23), 30, INK, True)
        self.text("SEARCH LAB   /   DFS & HillClimbing", (87, 61), 12, MUTED, True)
        self.card((916, 33, 216, 32), "#E2ECEB", radius=16)
        display_label = f"BTL 1  ·  RETINA {self.pixel_ratio:.0f}×" if self.pixel_ratio >= 1.5 else "BTL 1  ·  PYTHON + PYGAME"
        self.text(display_label, (1024, 49), 12, TEAL, True, center=True)

        metrics = (("TỔNG SỐ MÌN", f"{MINES:02d}", "Theo cấu hình bàn cờ"),
                   ("CỜ ĐÃ CẮM", f"{len(self.game.flags):02d} / {MINES:02d}", "Chuột phải để đánh dấu"),
                   ("Ô AN TOÀN ĐÃ MỞ", f"{self.safe_opened:02d} / {self.safe_total:02d}", "Mở hết để hoàn thành"),
                   ("THỜI GIAN DEMO", f"{int(self.elapsed())//60:02d}:{int(self.elapsed())%60:02d}", "Thời gian thao tác trên bàn"))
        for index, (label, value, caption) in enumerate(metrics):
            x = 28 + index*280
            self.card((x, 101, 264, 103))
            self.text(label, (x+17, 115), 11, MUTED, True)
            self.text(value, (x+17, 135), 27, TEAL if index == 2 else INK, True)
            self.text(caption, (x+17, 177), 12, MUTED)

        self.card((28, 224, 688, 482))
        self.text("Bàn chơi", (51, 244), 22, INK, True)
        self.text(f"{ROWS} × {COLS}  /  Input T{self.seed+1:02d}", (493, 250), 14, MUTED)
        self.draw_board()
        self.text("Chuột trái: mở ô     ·     Chuột phải: cắm / gỡ cờ", (372, 665), 14, MUTED, center=True)

        self.card((736, 224, 396, 297))
        self.text("Điều khiển AI", (758, 244), 22, INK, True)
        state = "ĐANG CHUẨN BỊ" if self.pending else "ĐANG CHẠY" if self.playing else "ĐÃ XONG" if self.game.won else "ĐÃ THUA" if self.game.game_over else "TẠM DỪNG" if self.game.ai_path else "SẴN SÀNG"
        self.text(state, (758, 278), 11, TEAL, True)
        self.button("dfs", (758, 303, 169, 40), "DFS", lambda: self.choose_algorithm("DFS"), active=self.algorithm == "DFS")
        self.button("hill", (939, 303, 171, 40), "Hill Climbing", lambda: self.choose_algorithm("HillClimbing"), active=self.algorithm == "HillClimbing")
        enabled = not self.game.game_over and self.pending is None
        self.button("step", (758, 355, 110, 43), "Step  →", self.step, enabled=enabled)
        self.button("play", (880, 355, 139, 43), "Pause" if self.playing or (self.pending and self.pending_action == "play") else "Play", self.toggle_play, primary=True, enabled=not self.game.game_over)
        self.button("speed", (1031, 355, 79, 43), ("0.5×", "1×", "2.5×")[self.speed_index], self.cycle_speed)
        count, total = self.game.ai_index, len(self.game.ai_path)
        self.text("TIẾN ĐỘ KẾ HOẠCH", (758, 416), 11, MUTED, True)
        self.text(f"{count} / {total} bước", (1034, 413), 14, INK, True)
        self.card((758, 440, 352, 7), "#E5ECEF", radius=3)
        if total and count:
            self.card((758, 440, max(7, int(352*count/total)), 7), TEAL, radius=3)
        self.text("Lập kế hoạch: " + (f"{self.plan_ms:.3f} ms" if self.plan_ms is not None else "—"), (758, 465), 13, MUTED)
        expanded = self.game.stats.get("expanded_nodes", None)
        generated = self.game.stats.get("generated_nodes", None)
        expanded_label = "Nhánh DFS hợp lệ" if self.algorithm == "DFS" else "Ứng viên mô phỏng"
        generated_label = "Phép gán đã thử" if self.algorithm == "DFS" else "Ứng viên chấm điểm"
        self.text(f"{expanded_label}: {expanded if expanded is not None else '—'}", (758, 487), 12, MUTED)
        self.text(f"{generated_label}: {generated if generated is not None else '—'}", (758, 502), 12, MUTED)

        self.card((736, 537, 396, 169))
        self.text("Các bước gần nhất", (758, 555), 17, INK, True)
        if not self.history:
            self.text("Các ô vừa mở sẽ xuất hiện ở đây.", (758, 599), 14, MUTED)
        for i, (cell, source, number) in enumerate(self.history[-3:]):
            index = len(self.history)-len(self.history[-3:])+i+1
            y = 589+i*33
            self.text(f"{index:02d}", (758, y), 14, TEAL, True)
            self.text(f"{source} ({cell[0]+1}, {cell[1]+1})", (797, y), 12, INK)
            label = "CẮM CỜ" if number == -1 else "MÌN" if cell in self.game.mine_positions else f"{number} lân cận"
            self.text(label, (1030, y), 13, MUTED)

        self.button("prev", (28, 719, 43, 39), "‹", lambda: self.new_board(self.seed-1), enabled=self.seed > 0)
        self.button("new", (79, 719, 158, 39), "Input tiếp  ›", self.new_board)
        self.button("reset", (249, 719, 146, 39), "Reset input", self.reset_board)
        busy = self.benchmark_process is not None
        self.button("benchmark", (736, 719, 160, 39), "Đang đo…" if busy else "Chạy benchmark", self.start_benchmark, enabled=not busy)
        self.wrapped(self.benchmark_notice, pygame.Rect(908, 719, 220, 44), 11, MUTED, 17)

        self.wrapped(self.notice, pygame.Rect(30, 771, 690, 44), 13, TEAL, 18)
        self.text("DỮ KIỆN: các số đã mở trên bàn", (737, 775), 12, "#9A7140")
        self.text("SPACE: Play/Pause   ·   →: Step   ·   R: Reset", (737, 796), 10, MUTED)

        if present:
            self.display.present(self.canvas)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE:
            self.display.resize((max(320, event.w), max(240, event.h)))
        elif event.type == pygame.WINDOWCLOSE:
            self.running = False
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            if not self.viewport.collidepoint(event.pos):
                self.hover = (-1, -1)
                return
            pos = ((event.pos[0]-self.viewport.x)/self.scale, (event.pos[1]-self.viewport.y)/self.scale)
            self.hover = pos
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    for rect, callback, enabled in list(self.buttons.values()):
                        if enabled and rect.collidepoint(pos):
                            callback()
                            return
                cell = self.cell_at(pos)
                if cell is not None:
                    if event.button == 3 or (event.button == 1 and pygame.key.get_mods() & pygame.KMOD_CTRL):
                        self.toggle_flag(cell)
                    elif event.button == 1:
                        self.player_reveal(cell)
        elif event.type == pygame.KEYDOWN:
            actions = {pygame.K_SPACE: self.toggle_play, pygame.K_RIGHT: self.step,
                       pygame.K_r: self.reset_board, pygame.K_n: self.new_board,
                       pygame.K_1: lambda: self.choose_algorithm("DFS"),
                       pygame.K_2: lambda: self.choose_algorithm("HillClimbing")}
            if event.key in actions:
                actions[event.key]()

    def close(self):
        self.running = False
        self._invalidate_plan()
        if self.benchmark_process is not None:
            self.benchmark_process.terminate()
            try:
                self.benchmark_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.benchmark_process.kill()
                self.benchmark_process.wait(timeout=2)
            self.benchmark_process = None
        if self.benchmark_log:
            self.benchmark_log.close()
            self.benchmark_log = None
        self.display.close()
        pygame.quit()

    def run(self):
        try:
            while self.running:
                for event in pygame.event.get():
                    self.handle_event(event)
                self.update()
                self.draw()
                self.clock.tick(60)
        finally:
            self.close()


if __name__ == "__main__":
    MinesweeperGUI().run()
