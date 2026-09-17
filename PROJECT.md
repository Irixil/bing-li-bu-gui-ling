# 病历不归零 MVP

> 本页由 DZ 项目账本生成；真实记录保存在 `.dz/state.json`。
<!-- DZ-CURRENT-VIEW:b92e8e4bc729957f484d4d8e3046219c951a5ac4c8b14707c9398f75823e6ff6 -->

## 现在做到哪
- 当前情况：正在继续
- 产品情况：一部分已经检查
- 当前进度：暂无可继续执行的工作
- 流程检查位置（不代替实际进度）：怎么做已确认
- 当前约定指纹：3a6377f04c4a
- 当前检查对象：bd4a069 / local macOS; frontend 127.0.0.1:5173 + backend 127.0.0.1:18768; isolated ego-browser 5174/18769 / d4772c034d2a
- 下一步：先修订规格和计划，再实现设备绑定、浏览器实测并发布 GitHub 主干
- 等待内容：无
- 等待决定的风险：无
- 正在使用的动作通行条：无
- 阻塞原因：无
- 阻塞类型：无
- 恢复条件：无
- 最后更新：2026-09-17T11:36:03+00:00

## 现在按哪个版本做
- 想解决的事：已经确认；当前版本：docs/sdlc/intent.md
- 这次做什么、不做什么：已经确认；当前版本：docs/sdlc/spec-device-binding-v3.md
- 准备怎么做和怎样试：已经确认；当前版本：docs/sdlc/plan-device-binding-v3.md

## 工作概览
- 当前约定共 1 项；已检查 1 项；待检查 0 项；留到以后或取消 0 项。
- 旧约定下的 23 项保留在历史里，不算本次待办。
- 详细记录：[docs/sdlc/work-items.md](docs/sdlc/work-items.md)
- 共记录 10 个重要问题；其中 6 个还没有彻底解决。
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
- RISK-GITHUB-MAIN-FULL-FRONTEND-20260917：将完整前端修复提交快进发布到 GitHub main（medium，declined，用户没有同意）

## 最近证据
以下是历史索引，不代表当前版本已通过；以相同检查对象和当前要求下的有效证据为准。
- E-D1-INAPP-20260917：当前确认的 v2 规格与方案仍定义前端唯一用户入口和独立后端 API，今天的运行复核没有改变产品约定。 — passed
- E-W1A-FULL-20260917：完整 elder-ui 已合入 5173；加密记录刷新后仍存在；5173 到 18768 登录与健康接口成功；36 项前端、765 项 Python 与 TypeScript 合同通过。 — passed
- E-W1A-FULL-FF62D82：提交 ff62d82 包含完整 elder-ui；加密记录刷新后仍存在；5173 到 18768 登录与健康接口成功；36 项前端、765 项 Python 与 TypeScript 合同通过。 — passed
- E-W1B-DEVICE-BINDING-BD4A069：提交 bd4a069 取消老人端第二密码，设备绑定与刷新复用通过，隔离浏览器完成建库、保存、刷新解锁和设置状态检查 — passed
- E-W1B-DEVICE-BINDING-BD4A069-FINAL：提交 bd4a069 取消老人端第二密码，设备绑定与刷新复用通过，隔离浏览器完成建库、保存、刷新解锁和设置状态检查 — passed

## 有没有漏掉要求
- 必做要求已登记。
- 漏记任务的要求：R1, R9
- 尚未通过的要求：R1, R9
- 旧任务待判断保留或调整：W1@bb2619691d27@f0d4b7ca8e96, W2@bb2619691d27@f0d4b7ca8e96, W3@bb2619691d27@f0d4b7ca8e96, W4@bb2619691d27@f0d4b7ca8e96, W5@bb2619691d27@f0d4b7ca8e96, W6@bb2619691d27@f0d4b7ca8e96, D1@bb2619691d27@f0d4b7ca8e96, W1A@f0d4b7ca8e96
