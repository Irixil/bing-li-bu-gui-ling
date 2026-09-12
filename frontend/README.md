# 老人端前端交接

这里由项目负责人开发。可以使用 React/Vite，也可以用其他熟悉的前端方案；后端不要求特定框架。

语音／照片后端已接入本地文件存储、SQLite 状态和 B 的识别模块。当前 HTTP 接线形状已经同步到 [正式 API 合同](../docs/API.md) 和 `contracts/api.ts`；真实 ASR/OCR、浏览器或手机验收仍未完成。默认无额外配置时是明确标注的离线 Mock 演示模式。

录音已确认：长时间没有声音先提醒，提醒后仍无回应再自动暂停，保留已录内容并可接着说。静音时长、提醒后等待时长和检测方法待真机验证小声、停顿、电视噪声；60 秒强制结束要求已撤回。自动暂停不等于上传成功或记录已核对。前端与 A 对齐暂停续录的文件交接，不能丢弃前段内容。

## 现有文字底座接线清单

1. 一个大字号输入框和“保存记录”按钮。
2. 保存成功后显示原文和“已保存”，并显示本地危险状态。
3. 一键“整理记录”，展示来源、时间不确定性、待核对状态。
4. “我核对过记录准确”按钮；文案写核对记录，不写医生确认。
5. 历史列表和修订入口，能看到旧版本仍在。
6. “生成就诊交接材料”页面。
7. AI 失败状态：原文保留、危险提醒保留、可重试。

## 接线约定

开发服务器把 `/api` 和 `/health` 代理到 `http://127.0.0.1:18768`。Vite 等代理设置 `changeOrigin:false`；在后端 `.env` 设置实际开发页的 `ALLOWED_ORIGIN=http://localhost:5173`，然后重启后端。浏览器改用 127.0.0.1 或另一个端口时，此值也要一致。构建放进后端同源服务后不用此设置。

JSON 写请求带 `Content-Type: application/json` 和 `X-Session-Token`；创建文字记录需要 `Idempotency-Key`。token 从 `/health` 的 `session_token` 读取，服务重启后重新获取，不要写死进代码。

保存成功后立刻更新界面。整理接口返回 `422` 时仍是可用状态，使用响应里的 `event` 和 `local_safety`，不要清空刚才的输入。具体字段和示例见 `docs/API.md` 与 `contracts/api.ts`。

## 媒体接线最短流程

1. 用 `multipart/form-data` 调 `POST /api/media/uploads` 创建元数据；这里只传 `kind`、`content_type`、`total_parts` 和可选校验字段，**不传文件**。
2. 把完整媒体按顺序作为 `file` 上传到 `/api/media/uploads/{upload_id}/parts/0..N-1`。每一步使用自己的幂等键；同一步重试复用原键和原内容。
3. 用 JSON 空对象 `{}` 调 `/api/media/uploads/{upload_id}/complete`。只有返回的 `media.save_status` 为 `saved` 才显示“原件已保存”。
4. 用当前 `version` 调 `/api/media/{media_id}/recognize`。收到 `202` 后显示“识别处理中”，通过 `GET /api/media/{media_id}` 轮询；不要把 `202` 当识别成功。
5. 原件用带 `X-Session-Token` 的 `fetch` 请求 `/api/media/{media_id}/original`，再创建 Blob URL；不要把 token 放在 URL。服务端已提供 Range 形状，但浏览器和手机播放仍需实测。

前端展示状态使用 `save_status`、`recognition_status` 和 `link_status`，不要沿用早期草案的 `upload_status`。如果详情中的 `recognition.is_mock === true`，必须清楚显示“离线 Mock 演示模式”；它不能标成真实识别。识别失败时继续展示原件入口和错误状态，不能让该条媒体从列表消失。

启动媒体流程前可先读取 `/api/media/capabilities`。只有 `enabled: true` 才展示上传入口；若能力返回 `disabled_reason: "media_limits_not_configured"`，显示“当前实例未配置媒体资源保护边界”，不要自行填入默认值。可用 `/api/media/{media_id}/link` 复用已经保存的成功初稿恢复关联，不能因此重新调用识别；请求必须带当前 `expected_version`。默认服务已经组装媒体后端；若返回 `media_backend_unavailable`，应显示明确错误，不要静默切换 Mock。

## 前端验收

- 断网或模拟失败：显示“原文已保存，AI 整理失败”，原文可查询。
- “胸口疼，喘不上气”：顶部显示固定急救提醒，不能被核对按钮隐藏。
- 普通输入：不误报危险，不显示“医学正常”。
- 刷新页面：从 GET 接口恢复记录和版本。
- 文字足够大，按钮有清楚的成功、失败和处理中状态。
- 媒体上传：创建元数据、分片、完成三个阶段分别显示；完成前不显示“已保存”。
- 识别启动：`202` 后可轮询；Mock 有显眼标识，失败后原件仍可进入。

媒体验收还欠真实浏览器、手机录音格式、暂停续录文件合并和真实 ASR/OCR。完成这些实测前，不要在演示文案里写“真实识别已通过”。

旧 HTML 只作为视觉参考，不要复制多套入口。若将构建产物放进 `frontend/dist`，后端会安全地提供静态文件；开发时用代理即可。
