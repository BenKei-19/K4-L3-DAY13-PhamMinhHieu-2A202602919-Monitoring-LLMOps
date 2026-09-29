# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Pham Minh Hieu
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

- **Cách tạo/nhận và truyền correlation ID:**
- **Các metadata được ghi vào structured log:**
- **Cách bảo đảm PII được scrub trước khi ghi:**
- **Cách kiểm chứng kết quả:**

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
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

- **Dashboard và sáu panel:**
- **SLO và lý do chọn:**
- **Cách tính error budget:**
- **Ba alert và runbook tương ứng:**

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, affected feature `monitoring`, `latency_threshold_ms` 2000)
- **Khoảng thời gian điều tra:** 2026-09-29 16:28:00–16:28:13 giờ VN (09:28:00–09:28:13 UTC); kiểm chứng sau khi tắt incident lúc 16:29:44
- **Triệu chứng từ metrics:** latency P50/P95/P99 = 2652/2654/2654 ms (bình thường 151/151/151 ms), TTFT P95 giữ nguyên 50 ms, error rate 0%, retrieval success 100% — [`12-incident-metric.txt`](evidence/12-incident-metric.txt)
- **Log line và correlation ID liên quan:** 5/5 `response_sent` của feature `monitoring` có `latency_ms` > 2000; ví dụ `req-edab947a` (session `k4-l3a-challenge-s02`, `latency_ms` 2654, `ttft_ms` 50, `tool_success` true) — [`13-incident-log.txt`](evidence/13-incident-log.txt)
- **Trace ID và span gây ảnh hưởng:** trace `d2b0bcc5c3eac19556554f27a4139bd5` (cùng `correlation_id` `req-edab947a`): `lab-agent-run` 2.655 s, trong đó span `retrieval` 2.501 s và `llm-generate` 0.151 s; trace bình thường có `retrieval` ≈ 0 s — [`14-incident-trace.txt`](evidence/14-incident-trace.txt)
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
