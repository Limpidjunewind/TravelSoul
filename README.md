# Nomie — AI Travel Planning Assistant

An AI-powered web agent that helps users plan trips. Instead of manually searching across multiple travel websites, users describe their travel needs (destination, dates, number of people, budget) in a chat, and the agent automatically browses travel sites, compares prices, and returns organized results with recommendations.

**Team**:
- KANG Jinyu (A0330139M)
- LI Jingwen (A0328022R)
- LI Zouran (A0329022N)

---

## Problem Statement

Planning a trip usually means opening a bunch of tabs — Google Flights, Trip.com, Booking.com — and manually comparing prices, schedules, and reviews. This process is time-consuming and often leads to suboptimal choices because:

- Users may not check every platform, missing out on cheaper options
- Comparing across different sites with different layouts is mentally exhausting
- By the time you finish comparing, prices might have already changed

Nomie aims to solve this by delegating the search and comparison work to AI agents that browse these sites on behalf of the user and return a curated summary. This problem will remain relevant as long as travel booking platforms exist, and is likely to grow in importance as AI agent technology matures over the next 5–10 years.

## Solution Architecture

The project follows a three-layer architecture:

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│   Frontend   │ ──> │   Backend API    │ ──> │   Agent Workers      │
│  (React)     │ <── │  (Express +      │ <── │  (Web browsing,      │
│              │     │   MongoDB)       │     │   search, compare)   │
└─────────────┘     └─────────────────┘     └──────────────────────┘
```

- **Frontend**: React + Vite, pixel-art themed UI. User chats with the agent, views real-time agent progress, and browses organized results (flights, hotels, itinerary, tips).
- **Backend**: Express.js server with MongoDB for storing user data, session history, and saved favorites. Handles authentication and coordinates agent tasks.
- **Agent Layer**: AI-powered agents that browse travel websites, extract flight/hotel data, compare prices, and generate itinerary suggestions. (In progress)

## Legal / Open Source

This project is open source under the MIT License.

### Borrowed Code / References

- Frontend pixel-art design style inspired by [Star-Office-UI](https://github.com/ringhyacinth/Star-Office-UI)
- Uses open source libraries: React, React Router, Vite, Bootstrap

No other external code was directly copied into this project.

## Competition Analysis

| Product | Type | Pros | Cons |
|---------|------|------|------|
| **携程 (Ctrip)** | Traditional OTA | Huge inventory, reliable booking | Manual search, no cross-platform comparison |
| **Skyscanner** | Meta-search engine | Compares across airlines | Still requires manual browsing, no personalized planning |
| **Google Flights** | Search tool | Clean UI, good filters | Only flights, no hotels/itinerary bundled |
| **Gemini Deep Research** | AI general search | Can research any topic in depth | Not travel-specific, no structured comparison output |

**Nomie's differentiator**: It combines the comparison ability of meta-search engines with AI automation. Users don't need to search manually — they just describe what they want, and the agent does the rest. The output is structured (flights, hotels, itinerary, tips) rather than a generic text response.

---

## Features

### Frontend (Implemented)

- **Login / Register page** with JavaScript form validation (email format, password length, confirm password)
- **Chat interface** for users to describe travel needs in natural language
- **Agent execution panel** — real-time 2x2 grid showing each agent's progress with step-by-step details, status badges, and animations
- **Result panel** — organized display of flights, hotels, day-by-day itinerary, and travel tips
- **Favorites system** — save and manage preferred flights/hotels
- **Session history** — sidebar with past trip sessions
- **Collapsible sidebar** for flexible layout
- **Pixel-art themed UI** with custom fonts (Ark Pixel), consistent color scheme, and CSS animations
- **React Router** for client-side navigation with auth guards
- **Responsive layout** that adapts when agent/result panels appear

### Backend (Planned)

- Express.js REST API
- MongoDB for user accounts, session history, favorites
- Authentication system
- Agent task coordination
- Docker deployment

---

## Getting Started

```bash
# install frontend dependencies
cd frontend
npm install

# start dev server
npm run dev
```

## Tech Stack

- React 19 + Vite
- JavaScript (JSX) + CSS
- Bootstrap 5
- Node.js + Express (planned)
- MongoDB (planned)
- Docker (planned)
