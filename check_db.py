import sys
sys.path.append("/Users/egeargun/akilli_envanter_api")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models
import os
from dotenv import load_dotenv

load_dotenv("/Users/egeargun/akilli_envanter_api/.env")
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    DB_URL = "mysql+pymysql://admin:5%3Dfq~%24PKqhvU9A-%3CuA2o%60zv@inventory-db.cj4socue4xip.eu-north-1.rds.amazonaws.com:3306/inventory_db"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()
items = db.query(models.MenuItem).all()
for i in items:
    print(f"{i.name} | {i.category} | {i.image_url}")
db.close()
