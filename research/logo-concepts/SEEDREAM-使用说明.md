# Seedream 生成说明

本目录的 `generate_seedream.py` 会生成三张 Q 版山羊角色探索图。脚本不会保存或输出 API Key。

## 使用

```bash
export ARK_API_KEY='你的豆包 API Key'
python3 research/logo-concepts/generate_seedream.py
```

如果 Key 已在另一个终端设置，当前对话进程不会自动继承。推荐存入 macOS 钥匙串，这样之后可以直接在对话里调用：

```bash
read -s ARKKEY; security add-generic-password -U -a "$USER" -s codex-seedream -w "$ARKKEY"; unset ARKKEY
```

脚本会优先读取环境变量，其次读取钥匙串服务 `codex-seedream`。

如果你的账号使用其他 Seedream 模型名，可以临时覆盖：

```bash
export SEEDREAM_MODEL='你的模型名'
```

生成结果会写入 `research/logo-concepts/seedream/`。如果账号所在区域使用不同的方舟地址，可以临时覆盖 `ARK_ENDPOINT`。
