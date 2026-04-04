import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, engine
import models

def seed_database():
    try:
        with engine.connect() as con:
            try: con.execute(text("ALTER TABLE suppliers ADD COLUMN contact_email VARCHAR(100);"))
            except: pass
            try: con.execute(text("ALTER TABLE products ADD COLUMN description_tr VARCHAR(255);"))
            except: pass
            try: con.execute(text("ALTER TABLE products ADD COLUMN description_en VARCHAR(255);"))
            except: pass
            try: con.execute(text("ALTER TABLE products ADD COLUMN warehouse_location VARCHAR(100);"))
            except: pass
            con.commit()
    except Exception as e:
        print("Alter error:", e)

    db = SessionLocal()
    try:
        print("Veritabanı tabloları hazırlanıyor...")
        models.Base.metadata.create_all(bind=engine)
        
        # Eşik değerini bilerek yüksek tutuyoruz (100) ki bu betik çalışınca veritabanını İngilizce+Türkçe datayla ezebilsin
        if db.query(models.Category).count() < 100:
            print("Kategoriler temizlenip yeniden oluşturuluyor...")
            db.query(models.InventoryTransaction).delete()
            db.query(models.Product).delete()
            db.query(models.Category).delete()
            db.query(models.Supplier).delete()
            db.commit()

            print("Yeni kategoriler ekleniyor...")
            categories = [
                models.Category(name_tr="Kahve Çekirdekleri", name_en="Coffee Beans"),
                models.Category(name_tr="Süt ve Süt Ürünleri", name_en="Dairy & Milk"),
                models.Category(name_tr="Şuruplar ve Tatlandırıcılar", name_en="Syrups & Sweeteners"),
                models.Category(name_tr="Sarf Malzemeler", name_en="Consumables"),
                models.Category(name_tr="Tatlı ve Atıştırmalıklar", name_en="Desserts & Snacks")
            ]
            db.add_all(categories)
            db.commit()

            suppliers = [
                models.Supplier(name="Global Coffee Co.", contact_email="supply@globalcoffee.com"),
                models.Supplier(name="Yeşil Ova Süt", contact_email="siparis@yesilova.com"),
                models.Supplier(name="SweetLife Şurupları", contact_email="b2b@sweetlife.com"),
                models.Supplier(name="EkoAmbalaj", contact_email="satis@ekoambalaj.com")
            ]
            db.add_all(suppliers)
            db.commit()

            cats = db.query(models.Category).all()
            sups = db.query(models.Supplier).all()

            cat_dict = {c.name_tr: c.category_id for c in cats}
            sup_dict = {s.name: s.supplier_id for s in sups}

            today = datetime.date.today()
            
            print("Yeni ürünler ekleniyor...")
            products = [
                models.Product(sku="BRZ-001", name_tr="Brezilya Arabica Çekirdeği (1kg)", name_en="Brazil Arabica Beans (1kg)", category_id=cat_dict["Kahve Çekirdekleri"], supplier_id=sup_dict["Global Coffee Co."], unit_cost=250.0, current_stock=150, reorder_point=40, abc_class="A"),
                models.Product(sku="COL-002", name_tr="Kolombiya Supremo Çekirdeği (1kg)", name_en="Colombia Supremo Beans (1kg)", category_id=cat_dict["Kahve Çekirdekleri"], supplier_id=sup_dict["Global Coffee Co."], unit_cost=320.0, current_stock=120, reorder_point=30, abc_class="A"),
                models.Product(sku="ETH-003", name_tr="Etiyopya Yirgacheffe (1kg)", name_en="Ethiopia Yirgacheffe (1kg)", category_id=cat_dict["Kahve Çekirdekleri"], supplier_id=sup_dict["Global Coffee Co."], unit_cost=380.0, current_stock=60, reorder_point=20, abc_class="A"),
                models.Product(sku="MLK-001", name_tr="Tam Yağlı Süt (1L)", name_en="Whole Milk (1L)", category_id=cat_dict["Süt ve Süt Ürünleri"], supplier_id=sup_dict["Yeşil Ova Süt"], unit_cost=35.0, current_stock=300, reorder_point=100, abc_class="A", expiration_date=today + datetime.timedelta(days=15)),
                models.Product(sku="MLK-002", name_tr="Yarım Yağlı Süt (1L)", name_en="Semi-Skimmed Milk (1L)", category_id=cat_dict["Süt ve Süt Ürünleri"], supplier_id=sup_dict["Yeşil Ova Süt"], unit_cost=32.0, current_stock=150, reorder_point=50, abc_class="B", expiration_date=today + datetime.timedelta(days=18)),
                models.Product(sku="MLK-003", name_tr="Badem Sütü (1L) - Vegan", name_en="Almond Milk (1L) - Vegan", category_id=cat_dict["Süt ve Süt Ürünleri"], supplier_id=sup_dict["Yeşil Ova Süt"], unit_cost=65.0, current_stock=80, reorder_point=20, abc_class="B", expiration_date=today + datetime.timedelta(days=90)),
                models.Product(sku="SYR-001", name_tr="Vanilya Şurubu (750ml)", name_en="Vanilla Syrup (750ml)", category_id=cat_dict["Şuruplar ve Tatlandırıcılar"], supplier_id=sup_dict["SweetLife Şurupları"], unit_cost=150.0, current_stock=40, reorder_point=15, abc_class="C", expiration_date=today + datetime.timedelta(days=365)),
                models.Product(sku="SYR-002", name_tr="Karamel Şurubu (750ml)", name_en="Caramel Syrup (750ml)", category_id=cat_dict["Şuruplar ve Tatlandırıcılar"], supplier_id=sup_dict["SweetLife Şurupları"], unit_cost=150.0, current_stock=35, reorder_point=15, abc_class="C", expiration_date=today + datetime.timedelta(days=365)),
                models.Product(sku="CUP-001", name_tr="Karton Bardak 8oz", name_en="Paper Cup 8oz", category_id=cat_dict["Sarf Malzemeler"], supplier_id=sup_dict["EkoAmbalaj"], unit_cost=1.5, current_stock=2000, reorder_point=500, abc_class="B"),
                models.Product(sku="CUP-002", name_tr="Karton Bardak 12oz", name_en="Paper Cup 12oz", category_id=cat_dict["Sarf Malzemeler"], supplier_id=sup_dict["EkoAmbalaj"], unit_cost=1.8, current_stock=1500, reorder_point=400, abc_class="B"),
                models.Product(sku="LID-001", name_tr="Bardak Kapağı (Standart)", name_en="Cup Lid (Standard)", category_id=cat_dict["Sarf Malzemeler"], supplier_id=sup_dict["EkoAmbalaj"], unit_cost=0.5, current_stock=3500, reorder_point=1000, abc_class="C"),
                models.Product(sku="SNK-001", name_tr="Çikolatalı Muffin", name_en="Chocolate Muffin", category_id=cat_dict["Tatlı ve Atıştırmalıklar"], supplier_id=sup_dict["Global Coffee Co."], unit_cost=25.0, current_stock=45, reorder_point=15, abc_class="C", expiration_date=today + datetime.timedelta(days=3)),
                models.Product(sku="SNK-002", name_tr="Limonlu Cheesecake", name_en="Lemon Cheesecake", category_id=cat_dict["Tatlı ve Atıştırmalıklar"], supplier_id=sup_dict["Global Coffee Co."], unit_cost=40.0, current_stock=20, reorder_point=5, abc_class="C", expiration_date=today + datetime.timedelta(days=4))
            ]
            
            # category fix for COL-002
            products[1].category_id = cat_dict["Kahve Çekirdekleri"]
            
            db.add_all(products)
            db.commit()

            print("Örnek stok hareketleri ekleniyor...")
            transactions = [
                models.InventoryTransaction(product_id=products[0].product_id, quantity=5, transaction_type="OUT", processed_by="berkcan", status="ONAYLANDI", notes="Günlük tüketim"),
                models.InventoryTransaction(product_id=products[3].product_id, quantity=10, transaction_type="OUT", processed_by="berkcan", status="ONAYLANDI", notes="Günlük tüketim, fire"),
                models.InventoryTransaction(product_id=products[8].product_id, quantity=100, transaction_type="OUT", processed_by="berkcan", status="ONAYLANDI", notes="Günlük tüketim")
            ]
            db.add_all(transactions)
            db.commit()
            print("Veritabanı başarıyla tohumlandı!")
        else:
            print("Veritabanında halihazırda yeterli içerik var. Seed komutu atlandı.")
    except Exception as e:
        print(f"Hata oluştu: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
