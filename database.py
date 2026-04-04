import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# .env dosyasından parametreleri çek (mevcut şifreler korunur)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "akilli_envanter")

# PyMySQL driver'ı ile SQLAlchemy URL'si oluştur
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# Engine (Motor) Kurulumu — Production connection pool ayarları
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,          # Her kullanımda bağlantı canlılık ping'i
    pool_size=10,                # Sürekli açık bağlantı sayısı
    max_overflow=20,             # Ani trafik artışında ek bağlantı izni
    pool_recycle=3600,           # 1 saatte bir bağlantı yenile (MySQL 8h timeout önce)
    pool_timeout=30,             # Bağlantı bekleme süresi (şaniye)
)

# Oturum Yöneticisi (Session)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tablo Modellerinin Türetileceği Temel Sınıf
Base = declarative_base()

# FastAPI için veritabanı oturumu sağlayan 'Generator'
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
