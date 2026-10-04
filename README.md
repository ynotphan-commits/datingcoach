# Dating Coach AI — Web Beta

"Full translator for modern dating." An AI dating-coach **training gym** (not a dating app):
practice dates with hidden red-flag training, two AI coaches, real-game assist tools,
and proactive check-ins.

## What this is

A shareable, multi-user web beta. One deployed URL → anyone with the link can sign up
and use the full app in their phone browser (installable to the home screen as a PWA).

**Product surface**
- **Onboarding** — deep first-date interview questionnaire → hard diagnostic questions (the uncomfortable ones: cheating, jealousy, money, sex; family background — who you're closest to and why, parents together/divorced, relationship with each parent; and whose dating advice you already listen to — who, why, and whether they're single or divorced, so the coach can credibility-check the voice in your head) → coach picker. Answers feed a rule-based "diagnosed patterns" summary that every coach prompt carries as context, so coaching targets the user's actual problems from day one.
- **Coaches** — Nia (27, nurse turned coach, blunt triage energy), Maya (32, event planner turned coach, warm and wise), and Marcus (34, personal trainer turned coach, no-excuses drill energy). All available to every user. A locked "Millionaire Matchmaker" premium slot is shown as coming soon (no billing in beta).
- **Practice dates** — 5 preset anime dates + custom date builder. Simulations run hidden red flags (love-bombing, hot/cold, negging, future-faking) that intensify — the training bites on purpose. Dates pull real information (not small talk), extract what makes the user awkward — and the crazy stuff — while the coach debrief names it and teaches better answers.
- **Ask Coach lifeline** — mid-date "Ask Coach" button opens a slide-over: ping your chosen coach without leaving the sim, get one tactical move in 2–4 sentences. Usage is timestamped and factored into the post-sim debrief.
- **Your Patterns** — a living mirror tab: the coach-voiced reflection of your dating patterns, grouped diagnosed patterns (dating / family dynamics / needs & drivers), what your dates exposed, and what you've asked your coach. Updates as you train — you leave understanding yourself better, not just trained.
- **Coach feedback + hearts** — hearts go up *and* down based on your choices;
  scorecards persist. **Fresh Restart** resets hearts/stats (keeps scorecards,
  requires confirmation).
- **Real-game assist** — *Help Me Reply* (2–3 reply options + strategy) and
  *Decode This* (subtext, tone, red flags).
- **Check-ins** — in-app morning (~9:54 AM) and evening (~6:54 PM) in the user's
  timezone. Push notifications are phase two (needs native app).

**Hard product rules baked in:** no corny pickup lines — every drafted reply must pass
"would a confident real person actually text this?"; user-led pacing, no time limits;
chat history paginates with "load older messages" (never silently capped).

## Run locally

```bash
cd dating-coach-beta/backend
cp ../.env.example .env   # then edit: set SECRET_KEY at minimum
export SECRET_KEY="a-long-random-string"
export MOCK_AI=true       # canned AI responses, zero API spend — good for UI testing
./run.sh                  # creates .venv, installs deps, starts uvicorn on :8000
# open http://localhost:8000
```

Or without the helper script:

```bash
cd dating-coach-beta/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
SECRET_KEY=... MOCK_AI=true .venv/bin/uvicorn main:app --port 8000
```

## Environment variables

| Var | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | yes | — | long random string for JWT signing |
| `AI_PROVIDER` | no | auto | `gemini` (free), `anthropic` (paid), or `mock`. Auto-picks gemini if `GEMINI_API_KEY` is set |
| `GEMINI_API_KEY` | for free live AI | — | Google AI Studio key — free, no card: https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | free-tier model |
| `ANTHROPIC_API_KEY` | for paid live AI | — | only needed with `AI_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-4-5` | model for chat/sim/tools |
| `DATABASE_URL` | no | sqlite `./dating_coach.db` | e.g. `postgresql+psycopg2://…` for Postgres |
| `MOCK_AI` | no | false | `true` = canned AI responses, no API calls/spend |
| `PORT` | no | 8000 | honored by the Docker CMD (HF Spaces injects 7860) |

## Deploy — FREE path (Render + Supabase + Google AI Studio)

Total cost: **$0**. No card required anywhere.

You need three free accounts: **GitHub**, **Render**, **Supabase** (all free tiers,
no card), plus the free Gemini key.

**Step 1 — database (Supabase, 3 min)**
1. Sign up at https://supabase.com → New project (free tier), pick a name + password.
2. Wait ~1 min for provisioning → Project Settings → Database → copy the
   **Connection string** in URI format
   (`postgresql://postgres:[YOUR-PASSWORD]@db.xxx.supabase.co:5432/postgres`).
   Keep it — it's step 3's `DATABASE_URL`.

**Step 2 — free AI key (2 min)**
1. Go to https://aistudio.google.com/apikey, sign in with Google → **Create API key**.
   Free tier ≈ 1,500 requests/day — plenty for a beta.

**Step 3 — hosting (Render, 5 min)**
1. Push this repo to GitHub (new repo, upload the files or push via git).
2. Sign up at https://render.com → New → **Web Service** → connect the repo →
   choose **Docker** as the runtime (it detects the Dockerfile).
3. Free instance type. Set environment variables in the Render dashboard:
   - `SECRET_KEY` — any long random string
   - `GEMINI_API_KEY` — from step 2
   - `DATABASE_URL` — the Supabase URI from step 1
4. Deploy → you get a public `https://dating-coach-ai.onrender.com`-style URL.
   Text it to testers.

Notes: the free Render service sleeps after 15 min of no traffic and wakes when
someone visits (~30–60s cold start on first load). The database lives on Supabase,
so accounts/chats/sims survive sleeps and redeploys. No build step: the FastAPI
backend serves the static frontend at `/`, API at `/api`.

## Deploy — paid alternatives (Railway)

Same as above, but on Railway ($5/mo): New Project → Deploy from repo → set the
same env vars. Add `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` if you'd rather
run on Claude (paid API).

No build step: the FastAPI backend serves the static frontend at `/`, API at `/api`.

## Project structure

```
dating-coach-beta/
├── Dockerfile            # Railway/Render deploy
├── .env.example          # env template (no secrets in repo)
├── README.md
├── backend/
│   ├── main.py           # FastAPI app, 22 endpoints, SSE streaming
│   ├── models.py db.py auth.py ai.py
│   ├── prompts_loader.py # defensive import of shared/prompts.py
│   ├── requirements.txt run.sh
│   └── README.md
├── frontend/
│   ├── index.html styles.css app.js   # vanilla JS SPA, mobile-first
│   └── assets/
│       ├── coaches/nia.webp maya.webp marcus.webp
│       ├── dates/date1.webp … date5.webp
│       └── icon.webp
└── shared/
    └── prompts.py        # all AI system prompts (Nia, Maya, dates,
                          # feedback/hearts, Help Me Reply, Decode This, check-ins)
```

## Auth & data isolation

Email + password, bcrypt-hashed, JWT (30-day). Every data query is scoped to the
authenticated user — users can never see each other's chats, sims, or scorecards.

## What Tony must provide to go live — FREE (no card anywhere)

1. **Free AI key** — Google AI Studio (https://aistudio.google.com/apikey), his
   Google sign-in. ~1,500 requests/day free.
2. **Free database** — Supabase (https://supabase.com), free tier → Postgres
   connection string.
3. **Free hosting** — Render (https://render.com), free tier → Docker Web Service
   from a GitHub repo, env vars `SECRET_KEY` + `GEMINI_API_KEY` + `DATABASE_URL`.
4. *(Later, for native iOS)* Apple Developer account ($99/yr) for TestFlight.

## Known limitations / not yet done

- The live-Gemini path is implemented but **not yet tested with a real API key**
  (no key in this environment) — run one live smoke test before inviting testers.
  The Anthropic path is also implemented, untested live.
- No rate limiting on API endpoints yet — add before public launch.
- No password-reset flow yet (beta-acceptable; add for launch).
- On Render's free tier the service sleeps after 15 min idle (~30–60s cold start
  on wake). Data is safe: the database lives on Supabase Postgres, not the
  container disk.
