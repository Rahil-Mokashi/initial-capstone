from sqlalchemy.orm import sessionmaker
from .connection import engine


SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
