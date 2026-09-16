# 本地优先内测版实施证据（2026-09-16）

## 对象与边界

- 对象：2026-09-16 当前未提交工作树。
- 环境：macOS 本机、Chromium 内核浏览器、Python 3.12、Node.js；模型调用使用测试替身，没有产生付费 AI 请求。
- 未覆盖：正式 veFaaS/TOS、真实手机、真实麦克风与摄像头、真实 DeepSeek/AIHubMix 请求、跨设备恢复。因此 W1–W5 只能标记为“已实现、待外部验证”。

## 自动化回归

| 检查 | 结果 |
|---|---|
| `.venv312/bin/python -m pytest -q` | `765 passed in 74.23s` |
| `node --test tests/*.test.cjs` | `30 passed` |
| `npm run check:contracts` | 通过 |
| `git diff --check` | 通过 |

Python 回归覆盖网站访问保护、会话/CSRF、无状态 AI 边界、媒体临时文件、TOS 授权、损坏备份拒绝、危险提醒保留和历史功能。Node 回归覆盖 AES-GCM 加密仓库、锁定、备份预览/损坏拒绝和界面安全规则。

## 浏览器实测

- 产品页面从独立前端 `http://127.0.0.1:5173/` 打开，页面配置指向独立后端 `http://127.0.0.1:18768`。
- 从前端页面执行跨端口登录后，后续会话请求能读到 HttpOnly Cookie；后端根路径只返回 `kind: api` 和 `frontend_hosted: false`。
- 建立加密仓库，保存合成健康记录，筛选、重载、锁定与重新解锁正常。
- 直接检查 IndexedDB，未发现健康正文明文；锁定页面不显示健康正文。
- 生成并恢复加密 `.bingli` 备份；备份中未发现健康正文、恢复口令或 API 密钥。
- 这一轮没有发送真实 AI 请求。

## 发布包检查

- `./build.sh` 成功。
- `crcmod` 被预构建为平台无关纯 Python wheel，未携带 macOS 扩展。
- 发布包内其他原生文件均经 `file` 确认为 Linux x86-64 ELF，适配目标 veFaaS Python 3.12 运行时。
- 云备份默认使用 veFaaS 绑定 IAM 角色的请求级临时凭证，不需要在生产环境保存长期 TOS AK/SK。

## 待外部验收

1. 创建隔离的 `bingli-beta` veFaaS 应用、私有 TOS 桶和最小权限 IAM 角色。
2. 部署后验证电脑关机仍可访问，并确认现有 DeepWe 地址/版本未变。
3. 在真实手机上验证文字、录音、照片、权限拒绝、断网、AI 同意、打印/PDF。
4. 发送可控的真实 DeepSeek/AIHubMix 请求，确认模型、超时、费用和失败文案。
5. 将密文备份上传到私有 TOS，从全新浏览器下载、预览、恢复，并检查损坏备份不覆盖当前数据。
