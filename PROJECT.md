# 病历不归零 MVP

> 本页由 DZ 项目账本生成；真实记录保存在 `.dz/state.json`。
<!-- DZ-CURRENT-VIEW:5830ae59a3baa7dfce7f2c1efbf6d3bd2b5ff68ea9193cff1ae5154d6e4ea34c -->

## 现在做到哪
- 当前情况：缺少执行条件
- 产品情况：尚未判断
- 当前进度：缺少执行条件
- 流程检查位置（不代替实际进度）：先把想法说清楚
- 当前约定指纹：无
- 当前检查对象：无
- 下一步：无
- 等待内容：无
- 等待决定的风险：无
- 正在使用的动作通行条：无
- 阻塞原因：当前工作区没有可用于真实语音识别的 DashScope ASR key，也没有支持图片的 OCR endpoint/model/key；代码、FFmpeg、离线完整链路和真实文字链路均已跑通，继续调用真实媒体服务会要求不存在的外部凭据
- 阻塞类型：missing_external_condition
- 恢复条件：提供 DashScope ASR key，以及支持图片的 OCR endpoint、model 和 key（只写入本地 0600 .env）
- 最后更新：2026-09-14T15:40:11+00:00

## 现在按哪个版本做
- 想解决的事：还没写下来；当前版本：docs/sdlc/intent.md
- 这次做什么、不做什么：还没写下来；当前版本：docs/sdlc/spec.md
- 准备怎么做和怎样试：还没写下来；当前版本：docs/sdlc/plan.md

## 工作概览
- 当前约定共 0 项；已检查 0 项；待检查 0 项；留到以后或取消 0 项。
- 旧约定下的 0 项保留在历史里，不算本次待办。
- 详细记录：[docs/sdlc/work-items.md](docs/sdlc/work-items.md)
- 共记录 6 个重要问题；其中 3 个还没有彻底解决。
- 问题记录：[docs/sdlc/issues.md](docs/sdlc/issues.md)

## 已知风险
- REAL-DEEPSEEK-C001：使用旧版本本地 DeepSeek 密钥做一次真实连通测试（low，accepted，动作失败）
- REAL-DEEPSEEK-C001-DIAG：诊断修复后再次运行一条 DeepSeek 合成样例（low，accepted，动作已完成）
- REAL-DEEPSEEK-HTTP-C001：当前项目真实文字 HTTP 链路请求（low，accepted，动作已完成）

## 最近证据
以下是历史索引，不代表当前版本已通过；以相同检查对象和当前要求下的有效证据为准。
- 暂无记录。

## 有没有漏掉要求
- 必做要求尚未形成可核对的清单；不能据此声称全部完成。
- 漏记任务的要求：无
- 尚未通过的要求：无
- 旧任务待判断保留或调整：无
