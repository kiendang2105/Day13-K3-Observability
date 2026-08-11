# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

### Nguyên lý thiết kế Symptom-based Alerting:
1. **Phản ánh đúng tác động thực tế (User Impact)**: Tránh báo động giả (Alert Fatigue) khi lỗi nội bộ đã được hệ thống tự retry/fallback thành công mà người dùng không bị ảnh hưởng.
2. **Bao phủ lỗi chưa lường trước (Unknown Unknowns)**: Dù nguyên nhân kỹ thuật là gì, triệu chứng cuối cùng luôn biểu hiện qua Latency, Error rate hoặc Quality.
3. **Bền vững khi Refactor**: Không bị hỏng cảnh báo khi thay đổi cấu trúc code, đổi tên hàm hoặc tách service.
4. **Phân vai rõ ràng**: Alert (Symptom) trả lời *CÁI GÌ bị hỏng*; Traces/Logs (Cause) trả lời *TẠI SAO và Ở ĐÂU*.

## Alert 1

- Tên: `high_latency_p95`
- Severity: `warning`
- SLI/SLO liên quan: `latency_p95_ms` (Mục tiêu: P95 $\le$ 3000ms trên 99.5% requests trong 28 ngày)
- Điều kiện và thời gian duy trì: `latency_p95 > 3000ms` duy trì trong 5 phút liên tục
- Ảnh hưởng tới người dùng: Người dùng phải chờ lâu khi nhận phản hồi từ AI Chat / Summary, trải nghiệm bị gián đoạn hoặc gặp timeout trên giao diện.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra dashboard Latency & Traffic để xác định độ trễ tăng trên toàn hệ thống hay chỉ tập trung ở một endpoint/feature cụ thể (`qa` vs `summary`).
  2. Mở Langfuse / Traces, lọc các trace có duration > 3000ms để xác định span chậm nhất (ví dụ: span `llm_call`, `retrieval`, hay `preprocessing`).
  3. Kiểm tra log hệ thống qua `data/logs.jsonl` xem có thông báo lỗi timeout, rate limit từ LLM provider hoặc tài nguyên server (CPU/RAM/IO) bị nghẽn.
- Mitigation tạm thời: Chuyển hướng traffic sang model fallback có độ trễ thấp hơn, kích hoạt caching cho câu hỏi phổ biến, hoặc tạm thời giảm `max_tokens`.
- Owner: `on-call-engineer`

## Alert 2

- Tên: `elevated_error_rate`
- Severity: `critical`
- SLI/SLO liên quan: `error_rate_pct` (Mục tiêu: Tỉ lệ lỗi $\le$ 2% trên 99.0% requests trong 28 ngày)
- Điều kiện và thời gian duy trì: `error_rate_pct > 5%` duy trì trong 3 phút liên tục
- Ảnh hưởng tới người dùng: Nhiều người dùng nhận mã lỗi 5xx, không nhận được câu trả lời từ AI, luồng nghiệp vụ bị gián đoạn nghiêm trọng.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra endpoint `/metrics` và trường `error_breakdown` để xác định loại lỗi chính đang phát sinh (ví dụ: `LLMTimeout`, `RateLimitError`, `InternalServerError`).
  2. Dùng correlation ID từ log `data/logs.jsonl` (lọc theo `level: "error"` hoặc `event: "request_failed"`) để đọc traceback và nguyên nhân gốc rễ.
  3. Kiểm tra trạng thái dịch vụ bên ngoài (LLM Provider Status Page, Vector DB, API Key quota hoặc kết nối mạng).
- Mitigation tạm thời: Rollback prompt/model về phiên bản ổn định trước đó nếu lỗi do version mới; hoặc kích hoạt circuit breaker chuyển sang LLM provider dự phòng.
- Owner: `on-call-engineer`

## Alert 3

- Tên: `cost_budget_exceeded`
- Severity: `warning`
- SLI/SLO liên quan: `daily_cost_usd` (Mục tiêu: Chi phí tích lũy trong ngày $\le$ $2.50)
- Điều kiện và thời gian duy trì: `daily_cost_usd > $2.50` trong ngày hiện tại
- Ảnh hưởng tới người dùng: Không ảnh hưởng trực tiếp đến trải nghiệm tức thời, nhưng có nguy cơ cạn kiệt ngân sách dự án dẫn đến hệ thống bị dừng dịch vụ đột ngột do hết credit.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra dashboard Cost và Token usage để xác định feature (`qa`, `summary`,...) hoặc user/session nào đang tiêu thụ lượng token vượt mức bình thường.
  2. Mở trace trên Langfuse để xem prompt template hoặc context injection có đang truyền quá nhiều tài liệu / token đầu vào bất thường (prompt bloat) hay không.
  3. Đối chiếu traffic count xem chi phí tăng do số lượng request tăng thật hay do một vài request cá biệt tiêu hao lượng token khổng lồ.
- Mitigation tạm thời: Siết chặt rate limit theo IP / session_id / user_id, cắt giảm số lượng context documents retrieved trong RAG pipeline, hoặc chuyển tạm sang model chi phí thấp hơn.
- Owner: `team-lead`
