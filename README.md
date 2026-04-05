# TravelSoul

> **Know yourself. Find your moment.**
>
> An AI travel concierge that knows who you are, watches your calendar, silently hunts deals, and only reaches out when it finds a moment worth your attention.

TravelSoul 是一个 AI 驱动的主动式旅行规划产品。与市面上 destination-first 的工具（Booking、Skyscanner、Trip.com）不同，TravelSoul 是 **person-first**：先通过旅行人格测试搞清楚你是谁，再结合实时价格监控和 Google Calendar 时间窗口，在最合适的时机推送最合适的旅行方案。

---

## ✨ 两大核心卖点

1. **旅行灵魂 MBTI** —— 5 维度旅行人格测试，生成可分享的专属标签（候鸟型探索者、都市猎人、山野独行侠…），自带社交传播钩子。
2. **心愿卡片实时监控** —— 基于 AgnesClaw 价格引擎 + Google Calendar 空档识别，**双条件触发**才推送，静默优先，绝不打扰。

---

## 🧭 三端架构

| 平台 | 职责 |
|------|------|
| **Web** | MBTI 测试 · Onboarding 漏斗 · 行程 Dashboard · Proposal 详情 |
| **Google Calendar** | Read-only 授权 · 识别空闲时间窗口 · 写入已确认行程 |
| **Telegram Bot** | 纯推送通道 · 价格提醒 · 行程确认跳转 |

```
┌──────────────────────────────────────────────────────┐
│  Web 前端                                             │
│  - MBTI 测试 + Onboarding（收集偏好 + Calendar 授权）  │
│  - /proposals/:uuid 详情展示                         │
│  - 行程 Dashboard（三栏：档案 / 规划区 / AI 对话）      │
└──────────────────────────────────────────────────────┘
                       ↓ 写入 preferences
┌──────────────────────────────────────────────────────┐
│  TravelSoul Backend                                   │
│  Lead Agent + 4 Sub-agents (基于 DeerFlow / LangGraph)│
│  + Duffel (flights) + LiteAPI (hotels)                │
└──────────────────────────────────────────────────────┘
      ↑                           ↓
┌────────────────────┐  ┌─────────────────────────┐
│  定时扫描器         │  │  Telegram Bot           │
│  - 每天 1 次        │  │  - 仅推送通知             │
│  - 读 Calendar      │  │  - 不做 onboarding       │
│  - 发现空档 → 规划  │  │  - 不做命令/查看          │
└────────────────────┘  └─────────────────────────┘
                                    ↓ 用户点链接
                             回到 Web 前端 Confirm
                                    ↓
                        ┌─────────────────────────┐
                        │  Google Calendar        │
                        │  （写入最小信息的 event）  │
                        └─────────────────────────┘
```

---

## 🪄 用户旅程

```
[绑定授权]
   ├── Google Calendar OAuth（read-only）
   └── Telegram Bot 激活（/start）

[Onboarding — Web 端]
   ├── Layer 1：MBTI 测试（90 秒，图片选择题）
   ├── Layer 2：旅行灵魂揭晓 + 半成品目的地推荐
   ├── Layer 3：卡片快选（出发地 · 出行构成 · 预算）
   ├── Layer 4：Calendar 授权 + 时间窗口确认
   └── Layer 5：完整方案出炉 → 「就这里了」/ 「换一个」

[后台持续运行]
   └── 心愿单监控 → 价格历史新低 + 日历有空 + 季节匹配 → Telegram 推送
```

---

## 🧠 旅行灵魂 MBTI：5 个评分维度

| 维度 | 轴标记 | 选项 A | 选项 B |
|------|--------|--------|--------|
| 距离感 | N / F | 附近微度假 | 跨洲远征 |
| 节奏 | S / W | 慢游深度 | 快闪多点 |
| 体验偏好 | T / U | 自然疗愈 | 城市人文 |
| 社交密度 | A / C | 独行 | 结伴 |
| 品质取向 | B / Q | 随性说走就走 | 精选品质体验 |

16+ 种人格组合，示例：
- **候鸟型探索者 (Migratory Explorer)** — F-S-T-A — 远距离切断，节奏慢，自然疗愈，独行
- **都市猎人 (Urban Hunter)** — N-W-U-C — 城市密集体验，快节奏，社交型
- **山野独行侠 (Lone Trail Seeker)** — F-S-T-A-B — 远途自然，慢游，完全独处，随性
- **秘境寻踪者 (Secret Path Seeker)** — F-W-T-A-Q — 远途自然，快闪探索，品质体验

---

## 🎯 推送触发：三条件缺一不可

```
条件 ① 机票价格 ≤ 30 天历史最低价
条件 ② Google Calendar 检测到 ≥ 3 天连续空档
条件 ③ 空档日期与目的地旺/淡季逻辑匹配
```

**核心原则：静默优先，只在真正有价值时才打扰用户。**

| 场景 | Telegram 通知？ |
|------|---------------|
| 新空档发现 + 生成新 proposal | ✅ 必通知 |
| pending proposal 价格波动 | ❌ 静默 |
| **confirmed trip 价格大跌 ≥ 阈值** | ✅ 通知 + 重置 baseline |
| confirmed trip 价格上涨 | ❌ 静默（不 actionable） |
| 例行扫描无变化 | ❌ 静默 |

推送消息极简 —— 只负责"叮咚一声 + 链接"，细节全在 Web：

```
🎉 Hey Jamie! I've planned a trip for you.

📅 Apr 20 – Apr 27 (7 days)

👉 View details: {LINK}
```

---

## 🔧 技术栈

| 层 | 技术 |
|---|------|
| LLM | Agnes Claw Model (via ZenMux) / Claude Sonnet 4.6 |
| Agent 框架 | LangGraph + DeerFlow base |
| 推送引擎 | **AgnesClaw** — 实时价格监控 + 推送触发 |
| 航班数据 | Duffel / Kiwi.com Tequila API |
| 酒店数据 | LiteAPI |
| 联盟备份 | Travelpayouts |
| Web 搜索 | Tavily |
| Web 抓取 | Jina AI |
| 天气 | Open-Meteo |
| Calendar | Google Calendar API v3（OAuth 2.0 read-only + events） |
| Telegram | python-telegram-bot |
| 调度 | APScheduler |
| 存储 | SQLite（demo）/ PostgreSQL（prod） |
| 缓存 | Redis（日历空档 · 价格基准） |

---

## 🗃 核心数据模型

### `user_preferences`
主键 `telegram_user_id`，存储：出发城市、destinations（JSON）、vague_preferences（自由文本）、预算、人数、`min_gap_days`、`price_drop_threshold`、`google_tokens`（OAuth）、`persona_type`、`dimension_scores`。

### `proposals`
- `proposal_id` (UUID 主键) · `telegram_user_id` · `slot_start_date` / `slot_end_date`
- `status`：`pending` → `confirmed` / `rejected`（rejected 为终态）
- `bundle_data` (JSON)：多目的地完整方案（flights / hotels / itinerary / tips / total_price）
- `baseline_price` · `last_price` · `calendar_event_id`

### `wishlist_items`
`destination_iata` · `preferred_duration` · `status`（active / snoozed / completed）· `price_baseline`（30 天最低价）· `last_notified_at`

---

## 🤖 Backend Pipeline（每天 1 次扫描）

```
for each user in user_preferences:
  1. 用 google_tokens 读取未来 1–2 个月 calendar events
  2. 计算空档（consecutive free days ≥ min_gap_days）
  3. for each 空档:
     - 检查 proposals 表（rejected → 跳过，pending → 只更新价格）
     - 调用 Lead Agent + 4 sub-agents：
       · flight-search   (duffel_tool)
       · hotel-search    (liteapi_tool)
       · itinerary-planner
       · travel-tips
     - 打包 bundle_data 插入 proposals（status=pending）
     - Telegram 推送一次

  4. for each confirmed proposal:
     - 重新 quote 航班/酒店
     - 下跌 ≥ price_drop_threshold → 通知 + 重置 baseline
```

---

## 🎬 Demo 流程

1. 展示 Web 前端已完成的 MBTI + onboarding
2. 展示当前 calendar（有明显的空档）
3. 触发扫描（`/admin/scan` 或手动按钮）
4. 等待 agent 工作（30 秒 ~ 1 分钟）
5. Telegram 弹出通知
6. 点击链接跳到 Web 前端的 proposal 页
7. 展示多目的地选项（A / B / C / D / E）
8. 选一个，点 Confirm
9. 切回 Google Calendar 展示新增的 event
10. （可选）再次触发扫描，模拟"价格下跌"，展示降价通知

### Pitch 5 分钟结构
- **0:00–0:30** 痛点：规划旅行要花大量时间搜比价
- **0:30–3:30** Live demo
- **3:30–4:00** 技术架构：Agnes + Multi-agent + Duffel + Calendar + Telegram
- **4:00–4:30** 差异化：对比被动工具，TravelSoul 是主动的
- **4:30–5:00** Future work & Q&A

---

## 📊 当前状态

| 模块 | 状态 |
|------|------|
| Web Onboarding + MBTI + Dashboard | ✅ 完整可演示 |
| 旅行人格引擎（16+ 类型） | ✅ 完整可演示 |
| 旅行人格结果页 + 分享卡片 | ✅ 完整可演示 |
| 行程 Dashboard 三栏布局 | ✅ 完整可演示 |
| Claude API 行程生成 | 🔧 架构完成，待连接 |
| Google Calendar OAuth + 空档识别 | 🔧 架构完成，待连接 |
| Telegram Bot 推送 | 🔧 架构完成，待连接 |
| AgnesClaw 价格监控接入 | 🔧 架构完成，待连接 |
| 价格历史基准（30 天窗口） | 📋 设计完成，待开发 |
| 用户偏好持久化 | 📋 设计完成，待开发 |

### Post-Hackathon 优先级

- **P0** — 前后端联调 · Calendar OAuth 完整流程 · Telegram Bot 基础指令 + 推送 · AgnesClaw 接入测试
- **P1** — 价格历史基准数据库 · 推送频率控制 · 分享卡片生成
- **P2** — 多目的地心愿单 · 好友同行 · 历史行程记录

---

*TravelSoul · Hackathon Edition*
*Know yourself. Find your moment.*
