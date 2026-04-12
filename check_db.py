import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()
items = db.query(models.MenuItem).all()
for i in items:
    print(f"{i.name} | {i.category} | {i.image_url}")
db.close()
