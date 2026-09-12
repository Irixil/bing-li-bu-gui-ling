# 本地识别适配器

`recognition.py` 是 B 任务的唯一 Python 调用边界。`vision_ocr.swift` 只负责在 macOS 上调用 Vision；Whisper 通过子进程运行，避免把模型生命周期和 A 的 HTTP／数据库进程混在一起。

```bash
./tools/media-recognition/build_vision_ocr.sh
WHISPER_PYTHON=/Library/Developer/CommandLineTools/usr/bin/python3 \
WHISPER_MODEL=base \
.venv/bin/python scripts/verify_media_recognition.py
```

没有配置或构建适配器时会返回 `provider_not_configured`；不会偷偷返回固定文本或 Mock。测试替身仅用于单元测试错误路径。
