# AIHubMix Gemini 真实合成语音验证（2026-09-16）

## 结论

当前分支的 AIHubMix 语音转写已使用 `gemini-2.5-flash-lite` 完成一次真实 HTTP 验证。请求成功，非 Mock，转写结果命中合成音频的两个预期危险表达“胸口疼”和“喘不上气”。本轮只调用一次，没有自动重试、模型切换或患者数据。

## 测试对象

- 分支：`codex/backend-integration-2026-09-14`
- 模型：`gemini-2.5-flash-lite`
- 供应商：AIHubMix / Google AI Studio
- 合成音频：`data/synthetic/selftest/voice.wav`
- 时长：6.892 秒，16 kHz，单声道
- 大小：220624 字节
- SHA-256：`8418ad10070a018ad1829261a26bcf3010f7a73454c56404a91b637002ed979f`

## 可核对结果

- 应用返回：`provider=aihubmix`、`model=gemini-2.5-flash-lite`、`is_mock=false`。
- 转写文字：“这是 一段合成测试 不是真实病例 今天胸口疼 喘不上气”。
- AIHubMix 控制台：Success，InputAudioTokens 221，端到端延迟 2.025 秒，扣费 `$0.000080`。
- Trace ID：`2026091606580621155562202060482`。
- 全量 Python 回归：`744 passed in 69.21s`。
- 前端 TypeScript 接口合同：`npm run check:contracts` 通过。

## 范围边界

这份证据证明当前 Key、模型、请求协议和一个仓库合成 WAV 在当时可用。它不证明手机浏览器 WebM、通用音质、长时录音、真实患者、临床准确性或公网生产已验收。语音结果仍是待人工核对初稿，不是诊断或医疗建议。
