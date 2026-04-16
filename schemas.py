# schemas.py dosyası - Sadece Veri Şablonları (JSON Modelleri) Burada Durur

from pydantic import BaseModel, field_validator
from typing import Optional, List

# 1. Stok Güncelleme Şablonu
class StokGuncelleme(BaseModel):
    yeni_stok: int

# 2. Yeni Nesil Kafe Ürün Ekleme Şablonu
class ProductCreate(BaseModel):
    sku: str
    name_tr: str
    name_en: str
    description_tr: Optional[str] = None
    description_en: Optional[str] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit_cost: float = 0.0
    unit_price: float = 0.0
    current_stock: int = 0
    reorder_point: int = 10
    abc_class: str = "C"
    expiration_date: Optional[str] = None # SKT (Termos için boş, Süt için dolu)
    warehouse_location: str = "Ana Depo"

    @field_validator("sku")
    @classmethod
    def sku_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU boş olamaz / SKU cannot be blank")
        return v

    @field_validator("unit_cost", "unit_price")
    @classmethod
    def price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Fiyat negatif olamaz / Price cannot be negative")
        return v

    @field_validator("current_stock", "reorder_point")
    @classmethod
    def stock_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Stok negatif olamaz / Stock cannot be negative")
        return v

class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name_tr: Optional[str] = None
    name_en: Optional[str] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    current_stock: Optional[int] = None
    reorder_point: Optional[int] = None
    expiration_date: Optional[str] = None
    warehouse_location: Optional[str] = None

# 3. Stok Hareketi Şablonu (Kim, Ne Zaman, Ne Yaptı)
class StockTransaction(BaseModel):
    product_id: int
    quantity: int
    transaction_type: str # 'IN', 'OUT' veya 'ADJUST'
    notes: Optional[str] = None
    processed_by: str = "Admin"
    # --- YENİ EKLENEN (İş Akışı İçin) ---
    status: str = "ONAYLANDI" # Kaan Barista ekranından yollarken buraya "BEKLEMEDE" yazacak

# En alta Depo Müdürünün talebi yanıtlarken kullanacağı yepyeni şablonu ekle:
class TalepYaniti(BaseModel):
    yeni_durum: str # 'ONAYLANDI' veya 'İPTAL'
    yanitlayan_kisi: str = "Depo Müdürü"


# --- Ürün Yaşam Döngüsü (Product Lifecycle) ---
class LifecycleEvent(BaseModel):
    date: str
    stage: str            # CREATED, RECEIVED, CONSUMED, ADJUST, NEAR_EXPIRY, DEPLETED, EXPIRED
    actor: str
    quantity_delta: int
    running_balance: int
    source: Optional[str] = None
    notes: Optional[str] = None

class LifecycleSummary(BaseModel):
    sku: str
    name_tr: str
    name_en: Optional[str] = None
    current_stock: int
    total_received: int
    total_consumed: int
    total_adjusted: int
    days_on_hand: Optional[int] = None
    turnover_ratio: Optional[float] = None
    remaining_shelf_life_days: Optional[int] = None
    expiration_date: Optional[str] = None

class ProductLifecycleResponse(BaseModel):
    summary: LifecycleSummary
    timeline: List[LifecycleEvent]

