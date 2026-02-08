**给 Codex 的标准文档（可直接存为 `docs/memory_rag.md`）**

# 向量化记忆库（LightRAG / GraphRAG 风格）集成方案

## 0. 背景与目标
当前系统的“上下文”主要来自：
- 当前分支最近 N 条 `timeline_messages`
- `user_interventions` 中 pending 的干预文本
- `world_preset`

目标是新增可选的“长期记忆库（Memory/RAG）”，用于：
- 跨大量 tick 保持世界细节一致性（人物、地名、制度、因果链）
- 降低模型遗忘与自相矛盾
- 在 prompt 中以可控预算注入“相关历史事实/关系”

约束：
- 不破坏 `instruction.md` 既定 API 合同与目录结构
- 默认关闭，通过配置开关启用
- 任何外部 LLM/Embedding 调用都必须走后端，且不泄露 key（不入日志、不进前端存储）

## 1. 方案选型（从易到难）
### 1.1 “LightRAG 风格”最小可行（推荐先做）
核心：向量检索 + 简单结构化记忆。
- 数据源：`timeline_messages`、`user_interventions(consumed)`、可选的“每 K 轮摘要”
- 索引：对消息做 chunk（或整条）embedding，存入本地向量表
- 查询：每轮生成前构造 query embedding，取 top-k 相关片段
- 注入：追加到 PromptBuilder 的 “Long-term Memory” 段落，带引用来源（message id / seq）

优点：
- 快、实现成本低、效果立竿见影
难点：
- 需要控制噪声与 token 预算
- 需要合理 chunk / 去重 / 新鲜度权重

### 1.2 “GraphRAG-lite”逐步增强（第二阶段）
核心：实体-关系图谱 + 图扩展召回 + 引用支撑。
- 抽取：从消息中抽取实体与关系（LLM JSON 抽取或规则 + LLM 校正）
- 存储：nodes/edges 表 + 引用到原消息
- 召回：从最近上下文的实体出发做 1~2 跳扩展，组合关键子图
- 注入：以“事实列表 + 关系列表 + 引用”方式注入

优点：
- 对“世界设定一致性/关系链”更强
难点：
- 抽取质量与一致性、图膨胀、性能与复杂度显著上升

### 1.3 直接集成第三方 GraphRAG / LightRAG 库（第三阶段）
优点：
- 快速获得成熟范式
难点：
- 依赖重、版本不稳定风险、与现有数据模型/异步 runner 的适配成本高
建议：
- 先用“内部抽象接口”做内核，第三方库作为可替换实现

## 2. 推荐架构（可插拔 Memory 层）
新增一个内部抽象，不改变现有 API 合同：
- `MemoryService`（或 `memory_service.py`）
- `Embedder` 接口（OpenAI embedding / 本地 embedding）
- `VectorStore` 接口（SQLite 简单实现起步）
- `GraphStore` 接口（SQLite 表）

Runner 每轮生成调用链改为：
1. 读取 session/active branch
2. 拉取最近 N 条 timeline + pending interventions
3. `MemoryService.retrieve_context(...)` 返回 `memory_snippets`（可为空）
4. PromptBuilder 注入 memory_snippets
5. LLM generate
6. 持久化新 message
7. `MemoryService.on_message_persisted(...)` 异步索引（或同步但要限时）

关键要求：
- Memory 必须按 `session_id`、`branch_id` 隔离（至少 branch 级过滤）
- 默认关：`MEMORY_MODE=off`

## 3. 数据模型（SQLite 建议）
在 `backend/app/db/models.py` 增表（create_all 自动建表）：

### 3.1 向量记忆表
- `memory_items`
  - `id` TEXT PK
  - `session_id` TEXT
  - `branch_id` TEXT
  - `source_message_id` TEXT NULL
  - `source_seq` INTEGER NULL
  - `kind` TEXT 例如 `timeline_chunk|summary|fact`
  - `content` TEXT
  - `content_hash` TEXT（去重）
  - `created_at` DATETIME
- `memory_embeddings`
  - `memory_item_id` TEXT PK/FK
  - `dim` INTEGER
  - `vector_blob` BLOB（float32 bytes）或 JSON（起步可用 JSON，后续再优化）
  - `model` TEXT
  - `created_at` DATETIME

查询策略：
- 起步：在 Python 里对候选做余弦相似度（候选集控制在近期/同 branch/同 session）
- 后续：引入 `sqlite-vss` 或外部向量库

### 3.2 图谱表（GraphRAG-lite）
- `memory_entities`
  - `id` TEXT PK
  - `session_id` TEXT
  - `name` TEXT
  - `type` TEXT（person/place/org/concept）
  - `canonical` TEXT（可选）
- `memory_edges`
  - `id` TEXT PK
  - `session_id` TEXT
  - `src_entity_id` TEXT
  - `rel` TEXT
  - `dst_entity_id` TEXT
  - `evidence_message_id` TEXT
  - `created_at` DATETIME

## 4. 检索与注入策略（避免“越检索越乱”）
- 预算：`MAX_MEMORY_TOKENS` 或 `MAX_MEMORY_CHARS`
- 排序：相似度 * 新鲜度权重 * 去重
- 结构：
  - `Memory Snippets`：最多 K 条，每条 1~3 句，带引用
  - `Key Entities`：最多 M 个（Graph 模式）
  - `Relations`：最多 R 条（Graph 模式）

PromptBuilder 注入位置建议：
- 在 “Recent timeline” 之后，“Pending interventions” 之前或之后固定位置
- 明确要求模型把 Memory 当作“既有事实”，并在输出中保持一致

## 5. 关键难度与解决办法
- 难度：Embedding 成本与延迟  
  - 解法：异步索引、批处理、只索引 system_report、限制 chunk 数、缓存 hash 去重
- 难度：噪声与错误事实被固化  
  - 解法：仅索引“已确认的事实段”（可引入置信度）、或对 Memory 做“可撤销”（delete-last 同步删索引/标记失效）
- 难度：分支与回滚一致性  
  - 解法：Memory 必须按 branch 过滤；`delete-last` 时将对应 memory_item 标记 `is_deleted` 或写 tombstone
- 难度：图谱抽取质量  
  - 解法：JSON schema 抽取 + 校验；抽取失败降级为纯向量；限制每条消息最大新增实体/边数
- 难度：测试可重复  
  - 解法：提供 `DeterministicEmbedder`（hash -> 向量），完全离线可测

## 6. 测试计划（必须新增）
- `MemoryService.retrieve_context`：相关性排序、去重、branch 隔离
- `delete-last`：回滚后对应 memory 不再被召回
- `fork`：新分支默认只召回新分支内容（或允许从 parent 继承到 fork 点，需明确策略并测试）
- 失败降级：embedding/graph 抽取失败不影响 runner 主流程（只是不注入 memory）

## 7. 交付方式（不改既有 API 合同）
- 默认 `MEMORY_MODE=off`
- 启用后自动增强 prompt，无需前端改动
- 可选新增调试 API（如果要加必须是新增，不改现有端点）
  - `/api/memory/{session_id}/reindex`
  - `/api/memory/{session_id}/stats`
  - `/api/memory/{session_id}/search`

  