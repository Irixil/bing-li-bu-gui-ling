# C 模块交接：模型整理、提示词与安全规则

交接对象：项目负责人／集成人，以及负责媒体存储/API 的 A、负责 ASR/OCR 的 B。C 是本次文本模型模块的交付名称，不改变 [两人开发指南](docs/team/README.md) 中 A/B 的分工。

原开发基线为 `e1a5967`，本次共享库同步目标为已合并协作指南的 `main`（核对时为 `6e1a7f3`）。交付使用 C 分支与 Draft PR；不会直接更新或合并 `main`。最终提交、同步结果和本次验证记录以本文下方及 `docs/evidence/c-integration/` 为准，旧阶段报告不代表整合版本验收。

## 集成人的最短操作路径

1. 打开 C 的 Draft PR，先看本文的共享文件表，再看 PR 的 Files changed。确认 `docs/team/`、媒体合同、前端及项目账本保留了最新 main 的成果。
2. 查看本次 `docs/evidence/c-integration/` 与 GitHub Actions 的运行提交是否对应 PR 最新代码；在比赛电脑运行下方离线验证命令。需要真实模型演示时，另配本人本地密钥并执行真实调用检查。
3. 请 A 核对 `server.py`、`store.py` 和 API 合同的兼容增量；请前端核对 422、历史提醒和临床候选提示。B 的 ASR/OCR 合同与实现仍按媒体任务推进，无需等待 C 提供识别能力。
4. 审阅及必需检查完成、项目负责人确认后，再将 Draft 标记 Ready for review，由指定集成人按仓库规则 squash 合并。此交接不代表已达到该步骤。
5. 合并后，各人在干净工作区执行 `git switch main`、`git pull --ff-only origin main`，重启服务并复跑文本闭环。自己的开发分支按 [整合指南](docs/team/INTEGRATION.md) 合入新 main，不整包覆盖目录、不强推历史。

如果 PR 开发期间 main 又有变化，作者在 C 分支的干净工作区执行 `git fetch origin`、`git merge origin/main`，逐项解决冲突后重跑检查并推送同一分支。不要同时抢改主分支。合并后需要撤回时，优先由集成人 revert 对应提交；恢复旧代码不会自动删除已经保存的审计字段或改变历史交接快照。

已核对 B 的 [PR #2](https://github.com/Irixil/bing-li-bu-gui-ling/pull/2)（`4e4eb7d`）：与 C 没有文件改动重叠，两者可独立审核、任意先合。本 PR 不包含 B 的分支；A 最终接线应基于已合入 C、B 的版本，并重跑联合验收。识别的 `provider/model/is_mock` 与整理的 `result_meta` 分别保存；完整识别文字先保存、扫描，再整理，超长文字或输出截断不得静默裁剪成成功结果。

## 本次交付与共享文件审阅地图

模型只做分类、复核路由与冲突候选；摘要和每条引用保留对应完整原文。模型失败先保留记录、危险提醒和安全的失败原因，不生成成功草稿，不自动诊断或改药。

| 文件 | 本次变化／集成时须保留的行为 | 接续人 |
| --- | --- | --- |
| `backend/adapter.py`、`backend/model_client.py`、`prompts/` | 通用非流式 Chat Completions；完整证据、来源、时间与安全校验；提示词和请求哈希 | C；B 不用它冒充 ASR/OCR |
| `backend/safety.py` | 离线危险规则、旧提醒保留、独立低心率待复核候选 | C；A 在识别文字出现后接入同一安全行为 |
| `backend/server.py` | 发给模型的原始证据白名单；422 错误白名单；成功/失败审计与本地提醒 | A 重点审查，保留未来媒体入口改动 |
| `backend/store.py` | 旧记录重扫的派生视图、模型审计字段、交接中的临床复核待办 | A 重点审查，不丢原文、版本与旧快照 |
| `contracts/api.ts`、`docs/API.md` | 新增可选追溯、失败及临床复核字段，现有 URL 和状态码不变 | A 收口，前端核对 |
| `.env.example`、模型接入文档 | 新增通用模型配置名称；仓库默认 Mock | A/B 保留各自服务配置，密钥各自本地管理 |
| `backend/evaluation.py`、评测入口、`data/synthetic/c-model-smoke.json`、测试 | 自动断言、失败和人工未判定项分开；11 条 C 合成对抗集 | C 提供证据，集成人复跑 |
| `config/clinical-review-backlog.json`、临床草案、盘点脚本 | 24 类待医学依据、规则评估和测试的研发清单 | C 维护，上线前由专业人员审核 |
| `config/transport-timing.placeholder.json` | 5 阶段计时均为 null，禁用且不由运行时加载 | 以后需要计时时再实现 |

本次不新增第三方依赖，不修改 `requirements*.txt`，不需要数据库表结构迁移。新审计信息继续使用既有 JSON 存储；读取旧记录时兼容缺失字段。新规则的读取派生视图不会回写原始扫描证据或旧交接卡；查看最新状态读取 Event，最新交接材料需重新生成。

没有交付上传、原件存储、ASR、OCR、媒体状态与重试、媒体备份、手机录音或浏览器验收。`source_kind=audio_transcript/document` 只是文字来源标签；文本模型成功不等于语音或图片识别成功。录音“提醒后无回应再暂停、内容可续录”的已确认方案和待定参数继续由原负责人推进。

## API 接入要点

- 原有保存、整理、核对、历史、修订、幂等和 409 合同保留。新增字段为可选兼容增量，旧记录允许缺少 `result_meta`、模型哈希与 `clinical_review_*`。
- 整理失败仍返回本地 HTTP **422**，包含已保存的 `event`、`raw_text_preserved=true`、`local_safety` 和固定失败原因。前端保留原文与提示，并明确本次整理失败；若已有旧草稿，不得显示为本次新结果。
- `failure_code`、`provider_http_status` 描述下游模型。模型的 401/403 不代表本地登录失效，429 不改变记录保存状态；未知错误不回显远端正文或密钥。
- 前端以 `local_safety` 和历史保留字段显示提醒，不能只依据 AI 草稿里的 `escalation_level=none` 清除历史危险提醒。`historical_notice_preserved=true` 表示历史曾命中；旧交接卡仍代表生成时快照。
- `clinical_review_status=candidate_unverified` 是待核查线索；`not_flagged` 只表示未命中有限候选规则，不能显示“医学正常”。记录确认只确认记录准确，交接中的 `clinical_measurement_review_required` 继续保留；已有急救路由优先。
- A 将未来识别结果接到 Event 时，保留原件、完整机器初稿和人工修订的来源关系，先执行本地文字扫描再整理；没有有效文字时不能宣称完成文字安全检查。具体媒体实现仍以 A/B 冻结后的合同为准。

## 本地运行与模型配置

按根 README 安装 Python 3.12 和现有依赖后，将 `.env.example` 复制为本地 `.env`，运行 `python -m backend.run_local`。默认 `MODEL_PROVIDER=mock` 可离线执行现有链路；Mock 身份必须明确展示，真实调用失败不会自动切换 Mock 或其他服务商。

| 用途 | 配置名称与非秘密选项 |
| --- | --- |
| 魔搭文本模型 | `MODEL_PROVIDER=modelscope`；`MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1`；`MODELSCOPE_MODEL=deepseek-ai/DeepSeek-V4-Pro-0813`；密钥变量名称为 `MODELSCOPE_ACCESS_TOKEN` |
| OpenAI Chat Completions 兼容中转站 | `MODEL_PROVIDER=openai_compatible`；显式配置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`，URL 保留服务要求的版本路径 |
| DeepSeek 官方服务 | `MODEL_PROVIDER=deepseek`；沿用 `DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_API_KEY` |
| 通用请求参数 | `MODEL_TIMEOUT_SECONDS`、`MODEL_MAX_TOKENS`、`LLM_JSON_MODE`、`LLM_EXTRA_BODY_JSON`；当前魔搭示例为 60 秒、4096 token、JSON mode 关闭、空扩展参数 |

密钥仅填本人本地 `.env` 或授权的环境配置，不提交、不发给队友、不放前端。更换服务商必须同时核对端点、模型与对应密钥；魔搭 token 管理网页不是推理 API 地址。修改 `.env` 后重启，shell 同名环境变量优先。模型请求的 60 秒超时不是录音时长限制，不得用于恢复已撤回的录音 60 秒强制结束规则。协议支持范围及地址限制见 [模型接入说明](docs/MODEL-CONNECTION.md)。

## 验证命令与证据

在仓库根目录运行。下面的离线检查不需要模型密钥或付费请求；HTTP 测试使用本机临时端口与临时数据库。

```bash
python -m pytest -q
python -m backend.evaluate_mock
python -m backend.evaluate_mock --dataset data/synthetic/c-model-smoke.json --strict
python -m scripts.demo --out runtime/demo-result.json
python -m scripts.clinical_review_inventory --out runtime/evaluations/clinical-review-inventory.json
```

真实服务验证与离线检查分别记录。配置完成后，可先执行第一条单样例连接检查，再按实际授权与演示范围运行后两条；报告有失败则保留失败，不以重试成功改写原批次。

```bash
python -m backend.evaluate_real --dataset data/synthetic/c-model-smoke.json --limit 1 --out runtime/evaluations/c-connection.json
python -m backend.evaluate_real --dataset data/synthetic/c-model-smoke.json --out runtime/evaluations/c-real.json
python -m backend.evaluate_real --dataset data/public_cases/cases.json --out runtime/evaluations/c-public-real.json
```

旧入口 `python -m backend.evaluate_modelscope` 继续兼容相同参数。报告仅保存通过应用校验的模型输出；单条成功不能代表全批成功。本 PR 在已有 CI 中补入 11 条 C 严格自动断言和临床清单盘点；旧 40 条仍按结构／安全 smoke 判定。CI 不验证真实模型、所有严格语义或医学安全。

本次整合记录（2026-09-12），未沿用历史结果：

| 项目 | 本次状态 |
| --- | --- |
| 同步 main、验证提交与环境 | main `6e1a7f3` 已合入 `c268495`；Python 3.12.13，macOS arm64。之后仅补交接、证据与 CI 命令，源码身份见 manifest |
| 全量测试 | **480 passed**，21.67 秒；含失败保原文、幂等、409、确认/重启/历史/交接、备份及安全边界 |
| 两套 Mock | 旧集 40/40 结构、6/6 指定安全；C 集 11/11、121 项自动断言通过，29 项人工未判定 |
| 公开病例本地闭环、临床盘点 | 1 位患者 3 段改编资料闭环通过；54 条材料中 53 条话题匹配，24 类待审，非医学结论 |
| 差异与敏感内容检查 | 源文件清单已核验；最终提交检查见 `docs/evidence/c-integration/submission-check.json`，仅报告统计与状态，不保存密钥 |
| GitHub Actions 与 Draft PR | 以此分支 Draft PR 的 Checks 和最新 head SHA 为准；本地结果不冒充远端 CI |
| 证据目录 | `docs/evidence/c-integration/`，记录实际命令、结果及对应源文件身份 |

历史临床轮次证据为 480 项测试、11 条 C 合成集的 121 项自动断言通过、29 项人工未判定；位于 `docs/evidence/clinical-review/`。它们是当时代码的结果，与本轮整合重跑结果分别记录。旧 40 条严格语义集仍有 54 个失败断言、15 个数据标签问题和 146 项未判定，原标签没有为通过率而改写。

## 真实模型限制与上线前待完成

`DeepSeek-V4-Pro-0813` 已有历史真实调用成功证据。60 秒／4096 token 的 11 条合成批次通过 8 条；有界重试后 C003、C009 成功，C011 在 180 秒／8192 token 参数下仍出现输出截断并被安全拒绝。1 位公开患者的 3 段许可改编摘要均曾分别获得成功输出，但完整批次出现过超时或校验失败，不能称稳定全量通过。证据见 [联调报告](docs/MODEL-INTEGRATION.md) 和 `docs/evidence/deepseek-v4-pro/`。

后续需在稳定网络下固定参数复跑，并完成真实输出和 29 项未自动判定语义的人工复核。当前没有分阶段网络计时，不能把所有波动归因为网络。时间占位均为 null，表示未采集，不表示零耗时；它不影响调用链。

规则草案明确标注 AI 起草，`medical_signoff=pending`。24 类待办的医学来源、适用范围、审核人和结论仍待上线前补齐，再依据审核结果修订规则与测试。低心率候选只是工程线索，不单独诊断或升级急救；未命中不代表安全。没有医师、护士或药师签署，也没有真实老人或医护试用，软件回归和机器辅助复核不能代替这些验收。详见 [临床规则草案](docs/CLINICAL-RULE-DRAFT.md)。

媒体真人样例、ASR/OCR 真服务、手机权限／录音体验和媒体备份仍由 A/B 与项目负责人交付。公开病例只用于许可范围内的改编演示与软件检查，保留 [来源和署名](data/public_cases/README.md)。本次不部署公网服务。
