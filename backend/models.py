"""SQLAlchemy models for the Dating Coach AI backend."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    pass_hash = Column(String(255), nullable=False)
    display_name = Column(String(120), nullable=True)
    coach_id = Column(String(32), nullable=True)
    hearts = Column(Integer, nullable=False, default=100)
    timezone = Column(String(64), nullable=False, default="UTC")
    onboarding_done = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    simulations = relationship("Simulation", back_populates="user", cascade="all, delete-orphan")
    custom_dates = relationship("CustomDate", back_populates="user", cascade="all, delete-orphan")
    scorecards = relationship("Scorecard", back_populates="user", cascade="all, delete-orphan")


class Onboarding(Base):
    __tablename__ = "onboarding"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    answers_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Message(Base):
    """Coach chat messages. role: 'user' | 'coach'."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    coach_id = Column(String(32), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user | coach
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    user = relationship("User", back_populates="messages")


class CustomDate(Base):
    __tablename__ = "custom_dates"

    id = Column(String(32), primary_key=True)  # custom-<n> (per user)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=False)
    personality = Column(Text, nullable=False)
    ethnicity = Column(String(120), nullable=True)
    vibe = Column(String(200), nullable=True)
    celebrity_type = Column(String(200), nullable=True)
    tagline = Column(String(200), nullable=True)
    img = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    user = relationship("User", back_populates="custom_dates")

    __table_args__ = (UniqueConstraint("user_id", "id", name="uq_custom_date_user"),)


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date_id = Column(String(32), nullable=False)  # preset-N or custom-N
    date_name = Column(String(120), nullable=False)
    persona_json = Column(Text, nullable=False, default="{}")
    started_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    ended_at = Column(DateTime, nullable=True)
    score = Column(Integer, nullable=True)

    user = relationship("User", back_populates="simulations")
    turns = relationship("SimMessage", back_populates="simulation", cascade="all, delete-orphan")


class SimMessage(Base):
    """Simulation turns. role: 'user' | 'date'."""
    __tablename__ = "sim_messages"

    id = Column(Integer, primary_key=True)
    simulation_id = Column(Integer, ForeignKey("simulations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user | date
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    simulation = relationship("Simulation", back_populates="turns")


class Scorecard(Base):
    __tablename__ = "scorecards"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date_name = Column(String(120), nullable=False)
    score = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    user = relationship("User", back_populates="scorecards")


class CoachLifeline(Base):
    """Mid-date 'Ask Coach' lifeline uses. Timestamped so the post-sim debrief
    can factor in what the user asked their coach about."""
    __tablename__ = "coach_lifelines"

    id = Column(Integer, primary_key=True)
    simulation_id = Column(Integer, ForeignKey("simulations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    coach_id = Column(String(32), nullable=False)
    question = Column(Text, nullable=False)
    advice = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class CheckinSeen(Base):
    __tablename__ = "checkins_seen"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    checkin_key = Column(String(64), primary_key=True)  # e.g. 2026-10-03-morning
    seen_at = Column(DateTime, nullable=False, default=utcnow)
