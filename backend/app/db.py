from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema() -> None:
    """SQLite create_all does not add columns to existing tables."""
    from sqlalchemy import text

    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(sessions)"))}
        if cols and "credential_id" not in cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN credential_id INTEGER"))
        if cols and "baud" not in cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN baud INTEGER DEFAULT 9600"))
        if cols and "folder" not in cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN folder VARCHAR(400) DEFAULT ''"))
        try:
            conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(title, body, doc_id UNINDEXED)"))
        except Exception:
            pass
