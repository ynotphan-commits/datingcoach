"""Dating Coach AI — backend. FastAPI + SQLAlchemy. Run: uvicorn main:app --port 8000"""
import json
import re
import hashlib
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Union

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel, Field

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db, init_db, SessionLocal
from models import (
    User, Onboarding, Message, CustomDate, Simulation, SimMessage, Scorecard, CheckinSeen,
    CoachLifeline,
)
from auth import (
    hash_password, verify_password, create_token, get_current_user, user_dict,
)
import ai
import prompts_loader as P

# ---------------------------------------------------------------- helpers

def iso(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def sse(data: dict) -> str:
    return "data: " + json.dumps(data) + "\n\n"


def parse_before(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid 'before' parameter")


COACHES = {
    "nia": {
        "id": "nia", "name": "Nia", "age": 27,
        "tagline": "Blunt triage for your dating life",
        "style": "Direct, no-fluff",
        "bio": "Nurse turned dating coach. Seen it all.",
        "lane": "Men's dating",
        "img": "/assets/coaches/nia.webp",
    },
    "maya": {
        "id": "maya", "name": "Maya", "age": 32,
        "tagline": "Warm wisdom that lasts",
        "style": "Warm, wise",
        "bio": "Event planner turned dating coach. She's planned the weddings and seen what lasts.",
        "lane": "Women's dating",
        "img": "/assets/coaches/maya.webp",
    },
    "marcus": {
        "id": "marcus", "name": "Marcus", "age": 34,
        "tagline": "No excuses. Build yourself.",
        "style": "Unfiltered, discipline-first",
        "bio": "Personal trainer turned dating coach. Lives in the gym, coaches like it — effort is the standard.",
        "lane": "Men's dating",
        "img": "/assets/coaches/marcus.webp",
    },
}

PRESET_DATES = [
    {"id": "preset-1", "name": "Chloe", "age": 24,
     "tagline": "Magnetic and fast-moving — love-bombs early",
     "img": "/assets/dates/date1.webp",
     "personality": "Magnetic, fast-moving, love-bombs early: intense compliments and fast attachment in the first messages."},
    {"id": "preset-2", "name": "Jazz", "age": 28,
     "tagline": "Charming but hot/cold",
     "img": "/assets/dates/date2.webp",
     "personality": "Charming but hot/cold: warm and engaged one moment, distant and dry the next. Keeps the user guessing."},
    {"id": "preset-3", "name": "Valentina", "age": 26,
     "tagline": "Charming, discreetly screens for wealth",
     "img": "/assets/dates/date3.webp",
     "personality": "Vegas club hostess turned dater — she sees money up close every night (bottle service, tables, watches) and reads wealth like a second language. Her questions have the polish of someone who's sized up a thousand men — the exact questions a top-tier Vegas dancer asks a new customer: warm, curious, never thirsty, always calculating. Modern gold digger, completely discreet: she NEVER asks about money directly. She screens through lifestyle questions that feel like genuine curiosity — where you went to school (private? Ivy? state?), where you vacation and WHICH hotels (Four Seasons vs Airbnb tells her everything), what cars you're into, whether they go to car shows, whether they collect anything ('do you collect anything? watches?'), crypto/stocks ('are you into crypto? do you trade?'), watches ('nice watch, what is that?'), sports ('do you play? courtside or nosebleeds?'), concerts ('who have you seen live? floor or lawn?'), your hobbies — and she silently prices the hobbies (golf, skiing, boating = expensive; video games, hiking = cheap — but she asks 'do you play games?' like she's genuinely curious). Charming, feminine, attentive; the vetting feels like interest. She builds a mental baseball card on every man — school, car, watch, vacation tier, hobby costs, crypto: stats on the back, rating on the front. She warms to wealth signals and cools on broke signals without ever naming why. PACING (critical — she is NOT an interrogator): she warms up FIRST. Opens as a real person — shares stories (road trips, memories with her dad on canyon roads), builds genuine rapport. The money questions emerge ORGANICALLY from her own stories: 'my dad and I used to take canyon roads every summer... what do you drive?' — the car question lands as a natural follow-up, never a probe. Same for watches (notices, compliments, then asks), vacations (shares hers first, then asks), crypto (mentions a friend, gauges reaction). Never rapid-fire screening, never back-to-back money questions. The screen is still always running — every answer still gets priced — but it feels like conversation, not vetting. Training: spot the screening, don't audition with your wallet, hold frame."},
    {"id": "preset-4", "name": "Jayden", "age": 29,
     "tagline": "Confident, negging disguised as teasing",
     "img": "/assets/dates/date4.webp",
     "personality": "Confident and smooth, but negs disguised as teasing: backhanded compliments that chip at confidence."},
    {"id": "preset-5", "name": "Dre", "age": 29,
     "tagline": "Firm, direct, clear expectations — hold your frame",
     "img": "/assets/dates/date5.webp",
     "personality": "Modern hip-hop listener, confident and direct, firm with expectations. Not a pushover, doesn't chase, says what he wants plainly. A strong personality with real standards — not a villain. Where it fits his personality he can run hot/cold or be blunt to the point of negging-adjacent directness, but his core is firm and clear, never abusive. The training: hold frame with a man who has expectations."},
]

# ---------------------------------------------------------------- mock canned content

def _mock_chat_text(coach_id: str, message: str) -> str:
    snippet = message.strip()[:60]
    if coach_id == "nia":
        return (
            f"Okay, let's triage this. You said: \"{snippet}\" — "
            "here's my honest read: you're overthinking the text and underthinking the pattern. "
            "Watch what they DO over the next 48 hours, not what they say tonight. "
            "If the energy isn't matched, you pull back. That's the whole game. "
            "Want me to help you draft the next move, or do you want the hard truth first?"
        )
    if coach_id == "marcus":
        return (
            f"You said: \"{snippet}\" — alright, let's cut the fluff. "
            "What's the actual effort here? Because from where I'm standing, "
            "you're negotiating with yourself instead of executing. "
            "Here's your rep: train today, text with intent or don't text at all, "
            "and stop waiting to 'feel ready.' Where are you coasting right now — "
            "be honest, I can take it."
        )
    return (
        f"I hear you — \"{snippet}\" — and it's completely normal to feel that way. "
        "Here's what I'd sit with: the right person makes things feel clearer over time, not more confusing. "
        "Notice how your body feels after interacting with them — calm or knotted up? "
        "That answer is usually wiser than any text analysis. Tell me more about how it left you feeling."
    )


def _mock_opening(persona: dict) -> str:
    name = persona.get("name", "there")
    style = (persona.get("personality") or "").lower()
    if "love-bomb" in style or "love-bomb" in style.replace("-", ""):
        return f"heyyy {name} is blushing already 😳 wow, your profile actually stopped my scroll. I feel like we'd get along scarily well"
    if "hot/cold" in style:
        return "hey 😌 you seem cool. fair warning I'm terrible at texting back sometimes lol"
    if "future-fake" in style:
        return "hiii! ✨ okay I already have a vision — we HAVE to do that rooftop cinema thing next weekend, you'd love it"
    if "neg" in style:
        return "hey. cute pics — you clean up better than I expected 😏"
    return f"hey {name} 🙂 so what should I know about you that your profile doesn't say?"


def _mock_date_reply(persona: dict, message: str) -> str:
    name = persona.get("name", "")
    style = (persona.get("personality") or "").lower()
    snippet = message.strip()[:40]
    if "love-bomb" in style or "love-bomb" in style.replace("-", ""):
        return f"omg stoppp 🥰 \"{snippet}\" — see?? this is exactly why I already know you're different. I've never clicked this fast with anyone"
    if "hot/cold" in style:
        return "haha yeah maybe. anyway what are you up to this weekend" if len(message) > 20 else "lol"
    if "future-fake" in style:
        return f"yesss I love that ✨ \"{snippet}\" — okay we're definitely doing that wine tasting trip I mentioned, I'm already planning it in my head"
    if "neg" in style:
        return f"lol \"{snippet}\" — that was almost smooth. almost 😏 keep trying though, it's cute"
    return f"haha fair 😄 \"{snippet}\" — okay your turn, ask me something real"


def _mock_feedback(persona: dict, turns: int) -> str:
    name = persona.get("name", "your date")
    return (
        f"## Simulation feedback — practice date with {name}\n\n"
        f"You traded {turns} messages. Here's the honest breakdown:\n\n"
        "### What you did well\n"
        "- You kept the conversation moving instead of freezing up.\n"
        "- Your tone stayed confident and light.\n\n"
        "### Red flags to spot next time\n"
        "- Watch for intensity that arrives too fast (love-bombing) or warmth that vanishes mid-chat (hot/cold).\n"
        "- Notice when big future plans get promised with zero specifics — that's future-faking.\n\n"
        "### Try next time\n"
        "1. Name the pattern out loud in your head before you reply.\n"
        "2. Slow the pace when someone rushes intimacy — matched energy, not chased energy.\n"
        "3. Ask one concrete question when plans get vague (\"which weekend?\").\n\n"
        "Keep repping — this is a gym, not a test.\n\n"
        "SCORE: 72"
    )


def _mock_checkin_text(kind: str, user: dict) -> str:
    name = (user or {}).get("display_name") or "there"
    if kind == "morning":
        return (
            f"Morning, {name}. Quick gut-check before the day starts: what's ONE thing "
            "you'd do differently on your next date? Hold that thought — small reps, big change."
        )
    return (
        f"Evening, {name}. Wind-down reflection: did anyone's energy feel off today — "
        "too fast, too cold, too vague? Noticing it is the whole skill. See you tomorrow."
    )


# ---------------------------------------------------------------- diagnosis
# The onboarding "hard questions" (dx_*) identify each user's specific dating
# problems up front. _diagnose() extracts plain-language patterns (never
# clinical labels) and stores them under answers["_diagnosis"]; _user_ctx()
# feeds the onboarding summary + diagnosed patterns into every AI prompt.

OB_LABELS = {
    "about_me": "About", "daily_life": "Daily life",
    "looking_for": "Looking for", "ideal_partner": "Ideal partner",
    "dating_history": "Dating history",
    "communication_style": "Communication style", "attachment": "Under pressure",
    "dealbreakers": "Dealbreakers", "pattern_to_break": "Pattern to break",
    "goals": "Goals",
}

DX_LABELS = {
    "dx_crazy": "Anything crazy about how they date",
    "dx_cheated": "Cheating history",
    "dx_last_why": "Why the last relationship failed",
    "dx_hurt": "Who hurt them",
    "dx_alone": "Why alone instead of with someone",
    "dx_expect": "What they expect from a partner",
    "dx_missing": "What the last person didn't do",
    "dx_money": "How important money is",
    "dx_jealousy": "How important jealousy is",
    "dx_sex": "How important sex is",
    "dx_fam_close": "Closest person and why",
    "dx_parents_together": "Parents together or divorced",
    "dx_dad_rel": "Relationship with dad",
    "dx_mom_rel": "Relationship with mom",
    "dx_parents_rel": "Parents' relationship with each other",
    "dx_advice_from": "Who they get dating advice from and why",
    "dx_advice_single": "Whether the advice-giver is single",
    "dx_advice_divorced": "Whether the advice-giver is divorced",
    "dx_talk_parents": "Whether they talk to their parents",
    "dx_model_who": "Who has the relationship they want (real model vs movies)",
}


def _has(text: Optional[str], *words: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in words)


def _diagnose(answers: dict) -> dict:
    """Rule-based pattern extraction from the hard-question answers.
    Direct but never cruel; patterns, never clinical diagnoses."""
    patterns: list = []
    get = lambda k: (answers.get(k) or "").strip()

    cheated = get("dx_cheated")
    if cheated and _has(cheated, "yes", "yeah", "yep", "i did", "i have", "once",
                        "twice", "a few", "almost", "came close", "thought about it"):
        patterns.append("Cheating in dating history (own or partner's) — trust repair is a live theme")
    elif cheated and _has(cheated, "cheated on me", "they did", "was cheated"):
        patterns.append("Was cheated on — betrayal wound still shaping partner selection")

    last = get("dx_last_why")
    if last:
        if _has(last, "she always", "he always", "they always", "she never",
                 "he never", "crazy", "psycho", "toxic"):
            patterns.append("Tends to externalize why relationships fail — accountability rep needed")
        elif _has(last, "i should", "my fault", "i didn't", "i messed", "i pushed"):
            patterns.append("Takes ownership of past failures — coachable, build on it")

    hurt = get("dx_hurt")
    if hurt and len(hurt) > 3:
        patterns.append("Carries a specific hurt — expect guardedness early, test for walls")

    alone = get("dx_alone")
    if alone:
        if _has(alone, "scared", "afraid", "fear", "hurt", "tired of", "done with"):
            patterns.append("Alone as protection after hurt — avoidance pattern, not preference")
        elif _has(alone, "peace", "happy", "focus", "building", "myself"):
            patterns.append("Genuinely content solo — low desperation, high standards possible")

    expect = get("dx_expect")
    if expect:
        if _has(expect, "take care of me", "provide", "pay", "money", "rich", "stable"):
            patterns.append("Provider/security expectations from a partner — money intertwined with love")
        if _has(expect, "peace", "calm", "safe", "home"):
            patterns.append("Seeks peace and safety — stability over excitement")

    money = get("dx_money")
    if money:
        if _has(money, "very", "10", "huge", "everything", "a lot"):
            patterns.append("Money weighs heavily in partner evaluation — screen both directions")
        elif _has(money, "not", "doesn't matter", "zero", "don't care"):
            patterns.append("Money not a driver — values-led selection")

    jealousy = get("dx_jealousy")
    if jealousy:
        if _has(jealousy, "important", "need", "like it", "love it", "want"):
            patterns.append("Jealousy reads as caring — validation-through-possessiveness pattern")
        elif _has(jealousy, "hate", "toxic", "poison", "red flag"):
            patterns.append("Anti-jealousy — trusts clean, may under-read possessive flags in others")

    sex = get("dx_sex")
    if sex:
        if _has(sex, "very", "10", "huge", "need", "important"):
            patterns.append("Physical connection is a core need — mismatch risk if partner differs")
        elif _has(sex, "not", "meh", "low"):
            patterns.append("Sex not central — emotional/mental connection leads")

    crazy = get("dx_crazy")
    if crazy and len(crazy) > 10:
        patterns.append(f"Self-reported wild pattern to watch: {crazy[:90]}")

    missing = get("dx_missing")
    if missing and len(missing) > 3:
        patterns.append(f"Unmet need from last relationship: {missing[:90]}")

    # ---- family background: family patterns shape dating patterns ----
    fam_close = get("dx_fam_close")
    if fam_close and len(fam_close) > 3:
        patterns.append(f"Primary attachment figure: {fam_close[:90]} — their approval pattern matters")

    parents = get("dx_parents_together")
    if parents:
        if _has(parents, "divorc", "split", "separated"):
            patterns.append("Parents divorced — their model of love includes endings; watch for commitment flinch or normalize-and-repeat")
        elif _has(parents, "together", "married", "still"):
            patterns.append("Parents together — long-term love is normalized, high bar or high pressure possible")

    dad = get("dx_dad_rel")
    if dad:
        if _has(dad, "no", "bad", "terrible", "absent", "don't", "never", "strained", "not really"):
            patterns.append("Strained/absent father relationship — authority and male-pattern echoes possible in dating")
        elif _has(dad, "yes", "good", "great", "close"):
            patterns.append("Solid father relationship — healthy male template present")

    mom = get("dx_mom_rel")
    if mom:
        if _has(mom, "no", "bad", "terrible", "absent", "don't", "never", "strained", "not really"):
            patterns.append("Strained/absent mother relationship — nurturing-pattern echoes possible in dating")
        elif _has(mom, "yes", "good", "great", "close"):
            patterns.append("Solid mother relationship — healthy nurturing template present")

    parents_rel = get("dx_parents_rel")
    if parents_rel:
        if _has(parents_rel, "fight", "fought", "yell", "argue", "toxic", "bad", "terrible", "cheat", "affair"):
            patterns.append("Grew up around parental conflict — may normalize tension or flinch from it; connect this dot in debriefs")
        elif _has(parents_rel, "good", "great", "love", "happy", "solid", "respect"):
            patterns.append("Parents modeled healthy partnership — strong template, measure partners against it honestly")

    # ---- intergenerational patterns: family dynamics repeat in dating ----
    fam_all = " ".join([fam_close, parents, dad, mom, parents_rel])
    if _has(fam_all, "single mom", "single mother", "raised by my mom", "mom raised me",
            "dad left", "father left", "dad was absent", "absent father",
            "never met my dad", "never knew my dad", "don't know my father",
            "mom did it alone", "grew up with just my mom", "just me and my mom"):
        patterns.append("Intergenerational pattern: raised by a single mother — high risk of recreating the same dynamic in dating life; connect the dots explicitly ('you were raised by [pattern], and you're recreating [pattern]') as a pattern to examine and break, never a verdict on anyone's worth")

    # ---- whose voice is already in their head ----
    advice_from = get("dx_advice_from")
    advice_single = get("dx_advice_single")
    if advice_from and len(advice_from) > 3:
        patterns.append(f"Takes dating advice from: {advice_from[:90]} — this is the voice already in their head; contrast it when it's wrong")
    if advice_single and _has(advice_single, "yes", "yeah", "yep", "single", "she is", "he is", "they are"):
        patterns.append("Takes dating advice from a SINGLE person — credibility check: single advising single is suspect; flag it playfully, not meanly")
    elif advice_single and _has(advice_single, "no", "married", "relationship", "taken"):
        patterns.append("Advice-giver is partnered — their counsel at least comes from inside the arena")
    advice_divorced = get("dx_advice_divorced")
    if advice_divorced and _has(advice_divorced, "yes", "yeah", "yep", "divorced", "twice"):
        patterns.append("Advice-giver is DIVORCED — credibility check with nuance: don't blindly trust marriage advice from them, but mine them for what NOT to do; flag playfully")

    # ---- relationship MODEL: is the ideal grounded or fantasy? ----
    talk = get("dx_talk_parents")
    if talk:
        if _has(talk, "no", "don't", "never", "estranged", "not really", "rarely"):
            patterns.append("Barely talks to parents — family template is memory, not a living reference; expectations may be frozen at childhood")
        elif _has(talk, "yes", "yeah", "regularly", "often", "every", "close"):
            patterns.append("In regular contact with parents — family data is live; their dynamic is still shaping expectations in real time")

    model_who = get("dx_model_who")
    if model_who:
        if _has(model_who, "movie", "film", "rom-com", "netflix", "nobody", "no one", "doesn't exist", "fantasy"):
            patterns.append("Relationship ideal exists only in MOVIES — fantasy gap; coach names it: no real model means uncalibrated expectations")
        elif _has(model_who, "my parents", "mom and dad", "my mom", "my dad"):
            patterns.append("Wants what their parents have — grounded model (healthy or not, it's real); measure whether it's worth wanting")
        elif _has(model_who, "friend", "buddy", "sister", "brother", "cousin", "coworker"):
            patterns.append("Wants a friend's/relative's relationship — borrowed model; check whether it's real or curated highlight reel")

    seen: set = set()
    uniq = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    patterns = uniq[:20]

    if not patterns:
        summary = ("No hard-question answers shared yet — coach is blind on root "
                   "patterns. Nudge them to answer when trust builds.")
    else:
        summary = ("Diagnosed from the hard-questions interview: " +
                   "; ".join(patterns[:6]) +
                   ". Target these patterns directly in coaching — this is the user's actual material.")
    return {"patterns": patterns, "summary": summary}


def _pattern_area(text: str) -> str:
    """Classify a diagnosed pattern for the Your Patterns view."""
    t = (text or "").lower()
    if any(w in t for w in ["father", "mother", "parents", "divorc", "attachment figure", "family"]):
        return "family"
    if any(w in t for w in ["unmet need", "money", "provider", "jealousy", "sex", "physical"]):
        return "needs"
    return "dating"


def _user_ctx(user: User, db: Session) -> dict:
    """user_dict + readable onboarding summary + diagnosed patterns, for AI prompts."""
    uinfo = user_dict(user)
    try:
        row = db.get(Onboarding, user.id)
        answers = json.loads(row.answers_json) if row and row.answers_json else {}
    except Exception:
        answers = {}
    lines: list = []
    for key, label in OB_LABELS.items():
        v = (answers.get(key) or "").strip()
        if v:
            lines.append(f"{label}: {v[:300]}")
    for key, label in DX_LABELS.items():
        v = (answers.get(key) or "").strip()
        if v:
            lines.append(f"Hard question — {label}: {v[:300]}")
    diag = answers.get("_diagnosis") or {}
    dpatterns = diag.get("patterns") or []
    if dpatterns:
        lines.append("DIAGNOSED PATTERNS (from the hard-questions interview — target these in coaching):")
        lines.extend(f"- {p}" for p in dpatterns)
        if diag.get("summary"):
            lines.append("Diagnosis summary: " + diag["summary"])
    uinfo["onboarding"] = "\n".join(lines) if lines else "no onboarding summary provided"
    return uinfo


# ---------------------------------------------------------------- app

app = FastAPI(title="Dating Coach AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

api = APIRouter()


@app.on_event("startup")
def _startup():
    init_db()


# ---------------------------------------------------------------- auth

class SignupBody(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    timezone: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


def _normalize_tz(tz: Optional[str]) -> str:
    if not tz:
        return "UTC"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "UTC"


def _issue(user: User) -> dict:
    return {"token": create_token(user.id), "user": user_dict(user)}


@api.post("/auth/signup")
def signup(body: SignupBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        pass_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or None,
        hearts=100,
        timezone=_normalize_tz(body.timezone),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(user)


@api.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.pass_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue(user)


# ---------------------------------------------------------------- me / onboarding

@api.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user_dict(user)}


class MeUpdateBody(BaseModel):
    display_name: Optional[str] = None
    timezone: Optional[str] = None


@api.put("/me")
def update_me(body: MeUpdateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    if body.timezone is not None:
        user.timezone = _normalize_tz(body.timezone)
    db.commit()
    db.refresh(user)
    return {"user": user_dict(user)}


class OnboardingBody(BaseModel):
    answers: dict = Field(default_factory=dict)


@api.post("/onboarding")
def save_onboarding(body: OnboardingBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Onboarding, user.id)
    answers = {k: v for k, v in (body.answers or {}).items() if k != "_diagnosis"}
    answers["_diagnosis"] = _diagnose(answers)
    payload = json.dumps(answers)
    if row:
        row.answers_json = payload
    else:
        db.add(Onboarding(user_id=user.id, answers_json=payload))
    user.onboarding_done = True
    db.commit()
    return {"ok": True, "diagnosis": answers["_diagnosis"]}


@api.get("/onboarding")
def get_onboarding(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Onboarding, user.id)
    answers = json.loads(row.answers_json) if row and row.answers_json else {}
    return {"answers": answers}


# ---------------------------------------------------------------- coaches

@api.get("/coaches")
def coaches():
    return {
        "coaches": [COACHES["nia"], COACHES["maya"], COACHES["marcus"]],
        "locked": [
            {"id": "matchmaker", "name": "Millionaire Matchmaker",
             "note": "Coming soon — premium coach"}
        ],
    }


class CoachPickBody(BaseModel):
    coach_id: str


@api.post("/coach-pick")
def coach_pick(body: CoachPickBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.coach_id not in COACHES:
        raise HTTPException(status_code=400, detail="Unknown or locked coach")
    user.coach_id = body.coach_id
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- coach chat (SSE)

class ChatBody(BaseModel):
    coach_id: str
    message: str


def _coach_system(coach_id: str, user: dict) -> str:
    if coach_id == "nia":
        return P.nia_system(user)
    if coach_id == "marcus":
        return P.marcus_system(user)
    return P.maya_system(user)


def _history_for_model(rows) -> list:
    out = []
    for m in rows:
        role = "assistant" if m.role in ("coach", "date") else "user"
        out.append({"role": role, "content": m.text})
    return out


@api.post("/chat")
def chat(body: ChatBody, user: User = Depends(get_current_user)):
    if body.coach_id not in COACHES:
        raise HTTPException(status_code=400, detail="Unknown coach")
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    uid = user.id

    def gen():
        db = SessionLocal()
        try:
            uinfo = _user_ctx(db.get(User, uid), db)
            db.add(Message(user_id=uid, coach_id=body.coach_id, role="user", text=body.message.strip()))
            db.commit()
            past = (
                db.query(Message)
                .filter(Message.user_id == uid, Message.coach_id == body.coach_id)
                .order_by(Message.id.desc()).limit(30).all()
            )
            past.reverse()
            system = _coach_system(body.coach_id, uinfo)
            mock_text = _mock_chat_text(body.coach_id, body.message)
            full = []
try:
    for chunk in ai.stream(system, _history_for_model(turns), mock_text):
        full.append(chunk)
        yield sse({"delta": chunk})
except Exception:
    pass
reply = "".join(full).strip()
if not reply:
    # Live AI refused or failed — fall back to the in-character
    # canned reply instead of leaving the user hanging.
    reply = mock_text
    yield sse({"delta": mock_text})

            msg = Message(user_id=uid, coach_id=body.coach_id, role="coach", text=reply)
            db.add(msg)
            db.commit()
            db.refresh(msg)
            yield sse({"done": True, "message_id": msg.id})
        finally:
            db.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


@api.get("/chat/history")
def chat_history(
    coach_id: str = Query(...),
    before: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if coach_id not in COACHES:
        raise HTTPException(status_code=400, detail="Unknown coach")
    before_id = parse_before(before)
    q = db.query(Message).filter(Message.user_id == user.id, Message.coach_id == coach_id)
    if before_id is not None:
        q = q.filter(Message.id < before_id)
    rows = q.order_by(Message.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return {
        "messages": [
            {"id": m.id, "role": m.role, "text": m.text, "created_at": iso(m.created_at)}
            for m in rows
        ],
        "has_more": has_more,
    }


# ---------------------------------------------------------------- dates

def _custom_date_dict(cd: CustomDate) -> dict:
    return {
        "id": cd.id, "name": cd.name, "age": cd.age, "tagline": cd.tagline,
        "img": cd.img, "personality": cd.personality,
        "ethnicity": cd.ethnicity, "vibe": cd.vibe, "celebrity_type": cd.celebrity_type,
    }


@api.get("/dates")
def list_dates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dates = list(PRESET_DATES)
    customs = (
        db.query(CustomDate)
        .filter(CustomDate.user_id == user.id)
        .order_by(CustomDate.created_at.asc()).all()
    )
    dates.extend(_custom_date_dict(c) for c in customs)
    return {"dates": dates}


class CustomDateBody(BaseModel):
    name: Optional[str] = None
    personality: str
    ethnicity: Optional[str] = None
    vibe: Optional[str] = None
    celebrity_type: Optional[str] = None


@api.post("/dates/custom")
def create_custom_date(body: CustomDateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.personality or not body.personality.strip():
        raise HTTPException(status_code=400, detail="personality is required")
    n = db.query(func.count(CustomDate.id)).filter(CustomDate.user_id == user.id).scalar() or 0
    date_id = f"custom-{n + 1}"
    digest = int(hashlib.md5(date_id.encode()).hexdigest(), 16)
    age = 24 + (digest % 8)  # 24-31
    img = f"/assets/dates/date{(digest % 5) + 1}.webp"
    tagline_src = (body.vibe or body.personality or "Custom date").strip()
    cd = CustomDate(
        id=date_id, user_id=user.id,
        name=(body.name or "").strip() or "Custom Date",
        age=age,
        personality=body.personality.strip(),
        ethnicity=(body.ethnicity or "").strip() or None,
        vibe=(body.vibe or "").strip() or None,
        celebrity_type=(body.celebrity_type or "").strip() or None,
        tagline=tagline_src[:120],
        img=img,
    )
    db.add(cd)
    db.commit()
    db.refresh(cd)
    return {"date": _custom_date_dict(cd)}


def _resolve_date(date_id: str, user_id: int, db: Session) -> dict:
    for p in PRESET_DATES:
        if p["id"] == date_id:
            return dict(p)
    cd = (
        db.query(CustomDate)
        .filter(CustomDate.user_id == user_id, CustomDate.id == date_id)
        .first()
    )
    if cd:
        return _custom_date_dict(cd)
    raise HTTPException(status_code=404, detail="Date not found")


# ---------------------------------------------------------------- simulations

class SimStartBody(BaseModel):
    date_id: str


@api.post("/sim/start")
def sim_start(body: SimStartBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    persona = _resolve_date(body.date_id, user.id, db)
    sim = Simulation(
        user_id=user.id, date_id=body.date_id, date_name=persona["name"],
        persona_json=json.dumps(persona),
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)

   system = P.date_system(persona, _user_ctx(user, db))
mock_opening = _mock_opening(persona)
try:
    opening = ai.complete(
        system,
        [{"role": "user", "content": "Send your opening message to start the conversation. Stay in character, keep it short and text-like."}],
        mock_opening,
        max_tokens=200,
    ).strip()
except Exception:
    opening = ""
if not opening:
    # Live AI refused or failed (safety filter, demand spike, etc.) —
    # fall back to the in-character canned opener instead of 500ing.
    opening = mock_opening

msg = SimMessage(simulation_id=sim.id, role="date", text=opening)
db.add(msg)
db.commit()
db.refresh(msg)
return {"simulation_id": sim.id, "opening": {"id": msg.id, "text": opening}}

    ).strip()
except Exception:
    opening = ""
if not opening:
    # Live AI refused or failed (safety filter, demand spike, etc.) —
    # fall back to the in-character canned opener instead of 500ing.
    opening = mock_opening

    msg = SimMessage(simulation_id=sim.id, role="date", text=opening)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"simulation_id": sim.id, "opening": {"id": msg.id, "text": opening}}


class SimMessageBody(BaseModel):
    simulation_id: int
    message: str


@api.post("/sim/message")
def sim_message(body: SimMessageBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    # Ownership / state checks happen BEFORE streaming so failures are real HTTP errors.
    sim = db.get(Simulation, body.simulation_id)
    if not sim or sim.user_id != user.id:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim.ended_at is not None:
        raise HTTPException(status_code=400, detail="Simulation already ended")
    uid = user.id

    def gen():
        db = SessionLocal()
        try:
            uinfo = _user_ctx(db.get(User, uid), db)
            sim = db.get(Simulation, body.simulation_id)
            db.add(SimMessage(simulation_id=sim.id, role="user", text=body.message.strip()))
            db.commit()
            persona = json.loads(sim.persona_json or "{}")
            turns = (
                db.query(SimMessage)
                .filter(SimMessage.simulation_id == sim.id)
                .order_by(SimMessage.id.asc()).all()
            )[-40:]
            system = P.date_system(persona, uinfo)
            mock_text = _mock_date_reply(persona, body.message)
            full = []
            for chunk in ai.stream(system, _history_for_model(turns), mock_text):
                full.append(chunk)
                yield sse({"delta": chunk})
            reply = "".join(full).strip()
            msg = SimMessage(simulation_id=sim.id, role="date", text=reply)
            db.add(msg)
            db.commit()
            db.refresh(msg)
            yield sse({"done": True, "message_id": msg.id})
        finally:
            db.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


class SimEndBody(BaseModel):
    simulation_id: int


def _hearts_delta(score: int) -> int:
    if score >= 80:
        return 15
    if score >= 65:
        return 10
    if score >= 50:
        return 5
    if score >= 35:
        return -5
    return -10


@api.post("/sim/end")
def sim_end(body: SimEndBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sim = db.get(Simulation, body.simulation_id)
    if not sim or sim.user_id != user.id:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim.ended_at is not None:
        raise HTTPException(status_code=400, detail="Simulation already ended")

    turns = (
        db.query(SimMessage)
        .filter(SimMessage.simulation_id == sim.id)
        .order_by(SimMessage.id.asc()).all()
    )
    persona = json.loads(sim.persona_json or "{}")
    transcript = "\n".join(
        f"{'You' if t.role == 'user' else persona.get('name', 'Date')}: {t.text}" for t in turns
    ) or "(no messages exchanged)"
    n_user_turns = sum(1 for t in turns if t.role == "user")

    grading_emphasis = ""
    if (sim.date_name or "").strip().lower() == "dre":
        grading_emphasis = (
            "\n\nGRADING EMPHASIS — this date (Dre) is a firm, direct man with clear "
            "expectations. Grade the user's BACKBONE and COMPOSURE above all: did "
            "they hold frame, stay composed under his directness, and state their "
            "own standards clearly? Hearts move on backbone and composure with a "
            "firm man — NOT on people-pleasing, over-accommodating, or shrinking "
            "to keep the peace."
        )

    lifelines = (
        db.query(CoachLifeline)
        .filter(CoachLifeline.simulation_id == sim.id)
        .order_by(CoachLifeline.id.asc()).all()
    )
    lifeline_note = ""
    if lifelines:
        items = "\n".join(
            f"- [{iso(l.created_at)}] User asked the coach: \"{l.question[:140]}\""
            for l in lifelines
        )
        lifeline_note = (
            "\n\nCOACH LIFELINE USED (using it is fine — note WHAT they asked and whether "
            "the transcript shows the advice helped or they ignored it):\n" + items
        )

    raw = ai.complete(
        P.feedback_system(user.coach_id or "nia"),
        [{"role": "user",
          "content": f"Practice date with {persona.get('name', 'a date')} "
                     f"(personality: {persona.get('personality', '')}). "
                     f"Transcript:\n{transcript}\n\nGive markdown feedback and end with SCORE: <0-100>."
                     f"{grading_emphasis}{lifeline_note}"}],
        _mock_feedback(persona, n_user_turns),
        max_tokens=1200,
    )
    m = re.search(r"SCORE:\s*(\d{1,3})", raw, re.IGNORECASE)
    score = max(0, min(100, int(m.group(1)))) if m else 70
    feedback = re.sub(r"(?im)^\s*SCORE:\s*\d{1,3}\s*$", "", raw).strip()

    delta = _hearts_delta(score)
    user.hearts = max(0, user.hearts + delta)
    sim.ended_at = datetime.utcnow()
    sim.score = score
    notes = feedback[:2000]
    card = Scorecard(user_id=user.id, date_name=sim.date_name, score=score, notes=notes)
    db.add(card)
    db.commit()
    db.refresh(card)
    db.refresh(user)
    return {
        "feedback": feedback,
        "hearts_delta": delta,
        "new_hearts": user.hearts,
        "scorecard": {
            "id": card.id, "date_name": card.date_name, "score": card.score,
            "notes": card.notes, "created_at": iso(card.created_at),
        },
    }


@api.get("/sim/history")
def sim_history(
    before: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    before_id = parse_before(before)
    q = db.query(Simulation).filter(Simulation.user_id == user.id)
    if before_id is not None:
        q = q.filter(Simulation.id < before_id)
    sims = q.order_by(Simulation.id.desc()).limit(limit + 1).all()
    has_more = len(sims) > limit
    sims = sims[:limit]
    counts = {}
    if sims:
        rows = (
            db.query(SimMessage.simulation_id, func.count(SimMessage.id))
            .filter(SimMessage.simulation_id.in_([s.id for s in sims]))
            .group_by(SimMessage.simulation_id).all()
        )
        counts = {sid: c for sid, c in rows}
    return {
        "sims": [
            {
                "id": s.id, "date_name": s.date_name,
                "started_at": iso(s.started_at), "ended_at": iso(s.ended_at),
                "message_count": counts.get(s.id, 0), "score": s.score,
            }
            for s in sims
        ],
        "has_more": has_more,
    }


# ---------------------------------------------------------------- ask-coach lifeline

def _mock_lifeline_text(coach_id: str, question: str) -> str:
    snippet = question.strip()[:60]
    if coach_id == "marcus":
        return (
            f"You asked: \"{snippet}\" — here's your move: stop thinking, execute. "
            "One honest sentence, hold frame, then flip it back on them. "
            "Backbone now, analysis later."
        )
    if coach_id == "maya":
        return (
            f"Good instinct asking — \"{snippet}\". Here's the move: stay warm but boundaried. "
            "Answer honestly in one or two sentences, then ask them the same question back. "
            "Reciprocity tells you everything."
        )
    return (
        f"Quick triage on \"{snippet}\": don't answer the question they asked — answer the one "
        "behind it. One calm, honest sentence, no over-explaining. Then flip it: \"what about you?\" "
        "Whoever's asking the questions is leading."
    )


class AskCoachBody(BaseModel):
    simulation_id: int
    question: str


@api.post("/sim/ask-coach")
def sim_ask_coach(body: AskCoachBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="Question required")
    sim = db.get(Simulation, body.simulation_id)
    if not sim or sim.user_id != user.id:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim.ended_at is not None:
        raise HTTPException(status_code=400, detail="Simulation already ended")
    coach_id = user.coach_id if user.coach_id in COACHES else "nia"
    persona = json.loads(sim.persona_json or "{}")
    turns = (
        db.query(SimMessage)
        .filter(SimMessage.simulation_id == sim.id)
        .order_by(SimMessage.id.desc()).limit(20).all()
    )
    turns.reverse()
    transcript = "\n".join(
        f"{'You' if t.role == 'user' else persona.get('name', 'Date')}: {t.text}" for t in turns
    ) or "(no messages yet)"
    uinfo = _user_ctx(user, db)
    advice = ai.complete(
        P.lifeline_system(coach_id),
        [{"role": "user",
          "content": f"Practice date with {persona.get('name', 'a date')} "
                     f"(personality: {persona.get('personality', '')}).\n"
                     f"Transcript so far:\n{transcript}\n\n"
                     f"User's diagnosed patterns: {(uinfo.get('onboarding') or '')[:1500]}\n\n"
                     f"User's mid-date question: \"{body.question.strip()}\"\n\n"
                     "Give your short tactical advice now."}],
        _mock_lifeline_text(coach_id, body.question),
        max_tokens=200,
    ).strip()
    row = CoachLifeline(
        simulation_id=sim.id, user_id=user.id, coach_id=coach_id,
        question=body.question.strip(), advice=advice,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "advice": advice,
        "coach_id": coach_id,
        "coach_name": COACHES[coach_id]["name"],
        "created_at": iso(row.created_at),
    }


# ---------------------------------------------------------------- your patterns (living mirror)

def _mock_mirror_text(coach_id: str, name: str) -> str:
    if coach_id == "marcus":
        return (
            f"{name}, here's your mirror: your patterns are showing up in every rep — "
            "that's the point, we found the material. Now it's reps, not realizations. "
            "Pick ONE pattern below and attack it this week."
        )
    if coach_id == "maya":
        return (
            f"{name}, look at how far this mirror goes back — every date, every debrief, it's all you, "
            "learning out loud. Be gentle with what you see here, but don't look away from it. "
            "Awareness is the whole first half of change."
        )
    return (
        f"{name}, this is your file — everything the gym has learned about your dating patterns. "
        "Read it like a chart, not a verdict. The stuff that repeats is the stuff to train."
    )


@api.get("/patterns")
def patterns(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = db.get(Onboarding, user.id)
        answers = json.loads(row.answers_json) if row and row.answers_json else {}
    except Exception:
        answers = {}
    diag = answers.get("_diagnosis") or {}
    dpatterns = diag.get("patterns") or []
    grouped = {"dating": [], "family": [], "needs": []}
    for p in dpatterns:
        grouped[_pattern_area(p)].append(p)
    cards = (
        db.query(Scorecard)
        .filter(Scorecard.user_id == user.id)
        .order_by(Scorecard.id.desc()).limit(5).all()
    )
    exposed = [
        {"date_name": c.date_name, "score": c.score,
         "notes": (c.notes or "")[:400], "created_at": iso(c.created_at)}
        for c in cards
    ]
    lifelines = (
        db.query(CoachLifeline)
        .filter(CoachLifeline.user_id == user.id)
        .order_by(CoachLifeline.id.desc()).limit(5).all()
    )
    lifeline_themes = [
        {"question": l.question[:160], "created_at": iso(l.created_at)} for l in lifelines
    ]
    coach_id = user.coach_id if user.coach_id in COACHES else "nia"
    name = user.display_name or "there"
    debriefs = (
        " | ".join(
            f"{c.date_name} (score {c.score}): {(c.notes or '')[:200]}" for c in cards
        ) if cards else "no sims yet"
    )
    mirror = ai.complete(
        P.mirror_system(coach_id),
        [{"role": "user",
          "content": f"User: {name}.\n"
                     f"Diagnosed patterns: {'; '.join(dpatterns) or 'none yet'}.\n"
                     f"Recent date debriefs: {debriefs}\n\n"
                     "Write the mirror reflection now."}],
        _mock_mirror_text(coach_id, name),
        max_tokens=300,
    ).strip()
    return {
        "mirror": mirror,
        "coach_id": coach_id,
        "coach_name": COACHES[coach_id]["name"],
        "diagnosis_summary": diag.get("summary", ""),
        "grouped_patterns": grouped,
        "exposed_in_sims": exposed,
        "lifeline_themes": lifeline_themes,
        "sims_completed": len(cards),
    }


# ---------------------------------------------------------------- tools

class ReplyBody(BaseModel):
    # Accept a pasted string (what the frontend sends) or a structured list.
    conversation: Union[str, list] = Field(default_factory=list)


@api.post("/tools/reply")
def tools_reply(body: ReplyBody, user: User = Depends(get_current_user)):
    convo = body.conversation or []
    if isinstance(convo, str):
        convo_text = convo.strip() or "(no conversation provided)"
    else:
        convo_text = "\n".join(
            f"{c.get('role', c.get('sender', '?'))}: {c.get('text', c.get('message', ''))}"
            for c in convo if isinstance(c, dict)
        ) or "(no conversation provided)"
    mock = json.dumps({
        "options": [
            {"reply": "Haha, that's one way to put it 😄 what was the highlight of your week though?",
             "strategy": "Playful deflection + redirect: acknowledge lightly, then steer to something real. Shows confidence without chasing the joke."},
            {"reply": "Interesting take. Tell me the story behind that — I'm curious.",
             "strategy": "Curiosity hook: invites them to invest more in the conversation. People love talking about themselves."},
            {"reply": "Bold 😏 I like it. But fair warning, I ask better questions than I answer.",
             "strategy": "Mirrored energy + playful challenge: matches their boldness and adds light tension. Keeps you from sounding needy."},
        ]
    })
    raw = ai.complete(
        P.help_reply_system(),
        [{"role": "user",
          "content": "Conversation so far:\n" + convo_text +
                     "\n\nRespond with JSON: {\"options\": [{\"reply\": \"...\", \"strategy\": \"...\"}, ...]} "
                     "with 3 options. Reply text only in 'reply', the why in 'strategy'."}],
        mock,
        max_tokens=800,
    )
    try:
        data = json.loads(raw)
        options = data.get("options") if isinstance(data, dict) else None
    except Exception:
        options = None
    if not options:
        # Try to salvage: if the model returned prose, wrap it as a single option set fallback.
        options = json.loads(mock)["options"]
    options = [
        {"reply": str(o.get("reply", "")), "strategy": str(o.get("strategy", ""))}
        for o in options[:3] if isinstance(o, dict)
    ]
    return {"options": options}


class DecodeBody(BaseModel):
    message: str


@api.post("/tools/decode")
def tools_decode(body: DecodeBody, user: User = Depends(get_current_user)):
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    mock = json.dumps({
        "subtext": "They're interested but keeping it casual — testing whether you'll chase.",
        "tone": "Playfully guarded",
        "red_flags": [
            {"flag": "Vagueness", "explanation": "No concrete details or plans; keeps things non-committal."},
        ],
    })
    raw = ai.complete(
        P.decode_system(),
        [{"role": "user",
          "content": f"Decode this message: \"{body.message.strip()}\"\n\n"
                     "Respond with JSON: {\"subtext\": \"...\", \"tone\": \"...\", "
                     "\"red_flags\": [{\"flag\": \"...\", \"explanation\": \"...\"}]}"}],
        mock,
        max_tokens=600,
    )
    try:
        data = json.loads(raw)
    except Exception:
        data = json.loads(mock)
    red_flags = data.get("red_flags") or []
    return {
        "subtext": str(data.get("subtext", "")),
        "tone": str(data.get("tone", "")),
        "red_flags": [
            {"flag": str(r.get("flag", "")), "explanation": str(r.get("explanation", ""))}
            for r in red_flags if isinstance(r, dict)
        ],
    }


# ---------------------------------------------------------------- history / stats

@api.get("/history")
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cards = (
        db.query(Scorecard)
        .filter(Scorecard.user_id == user.id)
        .order_by(Scorecard.id.desc()).all()
    )
    scores = [c.score for c in cards]
    return {
        "scorecards": [
            {"id": c.id, "date_name": c.date_name, "score": c.score,
             "notes": c.notes, "created_at": iso(c.created_at)}
            for c in cards
        ],
        "stats": {
            "simulations_completed": len(cards),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "hearts": user.hearts,
        },
    }


# ---------------------------------------------------------------- fresh restart

class FreshRestartBody(BaseModel):
    confirm: bool = False


@api.post("/fresh-restart")
def fresh_restart(body: FreshRestartBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.confirm is not True:
        raise HTTPException(status_code=400, detail="confirm must be true")
    uid = user.id
    # Clear chat messages
    db.query(Message).filter(Message.user_id == uid).delete(synchronize_session=False)
    # Clear simulations + their turns
    sim_ids = [s.id for s in db.query(Simulation.id).filter(Simulation.user_id == uid).all()]
    if sim_ids:
        db.query(SimMessage).filter(SimMessage.simulation_id.in_(sim_ids)).delete(synchronize_session=False)
        db.query(Simulation).filter(Simulation.user_id == uid).delete(synchronize_session=False)
    # Clear check-in seen markers
    db.query(CheckinSeen).filter(CheckinSeen.user_id == uid).delete(synchronize_session=False)
    # KEEP: scorecards, custom dates, onboarding, user identity/coach pick
    user.hearts = 100
    db.commit()
    db.refresh(user)
    return {"ok": True, "hearts": user.hearts}


# ---------------------------------------------------------------- check-ins

_checkin_text_cache: dict = {}

MORNING_AT = time(9, 54)
EVENING_AT = time(18, 54)


def _due_checkins(user: User, db: Session) -> list:
    try:
        tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    day = now.strftime("%Y-%m-%d")
    kinds = []
    if now.time() >= MORNING_AT:
        kinds.append("morning")
    if now.time() >= EVENING_AT:
        kinds.append("evening")
    seen_keys = {
        r.checkin_key for r in
        db.query(CheckinSeen).filter(CheckinSeen.user_id == user.id).all()
    }
    out = []
    uinfo = _user_ctx(user, db)
    for kind in kinds:
        key = f"{day}-{kind}"
        cache_key = (user.id, key)
        if cache_key not in _checkin_text_cache:
            _checkin_text_cache[cache_key] = ai.complete(
                P.checkin_prompt(kind, uinfo),
                [{"role": "user", "content": "Write the check-in message now. 1-2 sentences, text-message tone."}],
                _mock_checkin_text(kind, uinfo),
                max_tokens=150,
            ).strip()
        out.append({
            "id": key, "kind": kind,
            "text": _checkin_text_cache[cache_key],
            "seen": key in seen_keys,
        })
    return out


@api.get("/checkins")
def checkins(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"checkins": _due_checkins(user, db)}


class CheckinSeenBody(BaseModel):
    id: str


@api.post("/checkins/seen")
def checkin_seen(body: CheckinSeenBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.id:
        raise HTTPException(status_code=400, detail="id required")
    exists = db.get(CheckinSeen, {"user_id": user.id, "checkin_key": body.id})
    if not exists:
        db.add(CheckinSeen(user_id=user.id, checkin_key=body.id))
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- health + mount

@api.get("/health")
def health():
    return {"ok": True, "prompts": P.PROMPTS_SOURCE, "mock_ai": ai.is_mock()}


app.include_router(api, prefix="/api")

_frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(_frontend_dir):
    # Mounted AFTER the API router so /api/* routes take precedence.
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
