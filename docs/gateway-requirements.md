# Gateway 需求文档

## 概述

Gateway 是一个独立的后端服务，负责用户系统和收藏功能。前端会根据不同功能分别调用 Gateway 和 Agent 后端（LangGraph Server），两个服务各自独立运行。

## 负责的功能

### 1. 用户注册与登录

- 用户通过邮箱 + 密码注册和登录
- 登录后返回 token，前端后续请求带上 token 来识别用户身份
- 密码需要 hash 存储

### 2. 收藏管理

用户在查看 Agent 搜索结果时，可以点击"收藏"按钮保存某个机票或酒店方案。

**业务流程：**

1. Agent 搜索完成后，前端展示结果卡片（机票、酒店等）
2. 用户点击某张卡片上的"收藏"按钮
3. 前端把这张卡片的数据发送给 Gateway 的收藏 API
4. Gateway 存入数据库
5. 用户打开侧栏的"收藏"列表时，前端从 Gateway 获取该用户的所有收藏

**注意：** 收藏的数据是前端直接传给 Gateway 的，Gateway 不需要和 Agent 后端通信来获取这些数据。

### 3. 用户偏好（可选）

如果有时间，可以做用户偏好设置，比如默认出发城市、语言偏好等。

## 前端参考

收藏相关的前端代码在 `frontend/src/pages/MainPage.jsx` 和 `frontend/src/components/ResultPanel/ResultPanel.jsx` 里。可以参考现有的 mock 数据结构来设计 API 的请求和返回格式，比如：

```js
// 现有的收藏 mock 数据（MainPage.jsx）
const MOCK_FAVORITES = [
  { id: 'f1', type: 'flight', title: 'Spring Airlines SHA→TYO', price: '¥1,200/person' },
  { id: 'f2', type: 'hotel', title: 'Shinjuku Gracery Hotel', price: '¥400/night' },
]
```

API 的具体字段、路径、数据库设计自行决定，满足上述业务需求即可。

## 技术选型

自行决定，不限制框架和数据库。
