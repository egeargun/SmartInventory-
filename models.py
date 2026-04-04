from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Date, Index
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Category(Base):
    __tablename__ = "categories"
    category_id = Column(Integer, primary_key=True)
    name_tr = Column(String(100), index=True)
    name_en = Column(String(100), index=True)

class Supplier(Base):
    __tablename__ = "suppliers"
    supplier_id = Column(Integer, primary_key=True)
    name = Column(String(100), index=True)
    contact_email = Column(String(100))

class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, index=True)
    name_tr = Column(String(100), index=True)
    name_en = Column(String(100), index=True)
    description_tr = Column(String(255), nullable=True)
    description_en = Column(String(255), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.supplier_id"), nullable=True)
    unit_cost = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    current_stock = Column(Integer, default=0)
    reorder_point = Column(Integer, default=10)
    abc_class = Column(String(10), default="C")
    expiration_date = Column(Date, nullable=True, index=True)
    warehouse_location = Column(String(100), default="Ana Depo")
    
    # İlişkisel Erişim 
    category = relationship("Category", foreign_keys=[category_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    
    __table_args__ = (
        Index('idx_product_date', 'product_id', 'transaction_date'),
        Index('idx_transaction_date', 'transaction_date')
    )

    transaction_id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.product_id"))
    quantity = Column(Integer)
    transaction_type = Column(String(20)) # 'IN', 'OUT' vb.
    notes = Column(String(255), nullable=True)
    processed_by = Column(String(100))
    status = Column(String(20), default="BEKLEMEDE") # İş Akışı Durumu
    transaction_date = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String(50), default="Manuel") # İşlemin Kaynağı (Manuel, Webhook)
    
    # İlişkisel Erişim
    product = relationship("Product", foreign_keys=[product_id])

class User(Base):
    # JWT Auth için Yeni Eklenen Enterprise Tablosu
    __tablename__ = "app_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(255))
    role = Column(String(20)) # "Admin", "Depo Müdürü", "Barista"

class ApiKey(Base):
    """Makineler Arası İletişim (M2M) için JWT Alternatifi. 3. Parti POS Sistemleri İçin."""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(50)) # Örn: "Adisyo-Kadikoy"
    api_key = Column(String(64), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    price = Column(Float, default=0.0)
    image_emoji = Column(String(10)) # UI'da güzel görünüm için (☕,🥤)
    external_pos_id = Column(String(100), index=True, nullable=True) # 3. Parti POS Sistemi Ürün ID'si
    category = Column(String(50), default="Diğer")
    image_url = Column(String(255), nullable=True)

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    product_id = Column(Integer, ForeignKey("products.product_id"))
    quantity_required = Column(Float) # Örn: Latte (ID:1) -> Süt (ID:5) -> 0.2 Litre
    
    ürün = relationship("Product", foreign_keys=[product_id])
    menü_ürünü = relationship("MenuItem", foreign_keys=[menu_item_id])

class Sale(Base):
    """Z-Raporu ve Barista Performansını Tutan Satış (Nakit) Tablosu"""
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, default=1)
    total_price = Column(Float)
    customer_name = Column(String(100), nullable=True) # Bardak ismi
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # CRM DB bağlantısı
    barista_name = Column(String(50))
    payment_method = Column(String(20), default="Nakit") # Nakit / Kart
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String(50), default="Manuel") # Webhook-Adisyo falan buraya düşecek
    
    menü_ürünü = relationship("MenuItem")

class Shift(Base):
    """Personel Kasa Devir/Vardiya Tablosu"""
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True, index=True)
    barista_name = Column(String(50), index=True)
    expected_cash = Column(Float, default=0.0) # Sistemdeki nakit
    reported_cash = Column(Float, default=0.0) # Elden teslim edilen fiziksel
    expected_credit = Column(Float, default=0.0)
    reported_credit = Column(Float, default=0.0)
    closed_at = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLog(Base):
    """Güvenlik Denetim Kayıtları: Kim, Ne Zaman, Ne Yaptı?"""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String(50), index=True)          # Kullanıcı adı
    role = Column(String(30))                        # Rol
    action = Column(String(100))                     # İşlem kodu (e.g. STOCK_IN, LOGIN, APPROVE)
    resource = Column(String(100), nullable=True)    # Hedef kaynak (Product adı vb.)
    detail = Column(String(255), nullable=True)      # Ek açıklama
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    is_archived = Column(Integer, default=0)         # 0: Aktif, 1: Arşivlendi (7 günden eski)
    archived_at = Column(DateTime, nullable=True)

class SupplyOrderApproval(Base):
    """Onaylanan Tedarik Siparişleri."""
    __tablename__ = "supply_order_approvals"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.product_id"))
    quantity = Column(Float)
    approved_by = Column(String(50))
    supplier_name = Column(String(100), nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, ORDERED, RECEIVED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    product = relationship("Product")

class OutboundWebhook(Base):
    """Dış sistemlere gönderilen bildirimlerin günlüğü."""
    __tablename__ = "outbound_webhooks"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50))
    payload = Column(String(500))
    status_code = Column(Integer, nullable=True)
    response_body = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# --- YENİ: MASA VE SİPARİŞ YÖNETİMİ (V2.1) ---
# ==========================================

class Table(Base):
    """Mekandaki masaların durumu."""
    __tablename__ = "pos_tables"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    is_occupied = Column(Integer, default=0) # 0: Boş, 1: Dolu
    x_pos = Column(Float, default=0.0)
    y_pos = Column(Float, default=0.0)

class Order(Base):
    """Masa bazlı bekleyen (açık) siparişler."""
    __tablename__ = "pos_orders"
    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("pos_tables.id"), nullable=True) # Null ise Paket Servis
    status = Column(String(20), default="PENDING") # PENDING, PAID, CANCELLED
    total_amount = Column(Float, default=0.0)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # CRM bağlantısı
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    """Siparişin içindeki her bir menü kalemi."""
    __tablename__ = "pos_order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("pos_orders.id"))
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Float) # Satış anındaki fiyat
    
    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem")

# ==========================================
# --- YENİ: GİDER VE ZAYİ YÖNETİMİ (V2.2) ---
# ==========================================

class Expense(Base):
    """İşletme giderleri (Kira, Fatura, Personel Yemeği vb.)"""
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50)) # Mutfak, Fatura, Maaş vb.
    amount = Column(Float)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Wastage(Base):
    """Zayi ve Fire kayıtları (Dökülen süt, bozulan ürün vb.)"""
    __tablename__ = "wastage"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.product_id"))
    quantity = Column(Float)
    reason = Column(String(255))
    cost_impact = Column(Float) # Zayinin TL bazlı zararı
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    product = relationship("Product")

# ==========================================
# --- YENİ: CRM VE SADAKAT UYGULAMASI (V2.9) ---
# ==========================================

class Customer(Base):
    """Kafenin sadık müşterileri ve CRM Modülü"""
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True)
    name = Column(String(100))
    loyalty_points = Column(Integer, default=0) # 10 puanda 1 kahve bedava
    total_visits = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

