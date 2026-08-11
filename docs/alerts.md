# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Dashboard mặc định dùng time range 60 phút và refresh 30 giây.

## Alert 1

- Tên: `high_latency_p95`
- Severity: `warning`
- SLI/SLO liên quan: `latency_p95_ms`, objective `P95 <= 3000 ms`, target `99.5%` request trong cửa sổ 28 ngày.
- Điều kiện kích hoạt: `latency_p95 > 3000ms for 5 minutes`.
- Ảnh hưởng tới người dùng: Người dùng nhận phản hồi chậm, chat có thể cảm giác bị treo hoặc timeout ở client nếu latency tiếp tục tăng.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Latency Percentiles`, xác nhận P95/P99 vượt ngưỡng 3000 ms và so sánh với traffic cùng thời điểm để biết có phải do spike tải không.
  2. Mở các log `response_sent` trong `data/logs.jsonl` ở khoảng thời gian alert, lọc request có `latency_ms` cao nhất và ghi lại `correlation_id`, `feature`, `model`, `tokens_in`, `tokens_out`.
  3. Với các `correlation_id` chậm, kiểm tra trace tương ứng trong Langfuse nếu có; so sánh thời gian retrieval, prompt/model generation và token output để xác định đoạn nào làm request chậm.
- Mitigation tạm thời: Giảm concurrency hoặc rate limit traffic mới, tắt incident/thao tác gây chậm nếu đang bật, chuyển sang prompt ngắn hơn hoặc giới hạn `tokens_out` cho tới khi P95 xuống dưới SLO.
- Owner: `on-call-engineer`

## Alert 2

- Tên: `elevated_error_rate`
- Severity: `critical`
- SLI/SLO liên quan: `error_rate_pct`, objective `error_rate_pct <= 2`, target `99.0%` trong cửa sổ 28 ngày.
- Điều kiện kích hoạt: `error_rate_pct > 2 for 3 minutes` — bằng đúng objective của SLO, không nới lỏng. Thêm `for 3 minutes` để một spike lẻ không tạo cảnh báo giả.
- Ảnh hưởng tới người dùng: Một phần đáng kể request chat thất bại, người dùng không nhận được câu trả lời hoặc nhận lỗi 5xx.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Error Rate and Breakdown`, xác nhận error rate vượt 2% và xem breakdown theo `error_type` để biết loại lỗi nào đang chiếm nhiều nhất.
  2. Mở log `request_failed` trong `data/logs.jsonl`, nhóm theo `error_type`, lấy vài `correlation_id` đại diện và kiểm tra payload/detail đã được che PII chưa.
  3. Kiểm tra `/health` và các dependency liên quan tới request path như prompt fetch, tracing export, retrieval hoặc mock LLM; đối chiếu thời điểm lỗi với thay đổi config/deploy/load test gần nhất.
- Mitigation tạm thời: Rollback thay đổi gần nhất nếu lỗi bắt đầu sau deploy/config change, tắt incident đang bật, chuyển sang fallback prompt/local mode nếu lỗi đến từ prompt service, hoặc tạm disable feature gây lỗi nhiều nhất.
- Owner: `on-call-engineer`

## Alert 3

- Tên: `cost_budget_exceeded`
- Severity: `warning`
- SLI/SLO liên quan: `daily_cost_usd`, objective `daily_cost_usd <= 2.5`, target `100.0%` ngày trong cửa sổ 28 ngày.
- Điều kiện kích hoạt: `daily_cost_usd > 2.5`.
- Ảnh hưởng tới người dùng: Hệ thống có nguy cơ vượt ngân sách; nếu không xử lý có thể phải giới hạn request, giảm chất lượng câu trả lời hoặc dừng một số workflow tốn chi phí.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Cost Over Time`, xác nhận `total_cost_usd` hoặc daily rollup vượt 2.5 USD và xem xu hướng tăng theo phút/giờ.
  2. So sánh panel `Tokens` và `Traffic` cùng khoảng thời gian để xác định chi phí tăng do nhiều request, output quá dài, hay cả hai.
  3. Lọc log `response_sent` có `cost_usd` cao nhất, ghi lại `correlation_id`, `feature`, `tokens_in`, `tokens_out`, `quality_score` để tìm nhóm request tiêu thụ nhiều nhất.
- Mitigation tạm thời: Giảm `max_tokens`/độ dài câu trả lời, rate limit người dùng hoặc feature tốn chi phí, chuyển sang prompt ngắn hơn, và tạm dừng batch/load test không cần thiết.
- Owner: `team-lead`
