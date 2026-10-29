# Minesweeper — DFS và Hill Climbing

Ứng dụng Python 3 / Pygame để xem các bước xử lý Minesweeper và so sánh thời gian, bộ nhớ của DFS với Hill Climbing.

## Chạy trên macOS

Mở Terminal trong thư mục vừa giải nén rồi chạy:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Những lần sau chỉ cần kích hoạt môi trường và mở chương trình:

```bash
source .venv/bin/activate
python main.py
```

Trên Windows dùng `python -m venv .venv`, sau đó `.venv\Scripts\activate`.

## Sử dụng

| Điều khiển | Công việc |
|---|---|
| DFS / Hill Climbing | Chọn thuật toán |
| Step / phím → | Thực hiện một hành động: mở ô hoặc cắm cờ; ô số 0 có thể mở lan nhiều ô |
| Play / Pause / Space | Trình diễn liên tiếp hoặc tạm dừng vòng suy luận hiện tại |
| Reset input / R | Khôi phục vị trí mìn, các ô mở và cờ đúng như đầu input |
| Input tiếp / N và ‹ | Chuyển giữa T01–T09 |
| Chuột trái / chuột phải | Mở ô / cắm và gỡ cờ |
| Chạy benchmark | Đo lại 9 input × 2 thuật toán × 3 lần |

Khi một vòng suy luận kết thúc, bấm Step hoặc Play để phân tích trạng thái mới. Lịch sử ghi riêng **AI suy luận**, **AI cắm cờ** và **AI đoán**. Ô đoán có thể trúng mìn theo kết quả thực tế của bàn.

## Vì sao bàn đã mở sẵn vài ô?

Các số mở sẵn là dữ kiện ban đầu của bài toán, giống một câu đố được cho trước. DFS và Hill Climbing đều nhận cùng dữ kiện đó. Bộ input có bàn 5 × 5, 4 mìn, với 7, 10 hoặc 12 ô ẩn.

`inputs.json` lưu bàn để tái lập và kiểm tra kết quả. Khi chạy solver, `experiments.py` chỉ truyền kích thước, tổng mìn, số đang hiện và cờ qua `ObservationEngine`. Đối tượng này chặn việc đọc vị trí mìn ẩn.

## Chạy và đọc thực nghiệm

```bash
python benchmark.py --cases 9 --repeats 3
```

Mỗi lượt đo **một vòng suy luận từ input ban đầu**. Thời gian giải và đỉnh bộ nhớ Python được đo ở hai lượt riêng; mỗi thuật toán được tạo lại từ cùng dữ kiện. Thống kê được lấy sau khi solver trả kết quả xong.

Kết quả trong `benchmark_results/`:

- `BAO_CAO_THUC_NGHIEM.md`: bảng thời gian–bộ nhớ và nhận xét để đưa vào báo cáo nhóm.
- `by_input.csv`: trung vị từng thuật toán trên từng input.
- `raw.csv`: toàn bộ 54 lượt đo.
- `summary.csv`: số liệu tổng hợp.
- `metadata.json`: máy chạy, phiên bản Python và mã kiểm tra nguồn/input.
- `run.log`: tiến độ khi bấm nút trên giao diện.

Đọc cột `safe_deductions` và `mine_deductions` để biết số kết luận suy luận. `guesses` là số ô đoán, `guess_hits_mine` cho biết ô đoán trúng mìn. `missed_forced_safe` / `missed_forced_mines` là số kết luận suy ra được từ dữ kiện mà solver còn bỏ sót.

DFS đếm nhánh hợp lệ và phép gán nhị phân; Hill Climbing đếm ứng viên mô phỏng và ứng viên chấm điểm. Giao diện đặt tên theo từng cách đếm; bảng so sánh chính dùng thời gian, bộ nhớ và kết quả suy luận.

## Các file theo phần việc

| Phần | File |
|---|---|
| Thuật toán và bộ máy trò chơi — Người 1 | `src/minesweeper_game.py`, `src/hill_climbing.py` |
| Giao diện — Người 2 | `src/minesweeper_gui.py`, `rendering.py`, `main.py` |
| Input và đo thực nghiệm — Người 2 | `inputs.json`, `prepare_inputs.py`, `experiments.py`, `benchmark.py` |
| Phần viết báo cáo — Người 2 | `BAO_CAO_GIAO_DIEN.md`, `benchmark_results/BAO_CAO_THUC_NGHIEM.md` |
| Trao đổi với Người 1 | `PHOI_HOP_BACKEND.md`, `check_backend.py`, `backend_cases.json` |

Hai file thuật toán trong gói này đã được cập nhật để sửa các lỗi propagation, suy luận safe của DFS và quy tắc chấp nhận bước của Hill Climbing. Bản giao diện và bộ đo được tích hợp trong cùng thư mục để mở chạy trực tiếp.

Nếu thay đổi tiếp hai file trong `src/`, cần giữ giao tiếp `start_ai()` trả các nhãn `safe`, `mine`, `guess`, `unknown`, rồi chạy lại benchmark để cập nhật số liệu.

## Kiểm tra

```bash
python -m unittest discover -s tests -v
python check_backend.py
```

Bộ kiểm tra gồm 15 ca: Step, Pause, Reset, hủy lượt tính, cắm cờ, nhãn đoán, đường dẫn benchmark, Retina, input và số liệu sau khi solver hoàn tất. `check_backend.py` xuất trường hợp cụ thể vào `backend_cases.json`; các lỗi backend được liệt kê trong `PHOI_HOP_BACKEND.md` đã được xử lý.

Để đổi cấu hình bàn, sửa `config.py`, chạy `python prepare_inputs.py`, rồi đo lại. `GIAO_DIEN_RETINA.png` là ảnh giao diện khi chạy thực tế trên Mac; `KIEM_TRA_RETINA.json` ghi cửa sổ 1160 × 763 và vùng vẽ 2320 × 1526, tương ứng Retina 2×.
