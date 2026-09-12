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

推荐先测 `qwen3-asr-flash`：

```bash
MEDIA_ASR_PROVIDER=dashscope \
DASHSCOPE_ASR_MODEL=qwen3-asr-flash \
DASHSCOPE_API_KEY=\$DASHSCOPE_API_KEY \
.venv/bin/python -c 'from backend.recognition import recognize_file; print(recognize_file("/path/to/saved.wav", kind="audio", content_type="audio/wav", attempt_id="try_1"))'
```

`MEDIA_ASR_PROVIDER=paraformer` 会把同一适配器切到 `paraformer-v2`，用于同一批音频的成本和质量对照。真实医疗音频必须先获得授权；完整原件由 A 侧先持久化，识别失败仍可重试，不能丢失。
