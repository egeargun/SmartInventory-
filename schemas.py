# schemas.py dosyası - Sadece Veri Şablonları (JSON Modelleri) Burada Durur

from pydantic import BaseModel
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

