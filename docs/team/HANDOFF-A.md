# A 侧媒体后端交接

状态：**本地 MVP 媒体后端已组装并通过自动化验证；真实供应商、浏览器和手机仍未验收。**

实现基线：`fix/backend-api` 分支提交 `89a2ee2`（其父提交 `f328993`）；依赖 B 的 `backend/recognition.py`。

## 已交付

- `backend/media_store.py`：安全 ID、分片幂等、原件原子发布、真实类型魔数、SHA-256、不可变原件和安全读取。
- `backend/store.py`：媒体上传元数据、分片引用、识别尝试、状态/版本、重启中断恢复、完整文字、安全扫描和唯一 Event 关联。
- `backend/media_service.py`：调用 B，先保存完整文字，再危险扫描，再关联 Event；失败不删除原件，旧尝试不能覆盖新尝试。
- `backend/media_backend.py`：把文件、SQLite 和识别流程接成本地适配器；只有显式配置 `MEDIA_RECOGNITION_PROVIDER=mock` 才使用离线 Mock，未配置或配置真实 provider 时不会静默回退。
- `backend/server.py`：multipart 创建/分片/完成、能力发现、未配置边界禁写、媒体列表/详情/原件 Range 读取、202 识别和已保存文字的 `/link` 恢复入口。
- `scripts/backup.py`：SQLite 与被引用原件的联合备份与恢复校验、清单校验、空目录恢复和损坏/路径越界拒绝；它不承诺跨数据库与文件的严格原子快照。
- `docs/API.md`、`contracts/api.ts`、`frontend/README.md`：同步当前实际 HTTP 形状和前端接线规则。

## 接手后第一步

1. 确认工作区干净并切到 `fix/backend-api`，执行 `git show 89a2ee2`。
2. 复制 `.env.example` 为本地 `.env`，为 `MEDIA_UPLOAD_MAX_BYTES`、`MEDIA_UPLOAD_PART_MAX_BYTES`、`MEDIA_UPLOAD_MAX_PARTS` 设置明确正整数；不设置时媒体写入口会按设计关闭。
3. 启动 `python -m backend.run_local`，访问 `/health` 和 `/api/media/capabilities`。
4. 先运行 `python -m pytest -q` 与 `npm run check:contracts`，再按 [frontend/README.md](../../frontend/README.md) 接线。

## 当前可依赖的行为

原件只有在文件完整校验、数据库元数据提交后才显示 `save_status=saved`。新识别返回 `202` 后轮询详情；识别成功任务的重放返回 `200`，处理中重放仍为 `202`。机器初稿、危险扫描和 Event 链接分别持久化。识别失败、超长文字、无 Event 媒体仍可查询；交接快照会列出已保存但未关联的媒体附件。`/link` 复用已有成功初稿，不重复调用识别。

保留完整机器文字，不恢复 60 秒限制，不自动诊断或改药。显式配置 Mock 时必须在页面显示“离线 Mock 演示模式”；未命中危险词不代表医学正常。

## 验证结果

在 Python 3.12 环境执行：

```text
python -m pytest -q                         220 passed
npm run check:contracts                     passed
python -m backend.evaluate_mock             40/40 schema, 40/40 safety
python -m scripts.demo --out /tmp/...       passed
```

媒体专项还覆盖原件存储、状态机、识别编排、默认后端、HTTP 适配、能力发现、幂等/版本冲突和备份恢复。证据规则与未验证项见 `docs/evidence/media-a/README.md`。

## 明确未验证

- 真实 ASR/OCR 成功、费用、数据外传和供应商质量。
- 真实浏览器 Blob 播放、手机 MediaRecorder 编码、暂停/续录样本及真实多片音频合并。
- 大文件性能、实际机器资源边界、生产级公网鉴权和多家庭隔离。
- 临床安全、真实老人/医生试用。

接手者先运行全量测试，再做受控浏览器联调；不要把 Mock 或自动化 HTTP 结果写成真实识别通过。不要提交 `.env`、token、运行数据库或私人媒体。
