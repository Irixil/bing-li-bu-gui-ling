# 媒体后端合同 v0.2

状态：**本地 MVP 已实现，合同收口仍有明确缺口**。

更新日期：2026-09-12。
当前实现基线：`fix/backend-api` 分支的媒体整合提交；历史需求基线为 `6e1a7f3`。

本文件记录 A（媒体文件、状态与 HTTP）、B（ASR/OCR）和前端之间的产品约束、当前可依赖行为和未完成收口项。可调用的 HTTP 形状以 [正式 API 合同](../API.md) 和 [`contracts/api.ts`](../../contracts/api.ts) 为准；本文件中的“待收口”不能被前端当成已实现能力。

## 1. 状态分栏

### 已确认的产品决策

- 文件请求使用 `multipart/form-data`；不得把媒体正文塞进现有 JSON Event 接口。
- 识别使用异步语义：启动返回 `202 Accepted`，前端通过媒体详情查询结果。
- 不设置面向用户的固定文件大小、录音时长或图片像素限制；尤其不得恢复 60 秒录音限制，也不得偷偷截断原件。
- 系统仍必须有公开、可配置、实测的字节和资源保护边界。边界没有配置时，媒体写入口保持禁用，不使用隐藏默认值。
- 暂停和续录产生的音频片段由后端按顺序接收并合并为一个完整原件；不得丢失前段，也不得默认为多条 Event。
- 识别成功但 Event 关联失败时，保留原件和完整机器初稿，状态为“待关联”；恢复关联不得再次调用识别供应商。
- 超过现有 Event `raw_text` 10000 字符上限时，完整初稿仍然保存，不截断、不创建假成功 Event。
- 继续使用本机单人 session，不把本轮接口描述成公网、多家庭或正式医疗系统。
- 允许显式 Mock 作为离线备用；响应和页面必须显示 `is_mock: true`，不得冒充真实识别。

### 当前已实现

- 默认本地后端已连接媒体文件存储、SQLite 状态、B 的 `recognize_file(...)` 接缝和有限工作线程。
- 已实现元数据创建、分片上传、原件发布、媒体列表/详情、原件读取、识别启动、识别状态持久化和已保存文字的 `/link` 恢复入口。
- 原件、识别尝试、完整识别文字、危险扫描结果和媒体 Event 关联均可持久化；交接快照支持媒体附件字段。
- B 的离线测试覆盖显式 Mock、原件只读、格式校验、资源边界和供应商失败分类。

### 当前仍未验证或需要后续增强

- `/api/media/capabilities` 已实现；缺少任一合法保护边界时媒体写入口返回 `503 media_limits_not_configured`。
- 完成上传的幂等键已持久化并做跨请求冲突校验；相同键必须对应同一上传和同一最终摘要。
- `/api/media/{media_id}/link` 已支持可选 `expected_version`；提供时会校验版本，过期返回 `409 stale_version`。
- 带 household 的交接查询已包含该 household 的全部媒体，不会按 `save_status` 筛掉失败、处理中或上传中的附件。
- 当前上传和原件读取由 HTTP 层整体读入内存，严格流式传输仍未完成。
- 真实 ASR/OCR、真实浏览器播放、真实手机暂停续录合并，以及真实供应商/设备验收仍未验证。

### 尚待实测后填写的技术事实

- 能力端点使用 `MEDIA_UPLOAD_MAX_BYTES`、`MEDIA_UPLOAD_PART_MAX_BYTES`、`MEDIA_UPLOAD_MAX_PARTS` 三个正整数配置，并公开当前值。`MEDIA_REQUEST_MAX_BYTES` 仍可作为额外的 multipart 传输保护上限；这些都是资源保护边界，不是产品文件大小、录音时长或图片像素限制。
- 浏览器实际输出的音频容器与编码、多个暂停片段是否可无损合并，以及是否需要受控的转封装工具。
- 真实 ASR/OCR 的服务、模型、支持格式、供应商上限、费用、超时和数据保留范围。
- 真实浏览器是否需要特定 Range 播放行为，以及大文件的内存表现仍待实测；当前接口已提供 Range 读取，但前端仍应通过携带 session header 的 `fetch` 获取 Blob，不在 URL 中放 token。

这些事实未确认不妨碍本地 Mock 和状态机测试，但不能把当前默认的 128 MiB 请求保护值写成产品文件上限，也不能把真实能力写成已验证。

## 2. 模块接缝与责任

```text
前端上传片段
    → A 保存片段并完成原件
    → A 持久化媒体和识别尝试
    → B 只读完整原件并返回文字或分类失败
    → A 保存完整机器初稿
    → A 对同一份文字执行本地危险扫描
    → A 唯一创建并关联 Event，或保留为待关联
```

A 负责文件、数据库、任务占用、HTTP、危险扫描、Event 唯一关联、恢复和备份。B 不持有数据库对象、不创建 Event、不修改原件或 HTTP 响应。A 不重复实现 ASR/OCR 适配器。

B 的调用接缝冻结为：

```python
recognize_file(
    path,
    *,
    kind,
    content_type,
    attempt_id,
    provider=None,
    max_bytes=None,
)
```

成功至少返回 `text`、`provider`、`model`、`is_mock`、`attempt_id`。失败使用 `RecognitionError.code/message/retryable`。A 只传服务端已经保存的路径；路径、供应商原始正文和密钥不得进入公开响应。

Provider 由后端运行配置选择，普通前端请求不能任意指定。未配置真实服务返回 `provider_not_configured`，不得静默改用 Mock；演示 Mock 也必须由运行方显式配置。

## 3. 媒体对象

媒体对象的公共字段冻结如下。字段为 `null` 时表示尚未产生，不得用空字符串伪造完成。

```json
{
  "media_id": "media_...",
  "kind": "audio",
  "original_filename": "recording.webm",
  "content_type": "audio/webm",
  "size_bytes": 123456,
  "sha256": "64位小写十六进制",
  "saved_at": "2026-09-12T12:00:00Z",
  "save_status": "saved",
  "recognition_status": "not_started",
  "link_status": "not_linked",
  "link_pending_reason": "recognition_not_ready",
  "record_id": null,
  "version": 2,
  "actor_name": "老人",
  "occurred_time": null,
  "latest_attempt": null,
  "local_safety": null,
  "created_at": "2026-09-12T12:00:00Z",
  "updated_at": "2026-09-12T12:00:00Z"
}
```

约束：

- `kind` 只能是 `audio | image`。
- `original_filename` 只用于展示，去除客户端路径后保存；实际目录和文件名只由服务端 ID 生成。
- `content_type` 是后端验证后的最终类型，不盲信 multipart 声明。
- 原件完成后不可修改；`size_bytes`、`sha256`、`saved_at` 和存储相对引用必须一起持久化。
- 公共对象不返回磁盘相对引用或绝对路径。
- `actor_name` 在创建上传时必填，非空且最多 80 字符。`occurred_time` 可为字符串或 `null`；后端不得从 OCR 日期或模型输出推断发生时间。
- Event 来源由后端映射：`audio → audio_transcript`，`image → document`；客户端不能覆盖该映射。

### 状态

```text
save_status:          uploading | saved | failed
recognition_status: not_started | processing | succeeded | failed | interrupted
link_status:        not_linked | pending | linked
```

- `saved` 只表示完整原件和元数据都已持久化。
- `succeeded` 只表示完整机器文字已经持久化，不表示 Event 已生成或人工已核对。
- `linked` 必须同时有唯一 `record_id`。
- `pending` 表示已有可恢复的信息但 Event 尚未建立；`link_pending_reason` 使用稳定码，例如 `raw_text_too_long`、`event_validation_failed` 或 `event_link_interrupted`。
- 没有可用文字时保持 `not_linked`，不得创建空 Event，也不得声称已完成文字危险扫描。
- 进程启动恢复时，遗留 `processing` 必须转为 `interrupted`；是否再次调用可能计费的供应商由用户显式重试决定。

### 识别尝试

媒体详情包含有界的 `attempts` 列表；每项至少为：

```json
{
  "attempt_id": "attempt_...",
  "status": "succeeded",
  "provider": "mock",
  "model": "mock-recognition-v1",
  "is_mock": true,
  "text": "完整机器初稿",
  "error": null,
  "started_at": "2026-09-12T12:01:00Z",
  "finished_at": "2026-09-12T12:01:01Z"
}
```

失败时 `text` 为 `null`，`error` 为 `{code, message, retryable}`；成功时 `error` 为 `null`。机器初稿不可被人工修订覆盖。详情默认返回完整初稿；列表不返回全文。

## 4. 系统能力与保护边界

### `GET /api/media/capabilities`

已实现，返回当前运行实例公开能力，不需要上传文件：

```json
{
  "ok": true,
  "capabilities": {
    "enabled": false,
    "disabled_reason": "media_limits_not_configured",
    "max_total_bytes": null,
    "max_part_bytes": null,
    "max_parts": null,
    "max_audio_duration_seconds": null,
    "max_image_pixels": null,
    "audio_content_types": [],
    "image_content_types": [],
    "multipart_upload": true,
    "resumable_parts": true
  }
}
```

运行配置使用正整数 `MEDIA_UPLOAD_MAX_BYTES`、`MEDIA_UPLOAD_PART_MAX_BYTES`、`MEDIA_UPLOAD_MAX_PARTS`，响应公布实际值。任一未配置或非法时返回 `enabled=false`，媒体写请求返回 `503 media_limits_not_configured`。这些边界不是产品时长或像素限制：两者保持 `null`。上传和读取仍由 HTTP 层整体读入内存，严格流式处理属于后续增强。

## 5. 上传与后端合并

### `POST /api/media/uploads`

当前实现先创建上传元数据，不在此请求中携带文件。请求必须带 `Idempotency-Key`、`X-Session-Token` 和 `multipart/form-data`：

| 字段 | 规则 |
|---|---|
| `kind` | `audio` 或 `image` |
| `content_type` | 与 `kind` 匹配的预期 MIME；最终类型仍由后端校验 |
| `total_parts` | 正整数；后续片段索引为 `0..total_parts-1` |
| `original_filename` | 可选展示名；不参与路径生成 |
| `expected_size` | 可选正整数 |
| `expected_sha256` | 可选 64 位十六进制摘要 |
| `actor_name` | 可选；省略为“老人”，最多 80 字符 |
| `occurred_time` | 可选字符串或 `null`；不提供时保持未知 |

当前 HTTP 入口只接受上表字段。首次成功返回 `201`，其中 `upload.status="uploading"`、媒体 `save_status="uploading"`。这时只能显示“正在上传”，不能显示“原件已保存”。同一幂等键和相同元数据重放返回 `200` 及原上传对象；同键变更元数据返回 `409 idempotency_key_payload_mismatch`。文件内容不在此步骤发送。

### `POST /api/media/uploads/{upload_id}/parts/{index}`

按顺序上传片段。请求必须带新的 `Idempotency-Key`、`X-Session-Token` 和 multipart `file`；`file` 是唯一文件字段，不能夹带其他文本字段。`index` 从 `0` 开始，必须小于创建上传时声明的 `total_parts`。图片也使用同一分片接口；单片图片的索引为 `0`。

首次保存片段返回 `201`；相同片段重放返回 `200`；同一索引内容变化或同一幂等键用于不同请求返回 `409`。部分上传不得改写已完成原件。当前实现会持久化分片摘要和幂等键；正式的单片字节、累计字节和片段数能力发现仍待收口。

### `POST /api/media/uploads/{upload_id}/complete`

当前实现路由参数为 `upload_id`，请求是小型 JSON 空对象 `{}`，不含文件正文，也不接受 `expected_version` 或 `part_count`：

```json
{}
```

必须带 `Idempotency-Key` 和 `X-Session-Token`。A 检查创建时声明的 `0..total_parts-1` 均存在并按序合并，验证最终类型，计算最终大小和 SHA-256，把完整原件与元数据一起提交。首次成功返回 `201 {ok:true,created:true,media}`；只有响应中 `media.save_status="saved"` 才能显示“原件已保存”。

完成步骤的幂等键已写入 SQLite 的完成幂等记录，并按上传 ID和最终摘要校验冲突；同一完成请求重放返回 `200`，同键用于另一上传或不同最终摘要返回 `409 idempotency_key_payload_mismatch`。缺片返回 `409 upload_incomplete`；不支持的最终格式、摘要或存储失败必须保留可解释的上传状态，不得返回“已保存”。

“后端合并”是行为要求，不代表允许直接拼接任意容器字节。A 必须先用浏览器真实输出确认合并策略；需要转封装时由集成人审阅依赖、资源和许可后再启用。

## 6. 查询与读取原件

| 路由 | 成功语义 |
|---|---|
| `GET /api/media` | `200 {ok:true, media:[...]}`；包括未生成 Event、处理中和失败项；列表不含完整文字或磁盘路径 |
| `GET /api/media/{media_id}` | `200 {ok:true, media}`；媒体详情中包含 `attempts`，用于轮询识别和恢复关联 |
| `GET /api/media/{media_id}/original` | 携带 session header 后返回验证过的原件字节与正确 `Content-Type` |

列表采用有界查询；首版可固定服务端最大返回量，分页形状在实现正式同步 `docs/API.md` 前确定。未知 ID 返回 `404 media_not_found`。

原件读取只接受 `media_id`，不得接受客户端路径、跟随符号链接或返回存储路径。MVP 前端使用携带 `X-Session-Token` 的 `fetch` 获取 Blob，再生成页面内对象 URL；不得把 token 放入 URL。当前 HTTP 读取会整体读入内存，流式读取仍未完成。若磁盘内容缺失或 SHA-256 不符，返回稳定错误并记录审计，不提供被替换的内容。

## 7. 启动识别与轮询

### `POST /api/media/{media_id}/recognize`

请求：

```json
{"expected_version": 3}
```

必须带 `Idempotency-Key` 和 `X-Session-Token`。只有 `save_status=saved` 才能启动。首次占用成功返回：

```json
{
  "ok": true,
  "accepted": true,
  "attempt_id": "attempt_...",
  "media": {
    "media_id": "media_...",
    "recognition_status": "processing",
    "version": 4
  }
}
```

状态码和重放规则：

- 新任务：`202`。
- 同一请求重放或已有任务处理中：返回同一 `attempt_id`，不再调用供应商；处理中仍为 `202`。
- 已成功：`200` 返回现有成功结果，不重新识别、不重复创建 Event。
- 失败或 `interrupted`：只有新的幂等键和当前 `expected_version` 才创建下一次尝试；不可重试失败返回 `409 recognition_not_retryable`。
- 同键改变请求或版本过期：`409`。

后端只使用有限工作线程，不在 HTTP handler 内长期阻塞；本轮不引入外部队列。第三方调用不承诺 exactly-once，未知结果必须如实转为 `interrupted`，不能无限自动重试。

B 的稳定错误码为：`provider_not_configured`、`unsupported_format`、`invalid_media`、`limit_exceeded`、`no_text_detected`、`provider_timeout`、`provider_unavailable`、`provider_auth_failed`、`provider_rate_limited`、`invalid_provider_response`。A 只保存安全消息，不透传供应商正文。

## 8. 危险扫描和 Event 关联

识别成功后的顺序不可交换：

```text
完整机器初稿落库
    → 对这份完整初稿执行现有本地危险扫描并落库
    → 唯一创建 Event 与媒体关联
```

Event 创建使用上传时保存的 `actor_name` 和 `occurred_time`；`recorded_at` 由服务器生成。不得从照片日期、模型推测或供应商元数据补写发生时间。识别成功不把 Event 自动标记为 `recorded`，仍走既有整理、核对和修订流程。

关联失败不回滚初稿和危险提醒：媒体变为 `link_status=pending` 并保存安全的 `link_pending_reason`。危险命中在后续核对、修订来源和交接中保持可见；未命中只代表有限规则未命中，不代表医学正常。

### `POST /api/media/{media_id}/link`

用于复用已保存成功初稿恢复 Event 关联，不调用 B：

```json
{"actor_name":"老人"}
```

请求带新的 `Idempotency-Key` 和正整数 `expected_version`；后端校验媒体当前版本，版本过期返回 `409 stale_version`。首次关联成功返回 `201 {ok:true, linked:true, event_created:true, media, event}`；相同媒体已经关联时返回现有 Event，状态为 `200`。该入口复用已经保存的成功初稿，不再次调用识别。超过 10000 字符返回可恢复的待关联状态，媒体保持 `pending` 且全文可查；本轮不擅自增加自动分段或截取功能。

数据库必须约束一个媒体只能生成一个初始 Event。迟到识别结果不能覆盖更晚尝试、已保存初稿、Event 或人工修订。

## 9. 交接快照、备份和恢复

交接快照在既有 Event 条目之外增加媒体附件信息：至少包含 `media_id`、`kind`、原件保存状态、识别状态、Mock 标识、`link_status`、`record_id`、`pending_reason`、是否有文字、危险扫描结果和未解决原因。没有文字的失败媒体可以显示为“原件已保存、尚无可用文字”，不得伪造摘要；上传中或尚未保存的媒体也不得被误写成原件已保存。无 household 和带 household 的交接路径都会保留对应范围内的失败、处理中和上传中媒体。快照生成后保持不可变。

备份必须把 SQLite 一致快照、全部被引用原件、必要片段状态和校验清单放在同一恢复包中。恢复到空目录后验证数据库、SHA-256、媒体详情、原件读取、初稿、危险状态、Event 链接和旧文本记录；缺失或损坏文件必须被发现。仅复制数据库不算媒体备份完成。

## 10. HTTP 与安全规则

- 所有媒体写请求和读取原件沿用当前 `X-Session-Token`；本机服务重启后重新从 `/health` 获取。不得宣称已有公网用户隔离。
- 文件上传的 CORS 预检需允许 `Content-Type`、`Idempotency-Key`、`X-Session-Token`；只对明确配置的 Origin 返回许可。
- 所有媒体写请求使用 `Idempotency-Key`；识别启动和可选的 `/link` 版本保护使用正整数 `expected_version`。完成上传的键和冲突校验已持久化；同键不同请求使用稳定错误码 `idempotency_key_payload_mismatch` 或对应上传冲突码，过期版本返回 `409 stale_version`。
- 不信任文件名、扩展名或声明 MIME；不跟随符号链接，不允许路径穿越，不向前端返回异常正文、密钥或路径。
- 未预期异常统一返回 `{ "ok": false, "error": "internal_server_error" }`；原件未持久化时不能显示成功。
- Mock、真实服务、未配置三种状态必须可区分；Mock 不得由真实服务失败自动触发。

通用错误响应为：

```json
{"ok": false, "error": "stable_error_code", "message": "可公开说明", "retryable": false}
```

`message` 可选，前端流程依据稳定 `error`，不依据内部异常类型。

## 11. 实现验收门槛

- [x] 能力端点公开实际系统边界；未配置时写入口关闭。
- [x] 分片重放不重复、同键变内容 409；缺片、写盘失败、数据库失败不产生假成功。
- [ ] 暂停续录真实文件合并后前后内容均在，且最终文件可播放、可识别。
- [x] 列表和详情可恢复未关联、处理中、失败和中断媒体；交接查询保留失败媒体。
- [x] 新识别启动 202，处理中重放仍为 202，已成功重放为 200 并复用尝试；重启后无永久 `processing`。
- [x] 识别失败保留原件；成功先保存全文并扫描，再唯一关联 Event。
- [x] 超长全文不截断；关联恢复不再次调用 B；成功重放不创建第二个 Event。
- [x] 危险提醒不因核对或修订来源而消失；无文字时不声称已扫描。
- [ ] 原件读取无路径/凭据泄露；上传和读取改为流式；目标浏览器 Blob 播放通过。
- [ ] 数据库与原件一致备份并在空目录恢复；缺失和损坏被发现。
- [x] 已同步 `docs/API.md`、`contracts/api.ts` 和前端说明；真实供应商、浏览器和手机证据仍未完成。
