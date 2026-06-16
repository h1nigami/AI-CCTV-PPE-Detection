from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "ppe.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionFactory = sessionmaker(bind=engine)
Session = scoped_session(SessionFactory)


def init_db():
    from backend.db.models import Base
    Base.metadata.create_all(bind=engine)


def get_session():
    return Session()
