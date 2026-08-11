# Yêu cầu dashboard

Contract có thể kiểm tra bằng máy nằm tại `config/dashboard.yaml`. Hướng dẫn dựng và kiểm tra runtime nằm tại [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).

Dashboard chính cần đủ 6 nhóm thông tin:

1. Latency P50/P95/P99.
2. Traffic: request count hoặc QPS.
3. Error rate và breakdown theo loại lỗi.
4. Cost theo thời gian.
5. Tổng token input/output.
6. Quality proxy.

Tiêu chuẩn trình bày:

- Khoảng thời gian mặc định: 1 giờ.
- Tự refresh mỗi 30 giây.
- Có threshold hoặc SLO line.
- Ghi rõ đơn vị.
- Giữ đúng 6 panel quan trọng ở lớp chính.
- Screenshot hoặc evidence phải nhìn được tên panel, khoảng thời gian, đơn vị và threshold.

## Công cụ sử dụng

- Công cụ: `scripts/build_dashboard.py` — sinh một file HTML tự chứa, không cần cài thêm dependency và không gọi CDN.
- Nguồn dữ liệu: `data/logs.jsonl`. Đây là nguồn chuẩn theo `README.md`; endpoint `/metrics` **không** dùng cho dashboard vì nó chỉ là bộ đếm cộng dồn trong RAM, không có trục thời gian nên không hỗ trợ cửa sổ 60 phút, `rate_per_minute` hay `sum_by_minute`, và về 0 mỗi lần restart.
- Contract chấm điểm: `config/dashboard.yaml`. Tên panel, đơn vị và threshold trong HTML đọc thẳng từ file này, không hard-code.
- Time range mặc định: 60 phút gần nhất.
- Refresh mặc định: 30 giây.

## Cách chạy

```bash
uvicorn app.main:app --reload --env-file .env   # terminal 1
python scripts/load_test.py                     # terminal 2, tạo dữ liệu
python scripts/build_dashboard.py               # dựng dashboard
python scripts/build_dashboard.py --watch       # chế độ live, dựng lại mỗi 30 giây
```

Mở `data/dashboard.html` bằng browser. Ở chế độ `--watch`, thẻ meta refresh trong trang tự tải lại đúng nhịp `refresh_seconds` của contract.

Nếu 60 phút gần đây không có log nào, script neo cửa sổ vào bản ghi mới nhất và hiện một dòng cảnh báo ngay trên trang — thà nói rõ là đang xem dữ liệu cũ còn hơn vẽ một dashboard trống khiến người đọc tưởng hệ thống không có traffic.

Ví dụ output một lần chạy:

```text
Da dung D:\Day13-K3-Observability\data\dashboard.html
  [DAT] latency  P95 1 047 ms
  [DAT] traffic  12.5 req/phút
  [DAT] errors   0.0%
  [DAT] cost     0.0995 USD
  [DAT] tokens   in 1 881 / out 6 259
  [DAT] quality  0.88
```

## Panel Design

| # | Panel | Event và field trong `data/logs.jsonl` | Đơn vị | Hiển thị | Threshold |
|---|---|---|---|---|---|
| 1 | Latency percentiles | `response_sent.latency_ms` | ms | 3 KPI P50/P95/P99 + line chart theo phút | P95 ≤ 3000 ms |
| 2 | Request traffic | `request_received` | requests, req/phút | Column chart theo phút | ≥ 1 req/phút |
| 3 | Error rate and breakdown | `request_received`, `request_failed.error_type` | percent, count | KPI error rate + bảng breakdown | ≤ 2% |
| 4 | Cost over time | `response_sent.cost_usd` | USD | Column chart theo phút + tổng | Tổng ≤ 2.5 USD |
| 5 | Input and output tokens | `response_sent.tokens_in`, `tokens_out` | tokens | Grouped column 2 series | Mỗi chiều ≤ 50000 |
| 6 | Quality proxy | `response_sent.quality_score` | score 0–1 | Line chart theo phút | Trung bình ≥ 0.75 |

## Quy ước trình bày

- Threshold vẽ bằng đường **đứt nét đỏ có nhãn**; lưới và trục là hairline liền nét. Đứt nét chỉ dành riêng cho ngưỡng, không dùng cho lưới — nếu lưới cũng đứt nét thì người đọc không phân biệt được đâu là ngưỡng.
- Panel một series dùng một màu duy nhất, không tô đậm nhạt theo độ lớn. Panel nhiều series dùng bảng màu categorical cố định thứ tự (blue → orange → aqua) và **luôn có legend**.
- Mỗi biểu đồ có một bảng dữ liệu đi kèm ở phần `Dạng bảng`, để giá trị không bao giờ chỉ đọc được bằng màu.
- Trạng thái đạt/vượt ngưỡng hiển thị bằng icon kèm chữ, không dùng màu đơn độc.
- Phút không có dữ liệu bị ngắt đoạn trên line chart thay vì nối thẳng qua — nối qua khoảng trống là bịa ra dữ liệu không tồn tại.
- Mọi panel dùng chung một trục thời gian và một cửa sổ; không có panel nào có bộ lọc riêng.

## Evidence

- `submission/evidence/cp2_dashboard.png` — ảnh chụp dashboard đủ 6 panel, thấy rõ time range, đơn vị và đường threshold.
- `submission/evidence/cp2_validate_dashboard.txt` — kết quả `python scripts/validate_dashboard.py`.

Validator chỉ kiểm tra cấu trúc của `config/dashboard.yaml`; nó không chứng minh được biểu đồ dùng đúng dữ liệu. Vì vậy ảnh chụp dashboard runtime là bắt buộc, không thay thế bằng tài liệu spec được.

```bash
python scripts/validate_dashboard.py
```
