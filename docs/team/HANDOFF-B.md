# 任务 B 交接：语音转文字与照片识字

## 基线与分支

- 基线：GitHub `main` 的合并提交 `6e1a7f3f5d33b66b259fb2e35784e9447be23a07`。
- 本分支：`feat/media-recognition`。
- 本分支没有修改 `backend/server.py`、`backend/store.py`、数据库或前端。
- 仓库要求的 DZ 状态工具在本机未安装，因此没有伪造 `resume-report`；基线通过 Git、`PROJECT.md`、`.dz/state.json`、代码和证据文件交叉核对。

## 交付内容

| 文件 | 作用 |
|---|---|
| `backend/recognition.py` | 统一 `recognize_file(path, *, kind, content_type, attempt_id)` 函数；只读已保存文件，返回文字或稳定 `RecognitionError`。无数据库、Event、HTTP 和重试。 |
| `tools/media-recognition/whisper_runner.py` | 本地 Whisper 子进程边界，输出受控 JSON。 |
| `tools/media-recognition/vision_ocr.swift` | macOS Vision OCR 辅助程序源码。 |
| `tools/media-recognition/build_vision_ocr.sh` | 在 macOS 编译 Vision OCR 辅助程序。 |
| `tests/test_recognition.py` | 9 项协议、格式、Mock 禁止静默回退、超时、非法响应和错误分类测试。 |
| `scripts/verify_media_recognition.py` | 真实本机 ASR/OCR 冒烟验证并输出证据 JSON。 |
| `data/media_samples/` | FLEURS CC BY 4.0 公开中文音频元数据和本项目合成 OCR 图。 |
| `docs/evidence/media-b/` | 样例来源、复现命令、真实结果和限制。 |

## 函数用法

```python
from backend.recognition import RecognitionError, recognize_file

try:
    result = recognize_file(
        "/path/to/already/saved.wav",
        kind="audio",
        content_type="audio/wav",
        attempt_id="attempt_123",
    )
except RecognitionError as error:
    safe_failure = error.as_dict()
else:
    # result: text/provider/model/is_mock (+ optional warnings)
    pass
```

`kind` 支持 `audio`／`asr` 和 `image`／`ocr`／`document`。文件不存在、空文件、格式不支持、上限、缺少适配器、超时、不可用、非法响应和空文字均有分类错误。公开错误不包含绝对路径、服务原文或密钥。模块不添加自动纠错，不编造置信分数，不改变原件。

## 服务与配置

默认使用本机适配器，不外传健康资料；只有显式设置 `MEDIA_ASR_PROVIDER=dashscope` 才会上传已保存原件：

- ASR：已安装的 OpenAI Whisper Python 包；`WHISPER_PYTHON`、`WHISPER_RUNNER`、`WHISPER_MODEL`、`MEDIA_ASR_TIMEOUT_SECONDS`。
- OCR：macOS Vision；`VISION_OCR_BINARY`、`MEDIA_OCR_TIMEOUT_SECONDS`。
- 共用边界：`MEDIA_RECOGNITION_MAX_BYTES` 默认 50 MiB 只是适配器防护值，不是产品上传合同；A 必须与前端和负责人确认并公布正式限制。

当前仓库不把 Whisper/Torch 这类重量级本地模型依赖塞进基础 `requirements.txt`。运行 ASR 前，需要在单独的 Python 运行时安装并固定 `openai-whisper`（导入名 `whisper`）及其 PyTorch 依赖；`WHISPER_PYTHON` 必须指向该运行时。Vision OCR 使用系统框架和构建工具，不需要 Python OCR 包。

云端 ASR 已加入显式 DashScope provider 接线（提交 `191719c`），但本机未配置密钥，尚未产生真实云调用证据；没有读取或提交任何模型密钥。若后续选择云 ASR/OCR，需要另一个显式 provider、数据传输和费用决定；不能把模型整理接口当成语音或照片识别。

## 实测证据

运行：

```bash
./tools/media-recognition/build_vision_ocr.sh
WHISPER_PYTHON=/Library/Developer/CommandLineTools/usr/bin/python3 \
WHISPER_MODEL=base \
.venv/bin/python scripts/verify_media_recognition.py
```

本机实测结果见 `docs/evidence/media-b/README.md` 和运行生成的 `runtime/media-recognition-result.json`（runtime 被 Git 忽略）：

- ASR 返回非空文字，使用 `local-whisper/base`，最新一次约 3.0 秒；与 FLEURS 原文不完全一致，需人工核对。
- OCR 返回合成印刷图的非空文字；本机 Vision 读出药名、剂量、日期、血压和单位，仍需人工核对。
- `tests/test_recognition.py`：9 passed。

## 与任务 A 的接线边界

A 负责：已保存原件、媒体状态和尝试持久化、调用任务占用／重试、识别结果保存、危险扫描、Event 唯一关联、HTTP、备份恢复和重启联调。调用成功不等于 Event 已核对；失败原件不能消失。A 应在真实接线中把 `result["text"]` 原样保存，再交给现有安全扫描，不能让模块自行建 Event 或静默重试。

模块返回 `provider`、`model`、`is_mock`，便于交接材料区分真实本机结果和测试替身。B 没有修改待冻结的媒体合同、`docs/API.md` 或 `contracts/api.ts`；共享合同由 A 收口并在合并前与前端确认。

## 已知限制与后续

- `base` 的一条普通话公开样例仍有错字／繁简／标点差异，不能宣称生产医疗准确率；应扩展经许可的中文语音评测集，重点覆盖药名、数值、单位、日期和老人噪声场景。
- OCR 目前是清晰印刷资料；手写、复杂版式、低清照片和反光未验证。
- 录音“无声提醒后暂停并可续录”的阈值、续录合并由前端与 A/负责人验证；本模块不实现录音采集，也不恢复已撤回的 60 秒规则。
- 本地 Whisper 与 Vision 适用于当前 macOS 开发机；跨平台或生产部署需另行确认运行时、模型缓存、资源上限和隐私边界。

### 云 OCR 接线状态

已在 `backend/recognition.py` 增加显式 DashScope OCR provider：设置 `MEDIA_OCR_PROVIDER=dashscope` 后使用 `DASHSCOPE_OCR_MODEL=qwen3.5-ocr`，与 ASR 共用 `DASHSCOPE_API_KEY`。当前没有真实 OCR 云调用证据；本地 Vision OCR 仍可作为不外传数据的基线。Key 不进前端、不进 Git。
