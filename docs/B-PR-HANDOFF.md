# B 后端合同 PR 交接稿

本文是 `fix/backend-api` 合并时的 PR 描述底稿。提交号和最终命令结果由 E 在创建 PR 或发布候选时填写；未实际执行的检查不得打勾。

## 改了什么

- 冻结比赛 MVP 后端栈：Python 3.12、标准库 HTTP、SQLite/WAL、JSON Schema、pytest；不在比赛前迁移框架、ORM 或数据库。
- 整理、核对、修订统一要求正整数 `expected_version`。
- 整理请求在缺少/非法版本时于模型调用前返回 `400 expected_version_must_positive_integer`。
- 整理请求在已知旧版本时于模型调用前返回 `409 stale_version`；数据库提交时仍保留事务内二次版本检查。
- CORS 预检明确允许 `GET, POST, OPTIONS` 及合同要求的请求头。
- 未预期服务端异常统一返回 `500 internal_server_error`，不向客户端暴露数据库路径或内部异常正文。
- 补全前端 TypeScript 合同：请求、响应、AI 草稿、历史、审计、交接材料和错误类型。
- 增加真实 HTTP、CORS 和后端进程重启合同回归。
- 写明 A/C/D/E 与 B 的双向交付、接口变更规则和比赛冻结门槛。

## A/C/D/E 怎么接

- A：以 `docs/API.md` 和 `contracts/api.ts` 为唯一接口合同；所有写入使用刚收到的版本；422 先解析 JSON，409 重新 GET；后端重启后重新读取 `/health`。
- C：保持 `Provider.complete_json` 接缝和现有成功/失败 HTTP 包装；不得直接写数据库或改变冻结字段。
- D：按 HTTP 可见行为验收；112 项测试是当前 B 分支的软件回归，不是临床验证或真实模型质量证明。
- E：先合并 B 的合同底座，再收口 C/D/A；在唯一发布候选提交上重新跑全部门槛，不能直接引用个人分支结果。

完整说明见 [B-INTEGRATION-HANDOFF.md](B-INTEGRATION-HANDOFF.md)。

## 已执行检查

当前 B 分支本地结果：

- [x] `python -m pytest -q`：112 passed；JUnit 见 `docs/evidence/b-backend-tests.xml`
- [x] `npm ci && npm run check:contracts`：TypeScript 合同严格编译
- [x] `python -m backend.evaluate_mock`：40/40，errors 0
- [x] `python -m scripts.demo`：passed true，Mock，1 位患者、3 段公开病例改编摘要
- [ ] A 的真实浏览器闭环、422、409、刷新和后端重启联调
- [ ] C 的真实模型成功与失败证据，或明确冻结 Mock 备用模式
- [ ] E 在唯一发布候选上的从停止状态启动和备份恢复

## 风险与未完成项

- 当前仓库没有前端实现，B 不能独立完成真实浏览器验收。
- 当前没有真实模型成功证据；Mock 必须明确标注为离线演示模式。
- 本地危险规则覆盖有限，未命中不代表医学正常。
- 当前服务仅为本机单人 MVP，不能直接作为公网多人医疗系统。
- 公开资料是 1 位公开论文病例的 3 段改编摘要，不是 3 位患者或真实用户试验。

## 合并信息

- 基线：`e1a5967`
- B 分支：`fix/backend-api`
- B 合并提交：`待填写`
- 发布候选提交：`待 E 填写`
