# AIHubMix 媒体接入离线证据（2026-09-15）

> 历史快照：本文记录当日 Whisper 适配的离线证据。2026-09-16 确认当前 Key 的可用模型列表不含 Whisper，已改为更低价且实测通过的 `gemini-2.5-flash-lite`；当前结果见 [真实合成语音报告](real-aihubmix-gemini-audio-2026-09-16.md)。

## 结论

当前工作树已实现 AIHubMix 一把 Key 的媒体接入：保留现有 DeepSeek 文字整理，语音转写固定走 AIHubMix 官方 `/v1/audio/transcriptions`，图片识字固定走官方 `/v1/chat/completions`。默认模型分别为 `whisper-large-v3` 和 `qwen3.7-flash`。

本证据没有调用外部 AI 服务，没有产生 API 费用，也没有读取、记录或输出真实密钥。它证明本地接线、请求格式、安全边界和现有项目回归通过；不证明账号权限、模型实时可用性或真实识别质量。

## 已执行检查

- 配置检查：使用无效占位值模拟 `AIHUBMIX_API_KEY`，文字、ASR、OCR 和本地服务四部分均通过字段检查；该步骤不发送网络请求。
- 专项回归：`76 passed`，覆盖单 Key 默认配置、固定官方地址、旧供应商 Key 不串用、模型覆盖、中文 ASR 参数、图片高细节输入和 25MB 音频上限。
- 全量回归：`744 passed in 69.67s`。
- 补丁检查：通过，无空白错误。
- 本地 `.env`：保持 Git 忽略且权限为 `0600`；已写入空的 `AIHUBMIX_API_KEY` 配置槽，未写入密钥值。

## 仍需真实验证

在本地 `.env` 的 `AIHUBMIX_API_KEY=` 后填入用户自己的有效 Key，再运行在线配置检查和仓库合成 WAV/PNG 的完整 HTTP 自测。只有同一轮语音、图片和文字链路均通过，才可声称 AIHubMix 在线 Demo 跑通。真实患者资料和复杂医学影像不用于首次测试。
