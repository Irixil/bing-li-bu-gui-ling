# 病历不归零 MVP

> 本页由 DZ 项目账本生成；真实记录保存在 `.dz/state.json`。
<!-- DZ-CURRENT-VIEW:54d85a60e3be898c8c07c9495d61e98ae1068f04934d80270377245d43b23da5 -->

## 现在做到哪
- 当前情况：正在继续
- 产品情况：已经做出，但还没完整检查
- 当前进度：已经做出，但还没完整检查
- 流程检查位置（不代替实际进度）：怎么做已确认
- 当前约定指纹：f0d4b7ca8e96
- 当前检查对象：无
- 下一步：把本地优先内测版改为单仓库双服务：前端 5173、后端 18768，完成跨端口安全联调和完整回归。
- 等待内容：无
- 等待决定的风险：无
- 正在使用的动作通行条：无
- 阻塞原因：无
- 阻塞类型：无
- 恢复条件：无
- 最后更新：2026-09-16T15:52:23+00:00

## 现在按哪个版本做
- 想解决的事：已经确认；当前版本：docs/sdlc/intent.md
- 这次做什么、不做什么：已经确认；当前版本：docs/sdlc/spec-split-web-api-v2.md
- 准备怎么做和怎样试：已经确认；当前版本：docs/sdlc/plan-split-web-api-v2.md

## 工作概览
- 当前约定共 8 项；已检查 0 项；待检查 7 项；留到以后或取消 0 项。
- 旧约定下的 15 项保留在历史里，不算本次待办。
- 详细记录：[docs/sdlc/work-items.md](docs/sdlc/work-items.md)
- 共记录 7 个重要问题；其中 4 个还没有彻底解决。
- 问题记录：[docs/sdlc/issues.md](docs/sdlc/issues.md)

## 已知风险
- REAL-DEEPSEEK-C001：使用旧版本本地 DeepSeek 密钥做一次真实连通测试（low，accepted，动作失败）
- REAL-DEEPSEEK-C001-DIAG：诊断修复后再次运行一条 DeepSeek 合成样例（low，accepted，动作已完成）
- REAL-DEEPSEEK-HTTP-C001：当前项目真实文字 HTTP 链路请求（low，accepted，动作已完成）
- REAL-AIHUBMIX-MEDIA-HTTP-20260915：使用本地 AIHubMix Key 跑一次合成媒体真实 HTTP 自测（low，accepted，动作失败）
- REAL-AIHUBMIX-GEMINI-AUDIO-20260916：用低价 Gemini 轻量模型复测一次合成语音（low，accepted，动作已完成）
- RISK-CLOUD-BETA-20260916：创建内测版按量云资源并部署（medium，declined，用户没有同意）

## 最近证据
以下是历史索引，不代表当前版本已通过；以相同检查对象和当前要求下的有效证据为准。
- E-W4-LOCAL-20260916：时间线、筛选、历史、删除与浏览器打印实现已通过代码回归；六条记录、真实设备和导出 PDF 验收尚未完成。 — unverified
- E-W5-LOCAL-20260916：设备端密文备份、损坏拒绝、隔离预览及 TOS 临时授权实现已通过本地回归；私有 TOS 和全新浏览器恢复尚未验收。 — unverified
- E-W1A-SPLIT-20260916：前端 5173 显示完整内测页面并配置到后端 18768；跨端口登录和 Cookie 成功；后端根地址返回 api/frontend_hosted false；README 只引导打开前端。 — passed
- E-W1-SPLIT-20260916：本地双端口、精确来源限制、会话和独立后端发布包通过；线上地址、手机和 DeepWe 不变性尚未部署验收。 — unverified
- E-D1-SPLIT-20260916：已接受的前后端分离规格和实施方案定义了双服务拓扑、前端入口、安全边界、数据流与 R1-R13 验收。 — passed

## 有没有漏掉要求
- 必做要求已登记。
- 漏记任务的要求：R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13
- 尚未通过的要求：R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13
- 旧任务待判断保留或调整：无
