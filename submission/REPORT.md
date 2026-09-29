# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phạm Minh Hiếu
- **MSSV:** 2A202602919
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/BenKei-19/K4-L3-DAY13-PhamMinhHieu-2A202602919-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-02919`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png), [`evidence/06-trace-list.txt`](evidence/06-trace-list.txt) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png), [`evidence/07-08-trace-detail.txt`](evidence/07-08-trace-detail.txt) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png), [`evidence/07-08-trace-detail.txt`](evidence/07-08-trace-detail.txt) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png), [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt) |
| Prompt rollback | [`evidence/10-prompt-rollback.png`](evidence/10-prompt-rollback.png) (production → v2), [`evidence/10-prompt-rollback_2.png`](evidence/10-prompt-rollback_2.png) (sau rollback → v1), [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png), [`evidence/12b-incident-recovery.png`](evidence/12b-incident-recovery.png), [`evidence/12-incident-metric.txt`](evidence/12-incident-metric.txt) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png), [`evidence/14-incident-trace.txt`](evidence/14-incident-trace.txt) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Baseline: 60 bản ghi `api` thiếu `correlation_id` và enrichment, 0 correlation ID |
| `validate_dashboard.py` | 6/6 | 6/6 | Contract có sẵn; dashboard runtime: `scripts/dashboard.py` |
| `pytest` | 22 passed | 43 passed | Thêm test PII, correlation ID, child observations, dashboard, alert/SLO |
| Số traces hợp lệ | 0 (30 trace chỉ có root, `correlation_id=MISSING`) | 20 trace có root/retrieval/generation (14:18–14:44) | Xem `06-trace-list.txt` |
| Số PII leak | 0 | 0 | Validator quét toàn bộ `data/logs.jsonl` |
| Latency P95 / TTFT P95 | 1138 ms / 50 ms | 151 ms / 50 ms (load test 14:21, server đã warm); 7419 ms / 50 ms trên toàn cửa sổ 60 phút | Các request chậm (3–10 s) trùng lúc kết nối tới Langfuse Cloud chậm khi lấy prompt |
| Retrieval success rate | 100% | 100% | Không bật incident |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** [`CorrelationIdMiddleware`](../app/middleware.py) chạy đầu tiên cho mỗi request. Nó gọi `clear_contextvars()` để xóa context còn sót từ request trước. Nếu header `x-request-id` khớp đúng dạng `req-<8 hex>` thì dùng lại, còn không thì sinh ID mới từ `uuid4`. Tôi không nhận chuỗi tùy ý từ header để client không đưa được dữ liệu lạ (ví dụ một email) vào log. ID được `bind_contextvars` nên mọi dòng log trong request tự có `correlation_id`. ID cũng được lưu vào `request.state`, truyền vào `LabAgent.run` để ghi vào metadata của trace, và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** mọi dòng có `ts`, `level`, `service`, `event`, `correlation_id`. Ở đầu endpoint `/chat`, trước log `request_received`, tôi bind thêm `user_id_hash` (SHA-256 cắt 12 ký tự, không ghi user_id gốc), `session_id`, `feature`, `model`, `env`, nên cả `request_received` lẫn `response_sent` đều có đủ ngữ cảnh. `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name` và `tool_success`; đây chính là các trường mà dashboard dùng.
- **Cách bảo đảm PII được scrub trước khi ghi:** structlog chạy các processor theo thứ tự. Tôi đăng ký `scrub_event` sau `merge_contextvars`/`TimeStamper` nhưng **trước** `JsonlFileProcessor` (bước ghi file) và `JSONRenderer` ([`logging_config.py`](../app/logging_config.py)), nên dữ liệu được che trước khi bị serialize hay ghi xuống đĩa. Processor này che đệ quy cả dict/list lồng trong `payload`. [`pii.py`](../app/pii.py) có pattern cho email, thẻ thanh toán, CCCD, số điện thoại Việt Nam và hộ chiếu. Pattern được xếp từ dài đến ngắn (thẻ 16 số → CCCD 12 số → điện thoại 10 số) để một số dài không bị che mất một phần vì bị nhận nhầm là số điện thoại. Các preview gửi lên Langfuse cũng đi qua `summarize_text`, nên trace cũng không chứa PII thô.
- **Cách kiểm chứng kết quả:** unit test cho từng loại PII, cho văn bản thường không bị che nhầm ([`test_pii.py`](../tests/test_pii.py)), và cho correlation ID/enrichment/PII qua API thật ([`test_correlation_logging.py`](../tests/test_correlation_logging.py)). `validate_logs.py` tăng từ 30/100 lên 100/100, 0 PII leak. [`05-pii-redaction.txt`](evidence/05-pii-redaction.txt) cho thấy input chứa email, số điện thoại, số thẻ, CCCD, hộ chiếu giả đều thành `[REDACTED_*]` trong log. [`04-structured-log.txt`](evidence/04-structured-log.txt) cho thấy header `x-request-id: req-0a1b2c3d` do client gửi được giữ nguyên trong response và log.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** `.env` chỉ chứa key của project `day13-k4-l3a-02919` do tôi tự tạo (tên project hiện trên ảnh 06–10, 14). Mọi trace đều có `correlation_id` trùng với một dòng trong `data/logs.jsonl` sinh từ các lần tôi chạy workload. Danh sách 20 trace (14:18–14:44) đọc lại qua API observations v2 nằm trong [`06-trace-list.txt`](evidence/06-trace-list.txt).
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (loại `agent`, decorator `@observe`) có hai con ([`agent.py`](../app/agent.py)):
  - `retrieval` (loại `retriever`): input là preview câu hỏi đã che PII, output là `doc_count` và preview tài liệu; nếu retrieval lỗi thì span được đặt `level=ERROR`.
  - `llm-generate` (loại `generation`): có model `claude-sonnet-4-5`, usage `input`/`output`/`total`, cost tách input/output/total, và `completion_start_time` để Langfuse tính TTFT. Prompt version được link qua `propagate_attributes(prompt=...)`.

  Raw prompt và raw answer không được gửi lên trace. Ví dụ trace `8ab028e6…`: generation 36 input + 116 output token, cost $0.001848, prompt `day13-chat` v1 ([`07-08-trace-detail.txt`](evidence/07-08-trace-detail.txt)).
- **Cách nối trace với log:** `correlation_id` được đưa vào trace metadata bằng `propagate_attributes(metadata={"correlation_id": ...})`, nên trên Langfuse có thể lọc trace theo metadata này. Ví dụ log `req-70adcd05` ↔ trace `8ab028e66ebc0d9d10cd7e1365c9355f`, và log `req-edab947a` ↔ trace `d2b0bcc5c3eac19556554f27a4139bd5` trong phần điều tra challenge.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1, labels `baseline` và `production`
- **Version/label candidate:** v2, label `candidate`
- **Trace ID của mỗi version:**
  - Label `baseline` → v1: `49dc3c5a7c8a14973e3a4ebc553c45b0` (`req-597d98e8`)
  - Label `candidate` → v2: `165c425fdd1554f79665eda1eff9ba30` (`req-59f4a9c8`)
  - `production` sau khi promote → v2: `453d47b75d8b9de9edbed501bb08275f` (`req-0d66c3e9`)
  - `production` sau khi rollback → v1: `6aab0000455126b0acd2b24361be563a` (`req-b5bd9692`)
- **Cách promote và rollback `production`:** `python scripts/prompt_versions.py promote --version 2` và `python scripts/prompt_versions.py promote --version 1`; output đầy đủ trong [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [`scripts/dashboard.py`](../scripts/dashboard.py) đọc `data/logs.jsonl` và lấy tên panel, đơn vị, time range (60 phút), refresh (30 giây) và threshold trực tiếp từ [`config/dashboard.yaml`](../config/dashboard.yaml), nên dashboard runtime và validator luôn dùng chung một contract. Sáu panel:
  1. Latency P50/P95/P99 + TTFT P95.
  2. Request/phút.
  3. Error rate kèm breakdown theo `error_type` và retrieval success.
  4. Cost theo phút và tổng.
  5. Token input/output.
  6. Quality trung bình.

  Mỗi panel có đường threshold nét đứt, trạng thái Đạt/Vượt threshold và bảng số liệu theo phút. Logic tính toán có test riêng ([`test_dashboard_runtime.py`](../tests/test_dashboard_runtime.py)). Ảnh: [`11-dashboard-overview.png`](evidence/11-dashboard-overview.png).
- **SLO và lý do chọn:** SLO `fast_successful_requests` ([`config/slo.yaml`](../config/slo.yaml)): 99.5% request phải có `response_sent` với `latency_ms` ≤ 3000 ms, cửa sổ 28 ngày; request lỗi tự động bị tính là xấu. Baseline P99 là 1228 ms, nên ngưỡng 3000 ms dư khoảng 2.4 lần, đủ để cold start (khoảng 1.6 s) không bị tính là vi phạm. Baseline không có lỗi nên 99.5% là đạt được. Tôi không chọn 99.9% vì với lưu lượng nhỏ của lab, chỉ vài request lỗi đã làm cạn budget.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5%, tức `allowed_bad = total_requests × 0.5%`, tương đương 50 request xấu trên mỗi 10.000 request. Tính theo thời gian: 28 ngày = 40.320 phút × 0.5% ≈ 201.6 phút hệ thống hỏng hoàn toàn. Chính sách: còn trên 50% budget thì được đổi prompt/model bình thường; còn 0–50% thì mọi thay đổi phải có kế hoạch rollback đã thử; hết budget thì dừng thay đổi tính năng.
- **Ba alert và runbook tương ứng:** định nghĩa trong [`config/alert_rules.yaml`](../config/alert_rules.yaml), runbook trong [`docs/alerts.md`](../docs/alerts.md). Cả ba gửi về Slack `#day13-l3a-alerts`; mỗi runbook có ba bước kiểm tra theo Metrics → Logs → Traces và mitigation:
  - `HighLatencyP95` (P2): P95 > 2000 ms trong 5 phút.
  - `HighErrorRate` (P1): error rate > 2% trong 5 phút.
  - `CostPerRequestSpike` (P3): cost trung bình > $0.005/request (hơn 2 lần baseline $0.00214) trong 15 phút.

  Ngưỡng latency 2000 ms thấp hơn SLO vì tôi đo được incident `rag_slow` chỉ làm latency lên 2651 ms: nếu alert đặt ở 3000 ms thì sẽ không bao giờ bắt được sự cố này.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, affected feature `monitoring`, `latency_threshold_ms` 2000)
- **Khoảng thời gian điều tra:** 2026-09-29 16:28:00–16:28:13 giờ VN (09:28:00–09:28:13 UTC); kiểm chứng sau khi tắt incident lúc 16:29:44
- **Triệu chứng từ metrics:** latency P50/P95/P99 = 2652/2654/2654 ms (bình thường 151/151/151 ms), TTFT P95 giữ nguyên 50 ms, error rate 0%, retrieval success 100% — [`12-incident-metric.txt`](evidence/12-incident-metric.txt)
- **Log line và correlation ID liên quan:** 5/5 `response_sent` của feature `monitoring` có `latency_ms` > 2000; ví dụ `req-edab947a` (session `k4-l3a-challenge-s02`, `latency_ms` 2654, `ttft_ms` 50, `tool_success` true) — [`13-incident-log.txt`](evidence/13-incident-log.txt)
- **Trace ID và span gây ảnh hưởng:** trace `d2b0bcc5c3eac19556554f27a4139bd5` (cùng `correlation_id` `req-edab947a`): `lab-agent-run` 2.655 s, trong đó span `retrieval` 2.501 s và `llm-generate` 0.151 s; trace bình thường có `retrieval` ≈ 0 s — [`14-incident-trace.txt`](evidence/14-incident-trace.txt)
- **Root cause:** bước retrieval (vector store) chậm thêm khoảng 2.5 s cho mỗi request trong lúc incident `rag_slow` của challenge được bật. Ba lớp bằng chứng cùng chỉ về một chỗ:
  - Metric: latency tăng khoảng 17 lần nhưng TTFT vẫn 50 ms và error rate 0%.
  - Log: 5/5 request `monitoring` có `latency_ms` khoảng 2652 ms nhưng vẫn `tool_success=true`.
  - Trace: span `retrieval` chiếm 2.501 s trên 2.655 s, trong khi `llm-generate` vẫn 0.151 s như lúc bình thường.

  Vì vậy nguyên nhân không nằm ở LLM hay prompt: hệ thống chậm nhưng không lỗi, và toàn bộ phần chậm thêm nằm ở retrieval.
- **Fix action:** tắt nguồn gây chậm ở retrieval bằng `python scripts/inject_incident.py --disable` lúc 16:29:44, rồi kiểm chứng bằng cách chạy lại đúng 5 query của challenge: latency P50/P95 về 151/152 ms, không có lỗi ([`12-incident-metric.txt`](evidence/12-incident-metric.txt), [`12b-incident-recovery.png`](evidence/12b-incident-recovery.png)). Trong hệ thống thật, mitigation tương ứng là đặt timeout cho lời gọi vector store và trả lời bằng tài liệu cache/fallback khi retrieval quá chậm.
- **Preventive measure:** bốn đề xuất, mỗi đề xuất xuất phát từ một điểm yếu lộ ra trong lần điều tra này:
  1. **Timeout và fallback cho retrieval:** trong `retrieve()`, giới hạn thời gian gọi vector store ở khoảng 1 s. Quá thời gian thì trả lời bằng tài liệu cache hoặc câu trả lời chung, đồng thời ghi `tool_success=false`. Khi đó một vector store chậm chỉ làm giảm chất lượng câu trả lời, chứ không làm mọi request chậm thêm 2.5 s.
  2. **Đo và cảnh báo riêng cho retrieval:** ghi thêm `retrieval_ms` vào log `response_sent` (lấy từ thời lượng span `retrieval`), thêm vào panel latency, và tạo alert khi retrieval P95 > 1000 ms trong 5 phút. Lần này tôi phải mở trace mới biết phần chậm nằm ở retrieval; có metric riêng thì dashboard chỉ ra được ngay.
  3. **Sửa điều kiện lưu lượng tối thiểu của `HighLatencyP95`:** hiện alert cần ít nhất 10 request trong 5 phút, trong khi challenge chỉ có 5 request, nên alert sẽ không kêu dù P95 = 2654 ms > 2000 ms ([`12-incident-metric.txt`](evidence/12-incident-metric.txt)). Nên hạ điều kiện xuống ≥ 3 request, hoặc dùng cửa sổ 15 phút cho lưu lượng thấp.
  4. **Không để request phải xếp hàng chờ nhau:** `LabAgent.run` là code đồng bộ nhưng được gọi trong endpoint `async`, nên chặn event loop. 5 request đồng thời bị xử lý lần lượt: server ghi 2.65 s mỗi request nhưng phía client phải chờ 13.3 s. Nên chạy agent trong threadpool (khai báo endpoint bằng `def` hoặc dùng `run_in_threadpool`), và theo dõi thêm latency phía người dùng (`x-response-time-ms`). Nếu không, mỗi lần retrieval chậm sẽ bị nhân lên theo số request đồng thời.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** đặt ngưỡng alert latency ở 2000 ms thay vì dùng luôn ngưỡng SLO 3000 ms. Ban đầu tôi định dùng 3000 ms cho thống nhất, nhưng khi đo thử thì incident `rag_slow` chỉ đẩy latency lên 2651 ms. Với ngưỡng 3000, alert sẽ im lặng dù người dùng chờ lâu gấp 17 lần bình thường. Tôi giữ SLO và dashboard ở 3000 ms theo contract, và dùng 2000 ms làm cảnh báo sớm (baseline P95 1138 ms). Kết quả challenge sau đó (P95 2654 ms) xác nhận quyết định này đúng.
- **Một lỗi/blocker đã gặp:** sau khi chạy load test lúc 14:04, không có trace nào lên Langfuse, và 3 request đầu mất 9.7 s, 7.4 s, 3.1 s thay vì khoảng 150 ms. Về sau, một lần chạy với label `candidate` bị rơi về prompt local (`prompt_source=local-fallback`), và lần rollback đầu tiên thất bại vì lỗi SSL handshake timeout.
- **Cách tìm nguyên nhân và xử lý:**
  1. Đối chiếu log với Langfuse: log có đủ 10 request nhưng API observations trả về 0 observation trong khoảng 14:00–14:10.
  2. Gửi một request thử với `LANGFUSE_DEBUG=true`: SDK tạo đủ 3 span và trace lên được, nên code tracing không có lỗi.
  3. Đo kết nối bằng `curl` tới `cloud.langfuse.com`: TLS handshake dao động từ 0.6 s đến 22 s. Kết luận: mạng tới Langfuse Cloud chập chờn, làm cả bước lấy prompt (timeout 2 s) lẫn bước gửi trace thất bại.

  Cách xử lý: chạy lại workload khi mạng ổn định; tăng timeout và thêm retry cho các lệnh đọc Langfuse; sửa [`prompt_versions.py`](../scripts/prompt_versions.py) để phân biệt lỗi 404 với lỗi mạng (trước đó lỗi mạng bị báo nhầm là "không tìm thấy v1"); làm lại promote/rollback và xác nhận từng trace. App đã có fallback prompt local và ghi rõ `prompt_source`, nên dù mạng lỗi, request vẫn thành công và trace không bị ghi sai version. Ngoài ra, metadata trên Langfuse hiển thị `scope.attributes.public_key`, nên tôi đã che trường này trong ảnh 08 và 10.
- **Cách hiểu luồng Metrics → Logs → Traces:** mỗi lớp trả lời một câu hỏi và thu hẹp phạm vi cho lớp sau:
  - **Metrics** cho biết hệ thống có vấn đề gì và khi nào: P95 tăng từ 151 lên 2654 ms lúc 16:28, TTFT không đổi, không có lỗi.
  - **Logs** cho biết request nào bị ảnh hưởng: lọc `latency_ms > 2000` ra 5 request `monitoring`, mỗi request có một `correlation_id`.
  - **Traces** cho biết bước nào gây ra: trace cùng `correlation_id` cho thấy `retrieval` chiếm 94% thời gian.

  `correlation_id` là sợi dây nối log với trace. Kết luận chỉ đáng tin khi cả ba lớp cùng chỉ về một nguyên nhân, và phải kiểm chứng lại bằng cách sửa rồi đo lại.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - **Prompt version:** prompt là một phần của "code" nhưng có thể đổi mà không cần deploy. Nhờ gắn version vào generation, mọi thay đổi về chất lượng hay cost đều truy được về version cụ thể. Ví dụ, với cùng input, v2 làm `tokens_in` tăng từ 32 lên 48 so với v1, tức cost input tăng khoảng 50%.
  - **Rollback:** label `production` cho phép promote hoặc rollback chỉ bằng một lệnh. Trace `453d47b7…` cho thấy production dùng v2, và trace `6aab0000…` cho thấy sau rollback đã về v1.
  - **Token/cost:** cần theo dõi theo từng request vì cost tăng âm thầm, không gây lỗi; vì vậy mới có alert `CostPerRequestSpike`.
  - **SLO và error budget:** biến "hệ thống có ổn không" thành một con số. Con số đó quyết định khi nào được tiếp tục thay đổi prompt/model và khi nào phải dừng lại để ổn định hệ thống.
- **Điều quan trọng nhất đã học:** observability phải được thiết kế để trả lời được câu hỏi khi có sự cố, chứ không chỉ để có dữ liệu. Nếu thiếu `correlation_id`, thiếu child span, hoặc đặt alert mà không đo thử, thì lúc có sự cố sẽ không nối được triệu chứng với nguyên nhân. Tôi cũng học được rằng mọi ngưỡng (SLO, alert) phải dựa trên số đo thực tế, và evidence phải được kiểm tra lại (như public key bị lộ trong metadata) trước khi nộp.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
