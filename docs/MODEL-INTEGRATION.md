# 通用接口与魔搭联调记录

日期：2026-09-12。本地分支 `codex/model-safety`，基线 `e1a5967`，未提交/推送。本轮接续之前 C 安全修复；旧 `docs/evidence/c-review/` 是前一轮快照，本轮证据存 `docs/evidence/model-connection/`。

## 完成项

- 新增 `OpenAICompatibleProvider`，使用 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 接非流式 Chat Completions 兼容站点。
- 魔搭和 DeepSeek 共用同一协议实现，旧 provider 类名及环境变量保持兼容。
- 可配置输出 token 上限、超时、JSON mode 和受保护的扩展参数。通用接口没有默认站点，地址必须明确；URL 不跟随重定向。
- 拒绝无效 JSON、重复字段、无穷数值、截断、空输出、非文本/工具输出和 HTTP200 内错误。只有经过应用安全校验的输出会被接受。
- 新命令 `backend.evaluate_real` 支持通用站点、公开病例、执行数量限制和完整已验证输出留存，旧 `evaluate_modelscope` 入口保持兼容。
- 后端 422 增加白名单 `failure_code/provider_http_status`，明确区别模型鉴权、限流、超时和协议失败；不会泄露模型原始错误正文或凭据。
- 本地 `.env` 权限为 0600，Git 忽略确认通过；文档和示例只含占位符。

配置方法见 [MODEL-CONNECTION.md](MODEL-CONNECTION.md)。最初联调使用魔搭官方文档示例 `Qwen/Qwen3.5-35B-A3B`、`https://api-inference.modelscope.cn/v1`、60 秒超时、4096 输出 token、非思考附加参数；当前模型已按用户选择切换，见下文。推理地址与用户提供的令牌管理页面是不同用途。

## 对抗与回归

全量 **418 passed**（Python 3.12.13）。11 条 C 合成用例通过 **121 个自动断言**，29 项仍需人工复核。协议检查覆盖构造参数、跨站密钥、HTTP 301/302/303/307/308、错误脱敏、JSON/流式混入、长度截断、状态伪成功及其后端失败保真链路。

独立审查发现并修复两项问题：

1. 直接创建通用 Config 时漏填地址可能默认走魔搭，造成密钥串站。现在 generic 一律要求显式 URL，旧 provider 仅使用自身默认端点。
2. HTTP 200 同时含 error 与 choices，或消息 role=user，会被误收为成功。现在拒绝这些响应，完整 adapter 路径也有对应测试。缺 role 作为明确兼容例外保留。

## 首轮真实调用结果（历史）

**已实际向魔搭官方推理端点请求，但均返回 HTTP 401；没有拿到任何模型推理输出。** 不能据此宣称模型接通、11 条真实模型评测通过或公开病例真实模型验收通过。

- 首次只执行 11 条合成集中的第 1 条：失败，后续 10 条未执行。报告保留覆盖范围。
- 安全状态诊断及最小协议请求同样返回 401。返回信息不足以区分具体是令牌、账号权限或平台认证条件，不做猜测。
- 完整本机 HTTP 链路再验证一次：先保存“合成联调记录：胸口很疼，喘不上气。”，再调用魔搭。下游 401 被转换为本地 422，`failure_code=model_http_error`、`provider_http_status=401`，原文与危险提醒可查询，草稿为空，状态仍 inbox，数据库重开可恢复。
- 总计 4 次真实请求尝试：首次评测、错误状态诊断、最小协议诊断、完整 HTTP 失败链路。每个请求均未获模型成功输出；未继续运行整批或公开病例，避免把鉴权失败重复当评测。

## 后续

### 401 根因检修（历史，同日）

经直接无代理请求并限长脱敏检查官方返回，HTTP401 的具体原因为 `Please bind your Alibaba Cloud account before use.`。因此当时阻塞是魔搭账号未绑定阿里云账号，而非已经证明令牌失效。检查无重复配置、无环境覆盖、令牌格式及空白正常；离线捕获验证 URL 与 Bearer Header 正确。官方 API-Inference 文档还要求实名认证。

之前状态码被过度概括，未提供足够原因；现在客户端对官方 hostname、401/403 和精确已知消息进行限长白名单分类，返回固定错误码 `model_account_binding_required` 与“魔搭账号需先绑定阿里云账号”。其他站点同文、超限、读取异常、坏 JSON 均保持一般 HTTP 错误，不泄露原文或密钥。相关 **209 项测试通过**，真实请求确认新分类生效。证据见 `docs/evidence/auth-diagnosis/`。本轮额外 2 次请求分别用于直接诊断和客户端分类验收，均无模型成功输出。该模型绑定后的托管可用性仍待验证。

### 用户指定模型切换（同日）

随后按用户选择将本地 `MODELSCOPE_MODEL` 改为 `deepseek-ai/DeepSeek-V4.1-Flash`，保持 `MODEL_PROVIDER=modelscope`、魔搭官方推理地址与已有令牌。移除旧 Qwen 的 `enable_thinking` 扩展参数，保留 JSON mode 关闭及其余运行参数。模型页面标题及 ID 已核对，但页面未显示 API-Inference 入口，不能仅凭模型库页面认定该模型已开放托管推理。

新模型单独执行第 1 条合成输入，仍返回 `model_http_error` / HTTP **401**，没有输出；其他 10 条和公开病例未执行。报告保存为 `docs/evidence/model-connection/deepseek-v41-flash-attempt.json`。上文 Qwen 的 4 次尝试是历史记录，本次另计 1 次。只改配置与说明，没有更改业务代码，不重复全量测试。

### 阿里云绑定后重试（同日最新）

用户确认完成绑定后，保持原令牌、模型和端点重试。单条合成评测返回 `model_http_error` / HTTP **400**；额外最小协议诊断返回 `Model id : deepseek-ai/DeepSeek-V4.1-Flash , has no provider supported`，请求 ID 为 `ba035171-9c3e-4646-84e6-b75aec998a80`。此前 401 绑定错误已消失，当前阻塞是魔搭推理端点未提供所选模型的服务。模型仓库存在不能替代 API 可用性验证。

本轮共 2 次请求，均无模型输出；合成集实际执行 1/11 条，另外 10 条及公开病例未执行。证据见 `docs/evidence/model-connection/deepseek-v41-flash-after-binding.json` 和 `docs/evidence/model-connection/after-binding-summary.json`。本轮仅更新验证记录，未更改实现或模型配置，未重复代码测试。

下一步需由用户选择魔搭已开放 API-Inference 的模型，或提供支持当前模型的其他服务商配置。连接单条成功后，再跑 11 条合成对抗集、3 段公开病例和人工输出核对。不能将当前结果称为真实模型联调成功或公开病例验收通过。

### 官方模型页面复核（同日，用户质疑后）

重新打开用户提供的 `https://www.modelscope.cn/models/deepseek-ai/DeepSeek-V4.1-Flash`，确认是魔搭官方模型库页面。当前公开页面显示“下载模型”和“Notebook快速开发”，未显示 API-Inference 面板。正文描述的 `deepseek-recipe` 能转换 API 请求格式，同时明确“模型推理、工具执行和 HTTP 传输由调用方自行处理”；“最小化推理”指向权重转换与本地运行说明。同一未登录浏览器对照 Qwen/Qwen3.5-35B-A3B 页面，可看到 API-Inference 面板、魔搭社区提供方、官方端点与示例模型 ID。公开页面摘录存于本目录证据中的 `deepseek-page-support-check.json` 和 `qwen-api-panel-comparison.json`。

[官方 API 推理介绍](https://www.modelscope.cn/docs/model-service/API-Inference/intro) 要求以模型页面右侧 API-Inference 示范代码为准，并提醒示例模型可能下线。[API-Provider 文档](https://www.modelscope.cn/docs/model-service/API-Inference/api-provider) 另支持托管外部提供方密钥，在模型 ID 后添加页面指定的提供方后缀。账号绑定本身不等于完成这项外部服务配置；未找到所选 DeepSeek 页提供对应示例，不猜测后缀或自动切换服务。

结论范围：现有证据证明当前账号通过当前端点、以所选 ID 请求未取得可用提供方，公开页也未展示其托管 API 入口。不能扩大为模型不存在、魔搭官网不可信、不能自行部署或所有服务商均不支持。此次仅查阅公开页面及代码，无新增推理请求、账号操作或配置修改。

### DeepSeek-V4-Pro-0813 实际接通（同日最新）

用户要求尝试 `deepseek-ai/DeepSeek-V4-Pro-0813`。其官方页面明确显示“推理 API-Inference”、魔搭社区提供方及该精确模型 ID，端点仍为 `https://api-inference.modelscope.cn/v1`。使用既有令牌、非流式接口、4096 输出 token、JSON mode 关闭、空扩展参数，首次合成 C001 返回真实输出，通过 13 项自动断言，耗时 41.87 秒。无需更改业务代码；本地 `.env` 所选模型已更新，令牌保留且文件权限仍为 0600，Git 忽略有效。

初次公开病例批次 3/3 均在 60 秒限制超时。随后将单条诊断等待上限设为 180 秒，公开病例第 1 段在 51.65 秒返回，通过 4 项有限合同断言及对应的急救升级检查。该重试实际用时低于原上限，只能证明响应时间波动和重试成功，不能据此证明提高上限解决了全部超时。

机器辅助审阅首条合成与公开输出未发现新增事实、来源升级、日期臆造或改药建议。公开资料保留 1 位患者、3 段论文改编的来源与 CC BY 署名。公开集未配置完整语义标签，因此即使报告 `semantic_pass=1`、`not_evaluated=0`，也仅代表已配置的有限断言；不代表完整语义或临床通过。

当前代码重新运行全量 **438 passed**，包含绑定错误分类及失败保真回归。证据独立保存在 `docs/evidence/deepseek-v4-pro/`，保留所有失败和重试记录，不覆盖前面的 401/400 历史。真实输出审阅属于机器辅助核查，仍无真实老人或医生试用。

完整合成批次在 60 秒、4096 token 设置下通过 **8/11**，91 项自动断言通过、22 项仍需人工核对。C003 超时、C009 被应用校验拒绝、C011 返回截断标记而被客户端拒绝。完整公开批次在 180 秒、4096 token 设置下通过 **2/3**，8 项有限断言通过，第 3 段被应用校验拒绝。两个完整批次严格门槛均失败，不能用首次连接成功代替批次验收。

针对上述 4 条失败项的有界重试使用 180 秒、8192 token、并发 2，C003、C009 和公开第 3 段随后通过；C011 在约 120 秒后仍返回 `finish_reason=length`，被客户端按设计拒绝。重试证明部分响应具有波动，不能把原批次改写成全量通过，也不能通过放宽校验掩盖截断。诊断记录见 `targeted-8192-diagnostic.json`。

### 延迟与网络归因边界

当前证据不能把波动全部归因于网络。成功请求约 18.7–58.8 秒，60 秒超时约发生在 60.1 秒；公开批次在 60 秒下全部超时，改为 180 秒后两条约 28.7–35.1 秒成功，另一条在约 28.7 秒返回应用校验拒绝。C011 在约 120 秒仍返回输出截断。可能因素包括网络连接、平台排队、服务端生成和非流式等待；现有客户端未拆分 DNS、TCP、TLS、首字节和服务端生成耗时，无法定量判断各自占比。`temperature=0` 也不保证服务端延迟或输出完全稳定。

官方页面示例使用 `stream=True`，当前项目为安全起见使用非流式 `stream=False`，以便在接受前拿到完整 JSON 并验证 `finish_reason`。流式实验可能改善首字节等待，但仍须累计完整内容、检测截断并执行同一套校验，不能作为绕过超时或安全检查的方案。未来阶段计时预留如下占位，不参与安全判断、状态转换或 `passes()` 门槛：`transport_timing: {dns_ms: null, tcp_ms: null, tls_ms: null, ttfb_ms: null, read_ms: null, collection: "not_instrumented"}`。当前不自动重试或切换模型，避免医疗原文被重复发送；演示前应在稳定网络下固定超时和 token 配置，重复跑同一批次并保留失败。

独立机器辅助审核成功输出未发现截句、数字改写、诊断、改药或来源升级。公开病例心率 40 次/分现在会被 `offline-review-flags-v1` 批量标记为 `low_heart_rate_candidate` 并要求专业复核，但仍不自动诊断或升级急救；未命中其他规则不能解释为医学正常。同一公开第 1 段的事件类型和时间确定性在重试中有波动，原文与急救升级保持一致。输出中有急救提醒也不能替代前端等待期间及时显示提醒的验收。

### C 规则草案、待审清单及计时占位（同日后续）

新增 [临床规则草案](CLINICAL-RULE-DRAFT.md)，作者明确为 AI，专业医学签署保持 pending。`config/clinical-review-backlog.json` 列出 24 类待审项，包括已启用的全部危险规则、生命体征缺口、历史/否定/主体/单位/药物情境；医学依据、审核人及日期留空，测试场景已列出。`python -m scripts.clinical_review_inventory` 本地扫描 54 条既有合成/公开材料，53 条出现待查话题，输出仅含数据集、ID、哈希和待办映射，不修改数据或声称发现患者异常。

低心率独立候选保留 `candidate_unverified`；确认记录后交接仍显示待专业复核。新增数值/单位/跨句对抗检查和保存、AI失败、确认、重启、交接回归。计时占位文件 `config/transport-timing.placeholder.json` 为 `runtime_enabled=false`，5 个阶段全部 null，不由运行时加载。此次无新远程模型请求；之前真实模型报告属于此前代码快照，新增改动的验证证据在 `docs/evidence/clinical-review/`。

原有产品限制仍适用：结构整理保留完整原文、来源标签不核实医生身份、关键词规则不是诊断、复杂语义需人工核对、不能把未命中解释为正常。通用传输协议测试不等于所有中转站实际验收。

## AIHubMix 低价语音闭环（2026-09-16）

当前专用 Key 的控制台额度、模型范围和 IP 限制均无异常，但 Key 的 `/v1/models` 可用列表中不含 `whisper-large-v3`、`whisper-1` 或其他 Whisper 模型，与前一日 ASR 403 且无正常计费日志的现象一致。因此不放宽 Key 权限，改用同一 Key 已开放的 `gemini-2.5-flash-lite` 原生音频理解接口。

单次授权的 6.892 秒合成 WAV 真实请求成功，返回文字命中“胸口疼”和“喘不上气”。AIHubMix 日志标记 Success、InputAudioTokens 221、扣费 `$0.000080`。本轮没有重试或切换模型；请求只含仓库合成资料，没有患者数据。全量 Python 回归为 **744 passed**，前端接口合同检查通过。详细证据见 [真实合成语音报告](evidence/real-aihubmix-gemini-audio-2026-09-16.md)。
