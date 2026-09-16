// 非密密运行配置。本地 5173 会自动连接同主机的 18768。
// 正式前端服务会在响应本文件时填入独立 API 地址。
globalThis.__BINGLI_CONFIG__ = globalThis.__BINGLI_CONFIG__ || { apiBaseUrl: '' };
