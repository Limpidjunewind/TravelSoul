# TravelSoul

> **Know yourself. Find your moment.**
>
> An AI travel concierge that knows who you are, watches your calendar, silently hunts deals, and only reaches out when it finds a moment worth your attention.

TravelSoul is an AI-driven proactive travel planning product. Unlike destination-first tools on the market (Booking, Skyscanner, Trip.com), TravelSoul is **person-first**: first we figure out who you are through a travel personality test, then we combine real-time price monitoring with your Google Calendar time windows to push the right trip at exactly the right moment.

---

## ✨ Two Core Selling Points

1. **Travel Soul MBTI** — A 5-dimension travel personality test that generates a shareable personal label (Migratory Explorer, Urban Hunter, Lone Trail Seeker…), with built-in social virality.
2. **Wishlist Real-Time Monitoring** — Built on the AgnesClaw price engine + Google Calendar free-slot detection. Notifications only fire on **dual-condition triggers** — silent by default, never noisy.

---

## 🧭 Three-Surface Architecture

| Surface | Responsibility |
|---------|---------------|
| **Web** | MBTI test · Onboarding funnel · Trip Dashboard · Proposal detail pages |
| **Google Calendar** | Read-only OAuth · Free-window detection · Write confirmed trips back |
| **Telegram Bot** | Pure push channel · Price alerts · Confirmation deep links |

```
┌──────────────────────────────────────────────────────┐
│  Web Frontend                                         │
│  - MBTI test + Onboarding (prefs + Calendar auth)    │
│  - /proposals/:uuid detail view                      │
│  - Trip Dashboard (3-column: profile / plan / chat)  │
└──────────────────────────────────────────────────────┘
                       ↓ writes preferences
┌──────────────────────────────────────────────────────┐
│  TravelSoul Backend                                   │
│  Lead Agent + 4 Sub-agents (DeerFlow / LangGraph)     │
│  + Duffel (flights) + LiteAPI (hotels)                │
└──────────────────────────────────────────────────────┘
      ↑                           ↓
┌────────────────────┐  ┌─────────────────────────┐
│  Scheduled Scanner │  │  Telegram Bot           │
│  - Once per day    │  │  - Push-only             │
│  - Reads Calendar  │  │  - No onboarding         │
│  - Finds free slots│  │  - No commands / queries │
└────────────────────┘  └─────────────────────────┘
                                    ↓ user taps link
                             back to Web → Confirm
                                    ↓
                        ┌─────────────────────────┐
                        │  Google Calendar        │
                        │  (writes minimal event) │
                        └─────────────────────────┘
```

---

## 🪄 User Journey

```
[Auth Binding]
   ├── Google Calendar OAuth (read-only)
   └── Telegram Bot activation (/start)

[Onboarding — Web]
   ├── Layer 1: MBTI test (90 seconds, image-based choices)
   ├── Layer 2: Travel Soul reveal + teaser destination recommendation
   ├── Layer 3: Quick card picks (origin · party · budget)
   ├── Layer 4: Calendar auth + free-window confirmation
   └── Layer 5: Full proposal → "This is it" / "Show me another"

[Background Loop]
   └── Wishlist monitor → historical-low price + free slot + season match → Telegram push
```

---

## 🧠 Travel Soul MBTI: 5 Scoring Dimensions

| Dimension | Axis | Option A | Option B |
|-----------|------|----------|----------|
| Distance | N / F | Nearby micro-escapes | Long-haul expeditions |
| Pace | S / W | Slow & deep | Fast & multi-stop |
| Experience | T / U | Nature healing | Urban culture |
| Social Density | A / C | Solo | With others |
| Quality Mindset | B / Q | Spontaneous & casual | Curated & premium |

16+ personality combinations. Examples:
- **Migratory Explorer** — F-S-T-A — Long distance to disconnect, slow pace, nature healing, solo
- **Urban Hunter** — N-W-U-C — Dense urban experience, fast pace, social
- **Lone Trail Seeker** — F-S-T-A-B — Far-flung nature, slow travel, fully alone, spontaneous
- **Secret Path Seeker** — F-W-T-A-Q — Far nature, fast exploration, premium quality

---

## 🎯 Push Trigger: All Three Conditions Required

```
Condition ① Flight price ≤ 30-day historical low
Condition ② Google Calendar has ≥ 3 consecutive free days
Condition ③ Free-slot dates align with destination high/low season
```

**Core principle: silence first — only interrupt the user when it's genuinely worth it.**

| Scenario | Telegram Notify? |
|----------|-----------------|
| New free slot + new proposal generated | ✅ Always |
| Pending proposal price fluctuation | ❌ Silent |
| **Confirmed trip price drops ≥ threshold** | ✅ Notify + reset baseline |
| Confirmed trip price increase | ❌ Silent (not actionable) |
| Routine scan with no change | ❌ Silent |

Push messages are minimal — just a "ding + link". All details live in the Web app:

```
🎉 Hey Jamie! I've planned a trip for you.

📅 Apr 20 – Apr 27 (7 days)

👉 View details: {LINK}
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Agnes Claw Model (via ZenMux) / Claude Sonnet 4.6 |
| Agent Framework | LangGraph + DeerFlow base |
| Push Engine | **AgnesClaw** — real-time price monitoring + push triggers |
| Flight Data | Duffel / Kiwi.com Tequila API |
| Hotel Data | LiteAPI |
| Affiliate Backup | Travelpayouts |
| Web Search | Tavily |
| Web Fetch | Jina AI |
| Weather | Open-Meteo |
| Calendar | Google Calendar API v3 (OAuth 2.0 read-only + events) |
| Telegram | python-telegram-bot |
| Scheduler | APScheduler |
| Storage | SQLite (demo) / PostgreSQL (prod) |
| Cache | Redis (calendar slots · price baselines) |

---

## 🗃 Core Data Models

### `user_preferences`
Primary key `telegram_user_id`. Stores: origin city, destinations (JSON), vague_preferences (free text), budget, travelers, `min_gap_days`, `price_drop_threshold`, `google_tokens` (OAuth), `persona_type`, `dimension_scores`.

### `proposals`
- `proposal_id` (UUID PK) · `telegram_user_id` · `slot_start_date` / `slot_end_date`
- `status`: `pending` → `confirmed` / `rejected` (rejected is terminal)
- `bundle_data` (JSON): multi-destination full plan (flights / hotels / itinerary / tips / total_price)
- `baseline_price` · `last_price` · `calendar_event_id`

### `wishlist_items`
`destination_iata` · `preferred_duration` · `status` (active / snoozed / completed) · `price_baseline` (30-day low) · `last_notified_at`

---

## 🤖 Backend Pipeline (Daily Scan)

```
for each user in user_preferences:
  1. Use google_tokens to read the next 1–2 months of calendar events
  2. Compute free slots (consecutive free days ≥ min_gap_days)
  3. for each free slot:
     - Check proposals table (rejected → skip, pending → price update only)
     - Invoke Lead Agent + 4 sub-agents:
       · flight-search    (duffel_tool)
       · hotel-search     (liteapi_tool)
       · itinerary-planner
       · travel-tips
     - Bundle into bundle_data, insert proposal (status=pending)
     - Push once to Telegram

  4. for each confirmed proposal:
     - Re-quote the flight/hotel
     - If drop ≥ price_drop_threshold → notify + reset baseline
```

---

## 🎬 Demo Flow

1. Show the Web frontend with MBTI + onboarding already done
2. Show the current calendar (with a clear free window)
3. Trigger the scan (`/admin/scan` or a manual button)
4. Wait for the agent to work (30 seconds ~ 1 minute)
5. Telegram notification appears
6. Tap the link → jump to the proposal page on Web
7. Show multi-destination options (A / B / C / D / E)
8. Pick one, tap Confirm
9. Switch to Google Calendar to show the new event
10. (Optional) Trigger another scan to simulate a price drop and show the discount notification

### 5-Minute Pitch Structure
- **0:00–0:30** Pain point: planning trips eats massive time on search & comparison
- **0:30–3:30** Live demo
- **3:30–4:00** Tech architecture: Agnes + Multi-agent + Duffel + Calendar + Telegram
- **4:00–4:30** Differentiation: vs. reactive tools, TravelSoul is proactive
- **4:30–5:00** Future work & Q&A

---

## 📊 Current Status

| Module | Status |
|--------|--------|
| Web Onboarding + MBTI + Dashboard | ✅ Fully demoable |
| Travel personality engine (16+ types) | ✅ Fully demoable |
| Personality result page + shareable card | ✅ Fully demoable |
| 3-column Trip Dashboard | ✅ Fully demoable |
| Claude API itinerary generation | 🔧 Architecture ready, pending wiring |
| Google Calendar OAuth + slot detection | 🔧 Architecture ready, pending wiring |
| Telegram Bot push | 🔧 Architecture ready, pending wiring |
| AgnesClaw price monitoring | 🔧 Architecture ready, pending wiring |
| 30-day price baseline history | 📋 Designed, pending build |
| User preference persistence | 📋 Designed, pending build |

### Post-Hackathon Priorities

- **P0** — Frontend/backend integration · Full Calendar OAuth flow · Telegram Bot basic commands + push · AgnesClaw integration testing
- **P1** — Price baseline database · Push frequency control · Shareable card image export
- **P2** — Multi-destination wishlist · Friend-travel support · Trip history

---

*TravelSoul · Hackathon Edition*
*Know yourself. Find your moment.*
