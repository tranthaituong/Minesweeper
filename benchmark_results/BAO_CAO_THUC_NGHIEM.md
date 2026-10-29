# Minesweeper — Giao diện và thực nghiệm DFS / Hill Climbing

## Thiết kế thực nghiệm

Mỗi input là một bàn 5 × 5 có 4 mìn và một tập ô đã mở sẵn. Hai thuật toán nhận cùng các số đang hiện, tổng số mìn và cờ. Nhiệm vụ của mỗi lượt là suy luận một lần từ trạng thái đó: xác định ô an toàn, ô có mìn và, với Hill Climbing, đề xuất ô đoán nếu có.

Bộ thử gồm 9 input, mỗi thuật toán lặp 3 lần/input. Các input có 7, 10, 12 ô ẩn; số ô ẩn biểu thị quy mô đầu vào. Thời gian và bộ nhớ trong bảng là trung vị các lần lặp.

Thời gian đo bằng `time.perf_counter()` trong lúc chạy và thu kết quả solver, tách khỏi việc mở cửa sổ, dựng input và khởi tạo tiến trình. Bộ nhớ đo ở một lượt chạy riêng bằng `tracemalloc`: đỉnh bộ nhớ Python cấp phát cho đối tượng giải, suy luận và lưu kết quả. Đơn vị KiB = 1024 byte. Đây là bộ nhớ Python của lượt giải, khác với tổng RAM của cả ứng dụng.

## Kết quả trên từng input

| Input | Ô ẩn | DFS (ms) | HC (ms) | DFS (KiB) | HC (KiB) | An toàn DFS/HC | Mìn DFS/HC | Đoán HC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T01 | 7 | 0.2897 | 0.5122 | 29.09 | 38.55 | 3/2 | 4/3 | 1 |
| T02 | 10 | 1.8451 | 1.0515 | 107.22 | 40.07 | 3/2 | 1/1 | 1 |
| T03 | 12 | 0.1444 | 0.2338 | 21.40 | 22.52 | 8/8 | 4/4 | 0 |
| T04 | 7 | 0.1575 | 0.1892 | 22.39 | 24.34 | 3/3 | 4/4 | 0 |
| T05 | 10 | 0.4895 | 1.1139 | 46.91 | 40.48 | 6/4 | 4/1 | 1 |
| T06 | 12 | 1.7771 | 1.3859 | 93.83 | 41.41 | 7/3 | 3/1 | 1 |
| T07 | 7 | 0.5178 | 1.5452 | 40.80 | 41.98 | 3/1 | 4/2 | 1 |
| T08 | 10 | 0.4129 | 1.1346 | 34.08 | 41.52 | 6/5 | 4/2 | 1 |
| T09 | 12 | 1.8312 | 2.0550 | 139.27 | 41.09 | 6/4 | 2/0 | 1 |

## Phân tích

- Trên bộ input này, Hill Climbing nhanh hơn DFS ở 2/9 input và dùng ít bộ nhớ Python hơn ở 4/9 input.
- Trung vị toàn bộ lượt chạy: DFS 0.4594 ms, 40.80 KiB; Hill Climbing 1.0781 ms, 40.48 KiB.
- Xét tốc độ và bộ nhớ theo từng input; xét khả năng suy luận bằng số ô an toàn và mìn tìm được. Cột đoán được tách riêng vì đó là đề xuất cần mở ô để kiểm tra.
- Bộ kiểm tra liệt kê các cách đặt mìn phù hợp với số đang hiện để đối chiếu các kết luận safe/mine. Bước đối chiếu chạy sau khi đo và không cung cấp dữ liệu cho solver.

- DFS: kết luận safe/mine đúng ở 9/9 input. Tìm đủ các kết luận safe/mine suy ra được trên các input đã chạy.
- HillClimbing: kết luận safe/mine đúng ở 9/9 input. Còn bỏ sót kết luận suy ra được ở T01, T02, T05, T06, T07, T08, T09.

Khi số ô ẩn nhỏ, suy diễn ràng buộc có thể giải quyết phần lớn công việc, khiến hai thời gian gần nhau. Khi cần duyệt nhiều phép gán, DFS phải tổng hợp các cấu hình hợp lệ; Hill Climbing của phiên bản đang đo đánh giá nhóm ứng viên và trả đề xuất theo heuristic. Vì đầu ra có thể khác nhau, đọc các cột kết quả cùng với cột thời gian để chọn cách xử lý phù hợp.

## Cách dùng giao diện để trình bày

1. Chọn input T01–T09 bằng hai nút chuyển bàn.
2. Chọn DFS, bấm Step để xem từng hành động; Play/Pause để trình diễn liên tiếp.
3. Bấm Reset: khôi phục đúng các ô mở ban đầu, vị trí mìn và cờ ban đầu.
4. Chọn Hill Climbing và chạy trên cùng input. Lịch sử phân biệt suy luận an toàn, cắm cờ và đoán.
5. Bấm Chạy benchmark để xuất lại bảng thời gian và bộ nhớ.

## Thông tin lần chạy

- Bộ mã ban đầu tham chiếu: `a2b8610d1daf53633ccb333459a8a87dc2b8db06`; hai solver đã được sửa theo các lỗi backend được ghi trong `PHOI_HOP_BACKEND.md`.
- Python: 3.11.2.
- Máy chạy: Windows-10-10.0.26200-SP0.
- Thời điểm UTC: 2026-10-29T16:36:31.265696+00:00.
- Mỗi lượt benchmark đo một vòng suy luận; số đo không gồm hoạt ảnh hay thời gian người dùng thao tác.
- Bảng phản ánh phiên bản solver sau khi sửa lỗi DFS và Hill Climbing; cần chạy lại benchmark sau mỗi thay đổi thuật toán.
