from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from .config import get_settings

settings = get_settings()

# SQLAlchemy setup (for future use)
engine = create_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Motor (MongoDB) setup
mongo_client = AsyncIOMotorClient(settings.MONGODB_URI)
mongo_db = mongo_client[settings.MONGODB_DB]

def get_mongo_db():
    return mongo_db 