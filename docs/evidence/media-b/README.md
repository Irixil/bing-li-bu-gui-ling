# 任务 B 识别证据

本目录只保存脱敏、可公开的识别证据。真实健康资料和任何凭据不进入仓库。

## 样例

- `data/media_samples/fleurs-cmn-validation-1579.wav`：Google FLEURS `cmn_hans_cn/validation` 的公开中文音频，来源页为 <https://huggingface.co/datasets/google/fleurs>，按数据集说明使用 CC BY 4.0。该内容是普通新闻句子，不是医疗语音。
- `data/media_samples/合成印刷资料-OCR.png`：本项目用脚本生成的合成印刷资料，内容是虚构测试用户和测试用药字段，不是医院原始资料。

## 复现

```bash
# Python 3.12 环境已安装本仓库 requirements-dev.txt
./tools/media-recognition/build_vision_ocr.sh
WHISPER_PYTHON=/Library/Developer/CommandLineTools/usr/bin/python3 \
WHISPER_MODEL=base \
.venv/bin/python scripts/verify_media_recognition.py \
  --out runtime/media-recognition-result.json
```

Whisper 首次运行会在本机缓存模型；脚本本身不上传音频。`VISION_OCR_BINARY` 可指向由构建脚本生成的本机二进制。识别模块不会静默切换到 Mock。

## 结果解释

2026-09-12 本机 Apple M1 Pro 实测：

- ASR：`local-whisper/base` 返回非空中文文字，最新一次约 3.0 秒；与 FLEURS 原文存在繁简、标点和字词差异。它证明了真实本机模型调用和结果保留，不能证明医疗词汇、老人方言、噪声或所有口音的准确率。
- OCR：`macos-vision/VNRecognizeTextRequest` 成功读出合成图中的标题、日期、药名、剂量、用法、血压和提醒；药名／数值／单位仍应由人工核对，不能把 OCR 成功当成医学确认。

单元测试中的 subprocess 替身只验证统一协议和错误分类，结果会标为测试替身；不能替代上面的真实本机实测。

## 未验证

云端 ASR/OCR、医院真实资料、手写、复杂版式、方言、多说话人、流式录音、上传与重启恢复、A 的危险扫描和 Event 关联均不由此目录宣称通过。识别成功也不等于上传成功、家庭确认或医生确认。
