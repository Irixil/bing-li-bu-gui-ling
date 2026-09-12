# 病历不归零 · 比赛 MVP

帮助老人把自己的健康情况记下来，整理成有原文、有来源、时间不确定也不会乱填的记录，在复诊时带着连续资料去沟通。

当前交付是 **可运行的文本后端 + 已接入的本地媒体后端 + 公开病例演示数据**。媒体支持语音/照片原件上传、持久化、识别任务、识别失败保留、危险扫描和 Event 关联；前端仍由项目负责人开发，尚未在本主仓库完成浏览器整体验收。商业方向暂定 2C 订阅，未验证付费意愿，未做支付。

**团队只使用本仓库。** 历史多版本总包不属于当前开发包。代码底座保留最新持久化版本已有的记录、整理、核对、修订、历史和交接卡能力。

## 两位后端同学从这里开始

用 Git 克隆仓库并在 Codex 打开，告诉它“我负责任务 A”或“我负责任务 B”。先读 [团队入口与可复制的开场话](docs/team/README.md)，Codex 会按根目录 AGENTS.md 找到对应要求，核对现状并说明路线，确认后再开发。

| 选择 | 负责内容 | 任务单 |
|---|---|---|
| 任务 A | 文件保存／读取、SQLite 状态、重试与幂等、Event 关联、API、备份恢复 | [TASK-A-MEDIA.md](docs/team/TASK-A-MEDIA.md) |
| 任务 B | 语音转文字、照片识字、真实服务与失败处理、模型证据 | [TASK-B-RECOGNITION.md](docs/team/TASK-B-RECOGNITION.md) |

共同阅读 [接口草案](docs/team/MEDIA-CONTRACT.md) 与 [提交合并指南](docs/team/INTEGRATION.md)。两人分别推分支、发 PR，集成人按依赖顺序合并；不要上传整个文件夹覆盖仓库。

录音已确认“长时间无声先提醒，无回应再暂停，保留内容并可接着说”。具体时间和检测方法待真机验证；此前 **60 秒强制结束要求已撤回**，不得写成默认值或拒收规则。

## 十分钟启动

安装 Python **3.12** 与 Git。在要放项目的目录中执行：

```bash
git clone https://github.com/Irixil/bing-li-bu-gui-ling.git
cd bing-li-bu-gui-ling
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m backend.run_local
```

Windows PowerShell 把创建和启用环境两步换为：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

如 PowerShell 不允许执行激活脚本，可直接使用 `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` 与 `.venv\Scripts\python.exe -m backend.run_local`。首次装依赖需要联网。

访问 <http://127.0.0.1:18768/health> 应看到 `ok: true`。前端尚未构建时首页 `/` 可能返回 404；后端 API 仍可独立联调。数据库自动保存在 `runtime/records.sqlite3`。

复制 `.env.example` 后，文本整理和媒体识别的 Mock 都是显式的离线配置，不需要密钥、不调用外部 AI；页面必须明确标记为离线演示，不应对评委宣称为真实识别结果。未配置媒体 provider 时识别返回 `provider_not_configured`，不会静默改用 Mock。媒体写入口还要求在 `.env` 中配置三项正整数资源保护边界；未配置时可读取能力端点，但写入返回 `503 media_limits_not_configured`。密钥不进仓库。本版本真实模型调用已有有限成功证据，范围见 [模型接入说明](docs/MODEL-CONNECTION.md) 与 [联调报告](docs/MODEL-INTEGRATION.md)，不代表完整语义或临床验收。

现在也支持 `MODEL_PROVIDER=openai_compatible` 接 OpenAI Chat Completions 兼容中转站，配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 即可。魔搭和 DeepSeek 旧配置保持兼容。配置方法和实际联调状态见 [模型接入说明](docs/MODEL-CONNECTION.md) 与 [联调报告](docs/MODEL-INTEGRATION.md)。

2026-09-12 用户绑定阿里云后，按其新选择接通魔搭 `deepseek-ai/DeepSeek-V4-Pro-0813`，已取得通过应用校验的真实输出；首次单条耗时约 41.9 秒。此前 V4.1-Flash 的无可用提供方错误保留为历史证据。连通成功不等于完整语义或临床验收，批次结果和剩余问题以联调报告为准。

2026-09-12 C 部分修订采用“结构整理、完整原文保留”，模型负责分类和标记，暂不生成自由摘要。提示词为 `prompt-v0.5`，离线危险规则为 `offline-danger-v2`，独立专业复核候选为 `offline-review-flags-v1`。修复与第一性原理对抗审查见 [docs/C-REVIEW.md](docs/C-REVIEW.md)；AI 起草的规则与医学待审清单见 [临床规则草案](docs/CLINICAL-RULE-DRAFT.md)，阶段计时仅作禁用占位。C 的合并步骤、共享字段审阅与验证入口见 [HANDOFF-C.md](HANDOFF-C.md)。

另开一个终端，进入同一目录并启用环境，即可运行：

```bash
# 自动启动临时本地服务，完整演示公开病例；不会污染常用数据库
python -m scripts.demo

# 导入已经启动的展示服务，供你开发的前端查看
python -m scripts.demo --base-url http://127.0.0.1:18768

# 后端全部测试
python -m pytest -q

# 40 条合成用例的结构与指定安全规则回归
python -m backend.evaluate_mock

# 新 11 条 C 部分合成用例的自动断言；报告仍标记需人工复核项
python -m backend.evaluate_mock --dataset data/synthetic/c-model-smoke.json --strict

# 配好本地 .env 后验证真实模型（脚本名兼容旧命名，也支持 DeepSeek）
python -m backend.evaluate_modelscope --dataset data/synthetic/c-model-smoke.json --out runtime/evaluations/c-real-model.json

# 对常用数据库做一致性备份
python -m scripts.backup

# 一次执行 B 侧发布门槛，并输出机器可读 JSON（需先完成 npm ci）
python -m scripts.verify_b_release

# 检查前端 TypeScript 接口合同（首次需安装 Node.js 22 与依赖）
npm ci
npm run check:contracts

# 检查媒体能力；写入口启用前必须看到 enabled: true
curl http://127.0.0.1:18768/api/media/capabilities
```

导入脚本会保存、整理并模拟点击“核对记录准确”，生成交接材料。它是软件流程演示，不代表老人或医生实际参与了确认。重复导入同一份未改数据不会重复建记录。

## 现在能做什么

原文先入 SQLite，再执行本地危险规则，再请求 AI。模型断网、超时、非法 JSON 或其他异常时，原文和审计保留；若命中胸痛、呼吸困难等规则，仍返回固定危险提醒。成功结果继续经过原有结构、来源、时间和安全检查。

后端流程已通过自动检查：保存 → 整理 → 核对记录 → 历史 → 修订 → 就诊交接材料；媒体流程也已通过本地文件/SQLite/Mock 的上传 → 识别 → 危险扫描 → Event 关联回归。**网页上的完整比赛 demo 尚未通过验收**，需要前端接入与实际浏览器演练。

本机演示只面向一个老人、一份本地数据库。服务只监听 127.0.0.1，旧兼容读取路径没有强制账号隔离；不要把它直接发布成公网多人服务。

本地规则只识别有限表达，误报和漏报都可能发生。“未命中”不等于“医学正常”；老人核对记录也不能消除医学风险。产品不诊断、不自动改药。

## 媒体后端当前状态

媒体后端由 `backend/media_store.py`、`backend/store.py`、`backend/media_service.py`、`backend/media_backend.py` 和 `backend/server.py` 共同提供。前端按 [API 合同](docs/API.md) 和 [媒体接线说明](frontend/README.md) 接入，不需要读取 SQLite 表。

最短链路是：

1. `GET /api/media/capabilities`，确认 `capabilities.enabled`。
2. `POST /api/media/uploads` 创建元数据。
3. 将文件分片发送到 `/api/media/uploads/{upload_id}/parts/{index}`。
4. `POST /api/media/uploads/{upload_id}/complete` 完成原件发布。
5. 使用当前 `media.version` 调 `POST /api/media/{media_id}/recognize`。
6. 轮询 `GET /api/media/{media_id}`，识别成功后查看 `media.recognition`；失败时原件仍可读。

媒体在 `.env` 显式配置 `MEDIA_RECOGNITION_PROVIDER=mock` 时使用明确标记的 Mock 识别；未配置或配置真实 provider 时不会静默回退。真实 ASR/OCR、浏览器播放、手机暂停续录合并和公网部署仍未验证。详细字段、状态、错误码和版本语义见 [docs/API.md](docs/API.md)；交接与联调见 [docs/team/HANDOFF-A.md](docs/team/HANDOFF-A.md) 和 [docs/B-INTEGRATION-HANDOFF.md](docs/B-INTEGRATION-HANDOFF.md)。

## 团队从哪里开始

| 文件/目录 | 用途 |
|---|---|
| [docs/PROJECT-PLAN.md](docs/PROJECT-PLAN.md) | 当前定位、清理取舍、五人分工、今晚和明天的顺序 |
| [docs/B-BACKEND-PLAN.md](docs/B-BACKEND-PLAN.md) | B 已认领的后端数据/API 范围、工作顺序和验收标准 |
| [docs/B-PARALLEL-EXECUTION.md](docs/B-PARALLEL-EXECUTION.md) | B1–B6 的并列批次、完成证据和必须等待的联合验收 |
| [docs/B4-A-INTEGRATION-RUNBOOK.md](docs/B4-A-INTEGRATION-RUNBOOK.md) | A 接入 B 后端并验收 422、409、重启恢复的浏览器联调手册 |
| [docs/B-INTEGRATION-HANDOFF.md](docs/B-INTEGRATION-HANDOFF.md) | A/C/D/E 与 B 的同步联调、合并顺序和比赛冻结门槛 |
| [docs/decisions/0001-backend-mvp-stack.md](docs/decisions/0001-backend-mvp-stack.md) | 比赛 MVP 后端技术栈与开发规则 |
| [docs/team/README.md](docs/team/README.md) | 两人任务入口、已确认需求、待定事项、文件所有权和 Codex 开场话 |
| [HANDOFF-C.md](HANDOFF-C.md) | C 模块合并入口、配置、共享文件审阅地图和验证证据 |
| [docs/team/INTEGRATION.md](docs/team/INTEGRATION.md) | 分支、PR、合同先行、依赖合并、联合验收和交接 |
| [docs/API.md](docs/API.md) | 前后端正式接线合同，包含失败与危险提醒 |
| [contracts/api.ts](contracts/api.ts) | 与当前接口对应的 TypeScript 类型，供前端导入参考 |
| [frontend/README.md](frontend/README.md) | 项目负责人的前端任务与验收清单 |
| [docs/VALIDATION.md](docs/VALIDATION.md) | 实际测过的内容和没有证明的能力 |
| [data/public_cases/README.md](data/public_cases/README.md) | 真实公开病例的许可、来源与改编说明 |
| `backend/` | API、持久化、模型适配、本地规则 |
| `tests/`、`scripts/` | 回归测试、演示、备份 |
| `.dz/`、`PROJECT.md` | AI 接管记忆；本次发布协作需求不代表媒体实现或验收通过 |

项目代码暂未授予通用开源许可证；团队可以从本仓库协作开发。公开病例改编资料的 CC BY 4.0 许可单独适用，不应混为整个仓库的许可证。

## 比赛演示一键启动

如果只需要本机离线演示（文字 + 媒体 Mock），可直接运行：

```bash
.venv312/bin/python -m scripts.start_demo
```

它使用 `MODEL_PROVIDER=mock`、`MEDIA_RECOGNITION_PROVIDER=mock` 和有限的本地媒体资源边界；不会调用外部 AI。正式联调仍建议复制 `.env.example` 并显式配置。
