# 病历不归零 MVP

> 本页由 DZ 项目账本生成；真实记录保存在 `.dz/state.json`。
<!-- DZ-CURRENT-VIEW:be3f7a3bb5983bd907b35d16c2751fac930163ccfcb997a0a12e94283ce2c45b -->

## 现在做到哪
- 当前情况：正在继续
- 产品情况：一部分已经检查
- 当前进度：暂无可继续执行的工作
- 流程检查位置（不代替实际进度）：怎么做已确认
- 当前约定指纹：ee4ebac1a58c
- 当前检查对象：8ba7033 / local macOS; frontend 127.0.0.1:5173 + backend 127.0.0.1:18768; isolated Mock browser 5174/18769; Python 770; Node 38; TypeScript passed / f92174d544e5
- 下一步：实现 W1C：删除前端 AI 确认和家属绑定依赖，连通保存、自动识别、自动建记录和就诊报告，然后全量与浏览器验证。
- 等待内容：无
- 等待决定的风险：无
- 正在使用的动作通行条：无
- 阻塞原因：无
- 阻塞类型：无
- 恢复条件：无
- 最后更新：2026-09-18T12:25:41+00:00

## 现在按哪个版本做
- 想解决的事：已经确认；当前版本：docs/sdlc/intent.md
- 这次做什么、不做什么：已经确认；当前版本：docs/sdlc/spec-minimal-loop-v4.md
- 准备怎么做和怎样试：已经确认；当前版本：docs/sdlc/plan-minimal-loop-v4.md

## 工作概览
- 当前约定共 3 项；已检查 1 项；待检查 0 项；留到以后或取消 2 项。
- 旧约定下的 25 项保留在历史里，不算本次待办。
- 详细记录：[docs/sdlc/work-items.md](docs/sdlc/work-items.md)
- 共记录 11 个重要问题；其中 7 个还没有彻底解决。
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
- RISK-GITHUB-MAIN-DEVICE-BINDING-20260917：将单口令设备绑定修复发布到 GitHub main（medium，accepted，动作已完成）

## 最近证据
以下是历史索引，不代表当前版本已通过；以相同检查对象和当前要求下的有效证据为准。
- E-W1D-MINIMAL-LOOP-8BA7033：提交 8ba7033 已移除前端 AI 确认与家属绑定依赖，媒体保存后自动识别并建立记录；Python 770、Node 38、TypeScript 通过，隔离浏览器生成就诊交接材料。 — passed
- E-W1E-R1-8BA7033：隔离浏览器只输入本机恢复口令，点击保存并识别时 confirm 调用为 0，无家属绑定，自动启动识别。 — passed
- E-W1E-R2-8BA7033：本地加密与媒体回归通过；隔离浏览器保存 1 张原图，识别后自动建立 1 条已关联记录并可读取。 — passed
- E-W1E-R3-8BA7033：隔离浏览器生成的就诊交接材料包含识别原文、原件保存/识别/关联状态和打印入口。 — passed
- E-W1E-R4-8BA7033：前端合同测试和源码扫描确认无设备激活、家属绑定和 AI 确认流程；失败分支保留原件与可重试状态。 — passed

## 有没有漏掉要求
- 必做要求已登记。
- 漏记任务的要求：无
- 尚未通过的要求：无
- 旧任务待判断保留或调整：W1@bb2619691d27@f0d4b7ca8e96, W2@bb2619691d27@f0d4b7ca8e96, W3@bb2619691d27@f0d4b7ca8e96, W4@bb2619691d27@f0d4b7ca8e96, W5@bb2619691d27@f0d4b7ca8e96, W6@bb2619691d27@f0d4b7ca8e96, D1@bb2619691d27@f0d4b7ca8e96, W1A@f0d4b7ca8e96, W1B
