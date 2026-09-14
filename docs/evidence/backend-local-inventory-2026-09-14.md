# 后端 worktree 本机资源盘点 · 2026-09-14

检查位置：病历不归零-MVP-backend-handoff
检查原则：只检查文件名、工具版本和依赖可导入性；没有读取或输出任何密钥值，也没有进入前端 worktree。

## 已有内容

- 基线代码：feaf182，已创建 codex/backend-integration-2026-09-14。
- 数据：1 位公开发表病例的 3 段中文改编摘要；合成文字评测；合成 selftest WAV、PNG 与对应文字。
- 历史证据：后端、模型、安全、媒体、浏览器和在线自测记录。
- 系统工具：Python 3.12.13、Node 24.19.0、npm 11.17.0、Git 2.50.1。

## 当前缺少

- 没有 .env；只存在 .env.example。
- 初始没有项目虚拟环境；用户确认后已创建 .venv312，并按 requirements-dev.txt 安装锁定依赖。
- 已按 package-lock.json 安装 TypeScript；node_modules 保持 Git 忽略。
- Python 3.12 环境可导入 pytest 8.4.2、jsonschema 4.25.1、websockets 15.0.1。
- 没有发现 ffmpeg。

## 对本轮的影响

本 worktree 已能运行 Python 回归和 TypeScript 合同检查。没有可见在线配置，因此本轮没有重新运行真实模型；feaf182 的在线结果只作为绑定旧提交和合成输入的历史证据。缺少 ffmpeg 导致 1 项 DashScope streaming 真实转码测试跳过，其余完整 Python 回归通过。
