# 病历不归零 MVP

> 本页由 DZ 项目账本生成；真实记录保存在 `.dz/state.json`。
<!-- DZ-CURRENT-VIEW:3a7574fddfab48b5424d0a9e55bdd585440fb48a5165d7ef3667f2c8b976c78d -->

## 现在做到哪
- 当前情况：正在继续
- 产品情况：一部分已经检查
- 当前进度：已经做出，但还没完整检查
- 流程检查位置（不代替实际进度）：怎么做已确认
- 当前约定指纹：f0d4b7ca8e96
- 当前检查对象：working-tree@full-frontend-20260917 / local macOS; frontend 127.0.0.1:5173 + backend 127.0.0.1:18768; in-app Chromium / d89e35427656
- 下一步：把完整 elder-ui 前端接入当前本地优先双服务并在 5173 实测
- 等待内容：无
- 等待决定的风险：无
- 正在使用的动作通行条：无
- 阻塞原因：无
- 阻塞类型：无
- 恢复条件：无
- 最后更新：2026-09-17T05:59:45+00:00

## 现在按哪个版本做
- 想解决的事：已经确认；当前版本：docs/sdlc/intent.md
- 这次做什么、不做什么：已经确认；当前版本：docs/sdlc/spec-split-web-api-v2.md
- 准备怎么做和怎样试：已经确认；当前版本：docs/sdlc/plan-split-web-api-v2.md

## 工作概览
- 当前约定共 8 项；已检查 1 项；待检查 6 项；留到以后或取消 0 项。
- 旧约定下的 15 项保留在历史里，不算本次待办。
- 详细记录：[docs/sdlc/work-items.md](docs/sdlc/work-items.md)
- 共记录 9 个重要问题；其中 5 个还没有彻底解决。
- 问题记录：[docs/sdlc/issues.md](docs/sdlc/issues.md)

## 已知风险
- REAL-DEEPSEEK-C001：使用旧版本本地 DeepSeek 密钥做一次真实连通测试（low，accepted，动作失败）
- REAL-DEEPSEEK-C001-DIAG：诊断修复后再次运行一条 DeepSeek 合成样例（low，accepted，动作已完成）
- REAL-DEEPSEEK-HTTP-C001：当前项目真实文字 HTTP 链路请求（low，accepted，动作已完成）
- REAL-AIHUBMIX-MEDIA-HTTP-20260915：使用本地 AIHubMix Key 跑一次合成媒体真实 HTTP 自测（low，accepted，动作失败）
- REAL-AIHUBMIX-GEMINI-AUDIO-20260916：用低价 Gemini 轻量模型复测一次合成语音（low，accepted，动作已完成）
- RISK-CLOUD-BETA-20260916：创建内测版按量云资源并部署（medium，declined，用户没有同意）
- RISK-GITHUB-MAIN-SPLIT-20260916：用完整前后端内测版覆盖 GitHub 主干（medium，accepted，动作已完成）
- RISK-CLOUD-SPLIT-BETA-20260916：创建前端与后端两套按量云服务并完成内测验收（medium，declined，用户没有同意）

## 最近证据
以下是历史索引，不代表当前版本已通过；以相同检查对象和当前要求下的有效证据为准。
- E-W1A-COMMIT-20260916：提交 4ecbd92 在真实浏览器中从 5173 打开完整前端，跨端口登录和会话成功，18768 根路径只返回 API 身份，README 只引导前端入口。 — passed
- E-D1-COMMIT-20260916：当前确认的 v2 规格和方案完整定义单仓库双服务、前端入口、安全和数据边界及 R1-R13 验收。 — passed
- E-LOCAL-FRONTEND-ENTRY-20260917：现场从未运行的 file:// 错误入口恢复为双服务运行；浏览器当前选中 http://127.0.0.1:5173/，显示完整病历不归零前端；后端 18768 只返回 API 身份。 — passed
- E-D1-INAPP-20260917：当前确认的 v2 规格与方案仍定义前端唯一用户入口和独立后端 API，今天的运行复核没有改变产品约定。 — passed
- E-W1A-FULL-20260917：完整 elder-ui 已合入 5173；加密记录刷新后仍存在；5173 到 18768 登录与健康接口成功；36 项前端、765 项 Python 与 TypeScript 合同通过。 — passed

## 有没有漏掉要求
- 必做要求已登记。
- 漏记任务的要求：R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13
- 尚未通过的要求：R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13
- 旧任务待判断保留或调整：无
