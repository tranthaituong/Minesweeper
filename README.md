# Minesweeper — Game Engine & AI Solver

Dự án Python 3 với Pygame, cài đặt ba thuật toán giải Minesweeper và giao diện trực quan để thao tác từng bước, so sánh hiệu năng.

---

## Cấu trúc

```
.
├── main.py                    # Điểm khởi chạy Pygame
├── config.py                  # Cấu hình bàn cờ (ROWS, COLS, MINES, CELL_SIZE)
├── requirements.txt           # pygame==2.6.1
│
├── src/
│   ├── minesweeper_game.py    # GameEngine + AISolver (DFS/A*) + GameObservation
│   ├── minesweeper_gui.py     # Giao diện Pygame
│   ├── hill_climbing.py       # HillClimbingSolver — tách biệt hoàn toàn
│   └── rendering.py            # Hỗ trợ HiDPI / Retina
│
├── tests/
│   ├── test_ai_solver.py      # 10 test case cho DFS (CSP model)
│   ├── test_hill_climbing.py  # 8 test case cho Hill Climbing
│   └── test_frontend.py        # 19 test case cho giao diện
│
├── experiments.py             # Tạo bàn deterministic + đo hiệu năng
├── benchmark.py               # Chạy benchmark, xuất CSV
└── README.md
```

---

## Cài đặt

```bash
# Tạo môi trường ảo
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS / Linux

# Cài thư viện
python -m pip install -r requirements.txt

# Chạy giao diện
python main.py
```

---

## Các thuật toán

### DFS + Backtracking (CSP)
Mô hình hóa bàn cờ thành bài toán ràng buộc (CSP):

1. **Constraint propagation** — sinh ô chắc chắn `safe` / `mine` mà không cần duyệt.
2. **DFS nhị phân** — thử gán 0/1 cho từng ô, kiểm tra ràng buộc từng phần, backtrack khi vi phạm.
3. Chỉ kết luận an toàn/không an toàn khi thật sự có bằng chứng từ *mọi* cấu hình hợp lệ.

### Hill Climbing
Hoạt động tách biệt hoàn toàn với `GameEngine`, chỉ dùng `GameObservation`:

- **Giai đoạn A**: Constraint propagation giống DFS.
- **Giai đoạn B**: Khi không còn tiến bộ, dùng heuristic để chọn ô tốt nhất theo mức độ thỏa mãn ràng buộc cục bộ.
- Yield theo contract: `("safe", cell)` / `("mine", cell)` / `("guess", cell)` / `("prop_done", None)`.

---

## Giao diện

| Thao tác | Chức năng |
|---|---|
| Chuột trái | Mở ô |
| Chuột phải / Ctrl + trái | Cắm / gỡ cờ |
| DFS / HillClimbing | Chọn thuật toán |
| Step / → | Thực hiện một bước AI |
| Play / Pause · Space | Chạy hoặc tạm dừng |
| Nút tốc độ | 0.5× / 1× / 2.5× |
| Reset bàn cũ · R | Giữ vị trí mìn, đặt lại trạng thái |
| Bàn mới · N | Tạo bàn mới theo seed tiếp theo |
| ‹ / › | Quay lại / đi tới seed khác |
| Chạy benchmark | 10 bàn × 3 lần × mỗi thuật toán |

---

## Chạy benchmark

```bash
python benchmark.py --seeds 10 --repeats 3
```

Kết quả lưu trong `benchmark_results/`:

| File | Nội dung |
|---|---|
| `raw.csv` | Số liệu từng lượt chạy |
| `by_input.csv` | Trung vị theo từng seed |
| `summary.csv` | Tổng hợp theo thuật toán |
| `metadata.json` | Cấu hình benchmark |
| `run.log` | Nhật ký chạy từ giao diện |

Các chỉ số đo: `planning_ms`, `python_peak_kib`, `expanded_nodes`, `generated_nodes`, `safe_cells_found`.

---

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

| Bộ test | Test case | Phạm vi |
|---|---|---|
| `test_ai_solver.py` | 10 | DFS — CSP, mâu thuẫn, giới hạn, isolation |
| `test_hill_climbing.py` | 8 | Propagation, guess, trạng thái thắng/thua |
| `test_frontend.py` | 19 | Step, Play/Pause, Reset, cắm cờ, benchmark, resize, Retina |

---

## Cấu hình bàn cờ

Chỉnh trong `config.py`:

```python
ROWS = 10
COLS = 10
MINES = 10
CELL_SIZE = 50
```

Cùng cấu hình + seed sẽ tạo lại bàn cờ y hệt.
