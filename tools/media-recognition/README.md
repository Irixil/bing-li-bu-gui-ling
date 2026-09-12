# 本地识别适配器

`recognition.py` 是 B 任务的唯一 Python 调用边界。`vision_ocr.swift` 只负责在 macOS 上调用 Vision；Whisper 通过子进程运行，避免把模型生命周期和 A 的 HTTP／数据库进程混在一起。

```bash
./tools/media-recognition/build_vision_ocr.sh
WHISPER_PYTHON=/Library/Developer/CommandLineTools/usr/bin/python3 \
WHISPER_MODEL=base \
.venv/bin/python scripts/verify_media_recognition.py
```

没有配置或构建适配器时会返回 `provider_not_configured`；不会偷偷返回固定文本或 Mock。测试替身仅用于单元测试错误路径。

## 云端 ASR（P0 候选）

需要明确设置 `MEDIA_ASR_PROVIDER=dashscope` 才会上传已保存的原音频。默认不会从本地 Whisper 静默切换到云端。

当前 P0 先测 `paraformer-v2`：

```bash
MEDIA_ASR_PROVIDER=dashscope \
DASHSCOPE_ASR_MODEL=paraformer-v2 \
DASHSCOPE_API_KEY=\$DASHSCOPE_API_KEY \
.venv/bin/python -c 'from backend.recognition import recognize_file; print(recognize_file("/path/to/saved.wav", kind="audio", content_type="audio/wav", attempt_id="try_1"))'
```

`MEDIA_ASR_PROVIDER=dashscope` 配合 `DASHSCOPE_ASR_MODEL=paraformer-v2` 是当前 P0 配置；将 `DASHSCOPE_ASR_MODEL` 改为 `qwen3-asr-flash` 可做同音频对照。真实医疗音频必须先获得授权；完整原件由 A 侧先持久化，识别失败仍可重试，不能丢失。

单条真实 smoke test：

```bash
DASHSCOPE_API_KEY='你的百炼Key' \\
.venv/bin/python scripts/verify_dashscope_asr.py
```

指定对照模型：

```bash
DASHSCOPE_API_KEY='你的百炼Key' \\
.venv/bin/python scripts/verify_dashscope_asr.py --model paraformer-v2
```

脚本只输出识别结果和安全错误分类，不输出 Key。若服务端点、模型权限或请求形态不匹配，会返回错误并保持原件不变；此时不能把失败当成模型质量结论。

## 拍照 OCR

拍照 OCR 使用同一个 `DASHSCOPE_API_KEY`，但模型是视觉模型，不是 ASR 模型：

```env
MEDIA_OCR_PROVIDER=dashscope
DASHSCOPE_OCR_MODEL=qwen3.5-ocr
```

当前实现通过百炼 OpenAI 兼容视觉接口，把已保存图片以 Base64 Data URL 发送给 `qwen3.5-ocr`，要求逐字提取；模糊字符返回 `?`，不猜写。ASR 仍使用 `paraformer-v2`。同一个 Key 只代表同一个百炼账号，不代表 ASR 和 OCR 共用同一个模型。
