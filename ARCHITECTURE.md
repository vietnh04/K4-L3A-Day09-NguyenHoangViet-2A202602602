# L3A Architecture Record

Hệ thống điều tra và giải quyết tranh chấp thương mại điện tử đa tác nhân (Multi-Agent System) tích hợp giao thức MCP (Model Context Protocol) và chuẩn giao tiếp A2A (Agent-to-Agent).

## 1. System overview

Luồng xử lý từ input hồ sơ khiếu nại đến kết quả thẩm định và vết thực thi quan sát được:

```text
Input (inputs/<case_id>.json)
  │
  ▼
[Coordinator Agent] ──── emit: case_received, task_assigned
  │
  ├──► [Policy Specialist]     ──── call: get_policy
  ├──► [Order Specialist]      ──── call: get_order, get_order_items (khi cần)
  ├──► [Payment Specialist]    ──── call: get_order_payments (khi cần)
  ├──► [Refund Specialist]     ──── call: get_refund_timeline (khi có khiếu nại hoàn tiền)
  └──► [Shipment Specialist]   ──── call: get_shipment_summary (khi giao hàng muộn)
            │
            ▼ (MCP Server: xác thực bằng chứng, cấp evidence_ref)
       emit: tool_result_consumed
            │
            ▼
      emit: handoff (chuyển giao tập bằng chứng thu thập được)
            │
            ▼
[Verifier Agent] (Đối soát chéo, xác minh tính nhất quán seller, giải quyết tài chính)
  │
  ├──► emit: verification_completed
  └──► Output Generation (outputs/<case_id>.json)
            │
            ▼
[Coordinator Agent] ──── emit: case_finalized
```

## 2. Agent ownership

| Actor | Input | Trách nhiệm | Output/handoff | Tool được phép gọi |
| --- | --- | --- | --- | --- |
| **Coordinator** | `inputs/<case_id>.json` | Tiếp nhận hồ sơ khiếu nại, phân loại sơ bộ `primary_issue`, giao việc cho các specialist agents, chốt hồ sơ cuối cùng. | Giao việc tới `specialist_agents`, phát sự kiện `case_received`, `task_assigned`, `case_finalized`. | Không gọi MCP tool trực tiếp. |
| **Policy Specialist** | `case_id`, `policy_version` | Tra cứu bảng quy tắc nghiệp vụ chuẩn mực cho loại tranh chấp tương ứng. | Trả về `policy_ev` và `policy_rule` cho Verifier. | `get_policy` |
| **Order Specialist** | `case_id`, `order_id` | Lấy dữ liệu trạng thái đơn hàng và danh sách sản phẩm/người bán. | Trả về `order_ev`, `items_ev`, danh sách `item_ids`, `seller_ids`. | `get_order`, `get_order_items` |
| **Payment Specialist** | `case_id`, `order_id` | Lấy lịch sử giao dịch thanh toán, phương thức thanh toán và số tiền đã thu. | Trả về `pay_ev`, danh mục `payment_references`. | `get_order_payments` |
| **Refund Specialist** | `case_id`, `order_id` | Tra cứu dòng thời gian xử lý hoàn tiền cho các ca có khiếu nại hoàn tiền. | Trả về `refund_ev` (domain: refund) với trạng thái và số tiền hoàn. | `get_refund_timeline` |
| **Shipment Specialist** | `case_id`, `order_id` | Lấy tóm tắt vận chuyển, thời hạn giao hàng của người bán và hãng vận chuyển. | Trả về `ship_ev`, thời hạn bàn giao và nguyên nhân trễ. | `get_shipment_summary` |
| **Verifier** | Bằng chứng thu thập từ các Specialists | Đối soát chéo quy tắc nghiệp vụ, giải quyết mâu thuẫn dữ liệu, xác định bên chịu trách nhiệm thực tế, tính toán bồi hoàn và hiệu chỉnh độ tin cậy. | Phát hành `outputs/<case_id>.json` và sự kiện `verification_completed`. | Sử dụng LLM NIM API để kiểm chứng ngữ nghĩa. |

## 3. A2A protocol

- **Message Envelope:** Chuẩn hóa theo `trace-event-v1.schema.json` với các trường bắt buộc: `schema_version`, `event_id`, `case_id`, `event_type`, `occurred_at`, `actor`.
- **Correlation:** Mọi sự kiện liên kết chặt chẽ qua định danh `case_id`.
- **Thứ tự vòng đời (Lifecycle Invariants):**
  1. `case_received` (Actor: `coordinator`)
  2. `task_assigned` (Actor: `coordinator` -> Target: `specialist_agents`)
  3. `tool_result_consumed` (Từng Specialist Agent khi hoàn thành thu thập dữ liệu)
  4. `handoff` (Từ `specialist_agents` sang `verifier` kèm danh sách `evidence_refs`)
  5. `verification_completed` (Actor: `verifier` kèm quyết định và bằng chứng đã dẫn chứng)
  6. `case_finalized` (Actor: `coordinator` kết thúc hồ sơ)
- **Không suy diễn ngầm:** Mọi quyết định đều dựa trên sự kiện và bằng chứng quan sát được.

## 4. Evidence lifecycle

- **Validation:** Mọi phản hồi từ MCP Server được kiểm chứng qua `mcp-evidence-response-v1.schema.json`, bao gồm kiểm tra mã băm kết quả (`result_hash`), định danh `evidence_ref` và `domain`.
- **Scoping:** Bằng chứng được gắn nhãn theo phiên làm việc và `case_id`; nghiêm cấm tái sử dụng giữa các case khác nhau.
- **Tránh Forbidden Domains & Tối ưu Precision:**
  - Mỗi loại tranh chấp chỉ gọi và dẫn chứng các nhóm bằng chứng trực tiếp liên quan.
  - Vụ việc hủy đơn / thanh toán / hoàn tiền không trích dẫn bằng chứng vận chuyển (`shipment`).
  - Vụ việc hoàn tiền bắt buộc trích dẫn bằng chứng dòng thời gian hoàn tiền (`refund`).
  - Vụ việc khiếu nại vô căn cứ chỉ trích dẫn thông tin đơn hàng và chính sách.
  - `output.evidence_refs` là tập hợp duy nhất các bằng chứng thực sự được trích dẫn trong `claim_assessments`.

## 5. Failure policy

| Failure | Retry? | Fallback | Trace event/code |
| --- | --- | --- | --- |
| MCP timeout / Network lag | Có (Tối đa 3 lần với exponential backoff 2s, 4s) | Báo lỗi hệ thống sau 3 lần thất bại | `mcp_gateway.py` raise RuntimeError |
| MCP tool execution error | Có (Tự động retry) | Kiểm tra và làm mới phiên Active Run nếu token phiên hết hạn | `call_tool` retry loop |
| Missing/Inconsistent seller | Không retry | Trích xuất seller_id thực tế từ `get_order_items` hoặc `shipping_limits` thay vì dùng dữ liệu tĩnh trong policy | `VERIFIED_CONSISTENCY` |
| LLM API rate limit / failure | Không | Fallback về giá trị tin cậy mặc định chuẩn hóa (0.98 cho resolved, 0.92 cho needs_investigation) | `connect_model.py` Exception handler |

## 6. Verification invariants

Trước khi phát hành output và hoàn tất hồ sơ, hệ thống bắt buộc kiểm tra các bất biến sau:
1. **Schema Compliance:** Đầu ra tuân thủ 100% `contracts/schemas/l3a-output-v2.schema.json`.
2. **Seller Responsibility Consistency:** Nếu `responsible_parties` chỉ định bên chịu trách nhiệm là người bán (`seller`), thì `party_id` bắt buộc phải là seller ID thực tế của đơn hàng đó và phải nằm trong `affected_entities.seller_ids`.
3. **Status / Refund / Action Alignment:**
   - Nếu `recommended_refund_brl > 0`: `case_status` phải là `action_required`, `refund_lines` phải có đúng 1 dòng khớp số tiền và mã hành động.
   - Nếu `recommended_refund_brl == 0`: `case_status` là `no_action` hoặc `needs_investigation`, `refund_lines` là mảng rỗng `[]`.
4. **Claim-Evidence Linkage:** Mọi bằng chứng trong `claim_assessments` đều có trong tập bằng chứng MCP đã thu thập và được đồng bộ vào `evidence_refs` cấp cao nhất.
5. **Confidence Bounds:** Độ tin cậy nằm trong khoảng `[0.0, 1.0]`, được hiệu chuẩn ở mức cao cho các phán quyết đã đối soát dữ liệu thực tế.

## 7. Reproducibility

- **Môi trường thực thi:** Python 3.11, gói thư viện: `mcp>=1.0.0`, `httpx2`, `jsonschema>=4.20.0`, `ruff`, `pytest`.
- **Mô hình suy luận LLM:** NVIDIA NIM API (Model: `meta/llama-3.2-11b-vision-instruct`).
- **Lệnh thực thi quy trình:**
  ```bash
  day09 validate-inputs
  day09 run
  day09 validate
  day09 package --output dist/submission.zip
  ```
- **Tài nguyên:** Giới hạn thời gian kết nối mạng 300s, không lưu trữ thông tin API key vào kho mã nguồn hoặc tệp trace.
