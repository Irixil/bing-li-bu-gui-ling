# 后端选择性整合证据 · 2026-09-14

## 检查对象

- 分支：codex/backend-integration-2026-09-14
- 基线：feaf18204f29a674f7c9076920ffb01a804c2e59
- 受测提交：16c56cad71e84b888320a7992752e8ac6d0f95e6；复跑时工作树干净。
- 环境：macOS arm64，Python 3.12.13，pytest 8.4.2，Node 24.19.0，npm 11.17.0。
- 没有读取 .env 或凭据；没有调用真实模型；没有私人医疗资料。

## Public-case registry and runtime fixture

命令：python3.12 scripts/validate_task_d.py

结果：通过。登记表 3 条，运行夹具 3 条，测试矩阵 20 个用例；3 条病例各自的 CASE/TEXT 引用存在。registry.json 与 cases.json 的编号、来源类型、来源章节、中文输入和本地危险预期逐条一致。

命令：.venv312/bin/python -m scripts.demo --out /tmp/backend-integration-public-demo.json

结果：通过，provider=mock，1 位公开患者、3 段改编资料；每段原文可查询、幂等检查通过、记录状态为 recorded、历史各 3 条；危险提醒在确认后保留，数据库重新打开后可读。

干净提交复跑结果：通过，provider=mock，1 位公开患者、3 段改编资料。临时报告 SHA-256：e710abc26e8a716de2f35abd737574375881eb32d04d8bd7e245556fe3dacc91。该临时文件不含私人资料，但没有作为新的真实模型证据提交。

## 测试

命令：.venv312/bin/python -m pytest -q tests/test_task_d_retry.py tests/test_api_contract.py tests/test_offline_safety.py tests/test_backup.py tests/test_media_backup.py tests/test_process_restart_contract.py

结果：232 passed in 43.58s。首次在受限沙箱内运行时本机端口绑定被拒绝；获准仅使用 127.0.0.1 临时端口后，同一命令全部通过。第一次环境错误不计为代码失败。

命令：.venv312/bin/python -m pytest -q

提交前结果：728 passed, 1 skipped in 70.28s。干净提交 16c56ca 复跑结果：728 passed, 1 skipped in 69.74s。唯一跳过为 tests/test_dashscope_streaming.py 的真实 ffmpeg 转码检查；本机没有 ffmpeg。总收集 729 项。新增 TEXT-RETRY-01 另行复跑为 1 passed in 0.56s。

命令：npm run check:contracts；node --check frontend/app.js；node --check frontend/media.js；git diff --check

结果：全部通过。frontend/** 没有修改；前端脚本只做语法回归。

## Mock 评测

命令：.venv312/bin/python -m backend.evaluate_mock

结果：门槛通过仅指结构和指定安全 smoke。40/40 成功且 Schema 通过，6/6 指定危险样例通过；54 项断言失败、146 项未自动评估、15 个数据问题仍保留，不是业务语义或临床通过。

命令：.venv312/bin/python -m backend.evaluate_mock --dataset data/synthetic/c-model-smoke.json --strict

结果：11/11 成功，121 项自动断言通过，29 项未自动评估。人工语义复核未完成。

临时报告 SHA-256：
- 默认 Mock：5fc9e7814ad0d00922d314378fb8fa1526554d034ca8fe5602d9b53ce48d7f5b
- C 严格夹具：be5256cb503cbbab7ee8f017ba2519b35ccc4e3169eb8f7f4ba4385457ce12c4

## 未证明

- 本机没有 .env，没有重新调用真实文本模型、ASR 或 OCR。
- feaf182 的真实合成 WAV/PNG 156/156 只作为旧提交历史证据。
- 浏览器真实 WebM 的协议错误仍未修复；手机、通用格式、真实患者、临床准确率和生产部署未验证。
- P1 复杂医学图片只登记需求，本轮未实现。
