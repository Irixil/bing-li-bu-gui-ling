# B4：A 真实浏览器联调手册

本手册用于 A 在不阅读后端源码的情况下，将老人端页面接入 `fix/backend-api` 分支的固定 HTTP 接口。完整字段以 [API.md](API.md) 和 [TypeScript 合同](../contracts/api.ts) 为准。本文是可执行的联调步骤，**不代表真实浏览器已验收**。

## 1. 启动固定后端

在仓库根目录执行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
API_PORT=18768 DB_PATH=runtime/records.sqlite3 MODEL_PROVIDER=mock python -m backend.run_local
```

启动后访问 `http://127.0.0.1:18768/health`，必须看到 `ok:true`、`provider:"mock"`、`mode:"local_single_household"` 和 `session_token`。`mock` 不需要密钥，也不是真实大模型。

前端启动和每次后端重启后，都先请求 `GET /health`，只在内存中保存新的 `session_token`。不要写死、打印或提交 token。所有写请求带：

```text
Content-Type: application/json
X-Session-Token: <本次 /health 返回的 session_token>
```

只有 `POST /api/events` 额外带 `Idempotency-Key`。

## 2. 选择前后端连接方式

### 方式 A：开发代理（优先）

前端只请求相对路径 `/health` 和 `/api/...`，开发服务器将这两类路径转发到 `http://127.0.0.1:18768`。浏览器看到的始终是前端同源地址。后端收到的 `Origin` 为空可直接通过；如果代理保留 `Origin`，它必须等于显式配置的 `ALLOWED_ORIGIN`，或在未配置时等于代理转发的 `http://Host`。使用代理的默认行为就能满足时不要额外改写；出现 `403` 再检查转发后的 `Origin`/`Host`，或按下面的直连方式设置 `ALLOWED_ORIGIN`。

### 方式 B：浏览器直连后端

假设前端页面是 `http://localhost:5173`，停止后端后重新启动：

```bash
API_PORT=18768 DB_PATH=runtime/records.sqlite3 MODEL_PROVIDER=mock ALLOWED_ORIGIN=http://localhost:5173 python -m backend.run_local
```

前端 API Base URL 使用 `http://127.0.0.1:18768`。`ALLOWED_ORIGIN` 必须与浏览器地址栏的 `scheme://host:port` **完全一致**，不带末尾斜杠；`localhost` 与 `127.0.0.1` 不是同一 Origin。预检应返回 `204`，允许 `GET, POST, OPTIONS` 及 `Content-Type, Idempotency-Key, X-Session-Token, X-Auth-Token`。写请求返回 `403 csrf_or_origin_rejected` 时，先核对 Origin 和 token，不要当成数据丢失。

## 3. 前端最小请求规则

- 先解析 JSON，再根据 HTTP 状态处理；否则会丢掉 `422` 中的已保存原文和安全提醒。
- 页面中始终以最新响应的 `event.record_id`、`event.state` 和 `event.version` 为准。
- `organize`、`review`、`revise` 都传当前正整数 `expected_version`；不允许前端猜“最新版本”。
- `local_safety.danger_detected=false` 只表示本地规则未命中，页面不得显示“正常”或“无危险”。

## 4. 浏览器主闭环

### 4.1 保存后立即显示“已保存”

每次用户主动创建新记录时生成一个新的 `crypto.randomUUID()`：

```http
POST /api/events
Idempotency-Key: <crypto.randomUUID()>

{"raw_text":"今天散步二十分钟","source_kind":"elder","actor_name":"老人"}
```

首次成功是 `201`、`created:true`、`event.state:"inbox"`、`event.version:1`。收到该响应就显示“已保存”和原文，**不等整理请求**。只有保存成功才能显示该文案；`400/403/409/500` 不能显示“已保存”。

如保存请求超时或网络中断，自动/手动重试必须复用**原幂等键和完全相同的请求体**；返回 `200`、`created:false` 且 `record_id` 不变即为成功。同键换请求体会返回 `409 idempotency_key_payload_mismatch`。用户真正新建另一条时必须换新键，即使原文相同也不合并。

### 4.2 整理、核对、历史、修订、交接

1. `POST /api/events/{record_id}/organize`，请求体 `{"expected_version":1}`。`200` 后记录进入 `draft`、版本变为 2，显示整理结果仍待人工核对。
2. `POST /api/events/{record_id}/review`，请求体 `{"expected_version":2,"action":"confirm","note":"仅确认记录准确"}`。`200` 后进入 `recorded`、版本变为 3。核对只表示记录准确，不清除危险状态。退回时使用 `action:"return"` 并提供非空 `note`。
3. `GET /api/events/{record_id}` 读详情；`GET /api/events/{record_id}/history` 读 `history` 和 `audit`。
4. `POST /api/events/{record_id}/revise`，请求体：

   ```json
   {"expected_version":3,"raw_text":"修订：今天散步时没有头晕","source_kind":"elder","actor_name":"老人","reason":"更正刚才的输入"}
   ```

   `201` 返回新 `record_id`、`state:"inbox"`、`version:1`、`supersedes_id:旧 ID`。旧记录变为 `superseded`，但旧原文仍能查到；之后整理/核对使用新 ID。
5. `POST /api/handoffs`，请求体 `{}`，`201` 返回 `handoff`。随后用 `GET /api/handoffs/{handoff_id}` 重读。这是生成时快照；后续修订不会回写旧快照，需要最新内容就重新生成。

主列表用 `GET /api/events`。列表会包含 `superseded` 记录；页面可在主列表隐藏，但历史入口必须保留。

## 5. 必测异常路径

### 5.1 用现有未配置真实 Provider 稳定复现 `422`

不改 `.env`。停止正常后端，从仓库根目录以下命令启动：

```bash
API_PORT=18768 DB_PATH=runtime/records.sqlite3 MODEL_PROVIDER=modelscope MODELSCOPE_ACCESS_TOKEN='' MODELSCOPE_TOKEN='' MODELSCOPE_MODEL='' python -m backend.run_local
```

1. 重新 `GET /health`，确认 `provider:"modelscope"`，并替换内存中的 token。
2. 新建危险原文“今天胸口疼，喘不上气”。保存仍应 `201`，页面立即显示原文和顶部固定 `danger_reminder`。
3. 以该记录的 `version:1` 请求 `organize`。因现有 ModelScope 适配器缺少必需配置，稳定返回 `422`。
4. 页面必须显示“原文已保存，AI 整理失败”、原文、`failure_reason`、顶部危险提醒和重试入口；不得显示整理成功或空白卡片。

联调断言至少包含：`ok:false`、`error:"ai_organize_failed"`、`ai_failed:true`、`raw_text_preserved:true`、`event.raw_text` 不变、`event.state:"inbox"`、`event.version:1`、`local_safety.danger_detected:true`、`danger_detected:true`、`danger_reminder` 非空。这只验证失败契约，不是真实模型成功或网络故障证据。

验证完后停止该进程，用第 1 节的 `MODEL_PROVIDER=mock` 命令恢复，然后重新取 token。

### 5.2 用两个页签稳定复现 `409 stale_version`

1. 两个浏览器页签打开同一条 `version:1` 记录，都保留该版本。
2. 页签 A 以 `expected_version:1` 整理成功，服务器记录进入 `version:2`。
3. 页签 B 仍以 `expected_version:1` 请求整理，必须得到 `409 {"ok":false,"error":"stale_version"}`。
4. 页签 B 收到 `stale_version` 后立即 `GET /api/events/{record_id}`，显示最新版本，让用户选择重载或修订；不得静默重试或覆盖。

## 6. 后端重启与数据恢复

1. 记下一条已保存记录的 `record_id` 和已生成的 `handoff_id`。
2. 用 `Ctrl-C` 停止后端，再以相同 `DB_PATH=runtime/records.sqlite3` 启动；不要删除或替换数据库。
3. 前端重新 `GET /health`，用新 token 替换旧 token。旧 token 写请求应为 `403`。
4. 用 `GET /api/events/{record_id}`、`GET /api/events/{record_id}/history` 和 `GET /api/handoffs/{handoff_id}` 恢复原文、安全状态、历史与交接快照。
5. 页面必须把 `403` 解释为会话/Origin 问题并先刷新 token，不能误报记录丢失。

## 7. A 必须交回的验收证据

所有证据绑定 A 的提交号、B 后端提交号、操作系统、浏览器及版本、前端 Origin、连接方式（代理/直连）和 `/health.provider`。不得附带 token、`.env` 或密钥。

- 一段连续录屏或有顺序截图：保存响应后立即显示“已保存” → 整理 → 核对 → 详情/历史 → 修订新旧可追溯 → 生成并重读交接快照。
- 危险输入在保存后、`422` 后和核对后都保留顶部固定提醒的页面证据。
- 浏览器 Network 证据：保存 `201 created:true`、同请求同键重试 `200 created:false`、`422 ai_organize_failed`、`409 stale_version`，以及对应页面处理；响应体可留字段，请求头中的 token 必须打码。
- 后端重启前后的同一 `record_id`/`handoff_id` 查询证据，以及前端重取 token 后恢复写入的证据；不展示 token 值。
- 任何失败都提供：操作步骤、端点、输入（脱敏）、期望、实际、HTTP 状态/错误码和可重现性；不直接改数据库来“修复”联调。

B 只能在收到上述真实浏览器证据后，将 B4 从“B 侧准备完成”改为“联调验收完成”。

## 8. 明确限制

- 服务只监听 `127.0.0.1`，面向本地单老人/单家庭演示；不是可直接公网发布的多用户医疗系统。
- 账号兼容接口不属于老人端必接范围；本手册不证明正式身份认证、家庭隔离、限流或安全审计。
- `mock` 只是离线规则式演示；缺少 ModelScope 配置的 `422` 只证明失败保底。真实模型成功、超时、输出质量和备用切换仍需 C/E 另行验证。
- 危险规则是有限关键词规则，可能误报或漏报；本产品不诊断、不自动改药、不用核对消除风险。
- 交接材料是 SQLite 中的快照 JSON，当前不直接生成 PDF 或真实分享链接。
- 浏览器页面、可用性、真实老人/医生试用和临床安全均不在后端自动测试的证明范围内。
