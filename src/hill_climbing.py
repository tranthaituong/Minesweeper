"""
Hill Climbing Solver cho Minesweeper
====================================

Triển khai thuật toán Hill Climbing thực sự, tách biệt hoàn toàn
khỏi GameEngine. Chỉ dùng observation công khai:
  - ô đã mở + số hiển thị
  - cờ đã cắm
  - kích thước bàn cờ + tổng số mìn

KHÔNG BAO GIỜ truy cập mine_positions hay thông tin ẩn.

Luồng hai giai đoạn:
  A. Constraint propagation → ô chắc chắn an toàn / chắc chắn mìn.
  B. Hill Climbing → khi A không còn tiến bộ, dùng heuristic để
     đoán ô tốt nhất theo mức độ thỏa mãn ràng buộc.

Yield contract:
  - ("safe",  cell): ô đã được chứng minh an toàn (giai đoạn A).
  - ("mine",  cell): ô chắc chắn là mìn               (giai đoạn A).
  - ("guess", cell): ô đoán theo heuristic            (giai đoạn B).
  - ("prop_done", None): propagation kết thúc, bắt đầu B.

API chính:
  - HillClimbingSolver(engine) → solve() generator.
  - heuristic_score(obs, cell) → float  (không phải xác suất).
  - evaluate_state(obs, known_safe, known_mines, constraints) → float.
"""

import time
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

# Import config (no circular dep on minesweeper_game)
import config

# Lazy import to avoid circular dependency:
# minesweeper_game imports from hill_climbing.
def _get_types():
    """Lazy import của Cell, Constraint, GameObservation."""
    from minesweeper_game import Cell, Constraint, GameObservation
    return Cell, Constraint, GameObservation

Cell = Tuple[int, int]


# ============================================================
# HEURISTIC SCORE
# ============================================================

def heuristic_score(obs, cell: Cell) -> float:
    """Điểm heuristic cho ``cell``.

    ĐÂY KHÔNG PHẢI xác suất an toàn đã hiệu chuẩn.
    Đây là heuristic cục bộ đo mức độ "hợp lý" khi đặt cell = 0 (safe).

    Logic:
      - Nếu cell nằm trong một ràng buộc mà target == 0 → score = 1.0
        (chắc chắn an toàn vì tất cả lân cận đã có đủ mìn rồi).
      - Nếu cell nằm trong ràng buộc mà target == len(hidden) → score = -1.0
        (chắc chắn là mìn - mìn phải chiếm hết chỗ còn lại).
      - Nếu cell không liên quan ràng buộc nào → dùng xác suất nền
        P(safe) = 1 - mines/total_hidden.
      - Ngược lại: score = trung bình (1 - target/len) trên các ràng
        buộc liên quan. Giá trị càng cao → cell có vẻ "an toàn hơn"
        theo thông tin cục bộ.

    Trả về float trong khoảng [-1.0, 1.0].
    """
    related: List[Tuple[List[Cell], int]] = []
    for nb in obs.neighbors(cell):
        num = obs.numbers.get(nb)
        if num is None:
            continue
        hidden = [n for n in obs.neighbors(nb)
                  if n not in obs.revealed and n not in obs.flags]
        flags = sum(1 for n in obs.neighbors(nb) if n in obs.flags)
        target = max(0, min(num - flags, len(hidden)))
        related.append((hidden, target))

    for hidden, target in related:
        if cell in hidden:
            if target == 0:
                return 1.0
            if target == len(hidden):
                return -1.0

    if not related:
        hidden = [c for c in obs.all_cells
                  if c not in obs.revealed and c not in obs.flags]
        if not hidden:
            return 0.01
        prob = 1.0 - config.MINES / max(1, len(hidden))
        return max(0.01, min(0.99, prob))

    scores = [1.0 - target / max(1, len(hidden))
              for hidden, target in related]
    return max(0.01, min(0.99, sum(scores) / len(scores)))


# ============================================================
# STATE EVALUATION
# ============================================================

def evaluate_state(obs, known_safe: Set[Cell], known_mines: Set[Cell],
                   constraints) -> float:
    """Đánh giá tổng thể mức độ thỏa mãn ràng buộc của trạng thái.

    Score càng cao → trạng thái càng tốt (nhiều ô đã xác định đúng
    theo ràng buộc, ít mâu thuẫn).
    """
    score = 0.0

    for c in constraints:
        vars_ = set(c.variables)
        unassigned = vars_ - known_safe - known_mines
        assigned_mines = len(known_mines & vars_)
        assigned_safe = len(known_safe & vars_)

        if not unassigned:
            if assigned_mines == c.target:
                score += 1.0
            else:
                score -= 1.0
        else:
            remaining = len(unassigned)
            if assigned_mines <= c.target <= assigned_mines + remaining:
                score += 0.5
            else:
                score -= 0.5

    all_unknown = {c for c in obs.all_cells
                   if c not in obs.revealed and c not in obs.flags}
    determined = len(known_safe | (known_mines & all_unknown))
    score += determined * 0.1

    remaining = [c for c in all_unknown if c not in known_safe and c not in known_mines]
    if remaining:
        avg_h = sum(heuristic_score(obs, c) for c in remaining) / len(remaining)
        score += avg_h * 0.5

    return score


# ============================================================
# CONSTRAINT PROPAGATION
# ============================================================

def propagate(known_safe: Set[Cell],
              known_mines: Set[Cell],
              constraints: Sequence) -> Tuple[Set[Cell], Set[Cell], bool, str]:
    """Lan truyền ràng buộc đơn giản."""
    new_safe = set(known_safe)
    new_mines = set(known_mines)
    changed = True
    while changed:
        changed = False
        for c in constraints:
            vars_ = set(c.variables)
            unassigned = vars_ - new_safe - new_mines
            if not unassigned:
                total = len(new_mines & vars_)
                if total != c.target:
                    return new_safe, new_mines, False, "contradiction"
                continue
            if c.target == 0:
                for v in unassigned:
                    if v not in new_safe:
                        new_safe.add(v)
                        changed = True
            elif c.target == len(vars_):
                for v in unassigned:
                    if v not in new_mines:
                        new_mines.add(v)
                        changed = True
    return new_safe, new_mines, changed, "ok"


# ============================================================
# EVENT TAGS
# ============================================================
SAFE = "safe"
MINE = "mine"
GUESS = "guess"
PROP_DONE = "prop_done"
UNKNOWN = "unknown"


# ============================================================
# HILL CLIMBING SOLVER
# ============================================================

@dataclass
class HillClimbingStats:
    """Thống kê chạy Hill Climbing."""
    expanded_nodes: int = 0
    generated_nodes: int = 0
    propagation_steps: int = 0
    guesses: int = 0
    backtracks: int = 0  # luôn = 0
    elapsed_time: float = 0.0


class HillClimbingSolver:
    """Solver Minesweeper bằng Hill Climbing thực sự."""

    MAX_PROP_ITERS = 50
    MAX_HC_ITERS = 200
    MAX_GUESSES = 50
    RANDOM_SEED = 42

    def __init__(self, engine):
        self.engine = engine
        self.stats = HillClimbingStats()
        self._Constraint = None  # lazy
        self._GameObservation = None

    def _ensure_types(self):
        """Lazy import types tránh circular."""
        if self._Constraint is None:
            from minesweeper_game import Constraint, GameObservation
            self._Constraint = Constraint
            self._GameObservation = GameObservation

    # --------------------------------------------------------
    # Quan sát
    # --------------------------------------------------------
    def _get_observation(self):
        self._ensure_types()
        GameObservation = self._GameObservation

        rows = getattr(self.engine, "_rows", config.ROWS)
        cols = getattr(self.engine, "_cols", config.COLS)
        total_mines = getattr(self.engine, "_mines_count", config.MINES)
        numbers: Dict[Cell, int] = {}
        for cell in self.engine.revealed:
            value = self.engine.get_number(cell)
            if value is not None:
                numbers[cell] = value
        return GameObservation(
            rows=rows,
            cols=cols,
            total_mines=total_mines,
            revealed=set(self.engine.revealed),
            numbers=numbers,
            flags=set(self.engine.flags),
        )

    def _build_constraints(self, obs):
        self._ensure_types()
        Constraint = self._Constraint

        constraints = []
        for cell, num in obs.numbers.items():
            hidden: Set[Cell] = set()
            flags_around = 0
            for n in obs.neighbors(cell):
                if n in obs.revealed:
                    continue
                if n in obs.flags:
                    flags_around += 1
                    continue
                hidden.add(n)
            target = num - flags_around
            constraints.append(Constraint(variables=frozenset(hidden), target=target))

        all_unknown: Set[Cell] = set()
        for cell in obs.all_cells:
            if cell in obs.revealed or cell in obs.flags:
                continue
            all_unknown.add(cell)
        total_target = obs.total_mines - len(obs.flags)
        constraints.append(
            Constraint(variables=frozenset(all_unknown), target=total_target)
        )
        return constraints

    # --------------------------------------------------------
    # Stage A
    # --------------------------------------------------------
    def _stage_a(self, obs, constraints):
        self._ensure_types()
        Constraint = self._Constraint

        known_safe: Set[Cell] = set()
        known_mines: Set[Cell] = set()

        # Tách constraint thành 2 loại:
        #  - local: từ số hiện (target, vars của cell neighbors)
        #  - total: ràng buộc tổng số mìn (target = total_mines - flags)
        # Propagation chỉ dùng local. Total không dùng vì gây
        # contradiction khi tất cả unknown đã được xác định.
        local_constraints = [c for c in constraints[:-1]]
        total_constraint = constraints[-1] if constraints else None

        for _ in range(self.MAX_PROP_ITERS):
            ks, km, changed, status = propagate(known_safe, known_mines,
                                                local_constraints)
            self.stats.propagation_steps += 1
            if status == "contradiction":
                break
            known_safe, known_mines = ks, km
            if not changed:
                # Đến điểm cố định, không còn gì thay đổi
                break

        # Flood-fill: nếu ô safe là số 0, thêm lân cận vào safe
        newly = True
        while newly:
            newly = False
            for cell in list(known_safe):
                num = obs.numbers.get(cell)
                if num is not None and num == 0:
                    for nb in obs.neighbors(cell):
                        if nb not in known_safe and nb not in known_mines:
                            known_safe.add(nb)
                            newly = True

        # Reduced constraints
        reduced = []
        for c in local_constraints:
            vars_ = set(c.variables) - known_safe - known_mines
            target = c.target - len(known_mines & set(c.variables))
            if not vars_:
                if target != 0:
                    continue
                continue
            reduced.append(Constraint(variables=frozenset(vars_), target=target))

        # Thêm total constraint (luôn ở cuối để solve biết mines_target)
        if total_constraint is not None:
            total_vars = set(total_constraint.variables) - known_safe - known_mines
            total_target = total_constraint.target - len(known_mines)
            if total_vars:
                reduced.append(
                    Constraint(variables=frozenset(total_vars), target=total_target)
                )

        return known_safe, known_mines, reduced

    # --------------------------------------------------------
    # Stage B: Hill climbing (heuristic + simulate)
    # --------------------------------------------------------
    def _best_candidate(self, obs, candidates, baseline_score):
        """Trả về (cell, new_score, new_safe, new_mines, new_constraints)."""
        self._ensure_types()
        Constraint = self._Constraint

        # Score heuristic cho mỗi candidate
        scored = []
        for idx, cell in enumerate(candidates):
            h = heuristic_score(obs, cell)
            self.stats.generated_nodes += 1
            scored.append((h, idx, cell))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Chỉ thử top-K (tiết kiệm O(n²))
        TOP_K = min(5, len(scored))
        top_candidates = scored[:TOP_K]

        results: List[Tuple[float, Cell]] = []
        for h, idx, cell in top_candidates:
            # Simulate: đặt cell = safe
            sim_safe: Set[Cell] = set(obs.revealed) | {cell}
            sim_flags: Set[Cell] = set(obs.flags)

            sim_constraints = []
            for num_cell, num_val in obs.numbers.items():
                hidden: Set[Cell] = set()
                flags_around = 0
                for nb in obs.neighbors(num_cell):
                    if nb in sim_safe:
                        continue
                    if nb in sim_flags:
                        flags_around += 1
                        continue
                    hidden.add(nb)
                target = num_val - flags_around
                sim_constraints.append(
                    Constraint(variables=frozenset(hidden), target=target)
                )

            all_unknown_sim = {
                c for c in obs.all_cells
                if c not in sim_safe and c not in sim_flags
            }
            total_target = obs.total_mines - len(sim_flags)
            sim_constraints.append(
                Constraint(variables=frozenset(all_unknown_sim), target=total_target)
            )

            # Chạy propagation
            sim_ks: Set[Cell] = set()
            sim_km: Set[Cell] = set()
            for _ in range(self.MAX_PROP_ITERS):
                ks2, km2, ch, st = propagate(sim_ks, sim_km, sim_constraints)
                if st == "contradiction" or not ch:
                    break
                sim_ks, sim_km = ks2, km2

            new_score = evaluate_state(obs, sim_ks, sim_km, sim_constraints)
            self.stats.expanded_nodes += 1
            results.append((new_score, cell))

        if not results:
            return None

        results.sort(key=lambda x: x[0], reverse=True)
        best_score, best_cell = results[0]

        # Tái tính cho cell tốt nhất
        sim_safe = set(obs.revealed) | {best_cell}
        sim_flags = set(obs.flags)
        sim_constraints = []
        for num_cell, num_val in obs.numbers.items():
            hidden: Set[Cell] = set()
            flags_around = 0
            for nb in obs.neighbors(num_cell):
                if nb in sim_safe:
                    continue
                if nb in sim_flags:
                    flags_around += 1
                    continue
                hidden.add(nb)
            target = num_val - flags_around
            sim_constraints.append(
                Constraint(variables=frozenset(hidden), target=target)
            )
        all_unknown_sim = {
            c for c in obs.all_cells
            if c not in sim_safe and c not in sim_flags
        }
        total_target = obs.total_mines - len(sim_flags)
        sim_constraints.append(
            Constraint(variables=frozenset(all_unknown_sim), target=total_target)
        )
        sim_ks: Set[Cell] = set()
        sim_km: Set[Cell] = set()
        for _ in range(self.MAX_PROP_ITERS):
            ks2, km2, ch, st = propagate(sim_ks, sim_km, sim_constraints)
            if st == "contradiction" or not ch:
                break
            sim_ks, sim_km = ks2, km2

        return best_cell, best_score, sim_ks, sim_km, sim_constraints

    # --------------------------------------------------------
    # Solver chính
    # --------------------------------------------------------
    def solve(self) -> Iterable[Tuple[str, Cell]]:
        start = time.perf_counter()
        self.stats = HillClimbingStats()

        obs = self._get_observation()
        constraints = self._build_constraints(obs)

        known_safe, known_mines, reduced = self._stage_a(obs, constraints)

        # Yield kết quả propagation
        for cell in sorted(known_safe):
            if cell not in self.engine.revealed and cell not in self.engine.flags:
                yield (SAFE, cell)
        for cell in sorted(known_mines):
            if cell not in self.engine.flags:
                self.engine.flags.add(cell)
                yield (MINE, cell)

        # Tính trạng thái còn lại
        all_unknown = {
            c for c in obs.all_cells
            if c not in obs.revealed and c not in obs.flags
        }
        unknown_cells = [
            c for c in all_unknown
            if c not in known_safe and c not in known_mines
        ]
        remaining_mines = obs.total_mines - len(obs.flags | known_mines)

        if not unknown_cells:
            self.stats.elapsed_time = time.perf_counter() - start
            return
        if remaining_mines == 0:
            for cell in unknown_cells:
                yield (SAFE, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return
        # NOTE: Don't mark all remaining as mines on fresh board
        # remaining_mines == len(unknown_cells) only means we need more info

        # Stage B
        yield (PROP_DONE, None)
        baseline_score = evaluate_state(obs, known_safe, known_mines, reduced)
        hc_iters = 0
        guesses_made = 0

        while hc_iters < self.MAX_HC_ITERS and guesses_made < self.MAX_GUESSES and unknown_cells:
            hc_iters += 1
            current_score = evaluate_state(obs, known_safe, known_mines, reduced)
            result = self._best_candidate(obs, unknown_cells, current_score)
            if result is None:
                break

            best_cell, new_score, new_safe, new_mines, new_constraints = result

            guesses_made += 1
            self.stats.guesses += 1

            known_safe = new_safe
            known_mines = new_mines
            reduced = new_constraints

            yield (GUESS, best_cell)

            # Update engine
            self.engine.revealed.add(best_cell)

            # Refresh obs
            obs = self._get_observation()
            unknown_cells = [
                c for c in obs.all_cells
                if c not in obs.revealed and c not in obs.flags
                and c not in known_safe and c not in known_mines
            ]
            remaining_mines = obs.total_mines - len(obs.flags | known_mines)

            if not unknown_cells:
                break
            if remaining_mines == 0:
                for cell in unknown_cells:
                    yield (SAFE, cell)
                break
            if remaining_mines == len(unknown_cells):
                for cell in unknown_cells:
                    self.engine.flags.add(cell)
                    yield (MINE, cell)
                break

        self.stats.elapsed_time = time.perf_counter() - start
