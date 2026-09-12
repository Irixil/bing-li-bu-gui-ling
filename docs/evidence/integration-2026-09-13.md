# 集成比赛演示版本验收记录

- 集成分支：`codex/integration-demo-version`
- 基线：`origin/main`（2026-09-12 拉取）
- PR：[#8 集成比赛演示版本](https://github.com/Irixil/bing-li-bu-gui-ling/pull/8)
- 环境：macOS arm64，Python 3.12.13，Node/npm，默认 `MODEL_PROVIDER=mock`

## 合并范围

- PR #6 / `fix/backend-api`：媒体上传、分片、保存、原件读取、识别状态、幂等、危险扫描、Event 关联、备份恢复。
- PR #3 / `codex/model-safety`：AI 接口、安全规则、原文证据白名单、失败审计、模型追踪与专业复核候选。
- `feat/elder-ui`：老人端 HTML/CSS/JS；本次接入文字流程和媒体上传/识别状态展示。

未合并 PR #4（P1 复杂图片登记，按要求暂缓）、PR #2（识别实现与 PR #6 的 `recognition.py`、合同和测试重叠）、PR #7（额外 QA/公开病例证据，未在本次指定合并范围内）。P2 VAD 未修改。

## 冲突

合并 PR #3 时冲突于 `README.md`、`backend/server.py`、`backend/store.py`、`contracts/api.ts`、`docs/VALIDATION.md`；合并老人端时冲突于 `frontend/README.md`。已逐文件保留媒体、安全、历史、幂等、修订和交接行为。`.github/workflows/backend.yml` 恢复为 main 版本，因为当前 OAuth token 缺少 `workflow` scope；该权限限制已写入 PR #8。

## 实际验证

- `.venv312/bin/python -m pytest -q`：629 passed。
- `.venv312/bin/python -m backend.evaluate_mock`：40/40 schema，6/6 指定危险样例；旧数据集仍有 54 个语义断言失败和 146 项未评估，不能称语义全通过。
- `.venv312/bin/python -m backend.evaluate_mock --dataset data/synthetic/c-model-smoke.json --strict`：11/11，121 项自动断言通过，29 项人工未判定。
- `.venv312/bin/python -m scripts.demo`：公开病例保存→整理→核对→历史→交接通过；该脚本当时未覆盖修订。
- `.venv312/bin/python -m scripts.verify_b_release`：7/7 通过。
- `npm run check:contracts`、`node --check frontend/app.js`、`node --check frontend/media.js`、`git diff --check`：通过。
- 浏览器历史证据更正（2026-09-13）：先前“完整三轮全部通过”的表述不准确，撤回。工具记录只证明以下部分流程，不能作为完整三轮验收：
  - 第 1 轮：文字保存→整理→核对→历史→修订→修订后历史→交接；未点击修订前原文。
  - 第 2 轮：文字保存→整理→核对→历史；未完成该轮修订、交接。
  - 第 3 轮：文字保存→整理→核对→交接；未完成该轮历史、修订。
  - 三轮使用 Mock，不证明真实模型或 ASR/OCR 可用。
  - 首页、我的记录、看病资料导航和刷新媒体实际点击；当时无媒体上传、识别、播放、浏览器重复提交和浏览器 422 的完整验收证据。
  - 预置危险样例在历史和交接材料中显示危险提醒。刷新及任务服务重启后点击刷新，之前保存的文字记录仍显示。

## 流程与边界

自动化 HTTP/SQLite 测试覆盖保存、整理、核对、历史、修订、交接、失败时保留原文和危险提醒、幂等、持久化及媒体状态；这些自动化检查不替代逐按钮浏览器验收。上列测试数字属于之前提交，后续录音修复和在线接入需要重新运行验证。真实 ASR/OCR、完整三轮按钮流程及医学语义复核仍待补齐，不得据此声明整个 MVP 已稳定。

## 在线自测补强轮次（2026-09-13）

本轮新增默认拒绝 Mock 的 `scripts.selftest`、本地 `.env` 配置检查和同源启动、DashScope 流式 ASR 协议适配、录音暂停/续录/上传重试修复，以及合成 WAV/PNG 验收素材。没有合并 PR #2/#4 或更改 VAD 算法。

已实际运行：

- `python -m pytest -q`：706 passed，70.16 秒（含识别协议、真实 FFmpeg WebM 解码、HTTP 持久化；外部 AI 为测试替身）。
- `node --test tests/frontend_recording.test.cjs tests/frontend_media.test.cjs tests/frontend_organize.test.cjs`：14/14，受控录音器和 HTTP 替身，不代表真麦克风或真实 ASR；包含 422 后断网仍显示原文/危险提醒及修订重复点击、失败保留输入。
- `npm run check:contracts` 和 `git diff --check` 通过。
- `python -m backend.evaluate_mock`：40/40 结构、6/6 指定危险样例；仍有 54 断言失败、146 未评估，未改判定口径。
- `python -m scripts.demo`：Mock HTTP，1 位公开病例 3 段改编资料通过；此旧脚本不覆盖修订。
- 本轮自测服务器使用独立 SQLite 与媒体目录、端口 18769。`scripts.selftest --allow-mock` 连续三轮，每轮 138/138 检查、57 次 HTTP；三份报告的 `online_passed` 均为 false。这三轮不是浏览器按钮验收。
- 在线默认自测针对同一 Mock 服务退出 1，在 `health.real_provider` 拒绝；无写入，不能用真实 HTTP 冒充真实 AI。
- `scripts.start_demo --check-config` 退出 2，明确报告缺魔搭 Token、ASR Key、OCR 地址/模型/Key；未启动在线服务、未发送真实模型请求。

真实在线三轮仍未完成，不能声明整体稳定。PR #3 最新提交已包含在集成分支；PR 正文及 HANDOFF-C 明确凭据仅留开发者本地 `.env`，GitHub 没有交付可用 Key。公开库中的测试字符串不是有效凭据。本机 `.env` 已创建且被 Git 忽略，等操作者填写后再运行在线命令。

操作与逐按钮清单见 [在线自测指南](../DEMO-SELFTEST.md)。录音的固定 12 秒自动暂停仍是已知缺口：它不检测真正静音，也不满足先提醒后等待的完整策略。本轮不把暂停状态修复写成 VAD 验收通过。
