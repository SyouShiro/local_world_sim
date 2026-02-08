# instruction.md — LLM 世界线模拟器（前后端完整实现）给 Codex 的详细构建说明

## 0. 项目目标（你要构建什么）
构建一个**可运行的全栈网页应用**（前端 HTML/CSS/JS + 后端 Python），用于“LLM 驱动的世界进程模拟”。

核心体验：
1. 用户输入“世界设定（初始印象）”。
2. 系统进入自动演化：每轮生成一条“世界进程报告”（小说感 + 报告感），并把结果追加到时间线。
3. 下一轮必须在“上一轮完成后”再等待固定秒数（默认 5 秒）后触发（不是并发抢跑）。
4. 用户可随时：
   - 暂停/继续（停止/恢复自动生成）
   - 输入“干预文本”影响后续走向
   - 调整“每条消息代表的时间跨度”（默认“1个月”，允许任意文本）
   - 新建分支（branch）
   - 切换分支（tabs）
   - 删除上一条消息（回滚一步）
5. 支持多家模型提供商：OpenAI / Ollama / DeepSeek / Google Gemini。
   - 用户输入 API Key（如需要）
   - 用户通过“下拉选择”模型（模型列表后端拉取，不手输模型名）
   - 后端做 provider 协议适配，对前端暴露统一接口。

---

## 1. 非目标（明确不做）
- 不做多用户协同（先做单用户/单会话）
- 不做复杂权限系统
- 不做向量数据库/RAG（第一版）
- 不做生产级集群部署（先本地/单机可运行）

---

## 2. 技术栈与版本建议
- Python: 3.11+
- 后端框架: FastAPI + Uvicorn
- 前端: 原生 HTML + CSS + Vanilla JS（可用少量模块化）
- 持久化: SQLite（SQLAlchemy 2.x）
- 实时通道: WebSocket（前端收取“新消息/状态更新/错误”）
- 配置: pydantic-settings + `.env`
- HTTP 客户端: httpx（异步）
- 测试: pytest + anyio

---

## 3. 核心架构（必须按这个思路落地）

### 3.1 模块分层
1. **API 层**（FastAPI routers）
   - `/api/session/*`
   - `/api/provider/*`
   - `/api/branch/*`
   - `/api/message/*`
   - `/ws/{session_id}`
2. **应用服务层**（use-cases）
   - `SimulationService`
   - `BranchService`
   - `ProviderService`
3. **域模型层**（entities）
   - `WorldSession`
   - `Branch`
   - `TimelineMessage`
   - `UserIntervention`
   - `ProviderConfig`
4. **基础设施层**
   - DB Repositories
   - LLM Provider Adapters
   - Prompt Builder
   - Scheduler/Runner（异步循环）
5. **前端层**
   - 控制面板（provider/model/key，启动暂停，tick跨度）
   - 分支 tabs
   - 时间线展示区
   - 干预输入区
   - 状态日志区

### 3.2 时序约束（最关键）
自动循环伪逻辑：
```
while session.running:
    if generation_lock is busy:
        wait
    take snapshot of current branch state
    build prompt
    call llm provider -> get report text
    persist message (txn)
    push websocket event: message_created
    sleep(fixed_delay_seconds)   # 默认 5，且是在“生成完成后”睡眠
```
> 注意：是“完成后等待”而不是固定 cron。

### 3.3 并发与一致性
- 每个 session 一条 runner task（`asyncio.Task`）
- 每个 branch 写入时加“短事务 + 乐观检查”
- 删除上一条消息时，若 runner 正在写入：
  - 要么拒绝（返回 409）
  - 要么先暂停再删（推荐前者 + 前端提示）

---

## 4. 数据模型（SQLite）

## 4.1 表结构（建议）
### `world_sessions`
- `id` TEXT PK
- `title` TEXT
- `world_preset` TEXT NOT NULL
- `running` BOOLEAN NOT NULL DEFAULT 0
- `tick_label` TEXT NOT NULL DEFAULT '1个月'
- `post_gen_delay_sec` INTEGER NOT NULL DEFAULT 5
- `active_branch_id` TEXT NULL
- `created_at` DATETIME
- `updated_at` DATETIME

### `branches`
- `id` TEXT PK
- `session_id` TEXT FK -> world_sessions.id
- `name` TEXT NOT NULL
- `parent_branch_id` TEXT NULL
- `fork_from_message_id` TEXT NULL
- `is_archived` BOOLEAN NOT NULL DEFAULT 0
- `created_at` DATETIME

### `timeline_messages`
- `id` TEXT PK
- `session_id` TEXT FK
- `branch_id` TEXT FK
- `seq` INTEGER NOT NULL
- `role` TEXT NOT NULL   # 'system_report' | 'user_intervention'
- `content` TEXT NOT NULL
- `time_jump_label` TEXT NOT NULL
- `model_provider` TEXT
- `model_name` TEXT
- `token_in` INTEGER NULL
- `token_out` INTEGER NULL
- `created_at` DATETIME
- UNIQUE(`branch_id`, `seq`)

### `user_interventions`
- `id` TEXT PK
- `session_id` TEXT FK
- `branch_id` TEXT FK
- `content` TEXT NOT NULL
- `status` TEXT NOT NULL  # pending | consumed | canceled
- `created_at` DATETIME
- `consumed_at` DATETIME NULL

### `provider_configs`
- `id` TEXT PK
- `session_id` TEXT FK UNIQUE
- `provider` TEXT NOT NULL  # openai | ollama | deepseek | gemini
- `base_url` TEXT NULL
- `api_key_encrypted` TEXT NULL
- `model_name` TEXT NULL
- `extra_json` TEXT NULL
- `updated_at` DATETIME

---

## 5. 后端 API 设计（统一协议）

## 5.1 Session
### `POST /api/session/create`
请求：
```json
{
  "title": "我的世界",
  "world_preset": "一个蒸汽朋克世界...",
  "tick_label": "1个月",
  "post_gen_delay_sec": 5
}
```
响应：
```json
{
  "session_id": "...",
  "active_branch_id": "...",
  "running": false
}
```

### `POST /api/session/{id}/start`
- 启动 runner（若已运行则幂等）

### `POST /api/session/{id}/pause`
- 暂停 runner（幂等）

### `POST /api/session/{id}/resume`
- 恢复 runner（幂等）

### `PATCH /api/session/{id}/settings`
- 修改 `tick_label`, `post_gen_delay_sec`

---

## 5.2 Provider
### `POST /api/provider/{session_id}/set`
```json
{
  "provider": "openai",
  "api_key": "sk-...",
  "base_url": null,
  "model_name": "gpt-5.2"
}
```
- 后端验证 provider 可用性（最小探测）

### `GET /api/provider/{session_id}/models?provider=openai`
- 根据 provider + key/base_url 拉取模型列表
- 返回可选模型数组（给前端 dropdown）

### `POST /api/provider/{session_id}/select-model`
```json
{"model_name":"..."}
```

---

## 5.3 Branch & Timeline
### `POST /api/branch/{session_id}/fork`
```json
{
  "source_branch_id": "...",
  "from_message_id": "..."   // 可选，默认当前最后一条
}
```
- 新建分支，复制“逻辑历史指针”（不复制全文可选）
- 返回新 branch 信息

### `POST /api/branch/{session_id}/switch`
```json
{"branch_id":"..."}
```

### `DELETE /api/message/{session_id}/last?branch_id=...`
- 删除最后一条消息（回滚一步）
- 删除后 seq 连续

### `POST /api/intervention/{session_id}`
```json
{
  "branch_id":"...",
  "content":"在北方出现一场持续3个月的旱灾"
}
```
- 入队 pending，下一轮 prompt 注入

### `GET /api/timeline/{session_id}?branch_id=...&limit=200`
- 拉取当前分支消息

---

## 5.4 WebSocket 事件（前端订阅）
连接：`/ws/{session_id}`

服务端推送 JSON：
```json
{"event":"session_state","running":true}
{"event":"message_created","branch_id":"...","message":{...}}
{"event":"branch_switched","active_branch_id":"..."}
{"event":"error","code":"PROVIDER_TIMEOUT","message":"..."}
{"event":"models_loaded","provider":"openai","models":["..."]}
```

---

## 6. Prompt 设计（世界演化稳定性关键）

## 6.1 System Prompt（模板）
- 明确文风：`世界进程报告`
- 每次输出结构：
  1. 时间推进（基于 tick_label）
  2. 关键事件（2~5条）
  3. 因果解释
  4. 对下一阶段的风险/趋势预测
- 风格要求：客观、简洁、有连续性，避免每轮重置

## 6.2 User Prompt（每轮）
拼接内容：
- 世界初始设定
- 当前 branch 最近 N 条摘要（建议 8~20 条）
- 待消费的干预文本（pending interventions）
- 当前 tick_label（如“1个月”）
- 输出格式约束（建议 JSON 或固定 markdown 模板）

## 6.3 输出格式策略
优先要求 JSON：
```json
{
  "title":"第12期世界进程",
  "time_advance":"1个月",
  "summary":"...",
  "events":[...],
  "risks":[...]
}
```
若解析失败，则 fallback 为纯文本并记录 `parse_error=true`。

---

## 7. LLM Provider 适配层（统一接口）

定义抽象接口：
```python
class LLMAdapter(Protocol):
    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]: ...
    async def generate(self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool=False) -> LLMResult: ...
```

## 7.1 OpenAIAdapter
- list_models: `GET /v1/models`
- generate: 优先 `POST /v1/responses`（新项目推荐）；或可提供 chat-completions 兼容模式
- Bearer 鉴权

## 7.2 DeepSeekAdapter
- OpenAI 兼容风格
- base_url 默认 `https://api.deepseek.com`（可兼容 `/v1`）
- list_models: `GET /models`
- generate: `POST /chat/completions`（支持 stream）

## 7.3 OllamaAdapter
- 本地默认 base_url: `http://localhost:11434/api`
- list_models: `GET /api/tags`
- generate: `POST /api/chat`（推荐）或 `/api/generate`
- 本地通常无需鉴权（云端需 key）

## 7.4 GeminiAdapter
- REST endpoint: `https://generativelanguage.googleapis.com`
- list_models: `GET /v1beta/models`
- generate: `POST /v1beta/models/{model}:generateContent`
- API key 放请求参数或 header（后端处理，不在前端暴露）

---

## 8. Runner 设计（可暂停、可恢复、可切分支）

## 8.1 状态机
- `IDLE`（未运行）
- `RUNNING`
- `PAUSED`
- `ERROR_BACKOFF`（连续失败指数退避）
- `STOPPED`

## 8.2 失败重试
- provider 超时/429/5xx：
  - 首次重试 1s
  - 二次 2s
  - 三次 4s
  - 超过阈值进入 `ERROR_BACKOFF` 并推送前端告警
- 用户手动 resume 可强制离开 backoff

## 8.3 分支切换行为
- session 有 `active_branch_id`
- runner 每次循环读取 active_branch 快照
- 若中途切换分支，下一轮才生效（避免跨分支污染）

---

## 9. 前端页面设计（单页应用）

## 9.1 布局
- 左侧：控制面板
  - 世界标题、tick_label、post_gen_delay_sec
  - provider 选择 + API key + base_url + 模型下拉
  - Start / Pause / Resume
- 中间：分支 tabs（可新增、切换、删除）
- 主区：timeline 列表（按 seq）
- 底部：干预输入框 + 发送按钮
- 右侧（可选）：系统日志（状态/错误）

## 9.2 交互规则
- provider 改变后，点击“加载模型”按钮，更新下拉框
- 模型未选定禁止启动
- pause 状态允许：
  - fork
  - delete last
  - 修改 tick_label
- running 状态下删除最后一条提示风险，建议先 pause

## 9.3 前端状态管理
- 使用一个 `store` 对象（非框架）维护：
  - `session`
  - `branches`
  - `activeBranchId`
  - `timelineByBranch`
  - `connectionState`
- WebSocket 事件驱动更新，HTTP 仅用于命令请求

---

## 10. 安全与隐私（必须做）
1. API key 只到后端，不写进前端本地存储（至少默认不落地）
2. API key 不放 URL query，不打印到日志
3. 后端日志做敏感字段脱敏（`sk-***`）
4. CORS 限制为本地 origin（开发）+ 可配置
5. 输入长度限制与基本清洗，防止 prompt 注入跨层扩散
6. 为 provider 调用设置超时（如 90s）和最大并发（单 session 1）

---

## 11. 目录结构（Codex 必须按此生成）
```text
worldline-sim/
  backend/
    app/
      main.py
      api/
        session.py
        provider.py
        branch.py
        timeline.py
        websocket.py
      core/
        config.py
        logging.py
        security.py
      db/
        base.py
        models.py
        session.py
        migrations/ (可选)
      repos/
        session_repo.py
        branch_repo.py
        message_repo.py
        provider_repo.py
      services/
        simulation_service.py
        branch_service.py
        provider_service.py
        prompt_builder.py
        runner.py
      providers/
        base.py
        openai_adapter.py
        deepseek_adapter.py
        ollama_adapter.py
        gemini_adapter.py
      schemas/
        common.py
        session.py
        provider.py
        branch.py
        timeline.py
      utils/
        time_utils.py
        crypto.py
    tests/
      test_session_api.py
      test_branching.py
      test_runner_pause_resume.py
      test_provider_adapters.py
    requirements.txt
    .env.example
  frontend/
    index.html
    css/
      app.css
    js/
      api.js
      ws.js
      store.js
      ui.js
      app.js
  instruction.md
  README.md
```

---

## 12. 关键实现细节（防 bug 清单）

## 12.1 序号一致性
- 新消息 `seq = max(seq)+1` 在事务中计算，防并发重复
- 删除最后一条后不允许留下空洞（下次仍然 max+1）

## 12.2 事件消费
- `user_interventions` 只消费 `pending`
- 一条干预只消费一次；失败回滚时状态不变

## 12.3 启停幂等
- 多次 start 不创建多 runner
- pause/resume 重复调用不报错

## 12.4 断线恢复
- WebSocket 断线后前端自动重连（指数退避）
- 重连后调用 timeline API 拉取差量（或全量最近200条）

## 12.5 provider 切换
- 切 provider 后强制重新选择模型
- 未选择模型禁止生成

---

## 13. 测试计划（最低验收）

## 13.1 单元测试
- PromptBuilder：干预文本注入顺序正确
- BranchService：fork/switch/delete-last 行为正确
- ProviderAdapter：mock 响应解析正确（含异常）
- Runner：pause/resume 后循环行为正确

## 13.2 集成测试
1. 创建 session -> 设置 provider/model -> start -> 收到消息
2. 在运行中发送 intervention -> 下一轮出现影响
3. fork 新分支 -> 切换 -> 继续生成不污染旧分支
4. delete last -> seq 连续
5. provider API 失败 -> 重试与 backoff 生效

## 13.3 手工验收（E2E）
- 10 分钟连续运行无崩溃
- 可以在任意时刻暂停/恢复
- 分支切换视觉与数据一致
- 模型列表来自后端动态拉取而非硬编码

---

## 14. README 需要包含
- 本地运行步骤（backend + frontend）
- `.env` 配置说明
- 各 provider 的最小配置示例
- 常见错误排查（端口占用、ollama 未启动、API key 无效）

---

## 15. `.env.example`（示例）
```env
APP_ENV=dev
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
DB_URL=sqlite+aiosqlite:///./worldline.db

# default runtime
DEFAULT_POST_GEN_DELAY_SEC=5
DEFAULT_TICK_LABEL=1个月

# optional provider defaults
OPENAI_BASE_URL=https://api.openai.com
DEEPSEEK_BASE_URL=https://api.deepseek.com
OLLAMA_BASE_URL=http://localhost:11434
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
```

---

## 16. 代码风格约束（Codex 必须遵守）
1. 类型注解完整（mypy 友好）
2. 关键函数必须有 docstring（简洁、准确）
3. 统一异常模型与错误码
4. 不写无意义超长注释；注释解释“为什么”，不是“是什么”
5. 所有外部 I/O（DB/HTTP）都要显式 timeout / error handling
6. 返回 JSON 结构稳定，不随意变字段名

---

## 17. 第一版里程碑（建议）
- M1：后端骨架 + session + timeline + mock provider
- M2：接入 OpenAI + Ollama
- M3：接入 DeepSeek + Gemini + 模型列表
- M4：分支/回滚完整 + 前端交互打磨 + 测试补齐

---

## 18. 你最终要交付给用户的内容（Codex 输出）
1. 完整可运行源码（前后端）
2. `requirements.txt`
3. `.env.example`
4. `README.md`
5. 基础测试用例
6. 启动命令与演示流程

---

## 19. 一条可执行的“完成定义”（Definition of Done）
当用户可以：
- 输入世界设定并启动；
- 每轮在上一轮完成后约 5 秒生成新报告；
- 随时暂停、恢复；
- 发送干预并在后续体现；
- 创建/切换分支并独立演化；
- 删除上一条消息回滚；
- 切换 provider 并通过下拉选择模型；
且系统在常见异常（网络失败、模型不可用）下不崩溃并给出可读错误提示，
则判定完成。
