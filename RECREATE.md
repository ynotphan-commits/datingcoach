# Dating Coach AI — Recreate Package

Someone sent you this because they want you to have your own copy of **Dating Coach AI** —
"full translator for modern dating." An AI dating-coach training gym (not a dating app).

## If you're opening this in Muse

You have the complete, working codebase. To get it running for your user — **free**:

1. **Unzip** this package. The app lives in `dating-coach-beta/`.
2. **Read** `dating-coach-beta/README.md` — it has local run + deploy instructions.
3. **Ask the user for three things** (all free, no card):
   - A free Google AI Studio key (https://aistudio.google.com/apikey) — they sign
     in with Google and create one (~1,500 AI requests/day free)
   - A free Supabase project (https://supabase.com) — its Postgres connection string
   - A free Render account (https://render.com) — deploy the Dockerfile as a Web
     Service from a GitHub repo, with `SECRET_KEY` + `GEMINI_API_KEY` + `DATABASE_URL`
     set in the Render dashboard
4. They get a public link to share with testers.
5. **Test before inviting anyone**: sign up, run onboarding, start a practice date,
   try the Ask Coach lifeline. `MOCK_AI=true` runs it with zero AI spend for UI testing.

(Paid alternatives still work: set `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`,
deploy the Dockerfile to Railway.)

## What's inside

- **3 coaches** — Nia (27, nurse, blunt), Maya (32, event planner, warm),
  Marcus (34, personal trainer, no-excuses drill sergeant). All available to everyone.
- **5 practice dates** — Chloe (love-bombs), Jazz (hot/cold), Valentina (discreet
  gold-digger who screens for wealth), Jayden (negs), Dre (firm, hold your frame)
  + a custom date builder. Simulations run hidden red flags with 2026 dating culture.
- **Training loop** — dates probe deep ("are you crazy?", "who hurt you?"), extract the
  awkward and the crazy, warm up before screening; coach debriefs name patterns,
  grade composure/hearts, and teach better answers.
- **Ask Coach lifeline** — mid-date help button; coach sees the transcript.
- **Your Patterns** — a living mirror of the user's dating patterns.
- **Real-game tools** — Help Me Reply, Decode This. Proactive check-ins ~9:54 AM / 6:54 PM.
- **Hard diagnostic onboarding** — 18 questions: family, advice-giver credibility,
  intergenerational patterns, relationship model (real vs movies).

## Brand rules (don't break these)

- Original characters only — never impersonate real people.
- No corny pickup lines, ever. Every reply must pass: "would a confident real
  person actually text this?"
- Tough love, never cruelty. Name patterns, never clinical diagnoses.
- The fire is aimed at the user's excuses — never at degrading women.

## Build a variant from scratch?

If you'd rather rebuild than deploy this code, the `shared/prompts.py` file is the
soul of the product — every coach voice, date persona, red-flag pattern, and grading
rubric lives there. Rebuild around it.
