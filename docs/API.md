# 前后端接口合同 v0.3

本页描述现有文本接口。语音／照片上传与识别尚未实现，开发要求见 [团队入口](team/README.md)，拟议接口见 [媒体合同草案](team/MEDIA-CONTRACT.md)；不能把草案端点作为已可调用能力。实现 PR 必须同步本页、`contracts/api.ts` 和前端接线说明。

服务地址默认 `http://127.0.0.1:18768`。所有 JSON UTF-8。写请求带 `Content-Type: application/json` 和 `X-Session-Token`（从 `/health` 的 `session_token` 读取）。**只有创建记录要求 `Idempotency-Key`**；其余写入用 `expected_version` 防止覆盖。服务重启后重新获取 token。

`organize`、`review`、`revise` 的 `expected_version` 都必须是正整数。缺失、布尔值、字符串、零或负数返回 `400 expected_version_must_positive_integer`；与当前版本不一致返回 `409 stale_version`。服务器不会替调用方自动选择最新版本。

本 MVP 用单人本地会话，不发送 `X-Auth-Token`。已有 `/api/auth/*` 属于保留的账号兼容接口，不属于此次老人端必接合同，也不代表多家庭鉴权已安全完成。

## 核心流程

### `POST /api/events` 保存原话

请求：

```json
{"raw_text":"今天胸口疼，喘不上气","source_kind":"elder","actor_name":"老人"}
```

成功 `201`（重复幂等请求为 `200`）：`{ok:true, created:true|false, event}`。event 立即含 `raw_text`、`state:"inbox"`、`version:1`、`local_safety`。前端收到这个响应后就可以显示“已保存”，不要等 AI。

完整 Event 包含：`record_id`、`raw_text`、`source_kind`、`actor_name`、`occurred_time`、`recorded_at`、`state`、`version`、`draft`、`result_meta`、`review_notes`、`related_record_ids`、`supersedes_id`、`created_at`、`updated_at`、`household_id`、`local_safety`、`confirmation_scope`。未整理时 `draft/result_meta` 为 null；只有状态为 `recorded` 时 `confirmation_scope` 为 `record_accuracy`。本地单人 MVP 的前端不要根据 `household_id` 构建账号或家庭功能。

`raw_text` 必填，最多 10000 字符；`actor_name` 必填，最多 80 字符。`source_kind` 必填，可用 `elder`、`document`、`family_observation`、`family_report`、`caregiver`、`clinician_evidence`、`audio_transcript`、`system`、`unknown`。老人手输用 elder；公开论文摘要用 document，不能冒充亲口自述。

可选 `occurred_time:string|null`、`related_record_ids:string[]`（最多 10 个已存在记录 ID）。`occurred_time` 如果提供了非字符串、非 null 值，返回 `400 occurred_time_required`。不要传 `recorded_at`，让服务器记录输入时间；创建或修订时传入该字段会返回 `400 recorded_at_read_only`。不知道发生时间就不填。新记录 ID 由后端生成。

每次新建先生成 `crypto.randomUUID()` 作为幂等键，同一请求超时重试必须复用原键和原请求体。同键不同内容返回 409；用户新建另一条记录使用新键，即使文字相同也保留两条。

### `POST /api/events/{record_id}/organize` 整理

请求：`{"expected_version":1}`。可选 `actor_name`；省略时使用“本地用户”，如果提供，必须是非空字符串且最多 80 字符。成功 `200`，event 变为 `draft`、版本加一，并返回 `ok:true`、`ai_failed:false`、`event`、`output`、`provider`、`trace_id`、`prompt_version`、`schema_version`、`latency_ms`、`safety_guard_applied`、`raw_text_preserved:true`、`local_safety` 及扁平安全字段。output 是 `event-v0.3` 草稿，仍需人工核对；`event.draft` 与本次保存的 output 一致。后端持久化接缝会再校验草稿的 Schema、来源、记录 ID、时间和结果元数据，不会保存绕过 `event-v0.3` 规则的输出。

AI 失败、超时、断网或结果非法时为 `422`，响应仍含 `event`、`raw_text_preserved:true`、`ai_failed:true`、`failure_reason`、`local_safety` 和扁平的 `danger_detected/escalation_level/review_role/danger_reminder`。第一次整理失败时 event 保持 `inbox`，没有伪造 draft。若旧草稿已存在，失败保留原版本和旧草稿；页面必须注明本次重新整理失败，不能把旧结果当成本次成功。危险原文仍可用详情和历史接口查询。

```json
{
  "ok": false,
  "ai_failed": true,
  "error": "ai_organize_failed",
  "record_id": "rec_实际ID",
  "raw_text_preserved": true,
  "failure_reason": "网络连接失败",
  "danger_detected": true,
  "escalation_level": "emergency",
  "review_role": "emergency_services",
  "danger_reminder": "原始记录中出现需要及时人工或急救专业人员判断的描述，请联系当地急救服务或专业人员，不要自行改药。"
}
```

上面省略了完整 `event`、`local_safety`、`trace_id` 和审计元数据以便阅读，实际响应还包含 `failure_type`、`failure_cause_type`、`raw_text_sha256`、`prompt_version`、`schema_version`。这些字段用于问题追踪和审计关联；普通页面应依赖 `error`、`failure_reason`、`event`、`raw_text_preserved`、`local_safety` 与扁平安全字段，不应根据异常类名决定用户流程。可以从历史的 `audit` 看到失败类型和原因。前端应先解析 JSON 再处理 `response.ok`，不能遇到非 2xx 就丢掉响应体。

### `POST /api/events/{record_id}/review` 核对

请求：`{"expected_version":2,"action":"confirm","note":"仅确认记录准确"}`。`actor_name` 规则与整理接口一致；`note` 若提供必须是字符串，非字符串返回 `400 note_required`。成功 `200`，event 变为 `recorded`。`confirm` 只表示原文/整理是否记录准确，不能表示医生确认，也不能消除 `local_safety` 危险状态。退回时用 `action:"return"`，必须带原因。

### `POST /api/events/{record_id}/revise` 修订

请求带新 `raw_text`、`source_kind`、`actor_name`、`expected_version`、`reason`；`actor_name` 必填，非空且最多 80 字符。成功 `201` 返回 `{ok:true,event:新记录}`。旧版本标记为 `superseded` 并留在历史，新版本重新扫描危险描述；旧原文不覆盖。新记录 version 从 1 开始，`supersedes_id` 指向旧记录，后续用新 ID 整理与核对。

### `GET /api/events`、`GET /api/events/{id}`、`GET /api/events/{id}/history`

成功均为 200：列表 `{ok:true,events:[Event]}`；详情 `{ok:true,event:Event}`；历史 `{ok:true,history:[{revision_id,record_id,action,version,snapshot,actor_name,at}],audit:[{audit_id,record_id,action,version,actor_name,at,details}]}`。history 是该 ID 的版本，新旧修订 ID 通过 `supersedes_id` 关联。

列表包含 superseded 记录，主列表可筛掉，历史入口保留。每个 event 都有 `local_safety`。详情/历史查询不到返回 `404`。

### `POST /api/handoffs`、`GET /api/handoffs/{id}`

生成请求体必须严格为 `{}`，非空对象返回 `400 handoff_body_must_be_empty_object`。成功返回 `201 {ok:true,handoff}`；读取返回 `200 {ok:true,handoff}`。handoff 包含 `handoff_id`、`created_at`、`household_id`、`items`、`unresolved_count`。每个 item 是完整 Event，加上 `unresolved` 和 `unresolved_reasons`。本地单人前端不使用 `household_id`；它只是兼容层归属信息。

危险记录会带 `unresolved:true`、`unresolved_reasons` 中的 `local_danger_detected`；核对记录不会把它清掉。未核对、用药/医嘱、专业复核要求、升级和冲突也会成为未解决原因；不要自行把这些字段清空。

卡片是生成时的快照。后续修订不会修改旧卡片；希望显示最新内容需要重新 POST 生成。当前不直接提供 PDF 或真正的分享链接，前端负责可读页面或浏览器打印。

## 状态和常见错误

| 状态 | 含义 | 可继续动作 |
|---|---|---|
| inbox | 原话已保存 | 整理、修订、查历史、生成材料 |
| draft | 已有草稿，未核对 | 核对、退回、重新整理、修订 |
| recorded | 已核对记录准确 | 查历史、退回、修订、生成材料 |
| needs_review | 已退回待整理 | 重新整理、修订 |
| superseded | 已被新记录替代 | 查看旧原文和历史 |

所有状态都不是医学安全等级。200/201 为成功；400 为字段或请求格式错误；403 为本地 token/Origin 错误；404 为记录不存在；409 为版本、状态或幂等键冲突；422 为整理失败；500 为未预期的服务端错误。一般错误格式 `{ok:false,error:"错误码"}`。未预期异常只返回 `internal_server_error`，不会向客户端暴露数据库路径、供应商正文或内部异常信息。数据库本身无法保存时，不能显示“已保存”。

浏览器不使用开发代理而直接跨域访问时，后端 `.env` 的 `ALLOWED_ORIGIN` 必须与页面 Origin 完全一致。预检支持 `GET, POST, OPTIONS`，并允许 `Content-Type`、`Idempotency-Key`、`X-Session-Token` 和兼容账号接口使用的 `X-Auth-Token`。不匹配的 Origin 不会获得跨域许可，写请求返回 403。

## 前端必须怎么处理

- 保存接口成功后立刻展示已保存；危险输入把 `danger_reminder` 放在页面顶部，不能藏在折叠菜单。
- 422 不是“没有记录”。展示“原文已保存，AI 整理失败”，保留原话和重试按钮；不要显示空白卡片或“整理成功”。
- `danger_detected=false` 只表示本地规则没命中，文案不得写“无危险”“正常”。
- `local_safety` 与 AI 草稿的升级字段都要看；本地未命中不能抵消草稿中已有的 `urgent/emergency`。本地命中也不能被 AI 漏标或“核对准确”抵消。
- `review_role=emergency_services` 时只显示联系当地急救服务/专业人员的固定提醒，不显示疾病名、剂量或家庭处置建议。
- 版本冲突 `409` 时重新 GET 详情，让用户选择重载或修订，不能覆盖别人新版本。

完整 TypeScript 类型在 `contracts/api.ts`。Schema 只约束 AI 草稿；`local_safety` 是后端外层安全字段。
