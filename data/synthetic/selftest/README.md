# 在线自测合成素材

这些内容是本项目为软件测试编写的虚构资料，不含患者信息，不是医疗建议或公开病例。

- `voice.txt`：应读出的完整文本。
- `card.txt`：简单排版 OCR 文本。
- `voice.wav`：macOS 系统 Tingting 语音合成、FFmpeg 转成 16 kHz 单声道 WAV；不是实际老人录音。
- `card.png`：FFmpeg 用系统字体将 `card.txt` 渲染成图片，不是病历扫描件。

保留这些标签。关键词“胸口疼”和“喘不上气”用于检查转写及既有危险提醒是否保留；命中两个词不代表一般识别准确率或医学安全。

也可按 `voice.txt` 自行录一段不含个人信息的音频，交给 `scripts.selftest --audio`；不会调用 TTS 服务。
