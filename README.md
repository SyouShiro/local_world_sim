# worldline-sim

基于 FastAPI + SQLite + WebSocket + 原生前端的世界线模拟器。

## 1. 运行前准备

### 1.1 创建并激活环境
```bash
conda activate local_world_sim
```

如果环境不存在：
```bash
conda create -n local_world_sim python=3.10 -y
conda activate local_world_sim
```

### 1.2 安装依赖
```bash
python -m pip install -r backend/requirements.txt
python -m pip check
```

如果你不想手动 `conda activate`，也可以用：
```bash
conda run -n local_world_sim python -m pip install -r backend/requirements.txt
conda run -n local_world_sim python -m pip check
```

### 1.3 配置环境变量
```bash
cp backend/.env.example backend/.env
```

至少修改：
- `APP_SECRET_KEY`：必须设置高熵随机值，用于加密存储 provider key。
- `CORS_ORIGINS`：前端地址白名单。

## 2. 启动步骤

### 2.1 启动后端
```bash
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

### 2.2 启动前端（另一个终端）
```bash
cd frontend
python -m http.server 5500
```

打开：`http://127.0.0.1:5500`

### 2.3 常用自检
```bash
python -m pytest
```

## 3. 核心 API（与 instruction 合同一致）
- Session：`/api/session/create`、`/start`、`/pause`、`/resume`、`/settings`
- Provider：`/api/provider/{session_id}/set`、`/models`、`/select-model`
- Branch：`/api/branch/{session_id}`、`/fork`、`/switch`
- Timeline/Message/Intervention：`/api/timeline/{session_id}`、`/api/message/{session_id}/last`、`/api/intervention/{session_id}`
- WebSocket：`/ws/{session_id}`

## 4. Provider 最小配置示例

### OpenAI
- Provider: `openai`
- API Key: `sk-...`
- Base URL: `https://api.openai.com`

### DeepSeek
- Provider: `deepseek`
- API Key: `sk-...`
- Base URL: `https://api.deepseek.com`

### Ollama
- Provider: `ollama`
- API Key: 可留空（本地 Ollama）
- Base URL: `http://localhost:11434`

### Gemini
- Provider: `gemini`
- API Key: `AIza...`
- Base URL: `https://generativelanguage.googleapis.com`

## 5. 测试与自检

### 5.1 自动化测试
```bash
python -m pytest
```

### 5.2 启动冒烟检查
1. 后端启动后访问 `http://127.0.0.1:8000/docs`，应返回 200 并能打开 Swagger。  
2. 前端页面可加载并显示 Session/Runner/WebSocket 状态卡片。

## 6. 验收步骤（建议顺序）
1. 创建 session（填写 world preset）。
2. 设置 provider，加载模型并选择模型。
3. 点击 start，确认 timeline 自动增长。
4. pause 后执行 fork，切到新分支并 resume。
5. 在新分支发送 intervention，确认下一轮演化受影响。
6. pause 后执行 delete last，确认只回滚当前分支最后一条，seq 仍连续。
7. 切回旧分支，确认旧分支数据未被污染。

## 7. 常见问题与排障

### 7.1 端口占用
- 后端端口冲突：修改 `uvicorn --port`。
- 前端端口冲突：修改 `http.server` 端口，并同步更新 `frontend/js/api.js` 的 `API_BASE`。

### 7.2 Ollama 无法连接
- 确认 Ollama 已启动并监听 `11434`。
- 确认模型已拉取，例如：`ollama pull llama3`。
- 若仍失败，检查防火墙或代理规则。

### 7.3 API key/模型加载失败
- 检查 key 是否有效、是否有额度/权限。
- 检查 Base URL 是否匹配 provider。
- 切换 provider 后必须重新加载并重新选择模型。

### 7.4 Runner 报错或反复 backoff
- 查看右侧日志与 WS `error` 事件。
- 检查 provider 网络与可用性。
- pause 后修正配置，再 resume。

### 7.5 删除最后一条返回 409
- 说明 runner 正在写入，先 pause 再重试 delete。

### 7.6 SQLite 数据冲突或脏状态
- 开发环境可删除 `worldline.db` 后重建。
- 测试环境使用临时数据库，不应与开发库混用。

## 8. 更新与升级（代码与依赖）

当仓库后续有更新时，推荐按下面顺序升级（避免“代码更新了但依赖没更新”的问题）。

### 8.1 更新代码（git）
```bash
git pull
```

如果你本地有未提交改动导致冲突，建议先用 `git status` 确认变更，再决定是否提交/暂存/丢弃。

### 8.2 更新 Python 依赖（pip）
```bash
conda run -n local_world_sim python -m pip install -r backend/requirements.txt --upgrade
conda run -n local_world_sim python -m pip check
```

说明：
- 本项目依赖以 `backend/requirements.txt` 为准，没有 lock 文件时，升级后若遇到兼容性问题，优先回退到可用版本并提交 PR 固化版本范围。

### 8.3 同步环境变量（.env）
更新后如果新增了环境变量：
1. 对比 `backend/.env.example` 与你的 `backend/.env`。
2. 将新增变量补到 `backend/.env`（不要把真实 key 提交到 git）。

### 8.4 数据库变化（SQLite）
后端启动时会自动 `create_all` 创建缺失的表，所以多数情况下升级不需要手动迁移。

如果你遇到明显的 schema 不兼容（例如启动时报错、表结构差异导致读写失败）：
- 开发环境最简单的恢复方式是备份后删除 `worldline.db` 让其重建（会丢失历史数据）。
- 若需要保留数据，建议用 `sqlite3` 导出/导入或补一个迁移脚本（后续可以再加 Alembic）。

## 8. 长期记忆模块（LightRAG 最小实现）

后端已内置可插拔的 Memory 模块（默认关闭）：
- 抽象层：`MemoryService` + `Embedder` + `VectorStore`
- 存储：SQLite `memory_items` + `memory_embeddings`
- 默认 Embedding：`deterministic`（离线、可复现）
- 可选 Embedding：`openai`（需配置 `EMBED_OPENAI_API_KEY`）

### 8.1 开关与环境变量
- `MEMORY_MODE=off|vector|hybrid`（默认 `off`，关闭时行为与旧版本一致）
- `MEMORY_MAX_SNIPPETS=8`
- `MEMORY_MAX_CHARS=4000`
- `EMBED_PROVIDER=deterministic|openai`
- `EMBED_MODEL=...`
- `EMBED_DIM=...`
- `EMBED_OPENAI_API_KEY=...`（仅 `openai` 时需要）

### 8.2 分支与回滚语义
- 检索严格按 `session_id + branch_id` 隔离。
- `fork`：新分支继承到 fork 点的历史 memory（随后各分支独立演化）。
- `DELETE /api/message/{session_id}/last`：会同时使该消息关联 memory 失效，避免后续召回已回滚内容。

### 8.3 排障建议
- `MEMORY_MODE=off` 可快速确认问题是否由 memory 引起。
- `EMBED_PROVIDER=openai` 但未配置 key 时，服务会降级回 `deterministic`，不会阻断主流程。
- 若 runner 正常但召回为空，优先检查：分支是否切换、查询文本是否过短、是否刚做过 delete-last 回滚。

### 8.4 性能建议
- 优先使用 `deterministic` 做本地开发与 CI，保证离线可测。
- 增大 `MEMORY_MAX_SNIPPETS` 会提升上下文覆盖，但也增加提示词长度与推理成本。
- `MEMORY_MAX_CHARS` 建议保持在 2k~6k 区间，根据模型上下文窗口调优。
