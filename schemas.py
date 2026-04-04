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
    category_id: int
    supplier_id: int
    unit_cost: float
    unit_price: float
    current_stock: int
    reorder_point: int
    abc_class: str
    expiration_date: Optional[str] = None # SKT (Termos için boş, Süt için dolu)
    warehouse_location: str = "Ana Depo"

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

# 5. POS Entegrasyonu (Webhook) Şablonları
class WebhookSaleItem(BaseModel):
    external_product_id: str
    quantity: int
    price: float

class WebhookSalePayload(BaseModel):
    pos_provider: str
    receipt_id: str
    items: List[WebhookSaleItem]
    timestamp: Optional[str] = None

class ApiKeyCreate(BaseModel):
    provider_name: str

# 6. QR Müşteri (B2C) Sipariş Talepleri
class QROrderItem(BaseModel):
    menu_item_id: int
    quantity: int = 1

class QROrderRequest(BaseModel):
    table_id: int
    items: List[QROrderItem]