# Minesweeper — Giao diện và thực nghiệm

Ứng dụng Python 3 sử dụng Pygame để hiển thị bàn cờ, điều khiển DFS/A* và chạy
thực nghiệm. Frontend kết nối với backend qua lớp `MinesweeperGame`.

## 1. Phân công

| Người phụ trách | Công việc |
| --- | --- |
| Người 1 — Backend | Luật chơi, mô hình bài toán, DFS, A*, heuristic, bộ input và thống kê tìm kiếm |
| Người 2 — Frontend và thực nghiệm | Giao diện Pygame, điều khiển, kiểm thử, chạy benchmark, lập bảng và phân tích kết quả |
| Cả hai | Thống nhất dữ liệu trao đổi, ghép chương trình và chuẩn bị demo |

## 2. Cấu trúc và cách ghép

Đặt các file sau vào cùng thư mục dự án:

| File | Chức năng | Cách ghép |
| --- | --- | --- |
| `main.py` | Khởi chạy Pygame | Thay file khởi chạy Tkinter cũ |
| `minesweeper_gui.py` | Bàn cờ và các nút điều khiển | Thay giao diện cũ |
| `rendering.py` | Hiển thị Retina/HiDPI và biểu tượng ứng dụng | Thêm vào dự án |
| `experiments.py` | Tạo bàn theo seed và đo hiệu năng | Thêm vào dự án |
| `benchmark.py` | Chạy nhiều input và xuất bảng CSV | Thêm vào dự án |
| `requirements.txt` | Thư viện Pygame | Ghép với danh sách thư viện của nhóm |
| `tests/test_frontend.py` | Kiểm tra giao diện và công cụ đo | Đặt trong thư mục `tests/` |

Sử dụng `config.py` và `minesweeper_game.py` do Người 1 quản lý. Gói frontend
gồm các file trong bảng trên; ghép chúng với hai file backend để chạy chương trình.

## 3. Cài đặt và chạy

Sử dụng Python 3.10 trở lên. Mở Terminal trong thư mục dự án và chạy:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Trên Windows, tạo môi trường bằng `python -m venv .venv` và kích hoạt bằng
`.venv\Scripts\activate`.

Các lần chạy tiếp theo, kích hoạt môi trường rồi nhập `python main.py`.

## 4. Sử dụng giao diện

| Thao tác | Chức năng |
| --- | --- |
| Chuột trái | Mở ô |
| Chuột phải hoặc Control + chuột trái | Cắm/gỡ cờ |
| DFS / A* | Chọn thuật toán |
| Step hoặc phím mũi tên phải | Thực hiện một bước AI |
| Play/Pause hoặc phím Space | Chạy/tạm dừng AI |
| Nút tốc độ | Chuyển giữa 0.5×, 1× và 2.5× |
| Reset bàn cũ hoặc phím R | Giữ vị trí mìn, đặt lại các ô, cờ, kế hoạch và đồng hồ |
| Bàn mới hoặc phím N | Tạo bàn theo seed tiếp theo |
| Nút ‹ | Quay về seed trước |
| Chạy benchmark | Đo 10 input, mỗi thuật toán chạy 3 lần |

AI tạm dừng khi gặp ô đang cắm cờ. Gỡ cờ rồi bấm Step hoặc Play để tiếp tục.
Khi mở ô bằng tay, chương trình lập lại kế hoạch AI ở lần chạy tiếp theo.
Tọa độ trên giao diện bắt đầu từ 1; tọa độ trong backend bắt đầu từ 0.

Để xem hai thuật toán trên cùng bàn: chạy DFS, bấm Reset bàn cũ, chọn A* và chạy lại.

Giao diện hiển thị số mìn, cờ đã cắm, ô an toàn đã mở, trạng thái AI, tiến độ và
các bước gần nhất. Đồng hồ trên cùng tính thời gian chơi; mục “Lập kế hoạch”
hiển thị thời gian tính toán của backend.

## 5. Cấu hình và hiển thị

Chỉnh `ROWS`, `COLS`, `MINES` trong `config.py`, sau đó khởi động lại chương trình.
Cùng cấu hình và seed sẽ tạo lại cùng một bàn cờ.

Giao diện vẽ theo số pixel thực của cửa sổ. Màn hình Retina 2× hiển thị nhãn
`RETINA 2×` ở góc trên bên phải. Biểu tượng ứng dụng sử dụng ảnh M 512 × 512 pixel.

## 6. Kết nối backend

Giao diện sử dụng các thành phần sau của `MinesweeperGame`:

| Thành phần | Dữ liệu trao đổi |
| --- | --- |
| `reveal(cell, source)` | Thực hiện thao tác mở ô |
| `start_ai(algorithm)` | Lập kế hoạch cho DFS hoặc A* |
| `next_step()` | Lấy ô tiếp theo trong kế hoạch |
| `numbers`, `revealed`, `flags`, `mine_positions` | Dữ liệu bàn cờ để quản lý và hiển thị |
| `ai_path`, `ai_index` | Kế hoạch và bước hiện tại |
| `game_over`, `won` | Trạng thái kết thúc và chiến thắng |

Các đầu việc tích hợp tiếp theo:

| Đầu việc | Phụ trách |
| --- | --- |
| Xác định thông tin AI được phép biết, state, action, goal test và chi phí | Người 1 thiết kế; cả hai thống nhất |
| Với mô hình bàn mìn ẩn, cho solver nhận các ô đã mở và con số; bộ game giữ đáp án để kiểm tra thao tác | Người 1 |
| Điều chỉnh `start_ai()`, hiện đang lấy `safe_cells` trực tiếp từ `mine_positions`, theo mô hình đã chọn | Người 1 |
| Sửa luồng `astar_safe_order()` → `astar_path()`: hiện `start` thuộc tập đích nên hàm trả `[start]` ngay | Người 1 |
| Đồng bộ cách sinh nước đi, chi phí và heuristic của A*; kiểm tra khoảng cách Manhattan khi dùng 8 hướng chi phí 1 | Người 1 |
| Xuất kết quả, hành động và `expanded_nodes` từ backend | Người 1 |
| Kết nối kết quả và thống kê mới vào giao diện, bộ đo và `validate_plan()` | Người 2 |
| Chuẩn bị input theo các mức độ khó | Người 1 |
| Chạy bộ input, lập bảng và viết phần phân tích | Người 2 |

Khi solver ra quyết định sau từng lần mở ô, frontend gọi quyết định tiếp theo
sau khi cập nhật bàn cờ. Hai người thống nhất cách trả kết quả trước khi ghép
luồng xử lý này.

## 7. Chạy benchmark và đọc kết quả

Đóng cửa sổ game, rồi chạy trong Terminal:

```bash
python benchmark.py --seeds 10 --repeats 3
```

Chọn dải seed và thư mục kết quả bằng lệnh:

```bash
python benchmark.py --start-seed 20 --seeds 10 --repeats 3 --output ket_qua
```

Kết quả mặc định được lưu trong `benchmark_results/` cạnh chương trình:

| File | Nội dung |
| --- | --- |
| `raw.csv` | Số liệu từng lượt chạy |
| `by_input.csv` | Trung vị của từng thuật toán trên từng input |
| `summary.csv` | Bảng tổng hợp theo thuật toán |
| `metadata.json` | Cấu hình và cách đo |
| `run.log` | Nhật ký khi chạy benchmark từ giao diện |

Các chỉ số:

- `planning_ms`: thời gian gọi `start_ai()`, đo bằng `time.perf_counter()`.
- `python_peak_kib`: đỉnh bộ nhớ cấp phát Python, đo bằng `tracemalloc` ở lượt riêng.
- `planned_cells`: số ô trong kế hoạch mở.
- `expanded_nodes`: số trạng thái mở rộng do backend cung cấp; cột hiện để trống.
- `valid_plan`: kết quả kiểm tra danh sách ô mà backend trả về.

Bộ đo hiện gọi chức năng lập thứ tự mở ô của backend. Các seed thay đổi bố trí
mìn trên cùng cấu hình. Khi ghép bộ giải mới, Người 2 cập nhật phạm vi đo và
nhận thống kê tìm kiếm từ backend.

Quy trình thực nghiệm: chọn bộ input theo mức độ khó, chạy DFS và A* từ cùng
trạng thái ban đầu, lặp lại, tổng hợp trung vị theo input, rồi phân tích thời
gian, bộ nhớ và số trạng thái mở rộng. Báo cáo ghi rõ kết quả của từng thuật toán
trên từng nhóm input và giải thích nguyên nhân từ cách tìm kiếm, heuristic.

## 8. Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Bộ kiểm thử gồm 19 trường hợp: Step, Play/Pause, Reset, cắm cờ, đổi bàn, mở ô
bằng tay, kết nối kế hoạch AI, thay đổi kích thước cửa sổ, Retina và xuất CSV.

## 9. Nội dung báo cáo

- Người 1: mô hình bài toán, DFS, A*, heuristic và cách tạo input.
- Người 2: giao diện, kiểm thử, phương pháp đo, bảng số liệu và phân tích.
- Cả hai: hướng dẫn chạy, kịch bản demo và slides phần Minesweeper.
