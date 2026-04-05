# Nomie 优化待办

## 搜索质量

- **Sub-agent 搜索深度不够**：目前 sub-agent 可能只做 1 次 web_search 就直接总结，导致搜索太快、结果不精准。需要在 sub-agent prompt 里强调"必须至少搜索 2-3 次，必须用 web_fetch 抓取具体页面验证价格，不要只用搜索摘要"
- **搜索结果准确性**：Tavily 返回的是搜索页摘要，不是真实报价。sub-agent 需要用 web_fetch 深入抓取具体页面，而不是只用搜索摘要里的"最低 $XX 起"
- **链接质量**：返回的链接有时是搜索结果页而非具体预订页面

## Lead Agent 行为

- **需求收集不够充分**：用户只说了很简单的信息就直接开始搜索，没有追问日期、预算、偏好等关键细节。需要调整 thinking_style 和 clarification_system prompt
- **有时只派 3 个 agent**：Lead Agent 偶尔漏掉 travel-tips，prompt 需要强调"必须派 4 个"

## 前端展示

- **ResultPanel 解析精度**：markdown 解析不够完整，hotel 有时只显示一条笼统结果没有具体名字和价格，flight 有些字段缺失。需要优化 `parseMarkdownResults` 正则，或改用 output schema 后处理
- **收藏功能**：目前只是前端 local state，刷新就没了。需要等队友 A 实现 Gateway favorites 路由后对接

## 稳定性

- **网络错误无重试**：sub-agent 执行时网络断了就直接 error，可以加重试机制
- **Sidebar 功能**：缺少删除历史、重命名 session

## 架构优化

- **结果结构化**：可以在 Lead Agent 汇总后加一步后处理，用 OpenAI output schema 强制输出 JSON，替代前端 markdown 解析
- **浏览器自动化集成**：用 `agent-browser` CLI 封装成 LangChain tool，让 sub-agent 能真的操作网页（填日期、点搜索、读真实价格）。实现方式：写一个 Python wrapper 调用 `agent-browser` 命令（open → snapshot → interact → extract），注册为 LangChain tool 给 sub-agent 用
- **搜索工具升级**：接入航班/酒店平台的 API（如 Skyscanner API、Booking.com API）获取精确报价
