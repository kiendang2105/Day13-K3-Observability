# Yêu cầu dashboard

Contract có thể kiểm tra bằng máy nằm tại `config/dashboard.yaml`. Hướng dẫn dựng và kiểm tra runtime nằm tại [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).

## 1. Thông tin chung & Công cụ sử dụng

- **Công cụ sử dụng**: Langfuse kết hợp FastAPI Metrics endpoint (`/metrics`) theo spec `config/dashboard.yaml`.
- **Khoảng thời gian mặc định**: 60 phút (1 giờ).
- **Tần suất làm mới (Refresh rate)**: 30 giây.
- **Evidence ảnh dashboard**: [submission/evidence/dasboard_langfuse.png](../submission/evidence/dasboard_langfuse.png)

## 2. Chi tiết 6 Panel chính, Đơn vị & Threshold / SLO

| # | Tên Panel (ID) | Đơn vị | Threshold / SLO Line | Giá trị ghi nhận thực tế (`/metrics`) |
|---|---|---|---|---|
| 1 | **Latency percentiles** (`latency`) | `ms` | P95 $\le$ 3000 ms | P50: 1422.0 ms, P95: 5380.0 ms, P99: 5380.0 ms |
| 2 | **Request traffic** (`traffic`) | `requests_per_minute` / `count` | Rate $\ge$ 1 req/min | 20 requests |
| 3 | **Error rate and breakdown** (`errors`) | `%` (percent) | Error rate $\le$ 2% | `error_rate_pct`: 0.0%, `error_breakdown`: `{}` |
| 4 | **Cost over time** (`cost`) | `USD ($)` | Tổng chi phí $\le$ $2.50 | `avg_cost_usd`: $0.0022, `total_cost_usd`: $0.0432 |
| 5 | **Input and output tokens** (`tokens`) | `tokens` | Tổng tokens $\le$ 50,000 | `tokens_in_total`: 660, `tokens_out_total`: 2746 |
| 6 | **Quality proxy** (`quality`) | `score (0.0 - 1.0)` | Mean quality $\ge$ 0.75 | `quality_avg`: 0.88 |

## 3. Tiêu chuẩn trình bày

- Khoảng thời gian mặc định: 1 giờ.
- Tự refresh mỗi 15–30 giây nếu công cụ hỗ trợ.
- Có threshold hoặc SLO line.
- Ghi rõ đơn vị.
- Chỉ giữ 6–8 panel quan trọng ở lớp chính.
- Screenshot phải nhìn được tên panel và khoảng thời gian.

Kiểm tra contract trước khi chụp evidence:

```bash
python scripts/validate_dashboard.py
```
