# Phối hợp với phần thuật toán

Phần Người 2 đã tích hợp: giao diện DFS/Hill Climbing, Step/Play/Pause/Reset, chín input cố định, bộ đo thời gian–bộ nhớ, bảng kết quả và phần viết báo cáo.

Người 1 cập nhật hai file `src/minesweeper_game.py` và `src/hill_climbing.py`. Các trường hợp dưới đây được tái hiện bằng:

```bash
python check_backend.py
```

Kết quả chi tiết được ghi trong `backend_cases.json`; tọa độ trong file dùng chỉ số bắt đầu từ 0.

## 1. DFS trả thiếu ô an toàn khi đã xác định đủ mìn

Trong `AISolver.solve()`, nhánh `remaining_target == 0` trả về ngay. Lúc này các ô chưa xác định còn lại đều an toàn và cần được yield `("safe", cell)` trước khi kết thúc.

- Input T03: tìm được 5/8 ô an toàn; bỏ sót `(3,0)`, `(4,0)`, `(4,1)`.
- Input T04: tìm được 2/3 ô an toàn; bỏ sót `(2,3)`.

## 2. Hill Climbing cần giữ kết quả propagation trong bước mô phỏng

Trong hai vòng lặp của `_best_candidate()`, chương trình kiểm tra `not ch` rồi thoát trước khi nhận `ks2, km2`. Hàm `propagate()` có thể trả tập suy luận mới cùng `changed=False` sau khi đã chạy tới điểm cố định. Cần giữ các tập trả về trước khi kiểm tra điều kiện dừng; nhánh mâu thuẫn xử lý riêng.

Trường hợp tối thiểu: ràng buộc một ô có giá trị 0 trả về ô đó là safe và `changed=False`. Caller hiện tại bỏ qua tập safe vừa nhận.

## 3. Hill Climbing cần chốt quy tắc chấp nhận bước đi theo điểm

`_best_candidate()` nhận `baseline_score`; `solve()` nhận lại `new_score`, rồi phát `guess` trực tiếp. Cần dùng hai điểm này để áp dụng quy tắc chuyển trạng thái của biến thể Hill Climbing được trình bày trong báo cáo, gồm cách xử lý điểm bằng nhau và lúc không còn bước cải thiện.

Trường hợp tái hiện: input quan sát có `(2,2)=0`, `(4,3)=3`, tổng 4 mìn. Chương trình chấp nhận ô `(1,4)` dù điểm đánh giá giảm từ `2.1704347826` xuống `1.9155009452`.

## Cập nhật và gửi lại

1. Sửa thuật toán, giữ kết quả theo nhãn `safe`, `mine`, `guess`, `unknown`.
2. Chạy `python check_backend.py` để xem lại các trường hợp trên.
3. Chạy `python benchmark.py --cases 9 --repeats 3` để cập nhật số liệu và phần phân tích.
4. Gửi hai file thuật toán mới và phần mô tả state, action, goal, heuristic cho người tổng hợp báo cáo.

Giao diện lấy số liệu sau khi generator kết thúc và đo thời gian bên ngoài solver, nên các giá trị này sẽ tự cập nhật theo thuật toán mới.
