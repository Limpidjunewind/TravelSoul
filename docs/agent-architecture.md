# Nomie Agent 架构设计

基于 DeerFlow 框架进行旅行规划场景的定制化开发。

---

## 整体架构

```
用户 → 前端 → LangGraph Server
                    │
                Lead Agent（对话 + 编排）
                    │
        ┌───────────┼───────────┬───────────┐
        ↓           ↓           ↓           ↓
   Flight Agent  Hotel Agent  Itinerary   Tips Agent
                              Agent
```

- Lead Agent 负责对话、派发任务、汇总结果
- 4 个 Sub-agent 并行执行，互不依赖
- 所有通信通过 LangGraph Server 自带的 SSE 接口完成，不需要自己写 API

---

## Lead Agent

### 职责

1. **聊天阶段**：和用户对话，收集旅行需求（目的地、日期、人数、预算、偏好）
2. **触发阶段**：用户说"开始搜索"后，将需求打包，固定派发 4 个 sub-agent
3. **汇总阶段**：4 个 sub-agent 返回结果后，整理汇总返回给前端

### System Prompt 结构（沿用 DeerFlow 模板）

```
<role>           旅行规划助手身份
<soul>           人设/性格（可选）
<memory>         长期记忆（跨对话记住用户偏好）
<thinking_style> 思考方式（如何收集需求、何时触发搜索）
<clarification_system> 澄清规则（缺少信息时问用户）
<skill_system>   技能列表（如果有旅行相关 skill）
<subagent_system> 子 Agent 编排指令（固定 4 个，全部并行）
<working_directory> 文件路径
<response_style>  回复风格
<citations>       引用格式
<critical_reminders> 重要提醒
```

### System Prompt Modules (finalized)

| Module | Source | Content |
|--------|--------|---------|
| `<role>` | Custom | Nomie, cute friendly travel planning assistant |
| `<soul>` | DeerFlow (optional) | Agent personality via SOUL.md |
| `<memory>` | DeerFlow (unchanged) | Long-term memory injection |
| `<thinking_style>` | DeerFlow + travel additions | Collect destination, origin, dates, travelers before proceeding |
| `<clarification_system>` | DeerFlow + travel examples | Travel-specific missing_info and ambiguous_requirement examples |
| `<skill_system>` | DeerFlow (unchanged) | Skills loaded from skills/ directory |
| `<subagent_system>` | Custom | Fixed 4 travel sub-agents, dispatch all on user confirmation |
| `<working_directory>` | DeerFlow (unchanged) | Upload/workspace/output paths |
| `<response_style>` | Custom | Friendly, warm, occasional soft expressions (呀/哦/啦) |
| `<citations>` | DeerFlow (unchanged) | Markdown link citation format |
| `<critical_reminders>` | DeerFlow + travel additions | Must collect minimum info, user confirmation required |

### Middleware

| Middleware | 保留 | 说明 |
|-----------|------|------|
| ThreadDataMiddleware | ✅ | 创建对话工作目录 |
| UploadsMiddleware | ✅ | 用户可能上传图片或文件 |
| SandboxMiddleware | ❌ | Lead Agent 不需要执行代码 |
| DanglingToolCallMiddleware | ✅ | 防止用户刷新页面导致的异常 |
| SummarizationMiddleware | ✅ | 对话过长时压缩上下文 |
| TodoMiddleware | ❌ | 任务拆分已由固定的 sub-agent 替代 |
| TitleMiddleware | ✅ | 自动生成对话标题（侧栏显示） |
| MemoryMiddleware | ✅ | 跨对话记住用户偏好 |
| ViewImageMiddleware | ✅ | 用户可能发图片 |
| SubagentLimitMiddleware | ✅ | 改为固定 4 个的逻辑 |
| ClarificationMiddleware | ✅ | 聊天阶段向用户提问 |

### Tools

| Tool | 保留 | 说明 |
|------|------|------|
| task() | ✅ | 派发 sub-agent，核心 tool |
| ask_clarification | ✅ | 聊天阶段问用户 |
| view_image | ✅ | 看用户上传的图片 |
| web_fetch | ✅ | 读取用户发的链接 |
| web_search | ❌ | 搜索由 sub-agent 负责 |
| sandbox tools | ❌ | 不需要执行代码 |
| present_files | ❌ | 暂不需要 |

### 与 Sub-agent 的接口

沿用 DeerFlow 的 `task()` 接口，自然语言输入输出：

```python
task(
    description="3-5 词任务标签",
    prompt="详细任务指令（自然语言，包含所有需求信息）",
    subagent_type="flight-search"  # 或 hotel-search / itinerary-planner / travel-tips
)
```

Sub-agent 返回自然语言文本，Lead Agent 自行汇总。

---

## Sub-agents

### 通用设计

- 4 个 sub-agent 全部并行启动，互不依赖
- 每个有专属 system prompt，沿用 DeerFlow Lead Agent 的模板结构（做减法）
- 执行完即销毁，不持久化
- 不能再派发 sub-agent（没有 task() tool）
- 不能问用户问题（没有 ask_clarification tool）

### Sub-agent 的 System Prompt 结构

每个 sub-agent 只包含 4 个模块：

```
<role>              专业身份 + "自主工作，不要问用户问题"
<thinking_style>    搜索/分析策略
<output_format>     返回哪些信息字段
<citations>         标注数据来源
```

不包含的模块：memory、clarification_system、subagent_system、response_style、working_directory、skill_system

### Sub-agent Middleware

与 DeerFlow 一致，仅保留 2 个：

| Middleware | 说明 |
|-----------|------|
| ThreadDataMiddleware (lazy_init) | 复用父 Agent 的工作目录 |
| SandboxMiddleware (lazy_init) | 复用父 Agent 的沙箱环境 |

### 4 个 Sub-agent 定义

#### Flight Agent (flight-search)

**接收信息**：出发地、目的地、出发/返回日期、人数、预算

**返回信息**：
- 航空公司、航班号
- 路线（出发地 → 目的地）
- 日期和时间
- 价格（含税）
- 预订链接

#### Hotel Agent (hotel-search)

**接收信息**：目的地、入住/退房日期、人数、预算、住宿偏好

**返回信息**：
- 酒店名称
- 位置（距离主要地标/车站）
- 价格（每晚）
- 评分
- 预订链接

#### Itinerary Agent (itinerary-planner)

**接收信息**：目的地、旅行天数、用户偏好（想去的景点、旅行风格）

**返回信息**：
- 每天的行程安排（Day 1, Day 2, ...）
- 每天包含的景点/活动

#### Tips Agent (travel-tips)

**接收信息**：目的地、旅行日期、出发国家

**返回信息**：
- 签证要求
- 天气情况
- 交通方式建议
- 货币/支付
- 其他注意事项

### Sub-agent Tools

所有 4 个 sub-agent 共享相同的 tools（继承自 Lead Agent，不做限制），主要使用：
- `web_search`（Tavily）— 搜索航班、酒店、景点、签证等信息
- `web_fetch`（Jina AI）— 抓取具体网页获取详细信息

每个 sub-agent 通过 system prompt 来区分职责，不通过限制 tools。

---

## 后续优化方向（暂不实现）

- **两批执行**：Flight + Hotel + Tips 先并行，Itinerary 拿到机票酒店结果后再启动，行程安排更精准
- **用户上传计划评估**：用户上传已有旅行计划，Agent 验证价格/行程合理性
- **sub-agent 嵌套**：单个 sub-agent 内部再并行搜索多个平台（如 Flight Agent 同时搜携程和 Google Flights）

---

## 与 DeerFlow 的关系

### 直接沿用
- LangGraph Server 基础架构
- SSE 流式通信
- `task()` 接口（自然语言输入输出）
- Middleware 机制
- Memory 系统
- Checkpointer（对话持久化）

### 需要修改
- Lead Agent 的 system prompt → 旅行规划专用
- Sub-agent 类型 → 从 2 个通用类型改为 4 个旅行专用类型
- Sub-agent 派发逻辑 → 固定 4 个并行
- Tools → 去掉通用的，加旅行专用的
- MCP → 去掉不相关的（GitHub 等）

### 不需要修改
- Middleware 机制本身
- 记忆系统（memory.json）
- 对话持久化（checkpointer）
- SSE 事件推送机制
- 沙箱系统（sub-agent 复用）
