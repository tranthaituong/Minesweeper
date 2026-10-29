# Giao diện và kiểm thử Minesweeper

## Mục tiêu

Giao diện giúp người dùng quan sát các hành động của DFS và Hill Climbing trên cùng một bài toán Minesweeper. Người dùng có thể chọn thuật toán, xem từng bước, tạm dừng, khôi phục dữ kiện ban đầu và chạy bộ thực nghiệm.

## Thiết kế giao diện

Chương trình sử dụng Python 3 và Pygame. Bàn chơi đặt bên trái; điều khiển AI và lịch sử thao tác đặt bên phải. Phía trên hiển thị tổng mìn, số cờ, số ô an toàn đã mở và thời gian thao tác. Thời gian giải thuật được hiển thị riêng trong khung AI.

Các ô ẩn có nền xanh đậm; ô đã mở hiển thị số mìn lân cận bằng màu khác nhau. Ô vừa được xử lý có viền nhấn. Giao diện phân biệt ba hành động: suy luận mở ô an toàn, xác định mìn để cắm cờ và đề xuất ô đoán theo heuristic. Khi ván kết thúc, chương trình thông báo thắng hoặc trúng mìn.

| Chức năng | Hoạt động |
|---|---|
| Step | Thực hiện một hành động trong kế hoạch; luật mở lan vẫn áp dụng khi mở ô số 0 |
| Play/Pause | Chạy liên tiếp hoặc dừng vòng suy luận đang xem |
| Reset input | Khôi phục đúng các ô mở, cờ và vị trí mìn ban đầu |
| Chuyển input | Chọn một trong chín bàn cố định |
| Benchmark | Chạy hai thuật toán trên cùng các input, xuất bảng và báo cáo |

Chữ và hình được vẽ ở độ phân giải điểm ảnh thực của cửa sổ, hỗ trợ màn hình Retina. Khi thay đổi kích thước cửa sổ, bàn và các nút vẫn giữ đúng tọa độ tương tác.

Lần kiểm tra trực tiếp trên Mac ghi nhận cửa sổ 1160 × 763 có vùng vẽ 2320 × 1526, đúng tỉ lệ Retina 2×. Thao tác Step với Hill Climbing đã hiển thị một hành động và giữ trạng thái tạm dừng.

## Kết nối với thuật toán

Luồng xử lý gồm: **input → dữ kiện đang hiện → solver → hành động có nhãn → giao diện**. Chỉ các số của ô đã mở, cờ và tổng số mìn được truyền sang đối tượng quan sát của solver. Vị trí mìn được bộ máy trò chơi dùng để kiểm tra thao tác và được bộ thực nghiệm dùng để đối chiếu kết quả.

Giao diện tách lượt tính thuật toán sang tiến trình riêng để vẫn phản hồi khi chờ kết quả. Thay đổi input, Reset hoặc sửa cờ sẽ hủy kế hoạch cũ. Một lượt suy luận trên giao diện có giới hạn chờ 10 giây để người dùng có thể tiếp tục thao tác khi gặp trường hợp xử lý lâu.

## Kiểm thử và thực nghiệm

Bộ kiểm tra tích hợp gồm 15 ca, bao phủ các thao tác giao diện, việc khôi phục input, phân biệt ô đoán, thống kê sau khi giải xong và ranh giới dữ liệu truyền cho solver. Cả 15 ca đã chạy đạt trên môi trường ghi trong kết quả thực nghiệm.

Thực nghiệm dùng chín input cố định, ba lần lặp cho mỗi thuật toán. Phương pháp đo, bảng thời gian–bộ nhớ và phân tích từng input nằm trong `benchmark_results/BAO_CAO_THUC_NGHIEM.md`. Dữ liệu từng lượt được lưu riêng để nhóm có thể tính lại và đưa vào báo cáo tổng hợp.
