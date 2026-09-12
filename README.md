# 病历不归零 · 比赛 MVP

帮助老人把自己的健康情况记下来，整理成有原文、有来源、时间不确定也不会乱填的记录，在复诊时带着连续资料去沟通。

当前交付是 **可运行的文本后端 + 两人媒体后端开发任务包 + 公开病例演示数据**。语音／照片接入是本次开发目标，目前尚未实现；前端由项目负责人在独立任务开发，尚未在本主仓库完成整体验收。商业方向暂定 2C 订阅，未验证付费意愿，未做支付。

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

访问 <http://127.0.0.1:18768/health> 应看到 `ok: true`。首页 `/` 在前端构建完成前返回 404，这是当前尚未交付页面的表现。数据库自动保存在 `runtime/records.sqlite3`。

默认 `MODEL_PROVIDER=mock`，不需要密钥、不调用外部 AI。Mock 是规则式模拟整理器，用于前后端接线，不应对评委宣称为真实大模型结果。可把 `.env.example` 复制为 `.env`，填写自己的模型配置后启用 `deepseek` 或 `modelscope`；密钥不进仓库。本版本真实模型调用尚未验证。

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

# 对常用数据库做一致性备份
python -m scripts.backup
```

导入脚本会保存、整理并模拟点击“核对记录准确”，生成交接材料。它是软件流程演示，不代表老人或医生实际参与了确认。重复导入同一份未改数据不会重复建记录。

## 现在能做什么

原文先入 SQLite，再执行本地危险规则，再请求 AI。模型断网、超时、非法 JSON 或其他异常时，原文和审计保留；若命中胸痛、呼吸困难等规则，仍返回固定危险提醒。成功结果继续经过原有结构、来源、时间和安全检查。

后端流程已通过自动检查：保存 → 整理 → 核对记录 → 历史 → 修订 → 就诊交接材料。**网页上的完整比赛 demo 尚未通过验收**，需要前端接入与实际浏览器演练。

本机演示只面向一个老人、一份本地数据库。服务只监听 127.0.0.1，旧兼容读取路径没有强制账号隔离；不要把它直接发布成公网多人服务。

本地规则只识别有限表达，误报和漏报都可能发生。“未命中”不等于“医学正常”；老人核对记录也不能消除医学风险。产品不诊断、不自动改药。

## 团队从哪里开始

| 文件/目录 | 用途 |
|---|---|
| [docs/team/README.md](docs/team/README.md) | 两人任务入口、已确认需求、待定事项、文件所有权和 Codex 开场话 |
| [docs/team/INTEGRATION.md](docs/team/INTEGRATION.md) | 分支、PR、合同先行、依赖合并、联合验收和交接 |
| [docs/PROJECT-PLAN.md](docs/PROJECT-PLAN.md) | 当前定位、范围、实施顺序与已知限制 |
| [docs/API.md](docs/API.md) | 前后端正式接线合同，包含失败与危险提醒 |
| [contracts/api.ts](contracts/api.ts) | 与当前接口对应的 TypeScript 类型，供前端导入参考 |
| [frontend/README.md](frontend/README.md) | 项目负责人的前端任务与验收清单 |
| [docs/VALIDATION.md](docs/VALIDATION.md) | 实际测过的内容和没有证明的能力 |
| [data/public_cases/README.md](data/public_cases/README.md) | 真实公开病例的许可、来源与改编说明 |
| `backend/` | API、持久化、模型适配、本地规则 |
| `tests/`、`scripts/` | 回归测试、演示、备份 |
| `.dz/`、`PROJECT.md` | AI 接管记忆；本次发布协作需求不代表媒体实现或验收通过 |

项目代码暂未授予通用开源许可证；团队可以从本仓库协作开发。公开病例改编资料的 CC BY 4.0 许可单独适用，不应混为整个仓库的许可证。
