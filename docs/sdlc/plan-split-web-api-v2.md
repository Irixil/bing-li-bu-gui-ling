# 病历不归零·内测版实施方案（单仓库、双服务）

> 依据：`spec-split-web-api-v2.md`，以及 2026-09-16 项目所有者对“使用者打开前端，前后端保持两个独立端口/服务”的确认。

## 1. 最终形态

代码保留在同一 GitHub 仓库，但运行时是两个独立服务：

```text
使用者
  ↓ 只打开 Web 地址
frontend/  前端 Web（本地 5173）
  ↓ HTTPS + CORS + 安全会话
backend/   后端 API（本地 18768）
  ├─→ DeepSeek
  ├─→ AIHubMix
  └─→ 私有 TOS 密文备份
```

前端是唯一产品入口。后端的根路径不承担页面展示，仅提供服务状态和 `/api/*` 接口。

## 2. 本地启动

- `scripts/start_backend.py`：只启动后端 `127.0.0.1:18768`。
- `scripts/start_frontend.py`：只启动前端 `127.0.0.1:5173`。
- `scripts/start_dev.py`：一条命令同时管理两个进程，但两者仍监听不同端口；输出中把前端地址标成“请打开这里”，后端地址标成“程序接口，无需手动打开”。
- 前端通过 `window.__BINGLI_CONFIG__.apiBaseUrl` 或同等的非密密配置获得 API 地址；开发默认为 `http://127.0.0.1:18768`。

## 3. 前端改造

1. 新增统一配置文件，所有云端 `fetch` 从一个 API 基础地址构造 URL。
2. 本地 IndexedDB、Web Crypto、时间线、历史、删除、打印和本地备份仍在前端内完成，不改为后端存储。
3. 登录、AI 和私有备份授权请求使用 `credentials: 'include'`。
4. Service Worker 只缓存前端外壳；不缓存跨域 API 响应。
5. 前端配置中不出现 API 密钥、TOS 长期凭据或健康数据。

## 4. 后端改造

1. 后端不再托管 `frontend/` 静态文件；根路径只返回最小服务信息，`/health` 继续供机器检查。
2. `ALLOWED_ORIGIN` 是唯一允许携带凭证调用 API 的前端来源。
3. CORS 响应返回精确的 `Access-Control-Allow-Origin`、`Access-Control-Allow-Credentials: true`、`Vary: Origin`，不使用 `*`。
4. 预检请求明确允许必要的方法和请求头，不开放多余边界。
5. 状态变更仍同时要求有效会话、精确前端来源和 CSRF 令牌。
6. 本地两端口同属一个站点边界，可继续使用 `SameSite=Strict`。线上若为同一主域的 `app`/`api` 子域，也使用 `Secure` + `SameSite=Strict`；若只能使用不同站点的平台默认域名，必须专门验收 `SameSite=None; Secure` 和第三方 Cookie 限制，不得猜测成功。

## 5. 云端形态

新的云端范围与原单应用方案不同，需在本地完整联调后另行授权。预计资源是：

- 前端 Web 服务：`bingli-beta-web`，只保存和提供静态前端文件。
- 后端 API 应用：`bingli-beta-api`，运行 Python API、AI 转发和 TOS 短时授权。
- 私有 TOS Bucket：名称在授权前再确认，只保存 `.bingli` 密文备份。
- IAM 角色：只允许 API 应用访问该 Bucket 的备份前缀。
- 优先使用同一主域下的 `app` 和 `api` 子域；在没有可用主域时，用平台默认地址完成内测，但要如实记录 Cookie 兼容性。
- 不修改、重部署或删除现有 `deepwe-frontend`、`deepwe-backend` 应用。

## 6. 密钥和数据边界

- DeepSeek 和 AIHubMix 密钥只存在 API 应用的生产秘密配置中。
- TOS 使用绑定 IAM 角色的短期 STS 凭据，不在云端环境保存长期 AK/SK。
- 日志只记录请求关联号、耗时和白名单错误类型，不记录健康原文、媒体、模型原始响应或备份密文。
- 媒体在 API 应用中仅使用临时文件，请求成功或失败后删除。

## 7. 实施顺序

1. 把所有前端云请求收口到可配置 API 基础地址。
2. 完成后端精确 CORS、凭证和 CSRF 跨端口支持。
3. 建立前端、后端和双服务三个本地启动入口，同时更新 README。
4. 增加回归测试：前端 URL 构造、跨端口登录、Cookie、CORS 预检、非授权来源拒绝、API 根路径不提供前端。
5. 在真实浏览器中只打开 `5173`，完成本地仓库、网站登录、一次受控 AI 请求和备份接口联调。
6. 本地通过后，再以新的两服务资源清单申请云端创建授权。
7. 云端通过真实手机、AI、TOS 和恢复验收后，一次性提交 `frontend/`、`backend/`、启动脚本、测试和 README，再更新 GitHub `main`。

## 8. 验证组合

- Python 全量回归。
- Node 前端逻辑、加密仓库和 URL 构造回归。
- TypeScript 前后端合同检查。
- 真实浏览器从前端端口完成关键流程，并确认地址栏不是 API 地址。
- 非允许来源的登录和写请求失败；合法前端的登录、会话、AI 和备份请求成功。
- 发布候选版在密钥扫描、Linux 构建包、手机界面、真实 AI 和密文恢复都通过前，不宣称完成。
