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
- 浏览器真实串行验收（Ego/CUA，`http://localhost:5173/`，2026-09-13）：完成 3 轮，每个按钮均在上一步状态确认后点击，并在点击后重新读取无障碍树。
  - 第 1 轮：点击“说给我听”→输入并保存“今天上午头晕，吃饭后好一些”→“整理记录”后显示“整理草稿，待核对”→“我核对过了”后显示“已核对记录准确”→“查看历史”显示 created/organized/review_confirm 三个版本→“修订记录”填写原因并“保存修订”→再次“查看历史”看到 revised_from→“生成就诊交接材料”显示 2 项待处理。
  - 第 2 轮：同样完成保存（“昨晚咳嗽，今天已经缓解”）、整理、核对、历史、交接；历史树确认 v1/v2/v3，列表记录数增加且原文保留。
  - 第 3 轮：完成保存（“服药后胃部不适，暂无其他症状”）、整理、核对、交接；整理草稿识别为 medication，列表显示“已核对记录准确”。
  - 单独点击“看病资料”→“刷新媒体”：页面显示 0 张资料照片和“还没有上传原件”；“拍下来”入口可打开，浏览器文件/相机权限未授予，因此未伪造上传成功。
  - 预置脱敏危险样例“胸口疼”在历史和交接材料中持续显示危险提醒及“仍有待处理事项”。
  - 首页、我的记录、看病资料导航均实际点击并确认页面切换；刷新媒体实际点击并确认结果。

## 流程与边界

自动化 HTTP/SQLite 测试覆盖保存记录→整理→核对→历史→修订→交接、失败 422 保留原文和危险提醒、幂等重复提交、重启恢复、媒体失败后原件读取、上传分片和识别状态。浏览器三轮已验证主流程和刷新后数据仍在；服务重启恢复由自动化测试验证。浏览器真实麦克风/相机权限、手机暂停续录、Blob 播放、真实 ASR/OCR 和医学语义复核仍未完成。重启演练：停止并重新启动 `scripts.start_demo` 后，点击“我的记录”→“刷新”，三轮记录仍显示，证明 SQLite 持久化可恢复。
