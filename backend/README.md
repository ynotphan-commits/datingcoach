# Dating Coach AI — Backend

FastAPI backend for the Dating Coach AI web beta. Serves the JSON API under `/api`
and the frontend (sibling agent's build) at `/`.

## Run

```bash
cd ~/workspace/dating-coach-beta/backend
export SECRET_KEY="a-long-random-string"   # required
export MOCK_AI=true                        # canned AI, no API spend (dev/UI testing)
./run.sh
# or: .venv/bin/uvicorn main:app --port 8000
```

`./run.sh` creates `.venv`, installs `requirements.txt`, and starts uvicorn on
`$PORT` (default 8000).

## Env vars

| Var | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | yes | — | HS256 signing key for JWTs |
| `ANTHROPIC_API_KEY` | unless `MOCK_AI=true` | — | Anthropic API key |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-4-5` | Model for chat/sim/tools/checkins |
| `DATABASE_URL` | no | sqlite `./dating_coach.db` | e.g. `postgresql://...` for Postgres |
| `MOCK_AI` | no | off | `true` → canned-but-plausible streamed responses, no API calls |
| `PORT` | no | `8000` | run.sh only |

## Notes

- JWTs: HS256, 30-day expiry, `Authorization: Bearer <token>`.
- Every data query is scoped by the authenticated `user_id`.
- AI system prompts load from `../shared/prompts.py` (`nia_system`, `maya_system`,
  `date_system`, `feedback_system`, `help_reply_system`, `decode_system`,
  `checkin_prompt`); if that file is missing/broken the app falls back to built-in
  placeholder prompts and still boots.
- Chat and sim replies stream as SSE: `data: {"delta":"..."}` chunks, then
  `data: {"done":true,"message_id":<int>}`.
- Check-ins: morning due after 9:54 AM, evening after 6:54 PM, in the user's
  own timezone, once per day each; seen-state tracked per user per day.
- `POST /api/fresh-restart` (`confirm:true`) resets hearts to 100 and wipes
  chat/sim/check-in data but keeps scorecards, custom dates, and the user.
