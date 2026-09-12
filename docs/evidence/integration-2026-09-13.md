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
- `.venv312/bin/python -m scripts.demo`：公开病例保存→整理→核对→历史→修订→交接通过。
- `.venv312/bin/python -m scripts.verify_b_release`：7/7 通过。
- `npm run check:contracts`、`node --check frontend/app.js`、`node --check frontend/media.js`、`git diff --check`：通过。
- 浏览器打开 `http://127.0.0.1:18769/`：老人端首页可启动，标题和“离线 Mock 演示模式”可见。

## 流程与边界

自动化 HTTP/SQLite 测试覆盖保存记录→整理→核对→历史→修订→交接、失败 422 保留原文和危险提醒、幂等重复提交、重启恢复、媒体失败后原件读取、上传分片和识别状态。浏览器真实麦克风/相机权限、手机暂停续录、Blob 播放、真实 ASR/OCR 和医学语义复核仍未完成。
