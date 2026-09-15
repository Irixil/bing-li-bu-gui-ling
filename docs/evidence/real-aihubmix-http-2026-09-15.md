# AIHubMix 真实合成媒体 HTTP 自测（2026-09-15）

## 结论

同一轮真实 HTTP 自测未全部通过：134 项检查中 133 项通过、1 项失败。测试按授权只执行一轮，没有自动重试或更换模型。

- 文字整理：DeepSeek 真实接口通过。
- 图片识字：AIHubMix `qwen3.7-flash` 真实接口通过，合成图片中的“胸口疼”和“喘不上气”两个预期关键词均命中。
- 语音转写：AIHubMix `whisper-large-v3` 返回 `provider_auth_failed`。同一 AIHubMix Key 的图片请求已成功，因此本地 Key 读取和 AIHubMix 基础鉴权已确认；剩余优先排查该 Key 的模型权限、账户余额或付费通道权限。

本次只发送仓库明确标记的合成资料，没有发送真实患者资料。报告、日志和项目记录均未保存或输出密钥及供应商原始错误正文。

## 测试对象

- 分支：`codex/backend-integration-2026-09-14`
- 接入提交：`01d503b`
- 本地服务：隔离数据库与媒体目录，端口 `18769`，测试后已停止
- 合成音频：`data/synthetic/selftest/voice.wav`，SHA-256 `8418ad10070a018ad1829261a26bcf3010f7a73454c56404a91b637002ed979f`
- 合成图片：`data/synthetic/selftest/card.png`，SHA-256 `d72736a8bc57898ea1de1b358f5430d65fbe37e25108420bf70e5e02704e540a`

## 可核对事实

- 配置检查四部分均通过，`.env` 权限保持 `0600`。
- 图片原件在识别前后字节哈希一致；OCR provider 为 `aihubmix`，model 为 `qwen3.7-flash`，`is_mock=false`。
- 音频原件在失败前后字节哈希一致；安全错误为 `provider_auth_failed`，没有把失败伪装成成功。
- 文字保存、整理、核对、修订、历史、交接卡，以及图片上传、分片、幂等、识别、关联、整理和交接均通过。

## 下一步

在 AIHubMix 控制台核对当前 Key 是否允许 `whisper-large-v3`，并确认账户有余额且没有 IP 或模型白名单限制。修正后只复测一次仓库合成语音；WAV 通过后，再进行浏览器 WebM 录音实测。
