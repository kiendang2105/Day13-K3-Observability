# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL: https://github.com/kiendang2105/Day13-K3-Observability (nhánh `leduc`)
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: **100/100** (310 record, 142 correlation ID, 0 PII leak) — `evidence/checkpoint1_validate_logs.txt`
- Tổng số traces: **194** trên project Langfuse `cmso1m9n203ilad0j7fmjzvw7`
- Số PII leak còn lại: **0**
- Link/đường dẫn dashboard: `data/dashboard.html`, dựng bằng `python scripts/build_dashboard.py` từ `data/logs.jsonl`

## 3. Logging và tracing

- Evidence correlation ID: `evidence/checkpoint1_correlation_id.png` — cùng một ID xuất hiện ở response header `x-request-id`, trong body và trong toàn bộ log line của request.
- Evidence PII redaction: `evidence/checkpoint1_pii_redacted.png` — email, số điện thoại, thẻ, hộ chiếu và địa chỉ bị thay bằng `[REDACTED_*]` **trước khi** `JsonlFileProcessor` ghi xuống đĩa.
- Evidence trace waterfall: `evidence/cp2_trace_waterfall.png` — trace `8ba5b58f5e3d19a673832fbffb18d56d`.
- Giải thích một span đáng chú ý: span `run` là toàn bộ vòng đời một lượt hỏi đáp (retrieval → resolve prompt → LLM → tính quality/cost). Ở trạng thái bình thường span này khoảng 0.15–1.1 giây; dưới sự cố `rag_slow` nó lên 2.65 giây. Vì retrieval **không** được tách thành span con nên waterfall chỉ cho biết tổng thời gian tăng, không tự chỉ ra đoạn nào chậm — xem mục 6 để biết cách khoanh vùng bằng bằng chứng khác, và mục biện pháp phòng ngừa để biết cách vá lỗ hổng này.

## 4. Prompt versioning

- Prompt name: `day13-chat` (type `text`, 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`)
- Version/label baseline: **v1** — label `baseline` + `production`, commit message `v1 baseline`
- Version/label candidate: **v2** — label `candidate`, thêm dòng `Answer in at most 3 sentences.`
- Trace ID của mỗi version:
  - v1 / `baseline`: `1b3b13e18c006e97dbf458a1024b3a82`
  - v2 / `candidate`: `8ba5b58f5e3d19a673832fbffb18d56d`
  - v2 / `production` (sau khi promote): `8b3c1ef658b831f87229cf33e3e4d9a1`
- Bằng chứng đổi label hoặc rollback: `evidence/cp2_label_before.png` → `evidence/cp2_label_after_promote.png` → `evidence/cp2_rollback_to_v1.png`.

  Giữa ba mốc đó `.env` không đổi một ký tự nào (`LANGFUSE_PROMPT_LABEL=production`) và không deploy lại code. Prompt đang chạy production chuyển từ v1 sang v2 rồi quay về v1 hoàn toàn bằng thao tác label trên Langfuse. Label `baseline` nằm yên ở v1 suốt quá trình, làm mốc neo chứng minh đã quay về đúng bản gốc.

  Xác minh bằng `python scripts/check_prompt_trace.py` — script này bắt được trường hợp app im lặng fallback về template local: khi đó trace vẫn trả về 200, chỉ có metadata ghi `prompt_source=local-fallback` là sai.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel` — `evidence/cp2_validate_dashboard.txt`
- Evidence dashboard: `evidence/cp2_dashboard.png`
- SLO đã chọn và lý do: `config/slo.yaml` — P95 latency ≤ 3000 ms, error rate ≤ 2%, chi phí ≤ 2.5 USD/ngày, quality trung bình ≥ 0.75. Các ngưỡng này khớp đúng với `threshold` của từng panel trong `config/dashboard.yaml`, để dashboard và SLO không nói hai con số khác nhau.
- Alert rules và runbook: `config/alert_rules.yaml` + `docs/alerts.md`. Cả ba alert đều dựa trên triệu chứng người dùng cảm nhận được, không dựa vào tên component nội bộ. `elevated_error_rate` được chỉnh về đúng ngưỡng SLO 2% (trước đó đặt 5%, tức là có một vùng mù từ 2% đến 5% mà không ai được báo).

---

## 6. Điều tra challenge

### Thông tin

- Challenge ID: `day13-k3-observability-v1` (cohort K3)
- Incident được release: `rag_slow`, feature bị ảnh hưởng `refund`, ngưỡng `latency_threshold_ms = 2000`
- Lệnh đã chạy:

  ```bash
  python scripts/inject_incident.py
  python scripts/load_test.py --challenge --concurrency 5
  ```

### Bước 1 — Triệu chứng từ metrics

| Chỉ số | Trước sự cố | Trong sự cố |
|---|---|---|
| P95 latency (dashboard, từ `response_sent.latency_ms`) | 1 062 ms | **2 651 ms** |
| Latency client thực sự chịu | ~1 100 ms | **13 383 ms** |
| Error rate | 0% | **0%** |
| Quality trung bình | 0.88 | **0.8785** |
| Tokens out / request | ~133 | ~144 |

Ba điều rút ra ngay từ bảng này:

1. **Đây là sự cố thuần về latency.** Error rate vẫn 0%, quality không đổi, token không đổi. Panel Errors và Quality hoàn toàn im lặng — nếu chỉ nhìn hai panel đó thì kết luận "hệ thống khỏe".
2. **Dashboard báo ĐẠT trong khi sự cố đang diễn ra.** P95 = 2 651 ms vẫn nằm dưới SLO line 3 000 ms, nên panel Latency hiện dấu tích xanh. Nhưng ngưỡng chính thức của challenge là 2 000 ms — đã bị vượt. SLO của nhóm quá lỏng so với yêu cầu bài toán.
3. **Con số server ghi nhận lệch xa con số người dùng chịu.** Log ghi 2 651 ms, client đo 13 383 ms — chênh **5 lần**. Đây là manh mối quan trọng nhất, và nó dẫn tới root cause thứ hai.

### Bước 2 — Khoanh vùng bằng trace

Trace của 5 request chính thức (tra theo `session_id` `k3-challenge-s01`…`s05`):

| Session | Trace ID | Latency |
|---|---|---|
| k3-challenge-s01 | `5bff4847530ad49e318c91c8f1ccb9af` | 2.653 s |
| k3-challenge-s02 | `05295c78907a8a32dc2ff893d1dcac66` | 2.653 s |
| k3-challenge-s03 | `2e053f9a7eecb831b7f8ffe1161b1446` | 2.655 s |
| k3-challenge-s04 | `6bbce998051311a16ecc12e79dab2f8d` | 2.656 s |
| k3-challenge-s05 | `c8fedf7e2ef71129c4a744288e9062ea` | 2.652 s |

Trace chậm nhất: `9a8dbc46b676905c2a642deaff74e60b` (2.660 s), metadata `prompt_source=langfuse`, `prompt_version=1`, `prompt_label=production` — tức là prompt đúng, không phải sự cố do prompt.

Điểm đáng chú ý: **cả 5 trace đều gần như đúng 2.65 giây, sai lệch dưới 5 ms.** Một hệ thống chậm do tải sẽ có độ phân tán lớn; độ chụm cao thế này là dấu hiệu của một khoảng chờ cố định, không phụ thuộc nội dung câu hỏi.

Hạn chế gặp phải: `LabAgent.run` chỉ được bọc bằng **một** observation duy nhất, retrieval không có span riêng. Nên waterfall cho biết "toàn bộ lượt xử lý mất 2.65s" nhưng không tự chỉ ra 2.5 giây đó nằm ở đâu. Phải dùng log để thu hẹp tiếp.

### Bước 3 — Chứng minh root cause bằng log

Năm request chính thức trong `data/logs.jsonl`:

| correlation_id | latency_ms | tokens_in | tokens_out | quality |
|---|---|---|---|---|
| `req-f3649604` | 2658 | 31 | 155 | 0.9 |
| `req-16d827a2` | 2651 | 34 | 161 | 0.8 |
| `req-c284ff56` | 2651 | 29 | 106 | 0.9 |
| `req-0ad72b98` | 2651 | 34 | 166 | 0.8 |
| `req-75ebf78a` | 2651 | 34 | 132 | 0.9 |

So với baseline 10 request ngay trước đó: `latency_ms` trung bình **266 → 2 652 ms** (+2 386 ms), trong khi `tokens_in` **33 → 32** và `tokens_out` **133 → 144**.

**Suy luận khoá chặt root cause thứ nhất:** lượng token không đổi thì khối lượng sinh chữ của LLM không đổi, nên phần tăng thêm không nằm ở generation. Trong `LabAgent.run` chỉ còn retrieval nằm ngoài generation. Cộng với `/health` trả `"rag_slow": true`, kết luận là retrieval bị chèn một khoảng chờ cố định khoảng 2.4 giây. Con số +2 386 ms khớp với độ chụm 5 ms đã thấy ở trace.

**Root cause thứ hai — thứ khuếch đại 2.4 giây thành 13 giây.** Timestamp của 5 log `response_sent`:

```
05:03:49.184  05:03:51.851  05:03:54.511  05:03:57.170  05:03:59.831
```

Cách nhau đều đặn ~2.66 giây, đúng bằng thời gian xử lý một request. Dù load test gửi với `--concurrency 5`, **các request được xử lý nối đuôi nhau chứ không song song**.

Đo trực tiếp bằng `python scripts/probe_concurrency.py` — gửi 5 request đồng thời và đọc cả ba mốc thời gian của cùng một request (`evidence/cp3_probe_before_fix.txt`):

| correlation_id | client đo | header `x-response-time-ms` | log `latency_ms` | phần nằm chờ |
|---|---|---|---|---|
| `req-1be96915` | 4 667 ms | 4 204 ms | 3 723 ms | 463 ms |
| `req-718f8410` | 9 981 ms | 2 666 ms | 2 651 ms | 7 316 ms |
| `req-b1595f93` | 9 986 ms | 5 317 ms | 2 651 ms | 4 669 ms |
| `req-4a49cc5b` | 15 299 ms | 7 973 ms | 2 651 ms | 7 326 ms |
| `req-e6fc441f` | 15 300 ms | 7 972 ms | 2 651 ms | 7 328 ms |

Wall-clock cho cả 5 request: **15 307 ms**. Log ghi tối đa 3 723 ms, người dùng chờ tối đa 15 300 ms — chênh **11 577 ms** hoàn toàn không xuất hiện ở bất kỳ chỉ số nào của server.

Client time xếp thành từng bậc 4.7s → 10s → 15.3s thay vì tất cả cùng về một lúc. Đó là dấu vân tay của hàng đợi: request tới sau phải đợi request trước xử lý xong. Lần chạy load test chính thức cũng cho cùng hiện tượng ở mức 13 383 ms.

Nguyên nhân: `/chat` khai báo `async def`, nhưng bên trong gọi thẳng `agent.run()` là code đồng bộ. Khoảng `time.sleep` mà `rag_slow` chèn vào retrieval **giữ luôn event loop** (vòng lặp sự kiện — thứ điều phối mọi request đồng thời của server), nên trong suốt 2.5 giây đó server không nhận xử lý được request nào khác.

### Root cause

**Nguyên nhân trực tiếp:** incident `rag_slow` chèn một khoảng chờ cố định ~2.4 giây vào bước retrieval, làm thời gian xử lý một request tăng từ 266 ms lên 2 652 ms.

**Nguyên nhân khuếch đại:** handler `/chat` là `async` nhưng gọi code đồng bộ có thể chặn. Một chậm 2.4 giây bị nhân lên thành 14 giây ở phía người dùng khi có 5 request đồng thời.

**Lỗ hổng quan sát khiến sự cố suýt bị bỏ lọt:** `response_sent.latency_ms` chỉ đếm từ lúc `LabAgent.run` bắt đầu chạy ([agent.py:31](../app/agent.py#L31)), tức là **sau** khi request đã nằm chờ xong. Toàn bộ hệ thống đo lường — log, trace Langfuse, dashboard — đều báo 2.65 giây, còn người dùng chờ 14 giây. Không có chỉ số nào trên dashboard phản ánh trải nghiệm thật.

### Fix action

1. **Xử lý ngay:** `python scripts/inject_incident.py --disable` để gỡ khoảng chờ nhân tạo. Trong hệ thống thật, tương đương với rollback thay đổi gần nhất của tầng retrieval hoặc đặt timeout cho vector store — chính là bước "Mitigation tạm thời" trong [runbook Alert 1](../docs/alerts.md).

2. **Sửa phần khuếch đại:** đẩy `agent.run` sang worker thread thay vì gọi thẳng trong handler async ([main.py](../app/main.py)):

   ```python
   result = await run_in_threadpool(agent.run, ...)
   ```

   Đo lại bằng cùng một script, incident **vẫn bật**, cùng 5 request đồng thời (`evidence/cp3_probe_before_fix.txt` và `evidence/cp3_probe_after_fix.txt`):

   | | Trước fix | Sau fix |
   |---|---|---|
   | Client đo (max) | 15 300 ms | **4 668 ms** |
   | Header `x-response-time-ms` (max) | 7 973 ms | **4 143 ms** |
   | Log `latency_ms` (max) | 3 723 ms | 3 635 ms |
   | Wall-clock 5 request | 15 307 ms | **4 677 ms** |
   | Phần nằm chờ không được ghi nhận | 11 577 ms | **1 033 ms** |

   Thời gian người dùng chịu giảm **69%**. Sự cố gốc vẫn còn nguyên nên `latency_ms` không giảm — đúng như mong đợi, fix này chỉ gỡ phần khuếch đại chứ không chữa retrieval chậm.

   Một quan sát đáng chú ý: sau fix, 5 request chạy song song thật nên chúng cạnh tranh tài nguyên với nhau, khiến `latency_ms` của từng request **nhích lên** so với khi chạy nối đuôi (ở đó mỗi request được độc chiếm máy). Nhìn từng request thì tưởng xấu đi, nhưng thông lượng cả lô tốt hơn 3 lần. Đây đúng là kiểu đánh đổi mà chỉ nhìn một chỉ số đơn lẻ sẽ kết luận sai.

   Starlette copy contextvars sang worker thread nên correlation ID, log enrichment và trace context vẫn đi theo nguyên vẹn — đã có test khoá lại điều này.

### Preventive measure

1. **Đo đúng cái người dùng chịu.** Thêm access log `request_completed` ở tầng middleware ([middleware.py](../app/middleware.py)), ghi `latency_ms` tính từ lúc request vào tới lúc response ra. Trong sự cố này con số đó là 10 661 ms trong khi `response_sent.latency_ms` chỉ 2 651 ms. Một chỉ số chỉ đo phần xử lý sẽ luôn đẹp hơn thực tế đúng bằng thời gian nằm chờ.

2. **Test chống hồi quy.** `tests/test_request_latency_observability.py` gửi 3 request đồng thời với retrieval chậm giả lập và bắt buộc tổng thời gian phải nhỏ hơn mức xếp hàng. Đã kiểm chứng: gỡ `run_in_threadpool` ra thì test đỏ ngay.

3. **Siết ngưỡng cảnh báo.** Sự cố này đẩy P95 lên 2 651 ms — vượt ngưỡng 2 000 ms của challenge nhưng vẫn dưới SLO 3 000 ms của nhóm, nên dashboard vẫn hiện ĐẠT. Cần hoặc hạ SLO xuống sát mức chấp nhận được thật, hoặc thêm một alert theo tốc độ tăng tương đối (P95 tăng gấp đôi so với baseline 1 giờ trước) để bắt được dạng sự cố nằm dưới ngưỡng tuyệt đối.

4. **Tách span cho retrieval.** Bọc bước retrieval bằng một observation riêng để waterfall tự chỉ ra đoạn chậm, thay vì phải suy luận gián tiếp qua việc token không đổi. Đây là điểm yếu đã gặp ở Bước 2.

5. **Incident state đang nằm trong RAM.** `app/incidents.py` giữ trạng thái bằng biến module, nên mỗi lần server reload là mọi cờ tự tắt. Trong lúc điều tra, một lần `--reload` đã âm thầm tắt `rag_slow` và suýt cho ra kết quả đo sai. Trạng thái ảnh hưởng tới hành vi hệ thống cần được ghi ra ngoài hoặc ít nhất log lại mỗi lần khởi động.

---

## 7. Đóng góp cá nhân

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| **Lê Quang Đức** (`leduc1707`) | **Logging & PII.** Correlation ID trong middleware: sinh `req-<8hex>`, tái dùng `x-request-id` từ gateway nhưng validate trước khi tin, xoá contextvars giữa các request. Bind 5 field ngữ cảnh một lần đầu handler. Đặt `scrub_event` trước `JsonlFileProcessor`. Thêm pattern hộ chiếu và địa chỉ VN. | [`dfe70c7`](https://github.com/kiendang2105/Day13-K3-Observability/commit/dfe70c7) — 10 file, +347/−23 | Thứ tự processor trong structlog quyết định tất cả: `scrub_event` đặt sau chỗ ghi file thì PII đã nằm trên đĩa, xoá cũng vô nghĩa. Và ID từ bên ngoài phải validate — chứa `\n` là chèn được dòng log giả. |
| | **Prompt versioning & rollback.** Tạo `day13-chat` v1/v2 trên Langfuse, gán `baseline`/`candidate`/`production`, promote `production` sang v2 rồi rollback về v1. Viết `check_prompt_trace.py` xác minh trace gắn đúng version. | [`c2109e9`](https://github.com/kiendang2105/Day13-K3-Observability/commit/c2109e9) | App im lặng fallback về prompt local khi Langfuse không trả về được — trace vẫn 200, chỉ metadata ghi `local-fallback` là sai. Loại lỗi này không tự báo, phải chủ động đi kiểm. |
| | **Dashboard, SLO & Alert.** Viết `build_dashboard.py` sinh 6 panel từ `data/logs.jsonl`, đọc tên/đơn vị/threshold thẳng từ `config/dashboard.yaml`. Sửa spec đang map nhầm sang `/metrics`. Siết `elevated_error_rate` từ 5% về đúng SLO 2%. | [`c2109e9`](https://github.com/kiendang2105/Day13-K3-Observability/commit/c2109e9) — 18 file, +937/−108 | `/metrics` là bộ đếm cộng dồn trong RAM, không có trục thời gian nên không thể dựng cửa sổ 60 phút hay `rate_per_minute`, và về 0 mỗi lần restart. Nguồn của dashboard phải là log có timestamp. |
| | **Điều tra challenge & fix.** Chạy `day13-k3-observability-v1`, nối Metrics → Traces → Logs, tìm ra cả nguyên nhân trực tiếp lẫn phần khuếch đại. Đẩy `agent.run` sang threadpool, thêm access log `request_completed`, viết `probe_concurrency.py` và test chống hồi quy. | [`cc11f1a`](https://github.com/kiendang2105/Day13-K3-Observability/commit/cc11f1a) — 10 file, +432/−31<br>[`3447c69`](https://github.com/kiendang2105/Day13-K3-Observability/commit/3447c69) | Chỉ số mình đang theo dõi có thể không phải chỉ số người dùng cảm nhận. Log ghi 2 651 ms, client chờ 15 300 ms, dashboard hiện dấu tích xanh suốt thời gian sự cố — vì `latency_ms` bắt đầu đếm **sau** khi request đã nằm chờ xong. Chọn sai điểm đặt đồng hồ thì có đủ log, đủ trace, đủ dashboard vẫn không thấy sự cố. |

Toàn bộ commit nằm trên nhánh `leduc`. Kiểm tra bằng:

```bash
git log --author=leduc1707 --oneline cd84f4f..HEAD
```
