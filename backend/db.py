"""DB engine/session setup. SQLite by default; DATABASE_URL overrides (e.g. Postgres)."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    _here = os.path.dirname(os.path.abspath(__file__))
    DATABASE_URL = f"sqlite:///{os.path.join(_here, 'dating_coach.db')}"

# Force the psycopg2 driver: newer SQLAlchemy defaults to psycopg (v3),
# but we ship psycopg2-binary. Without the explicit dialect the import fails.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
