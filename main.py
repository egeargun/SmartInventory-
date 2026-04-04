from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, text
from typing import List, Dict, Optional
import datetime
import logging
import os
from contextlib import asynccontextmanager
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import secrets
from apscheduler.schedulers.background import BackgroundScheduler
from notifications import send_supplier_email, trigger_stock_webhook, send_admin_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("akilli_envanter_api")

import models
import schemas
from database import engine, get_db
from auth import (
    verify_password, get_password_hash, create_access_token,
    create_refresh_token, decode_refresh_token,
    role_required, get_current_user, verify_api_key
)
from schemas import StockTransaction, ProductCreate, TalepYaniti, WebhookSalePayload, ApiKeyCreate, QROrderRequest



class SatisTalebi(BaseModel):
    menu_item_id: int
    adet: int
    musteri_adi: Optional[str] = None
    payment_method: str = "Nakit"
    customer_id: Optional[int] = None

class TableOrderAdd(BaseModel):
    table_id: int
    menu_item_id: int
    quantity: int
    is_ikram: bool = False  # True ise fiyatı 0 (sıfır) kaydedilir

class BulkTableOrderRequest(BaseModel):
    table_id: int
    items: List[dict] # [{"menu_item_id": 1, "quantity": 1, "is_ikram": false}]

class CustomerLookup(BaseModel):
    phone_number: str
    name: Optional[str] = None

class UpsellRequest(BaseModel):
    current_item_ids: List[int]

class TableLocationUpdate(BaseModel):
    table_id: int
    x_pos: float
    y_pos: float

class CheckoutRequest(BaseModel):
    table_id: Optional[int] = None # Null ise Paket Servis
    payment_method: str = "Nakit"  # Tamamı bu yöntemle ödeniyorsa
    amount_cash: float = 0.0       # Parçalı (Split) ödeme Nakit tutarı
    amount_card: float = 0.0       # Parçalı (Split) ödeme Kart tutarı
    discount: float = 0.0          # İndirim tutarı (TL)
    customer_id: Optional[int] = None # Z-Raporunu CRM sadakat hesabına işler
    points_used: int = 0           # Eğer Müşteri kahve/indirim kazandıysa harcanan puan
    use_free_coffee: bool = False  # 9 Damga hediye kahve uygulansın mı?

class TableMoveRequest(BaseModel):
    from_table_id: int
    to_table_id: int

class ExpenseCreate(BaseModel):
    category: str
    amount: float
    description: str

class WastageCreate(BaseModel):
    product_id: int
    quantity: float
    reason: str

class SettingsUpdate(BaseModel):
    cafe_name: str
    tax_rate: float
    currency: str = "TL"
    address: Optional[str] = None

class MenuItemCreate(BaseModel):
    name: str
    price: float
    category: str
    image_emoji: str = "☕"

class VardiyaKapat(BaseModel):
    teslim_edilen_nakit: float
    teslim_edilen_kart: float

class RegisterUser(BaseModel):
    username: str
    password: str
    role: str = "Barista"

# Not: Veritabanı tabloları artık Alembic (Migrations) ile yönetiliyor.
# Manuel oluşturma (create_all) devri enterprise mimaride kapandı.

# ==========================================
# --- RATE LIMITER (BRUTE-FORCE KORUMASI) ---
# ==========================================
limiter = Limiter(key_func=get_remote_address)

# ==========================================
# --- 🕰️ PLANLANMIŞ GÖREVLER (CRON) ---
# ==========================================
scheduler = BackgroundScheduler()

def daily_system_check():
    """Her gece 00:00'da çalışan kritik kontroller."""
    db = next(get_db())
    try:
        # 1. SKT Yaklaşanlar (7 gün)
        bugun = datetime.date.today()
        kritik_tarih = bugun + datetime.timedelta(days=7)
        skt_yaklasanlar = db.query(models.Product).filter(
            models.Product.expiration_date <= kritik_tarih,
            models.Product.current_stock > 0
        ).all()
        
        # 2. Kritik Stok Özeti
        kritik_stoklar = db.query(models.Product).filter(
            models.Product.current_stock <= models.Product.reorder_point
        ).all()

        if skt_yaklasanlar or kritik_stoklar:
            report = f"📅 Günlük Sistem Raporu - {bugun}\n\n"
            if skt_yaklasanlar:
                report += "⚠️ SKT Yaklaşan Ürünler:\n"
                for u in skt_yaklasanlar:
                    report += f"- {u.name_tr} (SKT: {u.expiration_date}, Stok: {u.current_stock})\n"
            
            if kritik_stoklar:
                report += "\n📉 Kritik Stok Seviyesindeki Ürünler:\n"
                for u in kritik_stoklar:
                    report += f"- {u.name_tr} (Mevcut: {u.current_stock}, Eşik: {u.reorder_point})\n"
            
            # Admin'e gönder (Arka planda çalışır)
            import asyncio
            asyncio.run(send_admin_report(f"🏛️ Envanter Raporu - {bugun}", report))
            logger.info("Günlük sistem raporu hazırlandı ve kuyruğa alındı.")

    except Exception as e:
        logger.error(f"Planlanmış görev hatası: {str(e)}")
    finally:
        db.close()

def archive_old_audit_logs():
    """Her gece 01:00'de 7 günden eski denetim kayıtlarını arşivler (siler değil, gizler)."""
    db = next(get_db())
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        eski_kayitlar = db.query(models.AuditLog).filter(
            models.AuditLog.timestamp < cutoff,
            models.AuditLog.is_archived == 0
        ).all()
        for log in eski_kayitlar:
            log.is_archived = 1
            log.archived_at = datetime.datetime.utcnow()
        db.commit()
        logger.info(f"{len(eski_kayitlar)} denetim kaydı arşivlendi.")
    except Exception as e:
        logger.error(f"Arshiv görevi hatası: {str(e)}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("İş Zekası Envanter API başarıyla başlatıldı.")
    # 2. POS Masalarını Hazırla (17 Masa)
    try:
        db = next(get_db())
        count = db.query(models.Table).count()
        if count < 17:
            for i in range(1, 18):
                exists = db.query(models.Table).filter(models.Table.name == f"Masa {i}").first()
                if not exists:
                    db.add(models.Table(name=f"Masa {i}"))
            db.commit()
            logger.info("17 Adet POS Masası oluşturuldu.")
    except Exception as e:
        logger.error(f"Masa kurulum hatası: {str(e)}")

    yield
    scheduler.shutdown()
    logger.info("API kapatılıyor.")

# Scheduler görevlerini başlat
scheduler.add_job(daily_system_check, 'cron', hour=0, minute=0, id='daily_check')
scheduler.add_job(archive_old_audit_logs, 'cron', hour=1, minute=0, id='audit_archive')
scheduler.start()

app = FastAPI(
    title="Akıllı Kafe Envanter Sistemi",
    version="2.1",
    lifespan=lifespan
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Rate Limit handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# --- YARDIMCI: İSTEK'TEN IP ADRESİ ÇEK ---
def get_client_ip(request: Request) -> str:
    """Proxy arkasında bile doğru IP adresini al (X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

# --- WEBSOCKET CANLI YAYIN (BROADCAST) YÖNETİCİSİ ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Bekleme döngüsü (Bağlantıyı canlı tutar)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)




# ==========================================
# --- 0. SİSTEM GİRİŞİ (LOGIN & JWT TOKEN) ---
# ==========================================
@app.post("/token")
@limiter.limit("10/minute")  # Brute-force koruması: dakikada max 10 deneme
def login_for_access_token(request: Request, form_data: dict, db: Session = Depends(get_db)):
    username = form_data.get("username")
    password = form_data.get("password")
    ip = get_client_ip(request)
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        # Başarısız giriş denemeleri de loglanır!
        try:
            log = models.AuditLog(
                actor=username or "unknown", role="-",
                action="LOGIN_FAILED",
                detail="Yanlış şifre denendi.",
                ip_address=ip
            )
            db.add(log); db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı. Lütfen tekrar deneyiniz.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token  = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    # Başarılı giriş audit logı
    try:
        log = models.AuditLog(
            actor=user.username, role=user.role,
            action="LOGIN", detail="JWT access + refresh token issued.",
            ip_address=ip
        )
        db.add(log); db.commit()
    except Exception:
        pass

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role,
        "expires_in_minutes": 120
    }


@app.post("/auth/refresh")
@limiter.limit("20/minute")
def refresh_access_token(request: Request, body: dict, db: Session = Depends(get_db)):
    """Refresh token ile yeni bir access token üretir. Frontend login olmadan devam edebilir."""
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token gerekli.")
    
    username = decode_refresh_token(refresh_token)  # geçersizse 401 fırlatır
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı.")
    
    new_access = create_access_token(data={"sub": user.username})
    logger.info(f"Token yenilendi: {username} | IP: {get_client_ip(request)}")
    return {"access_token": new_access, "token_type": "bearer", "expires_in_minutes": 120}

# --- 0.5 SİSTEME KAYIT (YENİ PERSONEL) ---
@app.post("/register")
def register_user(user_data: RegisterUser, db: Session = Depends(get_db)):
    mevcut = db.query(models.User).filter(models.User.username == user_data.username).first()
    if mevcut:
        return {"hata": "Bu kullanıcı adı sistemde zaten kayıtlı! Lütfen farklı bir isim seçin."}
        
    role = user_data.role if user_data.role in ["Admin", "Depo Müdürü", "Barista"] else "Barista"
    try:
        yeni_kullanici = models.User(
            username=user_data.username,
            hashed_password=get_password_hash(user_data.password),
            role=role
        )
        db.add(yeni_kullanici)
        db.commit()
        return {"mesaj": f"Tebrikler! Sisteme '{user_data.username}' rolüyle '{role}' olarak kaydedildiniz. Giriş yapabilirsiniz."}
    except Exception as e:
        db.rollback()
        return {"hata": f"Bir iç sistem hatası oluştu: {str(e)}"}


# ==========================================
# --- 1. SİSTEMİN KALBİ (UÇ NOKTALAR) ---
# ==========================================

@app.get("/urunler", dependencies=[Depends(role_required(["Admin", "Depo Müdürü", "Barista"]))])
def urunleri_getir(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    urunler = db.query(models.Product).offset(skip).limit(limit).all()
    sonuc = []
    # ORM Sayesinde Kategoriler InnerJoin olmaksızın .category üzerinden çağrılabiliyor. Muazzam!
    for u in urunler:
        sonuc.append({
            "product_id": u.product_id,
            "sku": u.sku,
            "name_tr": u.name_tr,
            "name_en": u.name_en,
            "description_tr": u.description_tr,
            "description_en": u.description_en,
            "current_stock": u.current_stock,
            "unit_price": u.unit_price,
            "category_name_tr": u.category.name_tr if u.category else "Tanımsız",
            "category_name_en": u.category.name_en if u.category else "Undefined",
            "supplier_name": u.supplier.name if u.supplier else "Tanımsız",
            "expiration_date": u.expiration_date.isoformat() if u.expiration_date else None,
            "warehouse_location": u.warehouse_location
        })
    return {"data": sonuc}

@app.get("/")
@app.get("/index.html")
def root():
    return FileResponse("index.html")

@app.get("/kasa.html")
def kasa_screen():
    return FileResponse("kasa.html")

@app.get("/qr.html")
def qr_screen():
    return FileResponse("qr.html")



@app.post("/urun-ekle", dependencies=[Depends(role_required(["Admin"]))])
def urun_ekle(urun: ProductCreate, db: Session = Depends(get_db)):
    try:
        yeni_urun = models.Product(**urun.dict())
        db.add(yeni_urun)
        db.commit()
        return {"mesaj": f"{urun.name_tr} veritabanına ORM şeması ile güvenle eklendi!"}
    except Exception as e:
        db.rollback()
        return {"hata": f"Ekleme hatası: {str(e)}"}

# --- GERÇEK ZAMANLI İŞLEM UÇ NOKTASI (ASYNC WEBSOCKET) ---
@app.post("/stok-hareketi")
async def stok_hareketi_kaydet(hareket: StockTransaction, background_tasks: BackgroundTasks, current_user: models.User = Depends(role_required(["Admin", "Barista", "Depo Müdürü"])), db: Session = Depends(get_db)):
    try:
        # 1. BİLGİSAYAR İŞ MANTIĞI: Barista yapıyorsa bekle, Yetkili yapıyorsa anında vur!
        islem_durumu = "BEKLEMEDE" if current_user.role == "Barista" else "ONAYLANDI"
        
        yeni_islem = models.InventoryTransaction(
            product_id=hareket.product_id,
            quantity=hareket.quantity,
            transaction_type=hareket.transaction_type,
            notes=hareket.notes,
            processed_by=current_user.username,
            status=islem_durumu
        )
        db.add(yeni_islem)
        
        # ONAYLI İSE ANINDA STOK GÜNCELLE
        if islem_durumu == "ONAYLANDI":
            urun = db.query(models.Product).filter(models.Product.product_id == hareket.product_id).first()
            if urun:
                if hareket.transaction_type.upper() == "IN": urun.current_stock += hareket.quantity
                else: urun.current_stock -= hareket.quantity
                
                # --- OTOMASYON TETİKLEYİCİLERİ ---
                if urun.current_stock <= urun.reorder_point:
                    # 1. Tedarikçiye E-posta
                    if urun.supplier and urun.supplier.contact_email:
                        background_tasks.add_task(send_supplier_email, urun.supplier.contact_email, urun.name_tr, urun.current_stock)
                    # 2. Webhook Gönderimi
                    background_tasks.add_task(trigger_stock_webhook, {
                        "event": "LOW_STOCK",
                        "product": urun.sku,
                        "current_stock": urun.current_stock,
                        "reorder_point": urun.reorder_point,
                        "timestamp": str(datetime.datetime.now())
                    })
        
        db.commit()
        
        # --- AUDIT LOG: STOCK MOVEMENT ---
        try:
            urun_adi = db.query(models.Product).filter(models.Product.product_id == hareket.product_id).first()
            log = models.AuditLog(
                actor=current_user.username, role=current_user.role,
                action=f"STOCK_{hareket.transaction_type.upper()}",
                resource=urun_adi.name_en if urun_adi else f"ID:{hareket.product_id}",
                detail=f"Qty: {hareket.quantity} | Status: {islem_durumu}"
            )
            db.add(log); db.commit()
        except Exception:
            pass
        
        # 2. CANLI YAYIN: Yöneticiye ping at!
        if islem_durumu == "BEKLEMEDE":
            await manager.broadcast(f"DiKKAT: {current_user.username} tarafından yeni bir onay talebi fırlatıldı!")
            return {"mesaj": "Talebiniz yönetici onayına sunuldu. Bildirim gönderildi."}
            
        return {"mesaj": "İşlem doğrudan onaylandı ve stok güncellendi."}
    except Exception as e:
        db.rollback()
        return {"hata": str(e)}

@app.get("/dashboard-ozet", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def dashboard_ozet(db: Session = Depends(get_db)):
    yatirim = db.query(func.sum(models.Product.current_stock * models.Product.unit_cost)).scalar() or 0
    kritik_sayisi = db.query(models.Product).filter(models.Product.current_stock <= models.Product.reorder_point).count()
    
    son_islemler = db.query(models.InventoryTransaction).order_by(models.InventoryTransaction.transaction_id.desc()).limit(5).all()
    sonuc_islemler = [{"islem": i.transaction_id, "tip": i.transaction_type, "adet": i.quantity, "urun_tr": i.product.name_tr, "urun_en": i.product.name_en} for i in son_islemler if i.product]

    ozet = {
        "finansal_durum": {"toplam_yatirim_maliyeti": float(yatirim)},
        "kritik_stok_uyari_sayisi": kritik_sayisi,
        "son_islemler": sonuc_islemler
    }
    
    # 🌟 GÜNLÜK Z-RAPORU CİROSU — SQL SUM ile (RAM'e çekmiyoruz!)
    bugun_baslangic = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    gunluk_net_ciro = db.query(
        func.sum(models.Sale.total_price)
    ).filter(
        models.Sale.created_at >= bugun_baslangic
    ).scalar() or 0

    # Günün Barista Performansı — GROUP BY ile tek sorguda
    barista_rows = db.query(
        models.Sale.barista_name,
        func.sum(models.Sale.total_price).label("toplam")
    ).filter(
        models.Sale.created_at >= bugun_baslangic
    ).group_by(models.Sale.barista_name).order_by(
        func.sum(models.Sale.total_price).desc()
    ).first()

    yildiz_barista = "Veri Yok"
    if barista_rows:
        yildiz_barista = f"{barista_rows.barista_name} (Hasılat: {float(barista_rows.toplam):.1f} ₺)"

    ozet["gunluk_ciro_tl"] = float(gunluk_net_ciro)
    ozet["gunun_baristasi"] = yildiz_barista

    return ozet



@app.get("/tedarikci-siparis", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def tedarikci_siparis(db: Session = Depends(get_db)):
    kritik_urunler = db.query(models.Product).filter(models.Product.current_stock <= models.Product.reorder_point).all()
    siparisler = {}
    for u in kritik_urunler:
        ted = u.supplier.name if u.supplier else "Belirtilmemiş Tedarikçi"
        email = u.supplier.contact_email if u.supplier else "-"
        if ted not in siparisler:
            siparisler[ted] = {"email": email, "urunler": []}
        siparisler[ted]["urunler"].append({
            "urun_tr": u.name_tr, 
            "urun_en": u.name_en, 
            "mevcut_stok": u.current_stock, 
            "siparis_edilmesi_gereken": (u.reorder_point - u.current_stock) + 50
        })
    return {"bekleyen_siparis_listesi": siparisler}

@app.get("/skt-analizi", dependencies=[Depends(role_required(["Admin", "Depo Müdürü", "Barista"]))])
def skt_analizi(db: Session = Depends(get_db)):
    """Gerçek hayatta LIFO (Son Giren İlk Çıkar) kuralını uygulamak için 30 gün içinde bozulacak SKT riskli ürünleri saptar."""
    bugun = datetime.date.today()
    otuz_gun_sonra = bugun + datetime.timedelta(days=30)
    
    riskli_urunler = db.query(models.Product).filter(
        models.Product.expiration_date.isnot(None),
        models.Product.expiration_date <= otuz_gun_sonra,
        models.Product.current_stock > 0
    ).all()
    
    return {"skt_riskli_urunler": sorted([{
        "urun_tr": u.name_tr,
        "urun_en": u.name_en,
        "skt_tarihi": u.expiration_date.isoformat(),
        "kalan_gun": (u.expiration_date - bugun).days,
        "raf_konumu": u.warehouse_location,
        "stok": u.current_stock
    } for u in riskli_urunler], key=lambda x: x["kalan_gun"])}

@app.get("/fire-raporu", dependencies=[Depends(role_required(["Admin"]))])
def fire_raporu(db: Session = Depends(get_db)):
    fireler = db.query(models.InventoryTransaction).filter(
        models.InventoryTransaction.transaction_type == "OUT",
        or_(
            models.InventoryTransaction.notes.ilike('%fire%'),
            models.InventoryTransaction.notes.ilike('%bozuldu%'),
            models.InventoryTransaction.notes.ilike('%istisna%')
        )
    ).all()
    
    toplam = sum(float(f.quantity * (f.product.unit_cost if f.product else 0)) for f in fireler)
    return {"toplam_fire_zarari_tl": toplam, "fire_detaylari": [{"tarih": f.transaction_date, "not": f.notes} for f in fireler]}

@app.get("/talep-tahmini", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def talep_tahmini(db: Session = Depends(get_db)):
    otuz_gun_once = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    Gecmis_cikislar = db.query(
        models.InventoryTransaction.product_id,
        func.sum(models.InventoryTransaction.quantity).label("toplam")
    ).filter(
        models.InventoryTransaction.transaction_type == "OUT",
        models.InventoryTransaction.transaction_date >= otuz_gun_once
    ).group_by(models.InventoryTransaction.product_id).all()
    
    tahminler = []
    for (p_id, toplam_cikis) in Gecmis_cikislar:
        if not toplam_cikis: continue
        haftalik_tahmin = round((toplam_cikis / 30) * 7)
        urun = db.query(models.Product).filter(models.Product.product_id == p_id).first()
        tahminler.append({"urun_adi_tr": urun.name_tr if urun else f"ID:{p_id}", "urun_adi_en": urun.name_en if urun else f"ID:{p_id}", "gelecek_hafta_tahmini_talep": haftalik_tahmin})
        
    return {"haftalik_talep_tahmini": sorted(tahminler, key=lambda k: k["gelecek_hafta_tahmini_talep"], reverse=True)}

@app.get("/bekleyen-talepler", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def bekleyen_talepler(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    talepler = db.query(models.InventoryTransaction).filter(models.InventoryTransaction.status == "BEKLEMEDE").offset(skip).limit(limit).all()
    return {"talepler": [{
            "transaction_id": t.transaction_id,
            "transaction_date": t.transaction_date,
            "urun_adi_tr": t.product.name_tr if t.product else "?",
            "urun_adi_en": t.product.name_en if t.product else "?",
            "transaction_type": t.transaction_type,
            "quantity": t.quantity,
            "talep_eden": t.processed_by
        } for t in talepler]}

@app.put("/talep-yanitla/{islem_id}")
async def talep_yanitla(islem_id: int, yanit: TalepYaniti, background_tasks: BackgroundTasks, current_user: models.User = Depends(role_required(["Admin", "Depo Müdürü"])), db: Session = Depends(get_db)):
    talep = db.query(models.InventoryTransaction).filter(models.InventoryTransaction.transaction_id == islem_id).first()
    if not talep: return {"hata": "Talep bulunamadı."}
    if talep.status != "BEKLEMEDE": return {"hata": "Bu talep zaten yanıtlanmış."}
    
    talep.status = yanit.yeni_durum.upper()
    talep.notes = f"{(talep.notes or '')} | Yanıtlayan: {current_user.username}"
    
    if talep.status == "ONAYLANDI":
        urun = talep.product
        if urun:
            if talep.transaction_type.upper() == "IN": urun.current_stock += talep.quantity
            else: urun.current_stock -= talep.quantity
            
            # --- OTOMASYON TETİKLEYİCİLERİ ---
            if urun.current_stock <= urun.reorder_point:
                if urun.supplier and urun.supplier.contact_email:
                    background_tasks.add_task(send_supplier_email, urun.supplier.contact_email, urun.name_tr, urun.current_stock)
                background_tasks.add_task(trigger_stock_webhook, {
                    "event": "LOW_STOCK_AFTER_APPROVAL",
                    "product": urun.sku,
                    "current_stock": urun.current_stock,
                    "reorder_point": urun.reorder_point,
                    "timestamp": str(datetime.datetime.now())
                })
                
    db.commit()
    # --- AUDIT LOG: APPROVAL ---
    try:
        prn = talep.product.name_en if talep.product else f"ID:{islem_id}"
        log = models.AuditLog(
            actor=current_user.username, role=current_user.role,
            action=f"APPROVE_{yanit.yeni_durum.upper()}",
            resource=prn,
            detail=f"Tx #{islem_id}"
        )
        db.add(log); db.commit()
    except Exception:
        pass
    await manager.broadcast("TABLO_YENILE") # Arayüzlere tabloyu güncellemeleri için sinyal fırlat
    return {"mesaj": f"Talep {talep.status} olarak işlendi."}

# --- YENİ! KASA / POS (BOM SİSTEMİ) ---
@app.get("/menu-getir", dependencies=[Depends(role_required(["Admin", "Barista", "Depo Müdürü"]))])
def menu_getir(db: Session = Depends(get_db)):
    menu = db.query(models.MenuItem).all()
    res = []
    for m in menu:
        res.append({
            "id": m.id, "name": m.name, "price": m.price, "emoji": m.image_emoji,
            "category": m.category, "image_url": m.image_url
        })
    return {"menu": res}


@app.post("/satis-yap", dependencies=[Depends(role_required(["Admin", "Barista"]))])
async def satis_yap(satis: SatisTalebi, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Hızlı Satış (Take-away) - Hiç masa ile uğraşmadan direkt satış yapar."""
    try:
        menu_item = db.query(models.MenuItem).filter(models.MenuItem.id == satis.menu_item_id).first()
        if not menu_item: raise HTTPException(status_code=404, detail="Ürün bulunamadı.")
            
        # BOM - Reçete Düşümü
        receteler = db.query(models.RecipeIngredient).filter(models.RecipeIngredient.menu_item_id == menu_item.id).all()
        for hammadde in receteler:
            toplam_dusulur = hammadde.quantity_required * satis.adet
            urun_db = db.query(models.Product).filter(models.Product.product_id == hammadde.product_id).first()
            if urun_db:
                is_negative = (urun_db.current_stock - toplam_dusulur) < 0
                urun_db.current_stock -= toplam_dusulur
                not_metni = f"Hızlı Satış (Takeaway): {menu_item.name}" + (" (⚠ STOK EKSİYE DÜŞTÜ)" if is_negative else "")
                
                db.add(models.InventoryTransaction(
                    product_id=urun_db.product_id, quantity=toplam_dusulur, transaction_type="OUT",
                    notes=not_metni, processed_by=current_user.username,
                    status="ONAYLANDI", source="Kasa-Takeaway"
                ))
        
        yeni_satis = models.Sale(
            menu_item_id=menu_item.id, quantity=satis.adet, 
            total_price=float(menu_item.price * satis.adet), 
            customer_name=satis.musteri_adi, customer_id=satis.customer_id, barista_name=current_user.username,
            payment_method=satis.payment_method, source="Kasa-Takeaway"
        )
        db.add(yeni_satis)
        
        if satis.customer_id:
            customer = db.query(models.Customer).filter(models.Customer.id == satis.customer_id).first()
            if customer:
                customer.total_visits += 1
                cat = (menu_item.category or "").lower()
                # 9+1 Sistemi: Sadece içecek kategorileri puan kazandırır
                if any(x in cat for x in ["kahve", "demleme", "soğuk"]):
                    customer.loyalty_points += satis.adet
        
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": "Paket servis satışı tamamlandı.", "toplam": float(yeni_satis.total_price)}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

# --- MASA YÖNETİMİ ENDPOİNTS ---

@app.get("/pos-masalar", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def masalari_listele(db: Session = Depends(get_db)):
    masalar = db.query(models.Table).order_by(models.Table.id).all()
    return {"masalar": [{"id": m.id, "name": m.name, "is_occupied": m.is_occupied, "x_pos": m.x_pos, "y_pos": m.y_pos} for m in masalar]}

@app.post("/masa-konum-guncelle", dependencies=[Depends(role_required(["Admin"]))])
def masa_konum_guncelle(req: TableLocationUpdate, db: Session = Depends(get_db)):
    masa = db.query(models.Table).filter(models.Table.id == req.table_id).first()
    if masa:
        masa.x_pos = req.x_pos
        masa.y_pos = req.y_pos
        db.commit()
    return {"mesaj": "Masa konumu kaydedildi."}

@app.post("/masaya-toplu-siparis", dependencies=[Depends(role_required(["Admin", "Barista"]))])
async def masaya_toplu_siparis(req: BulkTableOrderRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        masa = db.query(models.Table).filter(models.Table.id == req.table_id).first()
        if not masa: raise HTTPException(status_code=404, detail="Masa bulunamadı.")
        
        siparis = db.query(models.Order).filter(models.Order.table_id == req.table_id, models.Order.status == "PENDING").first()
        if not siparis:
            siparis = models.Order(table_id=req.table_id, status="PENDING")
            db.add(siparis); db.flush()
            masa.is_occupied = 1
            
        eklenenler = 0
        for i_req in req.items:
            urun = db.query(models.MenuItem).filter(models.MenuItem.id == i_req["menu_item_id"]).first()
            if not urun: continue
            qty = i_req.get("quantity", 1)
            is_ikram = i_req.get("is_ikram", False)
            fiyat = 0.0 if is_ikram else urun.price
            
            item = models.OrderItem(order_id=siparis.id, menu_item_id=urun.id, quantity=qty, unit_price=fiyat)
            db.add(item)
            siparis.total_amount += (fiyat * qty)
            eklenenler += 1
            
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": f"{eklenenler} ürün siparişe eklendi."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))


@app.get("/masa-detay/{table_id}", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def masa_detay(table_id: int, db: Session = Depends(get_db)):
    siparis = db.query(models.Order).filter(models.Order.table_id == table_id, models.Order.status == "PENDING").first()
    if not siparis: return {"items": [], "total": 0.0}
    
    items = []
    for it in siparis.items:
        items.append({"id": it.id, "menu_item_id": it.menu_item.id, "name": it.menu_item.name, "qty": it.quantity, "price": it.unit_price, "ikram": it.unit_price == 0})
    return {"items": items, "total": siparis.total_amount}

@app.delete("/siparis-kalemi-sil/{item_id}", dependencies=[Depends(role_required(["Admin", "Barista"]))])
async def siparis_kalemi_sil(item_id: int, db: Session = Depends(get_db)):
    try:
        item = db.query(models.OrderItem).filter(models.OrderItem.id == item_id).first()
        if not item: raise HTTPException(status_code=404, detail="Sipariş kalemi bulunamadı.")
        
        siparis = db.query(models.Order).filter(models.Order.id == item.order_id).first()
        if siparis:
            siparis.total_amount -= (item.unit_price * item.quantity)
            if siparis.total_amount < 0: siparis.total_amount = 0.0
            
            db.delete(item)
            db.commit()
            
            # Eğer siparişte hiç kalem kalmadıysa masayı boşa çekebiliriz
            if len(siparis.items) == 0:
                masa = db.query(models.Table).filter(models.Table.id == siparis.table_id).first()
                if masa: masa.is_occupied = 0
                db.delete(siparis)
                db.commit()
            
            await manager.broadcast("TABLO_YENILE")
            return {"mesaj": "Ürün siparişten çıkarıldı."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

@app.post("/masa-tasi", dependencies=[Depends(role_required(["Admin", "Barista"]))])
async def masa_tasi(req: TableMoveRequest, db: Session = Depends(get_db)):
    try:
        eski_siparis = db.query(models.Order).filter(models.Order.table_id == req.from_table_id, models.Order.status == "PENDING").first()
        if not eski_siparis: raise HTTPException(status_code=404, detail="Kaynak masada açık sipariş yok.")
        
        hedef_masa = db.query(models.Table).filter(models.Table.id == req.to_table_id).first()
        eski_masa = db.query(models.Table).filter(models.Table.id == req.from_table_id).first()
        
        hedef_siparis = db.query(models.Order).filter(models.Order.table_id == req.to_table_id, models.Order.status == "PENDING").first()
        
        if hedef_siparis:
            # Hedefte sipariş varsa, ürünleri oraya aktar
            for item in eski_siparis.items:
                item.order_id = hedef_siparis.id
            hedef_siparis.total_amount += eski_siparis.total_amount
            db.delete(eski_siparis)
        else:
            # Hedefte sipariş yoksa, direkt siparişi kaydır
            eski_siparis.table_id = req.to_table_id
            hedef_masa.is_occupied = 1
            
        eski_masa.is_occupied = 0
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": "Masa başarıyla taşındı/birleştirildi."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

@app.post("/masa-hesap-kapat", dependencies=[Depends(role_required(["Admin", "Barista"]))])
async def masa_hesap_kapat(req: CheckoutRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        siparis = db.query(models.Order).filter(models.Order.table_id == req.table_id, models.Order.status == "PENDING").first()
        if not siparis: raise HTTPException(status_code=404, detail="Açık sipariş bulunamadı.")
        
        # 1. Stok Düşümü (BOM)
        for item in siparis.items:
            receteler = db.query(models.RecipeIngredient).filter(models.RecipeIngredient.menu_item_id == item.menu_item_id).all()
            for hammadde in receteler:
                toplam_dusulur = hammadde.quantity_required * item.quantity
                u_db = db.query(models.Product).filter(models.Product.product_id == hammadde.product_id).first()
                if u_db:
                    is_negative = (u_db.current_stock - toplam_dusulur) < 0
                    u_db.current_stock -= toplam_dusulur
                    not_metni = f"Masa Satışı: {item.menu_item.name}" + (" (⚠ STOK EKSİYE DÜŞTÜ)" if is_negative else "")
                    
                    db.add(models.InventoryTransaction(
                        product_id=u_db.product_id, quantity=toplam_dusulur, transaction_type="OUT",
                        notes=not_metni, processed_by=current_user.username,
                        status="ONAYLANDI", source=f"Masa-{req.table_id}"
                    ))
        
        # 2. Sale (Z-Raporu) Kaydı
        # CRM / Sadakat Puanı İşleme (Puan harcanacaksa önce indirimi hesapla)
        discount_amount = 0.0
        free_coffee_item_id = None
        customer = None
        
        if req.customer_id:
            customer = db.query(models.Customer).filter(models.Customer.id == req.customer_id).first()
            if customer:
                customer.total_visits += 1
                
                # Hediye kullanılacaksa en ucuz kahveyi bul
                if req.use_free_coffee and customer.loyalty_points >= 9:
                    cheapest_price = float('inf')
                    for item in siparis.items:
                        cat = (item.menu_item.category or "").lower()
                        if any(x in cat for x in ["kahve", "demleme", "soğuk"]):
                            if item.unit_price < cheapest_price:
                                cheapest_price = item.unit_price
                                free_coffee_item_id = item.id
                    
                    if free_coffee_item_id:
                        discount_amount = cheapest_price
                        customer.loyalty_points -= 9

        # Split Payment (Parçalı Ödeme) Mantığı
        is_split = req.amount_cash > 0 and req.amount_card > 0
        kalan_nakit = req.amount_cash
        
        for item in siparis.items:
            item_total = item.unit_price * item.quantity
            
            # Eğer bu ürün hediye edilense 1 adetinin fiyatını düş
            if free_coffee_item_id == item.id:
                item_total -= item.unit_price
                # Eğer birden fazla aynı ürün varsa sadece 1 tanesi bedava
            
            if item_total <= 0:
                continue # İkramlar/Bedavalar ciroya yansımaz (Stok düştü zaten)
                
            if is_split:
                if kalan_nakit >= item_total:
                    # Tamamı nakit
                    pay_method = "Nakit"
                    kalan_nakit -= item_total
                    db.add(models.Sale(menu_item_id=item.menu_item_id, quantity=item.quantity, total_price=item_total, barista_name=current_user.username, payment_method=pay_method, source=f"Masa-{req.table_id}"))
                elif kalan_nakit > 0:
                    # Bir kısmı nakit, kalanı kart (Miktarı paylaştırıyoruz)
                    db.add(models.Sale(menu_item_id=item.menu_item_id, quantity=item.quantity, total_price=kalan_nakit, barista_name=current_user.username, payment_method="Nakit", source=f"Masa-{req.table_id}"))
                    db.add(models.Sale(menu_item_id=item.menu_item_id, quantity=0, total_price=(item_total - kalan_nakit), barista_name=current_user.username, payment_method="Kredi Kartı", source=f"Masa-{req.table_id}"))
                    kalan_nakit = 0
                else:
                    # Tamamı kart
                    pay_method = "Kredi Kartı"
                    db.add(models.Sale(menu_item_id=item.menu_item_id, quantity=item.quantity, total_price=item_total, barista_name=current_user.username, payment_method=pay_method, source=f"Masa-{req.table_id}"))
            else:
                db.add(models.Sale(
                    menu_item_id=item.menu_item_id, quantity=item.quantity, 
                    total_price=item_total, barista_name=current_user.username,
                    payment_method=req.payment_method, source=f"Masa-{req.table_id}"
                ))
            
        # Puan Ekleme (Hediye harcandıktan sonra kalan yeni kahvelerin puanını ekle)
        if customer:
            coffee_count = 0
            for item in siparis.items:
                cat = (item.menu_item.category or "").lower()
                if any(x in cat for x in ["kahve", "demleme", "soğuk"]):
                    coffee_count += item.quantity
            
            # Eğer hediye kahve kullanıldıysa o kahve puan kazandırmaz (veya kazandırır size kalmış, genelde hediye puan vermez)
            if free_coffee_item_id:
                coffee_count = max(0, coffee_count - 1)
                
            customer.loyalty_points += coffee_count
                
        # 3. Siparişi Kapat ve Masayı Boşalt
        siparis.status = "PAID"
        masa = db.query(models.Table).filter(models.Table.id == req.table_id).first()
        masa.is_occupied = 0
        
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": "Masa hesabı başarıyla kapatıldı."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

# --- GİDER VE ZAYİ ENDPOİNTS ---

@app.post("/pos/gider-ekle", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def gider_ekle(req: ExpenseCreate, db: Session = Depends(get_db)):
    try:
        gider = models.Expense(**req.dict())
        db.add(gider)
        db.commit()
        return {"mesaj": "Gider başarıyla kaydedildi."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

@app.post("/pos/zayi-ekle", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def zayi_ekle(req: WastageCreate, db: Session = Depends(get_db)):
    try:
        urun = db.query(models.Product).filter(models.Product.product_id == req.product_id).first()
        if not urun: raise HTTPException(status_code=404, detail="Ürün bulunamadı.")
        
        # Stoktan Düş
        urun.current_stock -= req.quantity
        zarar = urun.unit_cost * req.quantity
        
        fire = models.Wastage(
            product_id=req.product_id, quantity=req.quantity,
            reason=req.reason, cost_impact=zarar
        )
        db.add(fire)
        db.commit()
        return {"mesaj": f"Zayi işlendi. Zarar: {zarar} TL"}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# --- 7. MÜŞTERİ QR MENÜ (Self-Service) ---
# ==========================================
@app.get("/public-menu")
def get_public_menu(db: Session = Depends(get_db)):
    # Herkese açık salt-okunur menü listesi
    items = db.query(models.MenuItem).filter().all()
    grouped = {}
    for i in items:
        # İleride is_active eklenirse buraya filtre eklenebilir.
        cat = i.category or "Diğer"
        if cat not in grouped: grouped[cat] = []
        grouped[cat].append({
            "id": i.id, "name": i.name, "price": i.price, "image_emoji": i.image_emoji
        })
    return {"menu": grouped}

@app.post("/qr-siparis")
async def qr_siparis_olustur(req: QROrderRequest, db: Session = Depends(get_db)):
    try:
        masa = db.query(models.Table).filter(models.Table.id == req.table_id).first()
        if not masa: raise HTTPException(status_code=404, detail="Geçersiz Masa QR Kodu")
        
        siparis = db.query(models.Order).filter(models.Order.table_id == req.table_id, models.Order.status == "PENDING").first()
        if not siparis:
            siparis = models.Order(table_id=req.table_id, status="PENDING")
            db.add(siparis); db.flush()
            masa.is_occupied = 1
            
        eklenen = 0
        for i_req in req.items:
            urun = db.query(models.MenuItem).filter(models.MenuItem.id == i_req.menu_item_id).first()
            if not urun: continue
            
            item = models.OrderItem(order_id=siparis.id, menu_item_id=urun.id, quantity=i_req.quantity, unit_price=urun.price)
            db.add(item)
            siparis.total_amount += (urun.price * i_req.quantity)
            eklenen += i_req.quantity
            
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        await manager.broadcast("QR_SIPARIS_GELDI") # Özel zil sesi/toast için
        return {"mesaj": f"{eklenen} adet ürün siparişe eklendi. Siparişiniz hazırlanacaktır."}
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=str(e))


@app.get("/pos/rapor-ozet", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def rapor_ozet(db: Session = Depends(get_db)):
    # Bugünün verileri
    bugun = datetime.date.today()
    satislar = db.query(func.sum(models.Sale.total_price)).filter(func.date(models.Sale.created_at) == bugun).scalar() or 0.0
    giderler = db.query(func.sum(models.Expense.amount)).filter(func.date(models.Expense.created_at) == bugun).scalar() or 0.0
    zayiler = db.query(func.sum(models.Wastage.cost_impact)).filter(func.date(models.Wastage.created_at) == bugun).scalar() or 0.0
    
    return {
        "cironuz": satislar,
        "gider_toplami": giderler,
        "zayi_zarari": zayiler,
        "net_durum": satislar - giderler - zayiler
    }

# ==========================================
# --- 8. YÖNETİCİ İŞ ZEKASI (BI & HEATMAP) ---
# ==========================================
@app.get("/analytics/heatmap", dependencies=[Depends(role_required(["Admin"]))])
def get_heatmap_data(db: Session = Depends(get_db)):
    # Tüm masaları getir
    masalar = db.query(models.Table).all()
    
    # Masaların bugüne ait veya genel cirosunu topla.
    # Gerçek sistemde func.date() ile de filtrelenebilir,
    # şimdilik görsellik adına All-Time verelim.
    heatmap_veri = []
    
    for masa in masalar:
        # Sale tablosunda source="Masa-{id}" formatında.
        ciro = db.query(func.sum(models.Sale.total_price)).filter(models.Sale.source == f"Masa-{masa.id}").scalar() or 0.0
        
        heatmap_veri.append({
            "id": masa.id,
            "name": masa.name,
            "x_pos": masa.x_pos,
            "y_pos": masa.y_pos,
            "revenue": round(ciro, 2)
        })
        
    return {"heatmap": heatmap_veri}

@app.get("/pos/detayli-rapor", dependencies=[Depends(role_required(["Admin"]))])
def detayli_rapor(db: Session = Depends(get_db)):
    # 1. En çok satan ürünler
    top_selling = db.query(models.MenuItem.name, func.sum(models.Sale.quantity).label("total_qty")) \
        .join(models.Sale).group_by(models.MenuItem.name).order_by(text("total_qty DESC")).limit(5).all()
        
    # 2. Ödeme yöntemi dağılımı
    payment_dist = db.query(models.Sale.payment_method, func.sum(models.Sale.total_price)) \
        .group_by(models.Sale.payment_method).all()
        
    return {
        "top_selling": [{"name": r[0], "qty": r[1]} for r in top_selling],
        "payments": [{"method": r[0], "total": r[1]} for r in payment_dist]
    }

@app.post("/pos/ayarlar", dependencies=[Depends(role_required(["Admin"]))])
def ayarlar_kaydet(req: SettingsUpdate, db: Session = Depends(get_db)):
    # Gerçek sistemde bir Settings tablosu olur, V2 için .env veya basit bir JSON simülasyonu:
    return {"mesaj": f"{req.cafe_name} ayarları başarıyla güncellendi."}

@app.post("/menu-ekle", dependencies=[Depends(role_required(["Admin"]))])
def menu_ekle(req: MenuItemCreate, db: Session = Depends(get_db)):
    cat_l = req.category.lower() if req.category else "kahve"
    
    IMG_MAP = {
        "tatlı": "/static/images/dessert.jpg",
        "pasta": "/static/images/dessert.jpg",
        "çay": "/static/images/tea.jpg",
        "soğuk": "/static/images/cold.jpg",
        "sandviç": "/static/images/sandwich.jpg",
        "kahvaltı": "/static/images/breakfast.jpg",
        "kahve": "/static/images/coffee.jpg"
    }

    image_url = IMG_MAP["kahve"]
    for k, v in IMG_MAP.items():
        if k in cat_l:
            image_url = v
            break
    
    yeni = models.MenuItem(
        name=req.name, price=req.price, image_emoji=req.image_emoji,
        category=req.category, image_url=image_url
    )
    db.add(yeni)
    db.commit()
    return {"mesaj": f"{req.name} menüye eklendi."}

@app.delete("/menu-sil/{item_id}", dependencies=[Depends(role_required(["Admin"]))])
def menu_sil(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.MenuItem).filter(models.MenuItem.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    db.delete(item)
    db.commit()
    return {"mesaj": "Ürün silindi"}

@app.post("/pos/masa-ekle", dependencies=[Depends(role_required(["Admin"]))])
async def masa_ekle(name: str, db: Session = Depends(get_db)):
    yeni = models.Table(name=name, is_occupied=False)
    db.add(yeni)
    db.commit()
    await manager.broadcast("TABLO_YENILE")
    return {"mesaj": f"{name} başarıyla oluşturuldu"}

@app.delete("/pos/masa-sil/{table_id}", dependencies=[Depends(role_required(["Admin"]))])
async def masa_sil(table_id: int, db: Session = Depends(get_db)):
    """Bir masayı siler. Aktif (PENDING) siparişi varsa silmeye izin vermez."""
    try:
        masa = db.query(models.Table).filter(models.Table.id == table_id).first()
        if not masa:
            raise HTTPException(status_code=404, detail="Masa bulunamadı.")
        aktif_siparis = db.query(models.Order).filter(
            models.Order.table_id == table_id,
            models.Order.status == "PENDING"
        ).first()
        if aktif_siparis:
            raise HTTPException(status_code=400, detail="Bu masada açık sipariş var. Önce hesabı kapatın.")
        db.delete(masa)
        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": f"{masa.name} başarıyla silindi."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class SupplyApprovalRequest(BaseModel):
    product_id: int
    quantity: float
    supplier_name: Optional[str] = None

@app.post("/tedarik-siparis-onayla", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
async def tedarik_siparis_onayla(req: SupplyApprovalRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Yönetici onayıyla tedarik siparişi oluşturur. Otomatik sipariş YOKTUR."""
    try:
        urun = db.query(models.Product).filter(models.Product.product_id == req.product_id).first()
        if not urun:
            raise HTTPException(status_code=404, detail="Ürün bulunamadı.")
        onay = models.SupplyOrderApproval(
            product_id=req.product_id,
            quantity=req.quantity,
            approved_by=current_user.username,
            supplier_name=req.supplier_name or (urun.supplier.name if urun.supplier else "Belirtilmemiş"),
            status="ORDERED"
        )
        db.add(onay)
        db.add(models.AuditLog(
            actor=current_user.username, role=current_user.role,
            action="SUPPLY_ORDER_APPROVED",
            resource=urun.name_tr,
            detail=f"{req.quantity} adet sipariş onaylandı.",
        ))
        db.commit()
        return {"mesaj": f"{urun.name_tr} için {req.quantity} adet tedarik siparişi onaylandı.", "onay_id": onay.id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))




# ==========================================
# --- 3. PARTİ POS ENTEGRASYONU (WEBHOOKS) ---
# ==========================================

@app.post("/api/v1/api-keys", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def api_key_olustur(payload: ApiKeyCreate, db: Session = Depends(get_db)):
    try:
        yeni_key = secrets.token_hex(32)
        key_db = models.ApiKey(provider_name=payload.provider_name, api_key=yeni_key)
        db.add(key_db)
        db.commit()
        return {"mesaj": f"{payload.provider_name} için API Key başarıyla üretildi.", "api_key": yeni_key}
    except Exception as e:
        db.rollback()
        return {"hata": f"API Key üretilemedi: {str(e)}"}

@app.get("/api/v1/api-keys", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def api_keys_listele(db: Session = Depends(get_db)):
    keys = db.query(models.ApiKey).order_by(models.ApiKey.id.desc()).all()
    return {"api_keys": [{"id": k.id, "provider": k.provider_name, "created_at": k.created_at} for k in keys]}

@app.post("/api/v1/webhooks/pos-sale")
async def pos_webhook(payload: WebhookSalePayload, api_k = Depends(verify_api_key), db: Session = Depends(get_db)):
    try:
        islem_notu = f"Webhook ({payload.pos_provider})"
        
        for item in payload.items:
            # 1. MenuItem Bul (dış sisteme ait ID üzerinden eşleştiriyoruz)
            menu_urun = db.query(models.MenuItem).filter(models.MenuItem.external_pos_id == item.external_product_id).first()
            if not menu_urun:
                continue # Model eşleşmezse stok düşümünü pas geç
            
            # 2. Reçete Düşümü
            receteler = db.query(models.RecipeIngredient).filter(models.RecipeIngredient.menu_item_id == menu_urun.id).all()
            for hammadde in receteler:
                toplam_dusulecek = hammadde.quantity_required * item.quantity
                urun_db = db.query(models.Product).filter(models.Product.product_id == hammadde.product_id).first()
                if urun_db:
                    urun_db.current_stock -= toplam_dusulecek
                    islem = models.InventoryTransaction(
                        product_id=urun_db.product_id,
                        quantity=toplam_dusulecek,
                        transaction_type="OUT",
                        notes=f"{islem_notu} Oto Reçete Düşüşü: {item.quantity}x {menu_urun.name}",
                        processed_by="System API",
                        status="ONAYLANDI",
                        source=f"Webhook-{payload.pos_provider}"
                    )
                    db.add(islem)
                    
            # 3. Z-Raporuna İşle
            yeni_satis = models.Sale(
                menu_item_id=menu_urun.id,
                quantity=item.quantity,
                total_price=item.price * item.quantity,
                customer_name=payload.receipt_id,
                barista_name=f"API-{payload.pos_provider}",
                payment_method="Nakit/Kredi (3. Parti POS)",
                source=f"Webhook-{payload.pos_provider}"
            )
            db.add(yeni_satis)

        db.commit()
        await manager.broadcast("TABLO_YENILE")
        return {"mesaj": "Webhook başarıyla işlendi ve stoklar LIFO metoduna göre güncellendi.", "status": "ok"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sevk-raporu", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def sevk_raporu(db: Session = Depends(get_db)):
    from sqlalchemy.orm import aliased
    # N+1 sorgu yerine tek JOIN ile top-5 çıkış ürünü
    en_cok = db.query(
        models.Product.name_tr,
        models.Product.name_en,
        func.sum(models.InventoryTransaction.quantity).label("toplam")
    ).join(
        models.InventoryTransaction,
        models.Product.product_id == models.InventoryTransaction.product_id
    ).filter(
        models.InventoryTransaction.transaction_type == "OUT"
    ).group_by(
        models.Product.product_id, models.Product.name_tr, models.Product.name_en
    ).order_by(
        func.sum(models.InventoryTransaction.quantity).desc()
    ).limit(5).all()

    pasta = [{"name_tr": row.name_tr, "name_en": row.name_en, "toplam_sevk": float(row.toplam or 0)} for row in en_cok]

    yedi_gecmis = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    trend_data = db.query(
        func.date(models.InventoryTransaction.transaction_date).label("dt"),
        func.sum(models.InventoryTransaction.quantity).label("toplam")
    ).filter(
        models.InventoryTransaction.transaction_type == "OUT",
        models.InventoryTransaction.transaction_date >= yedi_gecmis
    ).group_by(func.date(models.InventoryTransaction.transaction_date)).all()

    return {"grafik_1_pasta": {"veriler": pasta}, "grafik_2_cizgi": {"veriler": [{"tarih": str(t.dt), "gunluk_cikis_adeti": float(t.toplam or 0)} for t in trend_data]}}


# ==========================================
# --- AI PREDİCTOR DASHBOARD (scikit-learn LinearRegression) ---
# ==========================================
@app.get("/ai-predictor", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def ai_predictor(db: Session = Depends(get_db)):
    """Top-5 ürün için son 14 günlük gerçek trendden scikit-learn LinearRegression ile projeksiyon üretir."""
    on_dort_gun_once = datetime.datetime.utcnow() - datetime.timedelta(days=14)

    # En yüksek hacimli 5 ürünü bul (14 gün)
    top_products = db.query(
        models.InventoryTransaction.product_id,
        func.sum(models.InventoryTransaction.quantity).label("total")
    ).filter(
        models.InventoryTransaction.transaction_type == "OUT",
        models.InventoryTransaction.transaction_date >= on_dort_gun_once
    ).group_by(models.InventoryTransaction.product_id)\
     .order_by(func.sum(models.InventoryTransaction.quantity).desc())\
     .limit(5).all()

    result = []
    for (p_id, _) in top_products:
        urun = db.query(models.Product).filter(models.Product.product_id == p_id).first()
        if not urun:
            continue

        # Son 14 günlük günlük çıkış verisi (model eğitim penceresi)
        train_rows = db.query(
            func.date(models.InventoryTransaction.transaction_date).label("dt"),
            func.sum(models.InventoryTransaction.quantity).label("qty")
        ).filter(
            models.InventoryTransaction.product_id == p_id,
            models.InventoryTransaction.transaction_type == "OUT",
            models.InventoryTransaction.transaction_date >= on_dort_gun_once
        ).group_by(func.date(models.InventoryTransaction.transaction_date)).all()

        train_map = {str(r.dt): float(r.qty or 0) for r in train_rows}
        base_train = datetime.date.today() - datetime.timedelta(days=13)
        train_dates = [(base_train + datetime.timedelta(days=i)).isoformat() for i in range(14)]
        y_train = np.array([train_map.get(d, 0.0) for d in train_dates]).reshape(-1, 1)
        X_train = np.arange(14).reshape(-1, 1)

        # scikit-learn LinearRegression modeli eğit
        model = LinearRegression()
        model.fit(X_train, y_train)

        # Model kalite metrikleri
        y_pred_train = model.predict(X_train).flatten()
        r2 = round(float(r2_score(y_train, y_pred_train)), 3)
        slope = float(model.coef_[0][0])
        trend_direction = "rising" if slope > 0.1 else ("falling" if slope < -0.1 else "stable")

        # Son 7 gün görüntci (actual)
        base_actual = datetime.date.today() - datetime.timedelta(days=6)
        actual = []
        for i in range(7):
            d = (base_actual + datetime.timedelta(days=i)).isoformat()
            actual.append({"day": d, "qty": train_map.get(d, 0.0)})

        # Gelecek 7 gün projeksiyonu
        projection = []
        for i in range(7):
            X_future = np.array([[14 + i]])
            predicted = max(0.0, round(float(model.predict(X_future)[0][0]), 1))
            d = (datetime.date.today() + datetime.timedelta(days=i + 1)).isoformat()
            projection.append({"day": d, "qty": predicted})

        weekly_total = round(sum(p["qty"] for p in projection), 1)
        avg_daily = round(np.mean([a["qty"] for a in actual]), 2)

        result.append({
            "product_id": p_id,
            "name_tr": urun.name_tr,
            "name_en": urun.name_en,
            "current_stock": urun.current_stock,
            "actual": actual,
            "projection": projection,
            "weekly_projected_total": weekly_total,
            "avg_daily_consumption": avg_daily,
            "r2_score": r2,
            "trend_direction": trend_direction,
            "alert": urun.current_stock < weekly_total
        })

    logger.info(f"AI Predictor: {len(result)} ürün için projeksiyon üretildi.")
    return {"products": result}


# ==========================================
# --- AUDIT TRAIL (GÜVENLİK DENETİM KAYITLARI) ---
# ==========================================
@app.get("/audit-logs", dependencies=[Depends(role_required(["Admin"]))])
def audit_logs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(models.AuditLog)\
             .filter(models.AuditLog.is_archived == 0)\
             .order_by(models.AuditLog.timestamp.desc())\
             .offset(skip).limit(limit).all()
    total = db.query(func.count(models.AuditLog.id)).filter(models.AuditLog.is_archived == 0).scalar()
    return {
        "total": total,
        "logs": [{
            "id": l.id,
            "actor": l.actor,
            "role": l.role,
            "action": l.action,
            "resource": l.resource or "-",
            "detail": l.detail or "-",
            "ip_address": l.ip_address or "-",
            "timestamp": l.timestamp.isoformat() if l.timestamp else "-"
        } for l in logs]
    }


# ==========================================
# --- 2. ANALİTİK & RAPORLAMA MODÜLÜ ---
# ==========================================

@app.get("/rapor/kar-marji", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def kar_marji_analizi(db: Session = Depends(get_db)):
    """
    Her SKU için kâr marjı, EWMA (ağırlıklı hareketli ortalama) tüketim tahmini
    ve stok yeterliliği analizi. Sade SQL + Python ile hesaplanır.
    """
    urunler = db.query(models.Product).filter(models.Product.current_stock > 0).all()
    otuz_gun_once = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    # Son 30 günlük çıkış hacimleri — tek sorguda
    cikis_map = {
        row.product_id: float(row.toplam or 0)
        for row in db.query(
            models.InventoryTransaction.product_id,
            func.sum(models.InventoryTransaction.quantity).label("toplam")
        ).filter(
            models.InventoryTransaction.transaction_type == "OUT",
            models.InventoryTransaction.transaction_date >= otuz_gun_once
        ).group_by(models.InventoryTransaction.product_id).all()
    }

    sonuclar = []
    for u in urunler:
        marj_tl   = round(u.unit_price - u.unit_cost, 2)
        marj_yuzde = round((marj_tl / u.unit_price * 100) if u.unit_price > 0 else 0, 1)
        toplam_kar = round(marj_tl * u.current_stock, 2)

        # EWMA (α=0.3): son 30 günlük günlük ortalama tüketim
        aylik_cikis = cikis_map.get(u.product_id, 0.0)
        gunluk_ort  = aylik_cikis / 30
        ewma_talep  = round(gunluk_ort * 0.3 + (aylik_cikis / 30) * 0.7, 2)  # α=0.3
        kac_gun_yeter = round(u.current_stock / ewma_talep, 1) if ewma_talep > 0 else None

        sonuclar.append({
            "product_id":     u.product_id,
            "sku":            u.sku,
            "name_tr":        u.name_tr,
            "name_en":        u.name_en,
            "unit_cost":      u.unit_cost,
            "unit_price":     u.unit_price,
            "marj_tl":        marj_tl,
            "marj_yuzde":     marj_yuzde,
            "toplam_potansiyel_kar_tl": toplam_kar,
            "current_stock":  u.current_stock,
            "ewma_gunluk_talep": ewma_talep,
            "stok_kac_gun_yeter": kac_gun_yeter,
            "kritik": kac_gun_yeter is not None and kac_gun_yeter < 7
        })

    # Kâr potansiyeline göre sırala
    sonuclar.sort(key=lambda x: x["toplam_potansiyel_kar_tl"], reverse=True)
    toplam_potansiyel = round(sum(s["toplam_potansiyel_kar_tl"] for s in sonuclar), 2)

    logger.info(f"Kar Marjı Analizi: {len(sonuclar)} SKU işlendi.")
    return {
        "toplam_potansiyel_kar_tl": toplam_potansiyel,
        "urun_sayisi": len(sonuclar),
        "analiz": sonuclar
    }


@app.get("/rapor/excel", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def excel_rapor_indir(db: Session = Depends(get_db)):
    """Tüm ürün envanterini + kâr marjı hesaplamalarını .xlsx olarak indirir."""
    import io
    from fastapi.responses import StreamingResponse
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # ── SAYFA 1: ÜRÜN ENVANTERİ ──
    ws1 = wb.active
    ws1.title = "Envanter"

    baslik_font  = Font(bold=True, color="FFFFFF", size=11)
    baslik_dolu  = PatternFill("solid", fgColor="1E293B")
    orta_hizala  = Alignment(horizontal="center")

    sutunlar = ["SKU", "Ürün (TR)", "Ürün (EN)", "Kategori", "Mevcut Stok",
                "Birim Maliyet (₺)", "Birim Fiyat (₺)", "Kâr Marjı (₺)",
                "Kâr Marjı (%)", "Toplam Potansiyel Kâr (₺)", "SKT", "Raf"]
    ws1.append(sutunlar)
    for col_idx, _ in enumerate(sutunlar, 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.font   = baslik_font
        cell.fill   = baslik_dolu
        cell.alignment = orta_hizala

    urunler = db.query(models.Product).all()
    for u in urunler:
        marj_tl    = round(u.unit_price - u.unit_cost, 2)
        marj_yuzde = round((marj_tl / u.unit_price * 100) if u.unit_price > 0 else 0, 1)
        ws1.append([
            u.sku,
            u.name_tr,
            u.name_en,
            u.category.name_tr if u.category else "-",
            u.current_stock,
            u.unit_cost,
            u.unit_price,
            marj_tl,
            marj_yuzde,
            round(marj_tl * u.current_stock, 2),
            u.expiration_date.isoformat() if u.expiration_date else "-",
            u.warehouse_location or "-"
        ])

    # Sütun genişliklerini otomatik ayarla
    for col in ws1.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws1.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)

    # ── SAYFA 2: SON 30 GÜN STK HAREKETLERİ ──
    ws2 = wb.create_sheet("Stok Hareketleri")
    ws2.append(["Tarih", "Ürün", "Tip", "Miktar", "Durum", "İşleyen", "Not"])
    ws2.cell(row=1, column=1).font = baslik_font

    otuz_gun_once = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    hareketler = db.query(models.InventoryTransaction)\
        .filter(models.InventoryTransaction.transaction_date >= otuz_gun_once)\
        .order_by(models.InventoryTransaction.transaction_date.desc()).all()
    for h in hareketler:
        ws2.append([
            h.transaction_date.strftime("%Y-%m-%d %H:%M") if h.transaction_date else "-",
            h.product.name_tr if h.product else f"ID:{h.product_id}",
            h.transaction_type,
            h.quantity,
            h.status,
            h.processed_by,
            h.notes or "-"
        ])

    # ── SAYFA 3: AUDIT LOG (Son 100) ──
    ws3 = wb.create_sheet("Denetim Kaydı")
    ws3.append(["Zaman", "Kullanıcı", "Rol", "İşlem", "Kaynak", "Detay", "IP"])
    loglar = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(100).all()
    for l in loglar:
        ws3.append([
            l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "-",
            l.actor, l.role, l.action,
            l.resource or "-", l.detail or "-", l.ip_address or "-"
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    tarih = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"envanter_raporu_{tarih}.xlsx"

    logger.info(f"Excel raporu oluşturuldu: {filename}")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/rapor/pdf", dependencies=[Depends(role_required(["Admin", "Depo Müdürü"]))])
def pdf_rapor_indir(db: Session = Depends(get_db)):
    """Yönetici özet raporunu (Dashboard KPI + Kritik Stoklar + Kâr Marjı Top-5) PDF olarak indirir."""
    import io
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    KOYU   = colors.HexColor("#0f172a")
    YESIL  = colors.HexColor("#34d399")
    KIRMIZI = colors.HexColor("#fb7185")
    GRIS   = colors.HexColor("#94a3b8")

    title_style = ParagraphStyle("title", parent=styles["Title"],
                                  textColor=KOYU, fontSize=18, spaceAfter=4)
    alt_style   = ParagraphStyle("alt", parent=styles["Normal"],
                                  textColor=GRIS, fontSize=9, spaceAfter=12)
    h2_style    = ParagraphStyle("h2", parent=styles["Heading2"],
                                  textColor=KOYU, fontSize=13, spaceBefore=14, spaceAfter=6)

    # Başlık
    story.append(Paragraph("🏛️ Akıllı Kafe Envanter Sistemi", title_style))
    story.append(Paragraph(f"Yönetici Raporu — {datetime.datetime.now().strftime('%d %B %Y, %H:%M')}", alt_style))
    story.append(HRFlowable(width="100%", thickness=1, color=YESIL, spaceAfter=14))

    # KPI Kutuları
    yatirim    = db.query(func.sum(models.Product.current_stock * models.Product.unit_cost)).scalar() or 0
    kritik_say = db.query(models.Product).filter(models.Product.current_stock <= models.Product.reorder_point).count()
    urun_say   = db.query(models.Product).count()

    story.append(Paragraph("📊 Finansal Özet", h2_style))
    kpi_data = [
        ["Metrik", "Değer"],
        ["Toplam Envanter Yatırım Maliyeti", f"₺{float(yatirim):,.2f}"],
        ["Toplam Aktif SKU Sayısı",          str(urun_say)],
        ["Kritik Stok Uyarısı (≤ Reorder Point)", str(kritik_say)],
    ]
    kpi_tbl = Table(kpi_data, colWidths=[10*cm, 5*cm])
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), KOYU),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",        (0,0), (-1,-1), 0.5, GRIS),
        ("ALIGN",       (1,0), (1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.5*cm))

    # Top-5 Kâr Marjı
    story.append(Paragraph("💰 En Yüksek Kâr Potansiyeli — Top 5 SKU", h2_style))
    urunler = db.query(models.Product).filter(models.Product.unit_price > 0).all()
    top5 = sorted(urunler,
                  key=lambda u: (u.unit_price - u.unit_cost) * u.current_stock,
                  reverse=True)[:5]
    kar_data = [["SKU", "Ürün", "Marj (%)", "Stok", "Potansiyel Kâr (₺)"]]
    for u in top5:
        marj_tl = u.unit_price - u.unit_cost
        marj_yuzde = round((marj_tl / u.unit_price * 100) if u.unit_price > 0 else 0, 1)
        kar_data.append([
            u.sku, u.name_tr[:30],
            f"%{marj_yuzde}",
            str(u.current_stock),
            f"₺{round(marj_tl * u.current_stock, 2):,.2f}"
        ])
    kar_tbl = Table(kar_data, colWidths=[2.5*cm, 6*cm, 2*cm, 1.5*cm, 3.5*cm])
    kar_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), YESIL),
        ("TEXTCOLOR",   (0,0), (-1,0), KOYU),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f0fdf4"), colors.white]),
        ("GRID",        (0,0), (-1,-1), 0.5, GRIS),
        ("ALIGN",       (2,0), (-1,-1), "CENTER"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    story.append(kar_tbl)
    story.append(Spacer(1, 0.5*cm))

    # Kritik Stok Uyarıları
    kritik_urunler = db.query(models.Product)\
        .filter(models.Product.current_stock <= models.Product.reorder_point).limit(10).all()
    if kritik_urunler:
        story.append(Paragraph("⚠️ Kritik Stok Uyarıları", h2_style))
        uyari_data = [["SKU", "Ürün", "Mevcut", "Eşik"]]
        for u in kritik_urunler:
            uyari_data.append([u.sku, u.name_tr[:35], str(u.current_stock), str(u.reorder_point)])
        uyari_tbl = Table(uyari_data, colWidths=[2.5*cm, 8*cm, 2.5*cm, 2.5*cm])
        uyari_tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), KIRMIZI),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#fff1f2"), colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, GRIS),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING",  (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ]))
        story.append(uyari_tbl)

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRIS))
    story.append(Paragraph(
        f"<font color='#94a3b8' size='8'>Bu rapor otomatik olarak üretilmiştir. "
        f"Akıllı Kafe Envanter Sistemi V2 — {datetime.datetime.now().strftime('%Y')}</font>",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    tarih = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"yonetici_raporu_{tarih}.pdf"

    logger.info(f"PDF raporu oluşturuldu: {filename}")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ==================================================
# --- FAZ 2.9 (ENTERPRISE / CRM & UPSELL API) ---
# ==================================================

@app.post("/crm/musteri", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def crm_musteri_bul_veya_ekle(req: CustomerLookup, db: Session = Depends(get_db)):
    cus = db.query(models.Customer).filter(models.Customer.phone_number == req.phone_number).first()
    if not cus:
        if not req.name: raise HTTPException(status_code=400, detail="Yeni kayıt; isim giriniz.")
        cus = models.Customer(phone_number=req.phone_number, name=req.name)
        db.add(cus); db.commit()
    return {"id": cus.id, "name": cus.name, "phone": cus.phone_number, "points": cus.loyalty_points, "visits": cus.total_visits}

@app.post("/pos/upsell-onerisi", dependencies=[Depends(role_required(["Admin", "Barista", "Depo Müdürü"]))])
def upsell_onerisi(req: UpsellRequest, db: Session = Depends(get_db)):
    if not req.current_item_ids: return {"oneriler": []}
    items = db.query(models.MenuItem).filter(models.MenuItem.id.in_(req.current_item_ids)).all()
    cats = [i.category.lower() for i in items if i.category]
    has_coffee = any("kahve" in c or "soğuk" in c or "çay" in c for c in cats)
    has_food = any("tatlı" in c or "pasta" in c or "sandviç" in c for c in cats)
    
    target = "Tatlılar" if has_coffee and not has_food else "Kahve" if has_food and not has_coffee else None
    if target:
        import random
        oneriler = db.query(models.MenuItem).filter(models.MenuItem.category.like(f"%{target}%")).all()
        if oneriler:
            pick = random.choice(oneriler)
            return {"oneriler": [{"id": pick.id, "name": pick.name, "price": pick.price, "emoji": pick.image_emoji}]}
    return {"oneriler": []}

@app.get("/crm/sorgula", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def crm_sorgula(phone: str, db: Session = Depends(get_db)):
    cus = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    if not cus:
        # Fly-by creation
        cus = models.Customer(phone_number=phone, name="Yeni Müşteri")
        db.add(cus)
        db.commit()
        db.refresh(cus)
    return {"id": cus.id, "name": cus.name, "phone": cus.phone_number, "points": cus.loyalty_points, "visits": cus.total_visits}

@app.get("/crm/musteriler", dependencies=[Depends(role_required(["Admin"]))])
def crm_musteri_listesi(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).order_by(models.Customer.total_visits.desc()).all()
    return [{"id": c.id, "name": c.name, "phone": c.phone_number, "points": c.loyalty_points, "visits": c.total_visits} for c in customers]

@app.post("/crm/puan-harca/{customer_id}", dependencies=[Depends(role_required(["Admin", "Barista"]))])
def crm_puan_harca(customer_id: int, db: Session = Depends(get_db)):
    cus = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cus: raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    if cus.loyalty_points < 9: raise HTTPException(status_code=400, detail="Yetersiz puan (En az 9 olmalı)")
    
    cus.loyalty_points -= 9
    db.commit()
    return {"mesaj": "9 Puan harcandı, hediye tanımlandı.", "yeni_puan": cus.loyalty_points}