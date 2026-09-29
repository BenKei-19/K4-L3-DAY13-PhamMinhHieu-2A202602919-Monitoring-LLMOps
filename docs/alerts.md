# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Rule nằm trong [`../config/alert_rules.yaml`](../config/alert_rules.yaml); SLO nằm trong [`../config/slo.yaml`](../config/slo.yaml). Mọi bước điều tra đi theo thứ tự **Metrics → Logs → Traces**.

Lệnh lọc log dùng chung (PowerShell, chạy từ thư mục gốc repo):

```powershell
# Liệt kê request chậm hơn 2000 ms kèm correlation_id
Get-Content data/logs.jsonl | ConvertFrom-Json | Where-Object { $_.event -eq "response_sent" -and $_.latency_ms -gt 2000 } | Select-Object ts, correlation_id, feature, latency_ms, ttft_ms
```

## Alert 1

- Tên: `HighLatencyP95`
- Severity: P2-high
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (99.5% request trả lời thành công trong ≤ 3000 ms, cửa sổ 28 ngày)
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 2000 ms trong cửa sổ 5 phút, có ít nhất 10 request, và duy trì liên tục 5 phút. Đây là cảnh báo sớm, thấp hơn ngưỡng SLO 3000 ms: baseline P95 = 1138 ms, còn incident `rag_slow` đẩy latency lên khoảng 2650 ms.
- Ảnh hưởng tới người dùng: câu trả lời chậm gấp nhiều lần bình thường; nếu kéo dài hoặc nặng thêm sẽ vượt 3000 ms và tiêu error budget.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics**: mở panel *Latency percentiles and TTFT*, xác định phút bắt đầu tăng. So sánh TTFT P95 với latency P95: nếu TTFT vẫn khoảng 50 ms mà latency tăng mạnh thì phần chậm nằm ngoài giai đoạn sinh token đầu tiên (thường là retrieval).
  2. **Logs**: dùng lệnh lọc ở trên để lấy `correlation_id` của vài request chậm, kiểm tra chúng có cùng `feature`/`model` không.
  3. **Traces**: trong Langfuse, lọc trace theo metadata `correlation_id`, mở waterfall và so thời lượng span `retrieval` với `llm-generate`.
- Mitigation tạm thời: nếu `retrieval` chậm, giảm timeout của vector store và trả lời bằng tài liệu fallback/cache; nếu `llm-generate` chậm, chuyển sang model nhỏ hơn hoặc giảm độ dài output. Trong lab: `python scripts/inject_incident.py --scenario rag_slow --disable`.
- Owner: PhamMinhHieu

## Alert 2

- Tên: `HighErrorRate`
- Severity: P1-critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (request lỗi luôn bị tính là xấu) và guardrail `error_rate_pct_max: 2`
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2` trong cửa sổ 5 phút, có ít nhất 10 request, và duy trì liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 thay vì câu trả lời. Với mục tiêu 99.5%, error rate 2% làm cạn error budget của 28 ngày nhanh gấp khoảng 4 lần mức cho phép.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics**: panel *Error rate and retrieval success*, xem `error_type` nào chiếm đa số và retrieval success có giảm cùng lúc không.
  2. **Logs**: lọc `event == "request_failed"`, đọc `error_type`, `tool_name`, `tool_success` và `payload.detail`; lấy một `correlation_id`.
  3. **Traces**: mở trace cùng `correlation_id`; span `retrieval` có level `ERROR` và `status_message` cho biết lỗi xảy ra ở retrieval hay ở bước sau.
- Mitigation tạm thời: nếu lỗi ở retrieval, trả lời bằng fallback không dùng tài liệu thay vì trả 500, thêm retry có backoff; nếu lỗi xuất hiện ngay sau một lần deploy hoặc đổi prompt, rollback thay đổi đó. Trong lab: `python scripts/inject_incident.py --scenario tool_fail --disable`.
- Owner: PhamMinhHieu

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: P3-warning
- Duration: 15m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: trung bình `cost_usd` của `response_sent` > 0.005 USD/request (hơn 2 lần baseline 0.00214 USD), duy trì liên tục 15 phút. Cửa sổ dài hơn hai alert trên vì cost tăng không làm hỏng trải nghiệm ngay, nhưng sẽ làm cạn ngân sách ngày.
- Ảnh hưởng tới người dùng: câu trả lời thường dài hơn cần thiết; nếu không xử lý, hệ thống vượt ngân sách và có thể phải giới hạn dịch vụ.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics**: đối chiếu panel *Cost over time* với *Input and output tokens*: output tokens tăng thì do câu trả lời dài hơn, input tokens tăng thì do prompt hoặc context dài hơn.
  2. **Logs**: lọc `response_sent` có `cost_usd` cao nhất, xem `feature`, `model`, `tokens_in`, `tokens_out` và lấy `correlation_id`.
  3. **Traces**: mở generation `llm-generate` của trace đó, xem usage, cost và prompt version được link; kiểm tra label `production` có vừa bị chuyển sang version mới không (`python scripts/prompt_versions.py status`).
- Mitigation tạm thời: rollback label `production` về prompt version trước (`python scripts/prompt_versions.py promote --version 1`), giới hạn số output token tối đa, hoặc chuyển feature ít quan trọng sang model rẻ hơn. Trong lab: `python scripts/inject_incident.py --scenario cost_spike --disable`.
- Owner: PhamMinhHieu
