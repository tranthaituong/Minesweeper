"""
Minesweeper Game Engine & AI Solver
===================================

Tách bạch rõ ràng giữa:

- ``GameEngine``: biết vị trí mìn thật, dùng để vận hành trò chơi.
- ``AISolver``: chỉ quan sát được các ô đã mở, số hiển thị, cờ mìn
  và cấu hình bàn cờ. **Không bao giờ được phép truy cập**
  ``GameEngine.mine_positions`` hay ``GameEngine._numbers`` của những
  ô chưa mở.

Thuật toán DFS + Backtracking được thiết kế theo mô hình CSP:

1. Tách biệt *quan sát* và *suy luận* qua API ``get_observation``.
2. Xây dựng danh sách biến nhị phân (``unknown`` cells) và các
   ràng buộc ``sum(variables) == value`` từ số hiển thị và tổng mìn.
3. Constraint propagation chạy đến điểm cố định để sinh ra các ô
   chắc chắn ``safe`` / ``mine`` mà không cần DFS.
4. DFS thực sự thử các phép gán nhị phân, có kiểm tra ràng buộc
   từng phần, backtrack khi vi phạm, đếm trạng thái đã mở rộng và
   đã sinh. MRV / degree chỉ là heuristic sắp xếp thứ tự duyệt.
5. Tổng hợp các cấu hình hợp lệ tìm được; chỉ kết luận ``safe`` /
   ``mine`` cho ô nào giữ nguyên giá trị trong *mọi* cấu hình.
6. Khi vượt giới hạn tìm kiếm hoặc chưa đủ bằng chứng, trả về
   ``unknown`` thay vì tự ý đoán.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

from config import ROWS, COLS, MINES


# ============================================================
# CẤU TRÚC DỮ LIỆU
# ============================================================

Cell = Tuple[int, int]


@dataclass(frozen=True)
class Constraint:
    """Ràng buộc ``sum(mine in variables) == target``.

    ``target`` là số mìn phải có trong tập ``variables``. Các biến đã
    được gán ``0`` hoặc ``1`` ở ngoài tập này không tham gia ràng
    buộc này.

    Ràng buộc tổng số mìn trên toàn bàn cờ được biểu diễn bằng cùng
    cấu trúc: ``variables`` là tập các ô chưa biết, ``target`` là số
    mìn còn lại sau khi trừ mìn đã xác định (cờ + suy luận).
    """

    variables: FrozenSet[Cell]
    target: int

    def is_trivial(self) -> bool:
        """Ràng buộc hiển nhiên: tập rỗng hoặc target nằm ngoài
        khoảng hợp lý."""
        n = len(self.variables)
        return n == 0 or self.target < 0 or self.target > n


@dataclass
class GameObservation:
    """Ảnh chụp trạng thái bàn cờ mà AI được phép quan sát.

    Thuộc tính:
        rows / cols: kích thước bàn cờ.
        total_mines: tổng mìn cấu hình ban đầu.
        revealed: tập ô đã mở.
        numbers: ánh xạ từ ô đã mở sang số mìn lân cận hiển thị.
            Không bao giờ chứa ô chưa mở.
        flags: tập ô đã gắn cờ mìn (do người chơi hoặc AI khác).
    """

    rows: int
    cols: int
    total_mines: int
    revealed: Set[Cell] = field(default_factory=set)
    numbers: Dict[Cell, int] = field(default_factory=dict)
    flags: Set[Cell] = field(default_factory=set)

    @property
    def all_cells(self) -> List[Cell]:
        return [(r, c) for r in range(self.rows) for c in range(self.cols)]

    def neighbors(self, cell: Cell) -> Iterable[Cell]:
        r, c = cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    yield (nr, nc)


@dataclass
class SolverEvent:
    """Sự kiện có cấu trúc phát ra trong quá trình suy luận.

    Dùng để GUI / log dựng lại từng bước mà không cần dựa vào
    print của solver.

    Các loại:
        - ``observe``: chụp quan sát ban đầu.
        - ``constraint_built``: một ràng buộc vừa được xây dựng.
        - ``propagation_step``: một vòng lặp của constraint
          propagation hoàn tất.
        - ``dfs_start``: bắt đầu tìm kiếm.
        - ``dfs_try_value``: thử gán biến với 0 hoặc 1.
        - ``dfs_consistent``: phép gán vừa thử vẫn nhất quán.
        - ``dfs_backtrack``: phép gán vi phạm ràng buộc, quay lui.
        - ``dfs_solution``: tìm được một cấu hình hợp lệ.
        - ``infer_safe`` / ``infer_mine``: ô chắc chắn an toàn / mìn
          sau khi tổng hợp.
        - ``search_limit``: vượt giới hạn, không thể kết luận.
    """

    kind: str
    payload: dict = field(default_factory=dict)


@dataclass
class SolverStats:
    """Thống kê chạy thuật toán DFS.

    Định nghĩa:
        - ``expanded_nodes``: số lần một nhánh DFS được mở rộng - tức
          là số lần hàm đệ quy được gọi với một phép gán mới (chỉ
          tính khi phép gán đã vượt qua kiểm tra ràng buộc tức thời).
        - ``generated_nodes``: số phép gán ``var = 0/1`` được sinh ra
          tại mỗi bước đệ quy.
        - ``backtracks``: số lần DFS phát hiện mâu thuẫn và phải quay
          lui về bước trước.
        - ``valid_configurations``: số cấu hình hợp lệ tìm được.
        - ``elapsed_time``: tổng thời gian (giây).
        - ``search_truncated``: True nếu vượt giới hạn, kết quả có
          thể chưa đầy đủ.
    """

    expanded_nodes: int = 0
    generated_nodes: int = 0
    backtracks: int = 0
    valid_configurations: int = 0
    elapsed_time: float = 0.0
    search_truncated: bool = False


# ============================================================
# GAME ENGINE
# ============================================================

class GameEngine:
    """Bộ máy trò chơi - đây là chỗ DUY NHẤT được biết vị trí mìn."""

    def __init__(self):
        self.mine_positions: Set[Cell] = set()
        self.revealed: Set[Cell] = set()
        self.flags: Set[Cell] = set()
        self.game_over = False
        self.won = False
        self._numbers: Dict[Cell, int] = {}

    def new_game(self):
        all_cells = [(r, c) for r in range(ROWS) for c in range(COLS)]
        self.mine_positions = set(random.sample(all_cells, MINES))
        self._numbers = {}
        for cell in all_cells:
            count = sum(1 for n in self._neighbors(cell) if n in self.mine_positions)
            self._numbers[cell] = count
        self.revealed = set()
        self.flags = set()
        self.game_over = False
        self.won = False

    def _neighbors(self, cell: Cell) -> Iterable[Cell]:
        r, c = cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < ROWS and 0 <= nc < COLS:
                    yield (nr, nc)

    def get_number(self, cell: Cell) -> Optional[int]:
        """Chỉ trả về số mìn nếu ô đã mở. Trả về None nếu chưa mở."""
        if cell in self.revealed:
            return self._numbers.get(cell, 0)
        return None

    def reveal(self, cell: Cell) -> Optional[bool]:
        if self.game_over or cell in self.revealed:
            return False
        self.revealed.add(cell)
        if cell in self.mine_positions:
            self.game_over = True
            self.revealed.update(self.mine_positions)
            return True
        if len(self.revealed) == ROWS * COLS - MINES:
            self.game_over = True
            self.won = True
            return None
        return False

    def toggle_flag(self, cell: Cell):
        if self.game_over or cell in self.revealed:
            return
        if cell in self.flags:
            self.flags.remove(cell)
        elif len(self.flags) < MINES:
            self.flags.add(cell)


# ============================================================
# AI SOLVER - thiết kế mới
# ============================================================

# Kết quả của solver cho một ô.
UNKNOWN = "unknown"
SAFE = "safe"
MINE = "mine"


class AISolver:
    """Solver Minesweeper bằng DFS + Backtracking đúng nghĩa.

    Tách bạch hoàn toàn khỏi GameEngine. Solver chỉ đọc những gì
    ``get_observation`` cung cấp; không bao giờ chạm vào
    ``mine_positions`` hay ``_numbers`` của các ô chưa mở.

    API chính:
        - ``get_observation(engine)``: chụp trạng thái quan sát được.
        - ``build_constraints(observation)``: xây dựng danh sách
          ràng buộc.
        - ``propagate(...)``: suy ra ô chắc chắn không cần DFS.
        - ``dfs_enumerate(...)``: liệt kê tất cả cấu hình hợp lệ.
        - ``dfs_prove(...)``: DFS để chứng minh một ô là safe/mine.
        - ``solve(engine)``: hàm generator điều phối, yield
          ``SolverEvent`` và ``("safe", cell)`` / ``("mine", cell)`` /
          ``("unknown", cell)``.
        - ``get_stats()``: trả về ``SolverStats``.
    """

    # Giới hạn an toàn cho cấu hình nhỏ trong khuôn khổ bài tập.
    # Tăng lên để benchmark có thể hoàn thành trong thời gian hợp lý.
    DEFAULT_MAX_DEPTH = 20
    DEFAULT_MAX_CONFIGS = 50000

    def __init__(
        self,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_configurations: int = DEFAULT_MAX_CONFIGS,
    ):
        self.max_depth = max_depth
        self.max_configurations = max_configurations
        self.stats = SolverStats()
        # Event log lưu theo thứ tự thời gian. Có thể bật/tắt qua
        # ``self.record_events``. Mặc định tắt để benchmark nhanh.
        self.record_events: bool = False
        self._events: List[SolverEvent] = []

    # --------------------------------------------------------
    # Quan sát
    # --------------------------------------------------------

    def get_observation(self, engine: GameEngine) -> GameObservation:
        """Chụp trạng thái quan sát được từ GameEngine.

        AI *chỉ* dùng hàm này để lấy thông tin. Không truy cập trực
        tiếp vào ``engine`` ở chỗ khác.

        Đọc ``total_mines`` từ engine nếu có, ngược lại dùng
        config mặc định.
        """
        rows = getattr(engine, "_rows", ROWS)
        cols = getattr(engine, "_cols", COLS)
        if not hasattr(engine, "_rows"):
            rows = getattr(engine, "rows", ROWS)
            cols = getattr(engine, "cols", COLS)
        # Số mìn tổng - ưu tiên lấy từ engine, fallback config
        total_mines = getattr(engine, "_mines_count", MINES)
        if not hasattr(engine, "_mines_count"):
            total_mines = getattr(engine, "total_mines", MINES)
        numbers: Dict[Cell, int] = {}
        for cell in engine.revealed:
            value = engine.get_number(cell)
            if value is not None:
                numbers[cell] = value
        return GameObservation(
            rows=rows,
            cols=cols,
            total_mines=total_mines,
            revealed=set(engine.revealed),
            numbers=numbers,
            flags=set(engine.flags),
        )

    # --------------------------------------------------------
    # Xây dựng ràng buộc
    # --------------------------------------------------------

    def build_constraints(self, obs: GameObservation) -> List[Constraint]:
        """Từ quan sát, sinh danh sách các ràng buộc.

        Mỗi ô đã mở có số dương sinh ra một ràng buộc địa phương:
            sum(mine in hidden_neighbors) = num - flags_neighbors
        (đã trừ số cờ mìn nằm trong lân cận, vì cờ tương đương mìn
        đã biết.)

        Nếu số trên ô là 0 vẫn được sinh ra ràng buộc nhưng với
        target = 0 và tập biến = lân cận chưa biết; solver vẫn dùng
        để kiểm tra nhất quán tổng thể.

        Ngoài ra luôn có ràng buộc tổng:
            sum(mine in remaining_unknown) = total_mines - flags
        nếu còn ô chưa biết.
        """
        constraints: List[Constraint] = []

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
            if not hidden and target != 0:
                # Bất khả thi - nhưng vẫn để solver phát hiện qua
                # bước kiểm tra nhất quán thay vì tự sửa ở đây.
                pass
            constraints.append(
                Constraint(variables=frozenset(hidden), target=target)
            )

        # Ràng buộc tổng số mìn
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
    # Helper: kiểm tra nhất quán từng phần
    # --------------------------------------------------------

    @staticmethod
    def _check_partial(
        assignment: Dict[Cell, int], constraints: Sequence[Constraint]
    ) -> bool:
        """Kiểm tra ràng buộc trên phép gán hiện tại.

        Với mỗi ràng buộc, xét hai tập:
            - assigned_vars: biến đã được gán.
            - unassigned_vars: biến chưa gán.
        Tính sum_assigned + min_possible <= target <=
        sum_assigned + max_possible.
        Trả về False nếu vượt khoảng; True nếu còn khả thi.
        Nếu tất cả biến đã gán mà sum != target thì False (mâu thuẫn).
        """
        for c in constraints:
            assigned_sum = 0
            assigned_count = 0
            total = len(c.variables)
            for var in c.variables:
                if var in assignment:
                    assigned_sum += assignment[var]
                    assigned_count += 1
            unassigned = total - assigned_count
            if unassigned == 0:
                if assigned_sum != c.target:
                    return False
                continue
            if assigned_sum > c.target:
                return False
            if assigned_sum + unassigned < c.target:
                return False
        return True

    # --------------------------------------------------------
    # Sắp xếp biến (heuristic MRV / degree)
    # --------------------------------------------------------

    def _order_variables(
        self,
        variables: List[Cell],
        constraints: Sequence[Constraint],
    ) -> List[Cell]:
        """Sắp xếp biến theo MRV rồi degree.

        Đây chỉ là heuristic sắp xếp thứ tự duyệt; bản chất DFS
        vẫn là duyệt mọi cấu hình nếu không vượt giới hạn.

        MRV ưu tiên biến xuất hiện trong ràng buộc có khoảng khả
        thi nhỏ nhất; degree đếm số ràng buộc chứa biến.
        """

        def degree(cell: Cell) -> int:
            return sum(1 for c in constraints if cell in c.variables and not c.is_trivial())

        scored = []
        for cell in variables:
            # Tính "chật" nhất: biến nào có ràng buộc với khoảng
            # khả thi hẹp nhất được ưu tiên trước.
            tightness = None
            for c in constraints:
                if cell not in c.variables or c.is_trivial():
                    continue
                n = len(c.variables)
                spread = min(c.target, n - c.target)
                if tightness is None or spread < tightness:
                    tightness = spread
            if tightness is None:
                tightness = 10**6
            # Tuple: (tightness nhỏ trước, degree lớn trước)
            scored.append((tightness, -degree(cell), cell))
        scored.sort()
        return [item[2] for item in scored]

    # --------------------------------------------------------
    # DFS liệt kê tất cả cấu hình
    # --------------------------------------------------------

    def dfs_enumerate(
        self,
        variables: List[Cell],
        constraints: Sequence[Constraint],
        mines_target: int,
    ) -> List[Dict[Cell, int]]:
        """Liệt kê toàn bộ cấu hình gán biến nhị phân thỏa mãn ràng
        buộc, đồng thời đảm bảo tổng số mìn trong tập biến bằng
        ``mines_target``.

        Trả về danh sách các assignment (dict mapping cell -> 0/1).
        Một số ràng buộc có thể chứa biến nằm ngoài ``variables``
        (ràng buộc tổng) - solver vẫn kiểm tra tính nhất quán tổng
        thể qua ``_check_partial``.

        Tham số ``mines_target`` chính là target của ràng buộc tổng
        đã rút gọn về tập ``variables``: tức là số mìn dự kiến còn
        lại trong tập biến đang xét.
        """
        results: List[Dict[Cell, int]] = []

        ordered = self._order_variables(list(variables), constraints)
        # Tập biến đầy đủ dùng để kiểm tra tính nhất quán của ràng
        # buộc (bao gồm cả ràng buộc tổng). Các biến ngoài
        # ``variables`` được coi như đã biết = 0 trong partial check.
        baseline_outside: Set[Cell] = set()
        for c in constraints:
            for var in c.variables:
                if var not in {v for v in variables}:
                    baseline_outside.add(var)
        # Tổng mìn kỳ vọng trong tập "ngoài" theo baseline = 0.
        # Tổng mìn trong toàn bộ ràng buộc tổng phải = mines_target +
        # outside_mines = mines_target (vì outside_mines = 0).
        # Do đó ràng buộc tổng sẽ được kiểm tra tự nhiên.

        def recurse(idx: int, assigned: Dict[Cell, int], depth: int) -> bool:
            """Trả về True nếu bị cắt do vượt giới hạn cấu hình."""
            if (
                len(results) >= self.max_configurations
                or depth > self.max_depth * 4
                or self.stats.elapsed_time > 5.0
            ):
                self.stats.search_truncated = True
                return True

            if idx == len(ordered):
                # Hoàn tất một phép gán đầy đủ.
                if sum(assigned[var] for var in ordered) != mines_target:
                    return False
                if not self._check_partial(assigned, constraints):
                    self.stats.backtracks += 1
                    return False
                # Sao chép để tránh bị mutate khi backtrack.
                results.append(dict(assigned))
                self.stats.valid_configurations += 1
                # Phát event nếu đang ghi
                if self.record_events:
                    self._events.append(SolverEvent("dfs_solution", {
                        "config": dict(assigned),
                    }))
                return False

            var = ordered[idx]
            # Thử 0 (an toàn) trước
            for value in (0, 1):
                self.stats.generated_nodes += 1
                assigned[var] = value
                # Kiểm tra ràng buộc tức thời
                ok = self._check_partial(assigned, constraints)
                if ok:
                    self.stats.expanded_nodes += 1
                    if self.record_events:
                        self._events.append(SolverEvent("dfs_try_value", {
                            "var": var, "value": value, "result": "consistent",
                        }))
                    stop = recurse(idx + 1, assigned, depth + 1)
                    if stop:
                        return True
                else:
                    self.stats.backtracks += 1
                    if self.record_events:
                        self._events.append(SolverEvent("dfs_backtrack", {
                            "var": var, "value": value,
                        }))
            # Quay lui: gỡ phép gán
            assigned.pop(var, None)
            return False

        # Bắt đầu: kiểm tra ràng buộc trên assignment rỗng trước.
        # Nếu ngay từ đầu đã mâu thuẫn (ví dụ total_target < 0) thì
        # không có cấu hình nào.
        if not self._check_partial({}, constraints):
            return []

        # Thêm biến baseline_outside không thuộc variables vào
        # assignment với 0 để _check_partial tính đúng.
        init = {var: 0 for var in baseline_outside}
        recurse(0, init, 0)
        return results

    # --------------------------------------------------------
    # DFS chứng minh (target = safe / mine / unknown)
    # --------------------------------------------------------

    def dfs_prove(
        self,
        target: Cell,
        variables: List[Cell],
        constraints: Sequence[Constraint],
        mines_target: int,
    ) -> str:
        """Dùng DFS để chứng minh trạng thái của ``target``.

        Ý tưởng: liệt kê tất cả cấu hình hợp lệ trên tập biến
        ``variables`` (không bao gồm target). Sau đó:
            - Nếu trong mỗi cấu hình hợp lệ, khi đặt target = 0 vẫn
              suy ra được một cấu hình mở rộng hợp lệ => target an
              toàn. Cần xét thêm trường hợp target = 1: nếu không
              có cấu hình mở rộng hợp lệ nào khi target = 1 thì
              target không bao giờ là mìn => an toàn.
        Tương tự cho mìn.

        Để tránh hai lần duyệt, ta liệt kê *tất cả* cấu hình trên
        ``variables`` rồi phân loại:

            - C_safe = số cấu hình mà tổng mìn trong (variables ∪ {target})
              == mines_target (target=0 thì đếm mìn trong variables = mines_target,
              target=1 thì = mines_target - 1) VÀ thỏa ràng buộc địa phương.
        Nhưng đơn giản hơn: liệt kê cấu hình mở rộng bao gồm target
        luôn. Nếu còn cấu hình với target=0 và KHÔNG có cấu hình với
        target=1 => target chắc chắn mìn. Ngược lại.

        Triển khai chọn cách: gọi ``dfs_enumerate`` trên
        variables + [target], và đếm xem trong các cấu hình hợp
        lệ, target mang giá trị 0 bao nhiêu lần và 1 bao nhiêu lần.
        Rồi suy ra safe/mine/unknown.
        """
        if target in {v for v in variables}:
            # target đã nằm trong variables; chỉ cần liệt kê.
            expanded_vars = list(variables)
        else:
            expanded_vars = list(variables) + [target]

        configs = self.dfs_enumerate(expanded_vars, constraints, mines_target)
        if not configs:
            # Không tìm được cấu hình hợp lệ nào - nghĩa là mâu
            # thuẫn ở quan sát hiện tại. Trả về UNKNOWN vì không có
            # bằng chứng để kết luận.
            return UNKNOWN

        # Nếu bị cắt (search_truncated) nhưng có cấu hình, vẫn có
        # thể kết luận nếu đếm đầy đủ một phía.
        if self.stats.search_truncated:
            # Thiếu bằng chứng => không kết luận.
            return UNKNOWN

        seen_safe = 0
        seen_mine = 0
        for cfg in configs:
            v = cfg.get(target)
            if v == 0:
                seen_safe += 1
            elif v == 1:
                seen_mine += 1
        if seen_mine == 0:
            return SAFE
        if seen_safe == 0:
            return MINE
        return UNKNOWN

    # --------------------------------------------------------
    # Tổng hợp suy luận chắc chắn
    # --------------------------------------------------------

    def infer_certain_cells(
        self,
        variables: List[Cell],
        constraints: Sequence[Constraint],
        mines_target: int,
    ) -> Tuple[Set[Cell], Set[Cell], Set[Cell]]:
        """Dùng ``dfs_enumerate`` để tìm các ô chắc chắn.

        Trả về (certain_safe, certain_mine, unknown_set).
        """
        configs = self.dfs_enumerate(list(variables), constraints, mines_target)
        if not configs:
            return set(), set(), set(variables)

        if self.stats.search_truncated:
            # Không đủ bằng chứng
            return set(), set(), set(variables)

        certain_safe: Set[Cell] = set()
        certain_mine: Set[Cell] = set()
        for var in variables:
            always_zero = True
            always_one = True
            for cfg in configs:
                v = cfg.get(var)
                if v != 0:
                    always_zero = False
                if v != 1:
                    always_one = False
                if not always_zero and not always_one:
                    break
            if always_zero:
                certain_safe.add(var)
            elif always_one:
                certain_mine.add(var)
        unknown_set = set(variables) - certain_safe - certain_mine
        return certain_safe, certain_mine, unknown_set

    # --------------------------------------------------------
    # Constraint Propagation (miền rõ ràng)
    # --------------------------------------------------------

    @staticmethod
    def propagate(
        known_safe: Set[Cell],
        known_mines: Set[Cell],
        constraints: Sequence[Constraint],
    ) -> Tuple[Set[Cell], Set[Cell], bool, str]:
        """Chạy lan truyền ràng buộc đơn giản (subset solver).

        Với mỗi ràng buộc:
            - Nếu target == 0: tất cả biến chưa gán -> safe.
            - Nếu target == len(variables): tất cả biến chưa gán -> mine.
            - Các trường hợp khác không quyết định được từ một ràng
              buộc đơn lẻ; solver đầy đủ sẽ dùng tổ hợp ràng buộc
              ở bước DFS.

        Trả về (new_safe, new_mines, changed, status) với status là
        UNKNOWN nếu cần DFS, hoặc SAFE/MINE nếu kết luận ngay, hoặc
        "contradiction" nếu mâu thuẫn.
        """
        new_safe = set(known_safe)
        new_mines = set(known_mines)
        changed = True
        while changed:
            changed = False
            for c in constraints:
                vars_ = set(c.variables)
                unassigned = vars_ - new_safe - new_mines
                if not unassigned:
                    # Tất cả đã gán - kiểm tra xem tổng có khớp
                    total = (len(new_mines & vars_))
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
        return new_safe, new_mines, changed, UNKNOWN

    # --------------------------------------------------------
    # Điều phối
    # --------------------------------------------------------

    def _emit(self, kind: str, payload: Optional[dict] = None) -> None:
        if self.record_events:
            self._events.append(SolverEvent(kind, payload or {}))

    def solve(self, engine: GameEngine) -> Iterable[Tuple[str, Cell]]:
        """Hàm chính. Yield ``("safe", cell)``, ``("mine", cell)``,
        ``("unknown", cell)``.

        Khi một ô an toàn được xác định (từ propagation hoặc DFS),
        nếu đó là ô số 0, tự động thêm các ô lân cận chưa biết
        vào tập an toàn (flood-fill: mở 0 sẽ tự động mở toàn bộ
        vùng xung quanh).

        Luồng xử lý:
            1. Chụp quan sát.
            2. Xây dựng ràng buộc.
            3. Constraint propagation: kết luận safe/mine tức thì.
               Nếu ô an toàn là số 0, flood-fill các lân cận.
            4. Với mỗi ô chưa biết còn lại, dùng ``dfs_prove`` để
               kiểm tra chứng minh safe/mine. Nếu hết ô cần xét mà
               vẫn còn unknown, yield ``("unknown", cell)``.
            5. Không tự ý "đoán" một ô là safe.
        """
        start = time.perf_counter()
        self.stats = SolverStats()
        self._events = []

        obs = self.get_observation(engine)
        self._emit("observe", {"revealed": len(obs.revealed),
                               "flags": len(obs.flags)})

        constraints = self.build_constraints(obs)
        self._emit("constraint_built", {"count": len(constraints)})

        # Tập các ô chưa biết (chưa gán)
        unknown_cells: List[Cell] = []
        for cell in obs.all_cells:
            if cell in obs.revealed or cell in obs.flags:
                continue
            unknown_cells.append(cell)

        # Ràng buộc tổng luôn ở cuối - lấy ra để tính mines_target
        # trong tập unknown_cells.
        if not constraints:
            self.stats.elapsed_time = time.perf_counter() - start
            return

        total_constraint = constraints[-1]
        mines_target = total_constraint.target

        # Propagation
        known_safe: Set[Cell] = set()
        known_mines: Set[Cell] = set()
        ks, km, _, status = self.propagate(known_safe, known_mines, constraints)
        if status == "contradiction":
            # Quan sát mâu thuẫn - yield unknown cho tất cả
            for cell in unknown_cells:
                yield (UNKNOWN, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return
        known_safe = ks
        known_mines = km

        # Cập nhật tập unknown sau propagation
        unknown_cells = [c for c in unknown_cells
                         if c not in known_safe and c not in known_mines]
        # Cập nhật target: mìn còn lại trong unknown_cells = total - len(cờ & known_mines)
        already_mines = len(known_mines)
        remaining_target = mines_target - already_mines
        if remaining_target < 0:
            # Mâu thuẫn
            for cell in unknown_cells:
                yield (UNKNOWN, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return

        # Yield kết quả propagation trước (trước khi return sớm)
        # Flood-fill: nếu ô an toàn có số 0, thêm lân cận vào safe
        newly_added = True
        while newly_added:
            newly_added = False
            for cell in list(known_safe):
                num = obs.numbers.get(cell)
                if num is not None and num == 0:
                    for nb in obs.neighbors(cell):
                        if nb not in known_safe and nb not in known_mines:
                            known_safe.add(nb)
                            newly_added = True
            # Cập nhật unknown_cells sau flood-fill
            unknown_cells = [c for c in unknown_cells
                             if c not in known_safe and c not in known_mines]

        for cell in sorted(known_safe):
            yield (SAFE, cell)
        for cell in sorted(known_mines):
            yield (MINE, cell)

        # Trường hợp đặc biệt: hết ô / hết mìn
        if not unknown_cells:
            self.stats.elapsed_time = time.perf_counter() - start
            return
        if remaining_target == 0:
            # Đã yield known_safe ở trên; không còn unknown_cells nào
            # khác cần yield. Trả về.
            self.stats.elapsed_time = time.perf_counter() - start
            return
        if remaining_target == len(unknown_cells):
            # Tất cả các ô chưa xác định còn lại đều là mìn
            for cell in unknown_cells:
                yield (MINE, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return

        # Cập nhật constraints: loại bỏ biến đã biết khỏi tất cả ràng
        # buộc địa phương, đồng thời trừ target tương ứng với mìn đã
        # biết (cờ + suy luận); ràng buộc tổng đã được tính ở trên.
        reduced = []
        for c in constraints[:-1]:
            # Trừ các ô đã biết (safe hoặc mine) khỏi biến
            vars_ = set(c.variables) - known_safe - known_mines
            # Trừ số mìn đã biết (trong tập variables gốc) khỏi target
            target = c.target - len(known_mines & set(c.variables))
            if not vars_:
                # Tất cả biến đã gán - kiểm tra nhất quán
                if target != 0:
                    # Mâu thuẫn cục bộ
                    continue
                continue
            reduced.append(Constraint(variables=frozenset(vars_), target=target))
        # Ràng buộc tổng đã đúng (chỉ chứa unknown_cells)
        reduced.append(Constraint(
            variables=frozenset(unknown_cells),
            target=remaining_target,
        ))

        # DFS cho từng ô chưa biết
        proven = set()
        for cell in unknown_cells:
            # Nếu đã được prove từ vòng trước thì bỏ qua
            if cell in proven:
                continue
            # Bỏ qua nếu đã vượt giới hạn
            if self.stats.search_truncated:
                yield (UNKNOWN, cell)
                continue

            self._emit("dfs_start", {"target": cell})
            result = self.dfs_prove(cell, unknown_cells, reduced, remaining_target)
            if result == SAFE:
                yield (SAFE, cell)
                proven.add(cell)
                # Flood-fill nếu ô an toàn là số 0
                num = obs.numbers.get(cell)
                if num is not None and num == 0:
                    for nb in obs.neighbors(cell):
                        if nb not in known_safe and nb not in known_mines and nb not in proven:
                            yield (SAFE, nb)
                            proven.add(nb)
            elif result == MINE:
                yield (MINE, cell)
                proven.add(cell)
            else:
                yield (UNKNOWN, cell)

        self.stats.elapsed_time = time.perf_counter() - start
        """Hàm chính. Yield ``("safe", cell)``, ``("mine", cell)``,
        ``("unknown", cell)``.

        Luồng xử lý:
            1. Chụp quan sát.
            2. Xây dựng ràng buộc.
            3. Constraint propagation: kết luận safe/mine tức thì.
            4. Với mỗi ô chưa biết còn lại, dùng ``dfs_prove`` để
               kiểm tra chứng minh safe/mine. Nếu hết ô cần xét mà
               vẫn còn unknown, yield ``("unknown", cell)``.
            5. Không tự ý "đoán" một ô là safe.
        """
        start = time.perf_counter()
        self.stats = SolverStats()
        self._events = []

        obs = self.get_observation(engine)
        self._emit("observe", {"revealed": len(obs.revealed),
                               "flags": len(obs.flags)})

        constraints = self.build_constraints(obs)
        self._emit("constraint_built", {"count": len(constraints)})

        # Tập các ô chưa biết (chưa gán)
        unknown_cells: List[Cell] = []
        for cell in obs.all_cells:
            if cell in obs.revealed or cell in obs.flags:
                continue
            unknown_cells.append(cell)

        # Ràng buộc tổng luôn ở cuối - lấy ra để tính mines_target
        # trong tập unknown_cells.
        if not constraints:
            self.stats.elapsed_time = time.perf_counter() - start
            return

        total_constraint = constraints[-1]
        mines_target = total_constraint.target

        # Propagation
        known_safe: Set[Cell] = set()
        known_mines: Set[Cell] = set()
        ks, km, _, status = self.propagate(known_safe, known_mines, constraints)
        if status == "contradiction":
            # Quan sát mâu thuẫn - yield unknown cho tất cả
            for cell in unknown_cells:
                yield (UNKNOWN, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return
        known_safe = ks
        known_mines = km

        # Cập nhật tập unknown sau propagation
        unknown_cells = [c for c in unknown_cells
                         if c not in known_safe and c not in known_mines]
        # Cập nhật target: mìn còn lại trong unknown_cells = total - len(cờ & known_mines)
        already_mines = len(known_mines)
        remaining_target = mines_target - already_mines
        if remaining_target < 0:
            # Mâu thuẫn
            for cell in unknown_cells:
                yield (UNKNOWN, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return

        # Yield kết quả propagation trước (trước khi return sớm)
        for cell in sorted(known_safe):
            yield (SAFE, cell)
        for cell in sorted(known_mines):
            yield (MINE, cell)

        # Trường hợp đặc biệt: hết ô / hết mìn
        if not unknown_cells:
            self.stats.elapsed_time = time.perf_counter() - start
            return
        if remaining_target == 0:
            # Đã yield known_safe ở trên; không còn unknown_cells nào
            # khác cần yield. Trả về.
            self.stats.elapsed_time = time.perf_counter() - start
            return
        if remaining_target == len(unknown_cells):
            # Tất cả các ô chưa xác định còn lại đều là mìn
            for cell in unknown_cells:
                yield (MINE, cell)
            self.stats.elapsed_time = time.perf_counter() - start
            return

        # Cập nhật constraints: loại bỏ biến đã biết khỏi tất cả ràng
        # buộc địa phương, đồng thời trừ target tương ứng với mìn đã
        # biết (cờ + suy luận); ràng buộc tổng đã được tính ở trên.
        reduced = []
        for c in constraints[:-1]:
            # Trừ các ô đã biết (safe hoặc mine) khỏi biến
            vars_ = set(c.variables) - known_safe - known_mines
            # Trừ số mìn đã biết (trong tập variables gốc) khỏi target
            target = c.target - len(known_mines & set(c.variables))
            if not vars_:
                # Tất cả biến đã gán - kiểm tra nhất quán
                if target != 0:
                    # Mâu thuẫn cục bộ
                    continue
                continue
            reduced.append(Constraint(variables=frozenset(vars_), target=target))
        # Ràng buộc tổng đã đúng (chỉ chứa unknown_cells)
        reduced.append(Constraint(
            variables=frozenset(unknown_cells),
            target=remaining_target,
        ))

        # DFS cho từng ô chưa biết
        proven = set()
        for cell in unknown_cells:
            # Nếu đã được prove từ vòng trước thì bỏ qua
            if cell in proven:
                continue
            # Bỏ qua nếu đã vượt giới hạn
            if self.stats.search_truncated:
                yield (UNKNOWN, cell)
                continue

            self._emit("dfs_start", {"target": cell})
            result = self.dfs_prove(cell, unknown_cells, reduced, remaining_target)
            if result == SAFE:
                yield (SAFE, cell)
                proven.add(cell)
            elif result == MINE:
                yield (MINE, cell)
                proven.add(cell)
            else:
                yield (UNKNOWN, cell)

        self.stats.elapsed_time = time.perf_counter() - start

    # --------------------------------------------------------
    # API tiện cho GUI / benchmark (tương thích với code cũ)
    # --------------------------------------------------------

    def get_stats(self) -> SolverStats:
        return self.stats

    def get_events(self) -> List[SolverEvent]:
        return list(self._events)

    # Backwards compatibility shim ------------------------------------------------
    # Code cũ đọc ``self.expanded_nodes`` / ``self.generated_nodes`` trực tiếp.

    @property
    def expanded_nodes(self) -> int:
        return self.stats.expanded_nodes

    @property
    def generated_nodes(self) -> int:
        return self.stats.generated_nodes


# ============================================================
# MINESWEEPER GAME - facade cho GUI
# ============================================================

class MinesweeperGame:
    """Lớp facade kết nối GUI với engine + solver.

    Giữ nguyên hầu hết API để không phải sửa
    ``minesweeper_gui.py``. Chỉ thay phần nội bộ: dùng ``AISolver``
    mới và event log có cấu trúc để demo từng bước.
    """

    def __init__(self):
        self.engine = GameEngine()
        self.solver = AISolver()
        self.ai_path: List[Cell] = []
        self.ai_index = 0
        self.stats = {"expanded_nodes": 0,
                      "generated_nodes": 0,
                      "backtracks": 0,
                      "valid_configurations": 0,
                      "search_truncated": False}
        self.last_events: List[SolverEvent] = []

    def new_game(self):
        self.engine.new_game()
        self.ai_path = []
        self.ai_index = 0
        self.stats = {"expanded_nodes": 0,
                      "generated_nodes": 0,
                      "backtracks": 0,
                      "valid_configurations": 0,
                      "search_truncated": False}
        self.last_events = []

    @property
    def mine_positions(self) -> Set[Cell]:
        return self.engine.mine_positions

    @property
    def revealed(self) -> Set[Cell]:
        return self.engine.revealed

    @property
    def flags(self) -> Set[Cell]:
        return self.engine.flags

    @property
    def numbers(self) -> Dict[Cell, int]:
        return self.engine._numbers

    @property
    def game_over(self) -> bool:
        return self.engine.game_over

    @property
    def won(self) -> bool:
        return self.engine.won

    def reveal(self, cell: Cell, source: str = "AI") -> Optional[bool]:
        result = self.engine.reveal(cell)
        if source == "Player":
            self.ai_path = []
            self.ai_index = 0
        return result

    def toggle_flag(self, cell: Cell):
        self.engine.toggle_flag(cell)
        self.ai_path = []
        self.ai_index = 0

    def start_ai(self, algorithm: str = "DFS") -> Iterable:
        """Vẫn tương thích: yield các bước suy luận.

        Với ``algorithm == "DFS"`` sẽ chạy solver mới. HillClimbing
        giữ nguyên logic cũ nhưng vẫn dùng solver không truy cập
        mine_positions.

        Yield contract (giữ tương thích với code cũ):
            - ``cell`` (tuple 2 số): ô chắc chắn an toàn.
            - ``("mine", cell)``: ô chắc chắn là mìn.
            - ``("guess", cell)``: ô đoán (chỉ với HillClimbing).
            - ``("unknown", cell)``: ô chưa đủ bằng chứng (DFS).

        Để phân biệt với cell tuple thuần, ta yield các loại còn
        lại dưới dạng tuple 2 phần tử. Đây là API tương thích ngược:
        code cũ kiểm tra ``isinstance(item, tuple) and item[0] in
        {"mine", "guess", "unknown"}`` để bỏ qua.
        """
        self.stats = {"expanded_nodes": 0,
                      "generated_nodes": 0,
                      "backtracks": 0,
                      "valid_configurations": 0,
                      "search_truncated": False}

        if algorithm == "DFS":
            # Bật ghi event để GUI có thể hiển thị
            self.solver = AISolver(max_depth=self.solver.max_depth,
                                   max_configurations=self.solver.max_configurations)
            self.solver.record_events = True

            safe_cells = []
            mines_found = []

            for kind, cell in self.solver.solve(self.engine):
                self.last_events = self.solver.get_events()
                if kind == SAFE:
                    if cell not in self.ai_path:
                        self.ai_path.append(cell)
                    safe_cells.append(cell)
                    yield cell
                elif kind == MINE:
                    mines_found.append(cell)
                    yield ("mine", cell)
                else:
                    # unknown - thông báo cho caller biết nhưng KHÔNG
                    # gắn vào ai_path để tránh giả lập là safe.
                    yield ("unknown", cell)

            stats = self.solver.get_stats()
            self.stats.update({
                "expanded_nodes": stats.expanded_nodes,
                "generated_nodes": stats.generated_nodes,
                "backtracks": stats.backtracks,
                "valid_configurations": stats.valid_configurations,
                "search_truncated": stats.search_truncated,
            })
            return safe_cells, mines_found

        elif algorithm == "HillClimbing":
            safe_cells = []
            mines_found = []
            for item in self._solve_hillclimbing():
                if isinstance(item, tuple) and item[0] == "mine":
                    mines_found.append(item[1])
                else:
                    safe_cells.append(item)
                yield item
            return safe_cells, mines_found
        else:
            return [], []

    def _solve_hillclimbing(self) -> Iterable:
        """Phiên bản Hill Climbing đơn giản, vẫn không truy cập
        mine_positions. Chỉ dùng constraint propagation.

        Theo yêu cầu đề bài, việc đoán ngẫu nhiên phải tách riêng
        khỏi suy luận chắc chắn. Hàm này chỉ chạy propagation;
        việc chọn nước đi khi không đủ thông tin do caller quyết
        định (không tự ý đoán).

        Yield:
            - ``cell`` cho ô chắc chắn an toàn (từ propagation).
            - ``("mine", cell)`` cho cờ mìn suy ra được.
        """
        from config import MINES as _MINES
        obs = self.solver.get_observation(self.engine)
        known_safe: Set[Cell] = set()
        known_mines: Set[Cell] = set()
        expanded = 0

        # Chạy propagation đến điểm cố định. Không tự ý đoán.
        for _ in range(50):
            constraints = self.solver.build_constraints(obs)
            ks, km, _, _ = self.solver.propagate(known_safe, known_mines, constraints)
            new_safe = ks - known_safe
            new_mines = km - known_mines
            known_safe, known_mines = ks, km
            for cell in new_safe:
                if cell not in self.engine.revealed and cell not in self.engine.flags:
                    expanded += 1
                    self.ai_path.append(cell)
                    yield cell
            for cell in new_mines:
                if cell not in self.engine.flags:
                    self.engine.flags.add(cell)
                    yield ("mine", cell)
            if not new_safe and not new_mines:
                break

        self.stats.update({"expanded_nodes": expanded,
                           "generated_nodes": 0})

    def _hill_score(self, obs: GameObservation, cell: Cell) -> float:
        from config import MINES as _MINES
        related = []
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
            prob = 1.0 - _MINES / max(1, len(hidden))
            return max(0.01, prob)
        # Trung bình 1 - target/len
        scores = [1.0 - target / max(1, len(hidden))
                  for hidden, target in related]
        return max(0.01, min(0.99, sum(scores) / len(scores)))

    def next_step(self) -> Optional[Cell]:
        if self.ai_index >= len(self.ai_path):
            return None
        cell = self.ai_path[self.ai_index]
        self.ai_index += 1
        return cell

    def reset(self):
        self.engine.revealed = set()
        self.engine.flags = set()
        self.engine.game_over = False
        self.engine.won = False
        self.ai_path = []
        self.ai_index = 0
        self.stats = {"expanded_nodes": 0,
                      "generated_nodes": 0,
                      "backtracks": 0,
                      "valid_configurations": 0,
                      "search_truncated": False}
        self.last_events = []
