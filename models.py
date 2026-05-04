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
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255))
    role = Column(String(20)) # "Admin", "Depo Müdürü", "Depo Elemanı"
    is_approved = Column(Integer, default=0) # 0: Onay bekliyor, 1: Onaylandı


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


