# 在线配置验收记录 · 2026-09-13

## 基线与命令

- 分支：`codex/online-acceptance-2026-09-13`
- 基线：`codex/handoff-2026-09-13@a7bcb35`
- 已安装依赖：Python 3.12 虚拟环境 `.venv312`（被 `.gitignore` 忽略，未提交）
- `python3.12 -m pytest -q`：因全局环境没有 pytest，先按项目声明创建虚拟环境并安装 `requirements-dev.txt`；随后 `.venv312/bin/python -m pytest -q`：`728 passed`。
- `node --test tests/frontend_visibility.test.cjs tests/frontend_recording.test.cjs tests/frontend_media.test.cjs tests/frontend_organize.test.cjs`：`17/17 passed`。
- `npm run check:contracts`：通过。

## 真实配置检查

本机真实凭据只通过环境变量注入，未读取、打印或写入证据。配置检查通过，真实服务在 `18769` 启动；使用的真实 OpenAI-compatible 接口为智谱：文字 `glm-5.3-flash`、语音 `glm-asr-2512`、图片 `glm-4.6v`。 “Eagle light”是浏览器验收工具，不是项目 provider；项目 API 在本机端口提供。

首次在线整理发现模型把安全说明误填入 `forbidden_actions`，服务按安全契约返回 422 并保留原文。已在提示词中明确该字段必须省略或为空数组，提示词版本升至 `prompt-v0.6`；修复后真实整理成功。

## 结论

- 真实 HTTP 自测：`156/156 passed`，`passed=true`、`online_passed=true`，64 次 HTTP 调用；三类 provider 均 `is_mock=false`。
- 首轮真实浏览器录音产生的 WebM 识别失败时，页面保留原件并明确显示失败；仓库 WAV 真实 ASR 通过。浏览器麦克风权限、暂停/续录计时和原件保存已点击验证，手机真机和真实媒体播放仍未验收。
- 失败或未配置时原文和原始媒体保留策略已由自动化和离线浏览器证据覆盖；本文件不包含 token、`.env`、runtime 数据库或媒体原件。
