# B 任务交接：语音转文字与照片识字

状态：识别模块与离线测试已完成；真实 ASR/OCR 成功证据尚未验证。媒体上传、数据库状态、Event 关联和 HTTP 合同仍由 A 收口。

## 本次交付

- `backend/recognition.py`：统一的 `recognize_file(...)` 识别接缝。
- `tests/test_recognition.py`：17 项离线行为测试，覆盖 Mock、格式／文件校验、原件不变、大小限制、供应商错误分类、空结果、非法响应、响应大小边界和安全文件名。
- `docs/evidence/media-b/README.md`：真实服务证据缺口和补证要求。

本模块不写数据库、不修改原件、不创建 Event、不启动 HTTP 处理器，也不调用现有文本整理 `backend/adapter.py`。

## 调用方式

```python
from backend.recognition import RecognitionError, recognize_file

try:
    result = recognize_file(
        saved_path,
        kind="audio",              # "audio" 或 "image"
        content_type="audio/wav", # 服务端持久化时确认的 MIME
        attempt_id="attempt_...",  # A 生成并持久化的尝试 ID
        provider="mock",           # 仅演示时显式选择
        max_bytes=contract_limit,   # 合同冻结后由 A 传入；不传则不偷偷猜上限
    )
except RecognitionError as error:
    failure = {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
    }
```

成功结果至少包含：

```json
{
  "text": "机器识别原文",
  "provider": "openai_compatible",
  "model": "服务端配置的模型名",
  "is_mock": false,
  "attempt_id": "attempt_..."
}
```

成功只表示识别文字已产生，不表示文字已经核对，也不表示已经创建 Event。A 应先保存完整机器初稿，再把同一份文字交给既有危险词扫描；不能因为识别成功就自动标记 `recorded`、诊断或改药。

## Provider 与配置

当前实现提供两种显式模式：

| 模式 | 选择方式 | 结果含义 |
|---|---|---|
| Mock | 调用时传 `provider="mock"` | `is_mock: true`，只用于离线接线，不代表真实识别质量 |
| OpenAI-compatible | `provider="openai_compatible"` | 需要分别配置 ASR/OCR 的 URL、模型和密钥；未配置返回 `provider_not_configured`，不会回退 Mock |

真实模式的配置变量名称：

- 音频：`MEDIA_ASR_URL`、`MEDIA_ASR_MODEL`、`MEDIA_ASR_API_KEY`
- 图片：`MEDIA_OCR_URL`、`MEDIA_OCR_MODEL`、`MEDIA_OCR_API_KEY`
- 可选：`MEDIA_RECOGNITION_API_KEY` 作为两者的共同密钥；`MEDIA_RECOGNITION_TIMEOUT_SECONDS`；`MEDIA_RECOGNITION_MAX_RESPONSE_BYTES`

密钥只存在运行环境的 `.env` 或密钥管理器中，不进 Git、日志、测试报告或响应消息。当前仓库没有新增运行依赖；模块使用 Python 3.12 标准库。

OpenAI-compatible 适配器约定：音频向配置的 URL 发 multipart 请求，字段为 `model` 和 `file`；图片向配置的 URL 发 JSON，对图片使用 data URL，并要求模型逐字识别、不补写、不纠错、不推测。具体供应商是否支持这些形状、语言、格式、时长、费用和数据留存，必须由 A/C/E 在授权后单独实测，不得由本模块推断。

## 失败码

| 错误码 | 可重试 | 含义 |
|---|---:|---|
| `provider_not_configured` | 否 | 真实服务配置缺失或未选择 |
| `unsupported_format` | 否 | `kind` 与 MIME 不在当前识别支持集合 |
| `invalid_media` | 否 | 文件不存在、为空、损坏、符号链接或魔数与 MIME 不匹配 |
| `limit_exceeded` | 否 | A 传入的明确 `max_bytes` 被超过 |
| `no_text_detected` | 否 | 服务返回空文字 |
| `provider_timeout` | 是 | 请求超时或供应商返回 408/504 |
| `provider_unavailable` | 是 | 网络失败或供应商 5xx（504 单独归超时） |
| `provider_auth_failed` | 否 | 401/403 |
| `provider_rate_limited` | 是 | 429 |
| `invalid_provider_response` | 否 | 非 JSON、字段不符合约定或响应超过读取上限 |

公开错误消息不会包含供应商原始正文、密钥、请求头、绝对路径或完整文件名。模块不做自动重试；重试次数、尝试状态和幂等由 A 的任务接口管理。第三方调用是否收费、是否 exactly-once，当前均未承诺。

## 已验证与未验证

已验证：

- `uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q tests/test_recognition.py`：17 项通过。
- 音频和图片走同一个公开函数；Mock 与真实模式结果明确区分。
- 识别失败不会写原件；原件字节和文件修改时间在测试中保持不变。
- 供应商超时、网络不可用、鉴权、限流、非法响应和空文字都有稳定分类。
- 全仓库当前回归：`161 passed`；其中包含本轮媒体识别测试。

未验证：

- 没有合法的 ASR/OCR 服务凭据、授权样例或可公开的脱敏真实媒体，因此真实中文录音成功、清晰印刷照片成功、真实超时和真实失败均不能写成已完成。
- 具体服务的语言、编码、时长、大小、像素、费用、数据传输和保留策略尚未冻结。
- 未验证手写字、复杂版式、方言、噪声环境、静音检测和转码质量。

## A 接入顺序

1. A 先把上传原件安全保存，并为识别尝试生成 `attempt_id`。
2. A 调用 `recognize_file`，只传已保存原件的服务端路径、已经确认的 MIME、`kind` 和合同中的 `max_bytes`。
3. 成功时持久化完整 `text`、`provider`、`model`、`is_mock` 和 `attempt_id`，然后执行危险扫描；失败时持久化安全失败结构，保留原件。
4. 之后再按冻结媒体合同关联现有 Event；B 模块不创建 Event。若关联失败，保留识别文字并提供恢复入口，不重新收费请求识别。
5. 识别成功不等于人工核对；重试和重启恢复由 A 的状态机保证。不要在 URL 中放 token，也不要把供应商原始错误转给前端。

媒体端点仍以 `docs/team/MEDIA-CONTRACT.md` 的草案为起点，当前不能宣称已经实现。A 完成合同 PR 后，应把字段和状态同步到正式 `docs/API.md`、`contracts/api.ts` 和前端说明。
