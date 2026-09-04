from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pathlib import Path

db_path = Path(__file__).parent.parent / 'data.db'

engine = create_engine(
    f"sqlite:///{db_path}",
    echo=True, #打印sql
    connect_args={"check_same_thread":False}
)


SessionLocal = sessionmaker(bind=engine,autoflush=True)