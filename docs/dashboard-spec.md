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

- Công cụ: spec-based dashboard, dùng dữ liệu runtime từ endpoint `/metrics`.
- Nguồn chuẩn của contract: `config/dashboard.yaml`.
- Nguồn log gốc: `data/logs.jsonl`.
- Time range mặc định: 60 phút gần nhất.
- Refresh mặc định: 30 giây.

Lệnh xem dữ liệu hiện tại:

```bash
curl http://localhost:8000/metrics | python -m json.tool
```

Snapshot hiện tại sau baseline:

```json
{
  "traffic": 10,
  "latency_p50": 1170.0,
  "latency_p95": 1668.0,
  "latency_p99": 1668.0,
  "avg_cost_usd": 0.0021,
  "total_cost_usd": 0.0205,
  "tokens_in_total": 330,
  "tokens_out_total": 1303,
  "error_rate_pct": 0.0,
  "error_breakdown": {},
  "quality_avg": 0.88
}
```

## Panel Design

| # | Nhóm | Tên panel | Nguồn dữ liệu | Đơn vị | Hiển thị | Threshold hoặc SLO line |
|---|---|---|---|---|---|---|
| 1 | Latency | Latency Percentiles | `/metrics`: `latency_p50`, `latency_p95`, `latency_p99` | milliseconds (ms) | Single Value hoặc line chart gồm P50/P95/P99 | P95 <= 3000 ms |
| 2 | Traffic | Request Traffic | `/metrics`: `traffic` | requests, requests/min | Counter tổng request và gauge RPM/QPS | RPM >= 1 trong lúc load test |
| 3 | Error | Error Rate and Breakdown | `/metrics`: `error_rate_pct`, `error_breakdown` | percent (%), count | Single Value error rate và table breakdown theo `error_type` | Error rate <= 2% |
| 4 | Cost | Cost Over Time | `/metrics`: `total_cost_usd`, `avg_cost_usd` | USD | Single Value total cost, line hoặc gauge so với budget | Total cost <= 2.5 USD trong cửa sổ 60 phút |
| 5 | Tokens | Input and Output Tokens | `/metrics`: `tokens_in_total`, `tokens_out_total` | tokens | Bar hoặc stacked value cho input/output tokens | Total tokens <= 50000 |
| 6 | Quality | Quality Proxy | `/metrics`: `quality_avg` | score 0..1 | Single Value hoặc line chart quality trung bình | Quality average >= 0.75 |

## Chi tiết từng panel

### 1. Latency Percentiles

- Mục tiêu: theo dõi tốc độ phản hồi của API AI.
- Fields: `latency_p50`, `latency_p95`, `latency_p99`.
- Đơn vị: ms.
- Time range mặc định: 60 phút.
- Threshold/SLO: vẽ SLO line tại `p95 = 3000 ms`.
- Cảnh báo khi: `latency_p95 > 3000`.
- Giá trị baseline hiện tại: P50 `1170.0 ms`, P95 `1668.0 ms`, P99 `1668.0 ms`.

### 2. Request Traffic

- Mục tiêu: biết hệ thống đang nhận bao nhiêu request.
- Field: `traffic`.
- Đơn vị: request hoặc request/phút.
- Time range mặc định: 60 phút.
- Threshold/SLO: trong lúc load test, RPM nên `>= 1`.
- Cảnh báo khi: traffic bằng 0 trong giai đoạn cần có tải kiểm thử.
- Giá trị baseline hiện tại: `10` requests.

### 3. Error Rate and Breakdown

- Mục tiêu: phát hiện lỗi runtime và phân loại nguyên nhân.
- Fields: `error_rate_pct`, `error_breakdown`.
- Đơn vị: `%` cho error rate, `count` cho breakdown.
- Time range mặc định: 60 phút.
- Threshold/SLO: error rate `<= 2%`.
- Cảnh báo khi: `error_rate_pct > 2` hoặc một `error_type` tăng bất thường.
- Giá trị baseline hiện tại: `error_rate_pct = 0.0`, `error_breakdown = {}`.

### 4. Cost Over Time

- Mục tiêu: theo dõi chi phí hiện tại so với ngân sách.
- Fields: `total_cost_usd`, `avg_cost_usd`.
- Đơn vị: USD.
- Time range mặc định: 60 phút.
- Threshold/SLO: tổng chi phí `<= 2.5 USD`.
- Cảnh báo khi: `total_cost_usd > 2.5` hoặc `avg_cost_usd` tăng đột biến.
- Giá trị baseline hiện tại: total `0.0205 USD`, average `0.0021 USD`.

### 5. Input and Output Tokens

- Mục tiêu: theo dõi lượng token tiêu thụ, tách input và output.
- Fields: `tokens_in_total`, `tokens_out_total`.
- Đơn vị: tokens.
- Time range mặc định: 60 phút.
- Threshold/SLO: tổng input + output tokens `<= 50000`.
- Cảnh báo khi: token output tăng bất thường, vì thường kéo theo latency và cost tăng.
- Giá trị baseline hiện tại: input `330`, output `1303`, total `1633`.

### 6. Quality Proxy

- Mục tiêu: theo dõi chất lượng trung bình của phản hồi.
- Field: `quality_avg`.
- Đơn vị: score từ `0` đến `1`.
- Time range mặc định: 60 phút.
- Threshold/SLO: quality average `>= 0.75`.
- Cảnh báo khi: `quality_avg < 0.75`.
- Giá trị baseline hiện tại: `0.88`.

## Evidence

Do chưa dựng dashboard bằng Langfuse hoặc Grafana trong bước này, evidence được nộp ở dạng spec đầy đủ trong file này. Spec đã ghi rõ:

- Tên panel.
- Đơn vị.
- Khoảng thời gian mặc định.
- Threshold hoặc SLO line.
- Công cụ sử dụng.
- Mapping dữ liệu từ `/metrics`.

Kiểm tra contract trước khi chụp evidence hoặc nộp báo cáo:

```bash
python scripts/validate_dashboard.py
```
