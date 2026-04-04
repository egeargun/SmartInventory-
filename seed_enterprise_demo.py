import random
import datetime
import os
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import engine, SessionLocal
import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_password_hash(password):
    return pwd_context.hash(password)

def seed_enterprise_data():
    print("🚀 MEGA Enterprise Demo Veritabanı Yüklemesi Başlıyor...")
    
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    
    try:
        users = [
            models.User(username="admin", hashed_password=get_password_hash("123"), role="Admin"),
            models.User(username="depo_merkez", hashed_password=get_password_hash("123"), role="Depo Müdürü"),
            models.User(username="barista_ege", hashed_password=get_password_hash("123"), role="Barista"),
            models.User(username="barista_ayse", hashed_password=get_password_hash("123"), role="Barista")
        ]
        db.add_all(users)
        db.commit()

        suppliers = [
            models.Supplier(name="Global Coffee Roasters", contact_email="b2b@globalcoffee.com"),
            models.Supplier(name="Sütaş Kurumsal", contact_email="satis@sutas.com.tr"),
            models.Supplier(name="Monin Şurupları", contact_email="dist@monin.tr"),
            models.Supplier(name="EcoCup Ambalaj", contact_email="karton@ecocup.com"),
            models.Supplier(name="Pelit Tatlıcılık (Fırın)", contact_email="firin@pelit.com")
        ]
        db.add_all(suppliers)
        
        categories = [
            models.Category(name_tr="Kahve Çekirdekleri", name_en="Coffee Beans"),
            models.Category(name_tr="Süt & Süt Ürünleri", name_en="Dairy"),
            models.Category(name_tr="Şuruplar & Tatlandırıcılar", name_en="Syrups"),
            models.Category(name_tr="Ambalaj & Sarf Malzeme", name_en="Packaging"),
            models.Category(name_tr="Taze Unlu Mamuller", name_en="Bakery")
        ]
        db.add_all(categories)
        db.commit()

        today = datetime.date.today()
        # Çok Çeşitli Depo Ürünleri (Hammadde)
        products_data = [
            {"sku": "BEAN-ESP-01", "name_tr": "Espresso Blend %100 Arabica", "name_en": "Espresso Blend 100% Arabica", "cat": 1, "sup": 1, "cost": 450.0, "stock": 120, "reorder": 30, "exp": today + datetime.timedelta(days=120)},
            {"sku": "BEAN-FLT-02", "name_tr": "Kolombiya Filtre Çekirdek", "name_en": "Colombia Filter Beans", "cat": 1, "sup": 1, "cost": 520.0, "stock": 85, "reorder": 20, "exp": today + datetime.timedelta(days=90)},
            {"sku": "MILK-TAM-01", "name_tr": "Tam Yağlı Süt (1L)", "name_en": "Whole Milk (1L)", "cat": 2, "sup": 2, "cost": 32.0, "stock": 850, "reorder": 200, "exp": today + datetime.timedelta(days=14)},
            {"sku": "MILK-YUL-02", "name_tr": "Oatly Yulaf Sütü (1L)", "name_en": "Oatly Oat Milk (1L)", "cat": 2, "sup": 2, "cost": 85.0, "stock": 70, "reorder": 40, "exp": today + datetime.timedelta(days=25)},
            {"sku": "MILK-BDS-03", "name_tr": "Badem Sütü (1L)", "name_en": "Almond Milk (1L)", "cat": 2, "sup": 2, "cost": 90.0, "stock": 45, "reorder": 20, "exp": today + datetime.timedelta(days=30)},
            {"sku": "SYR-CAR-01", "name_tr": "Karamel Şurubu (70cl)", "name_en": "Caramel Syrup (70cl)", "cat": 3, "sup": 3, "cost": 210.0, "stock": 42, "reorder": 15, "exp": today + datetime.timedelta(days=300)},
            {"sku": "SYR-VAN-02", "name_tr": "Vanilya Şurubu (70cl)", "name_en": "Vanilla Syrup (70cl)", "cat": 3, "sup": 3, "cost": 210.0, "stock": 38, "reorder": 15, "exp": today + datetime.timedelta(days=300)},
            {"sku": "SYR-SFB-03", "name_tr": "Beyaz Çikolata Şurubu", "name_en": "White Chocolate Syrup", "cat": 3, "sup": 3, "cost": 230.0, "stock": 25, "reorder": 10, "exp": today + datetime.timedelta(days=300)},
            {"sku": "PAK-CUP-12", "name_tr": "12oz Karton Bardak", "name_en": "12oz Paper Cup", "cat": 4, "sup": 4, "cost": 1.5, "stock": 5000, "reorder": 1500, "exp": None},
            {"sku": "PAK-LID-12", "name_tr": "12oz Bardak Kapağı", "name_en": "12oz Cup Lid", "cat": 4, "sup": 4, "cost": 0.8, "stock": 4800, "reorder": 1500, "exp": None},
            {"sku": "PAK-CUP-08", "name_tr": "8oz Karton Bardak", "name_en": "8oz Paper Cup", "cat": 4, "sup": 4, "cost": 1.2, "stock": 3500, "reorder": 1000, "exp": None},
            {"sku": "PAK-SWC-01", "name_tr": "Sandviç/Tatlı Kutusu", "name_en": "Sandwich/Dessert Box", "cat": 4, "sup": 4, "cost": 3.0, "stock": 1200, "reorder": 500, "exp": None},
            {"sku": "BAK-SAN-01", "name_tr": "San Sebastian Cheesecake(Dilim)", "name_en": "San Sebastian Cheesecake(Slice)", "cat": 5, "sup": 5, "cost": 45.0, "stock": 40, "reorder": 10, "exp": today + datetime.timedelta(days=3)},
            {"sku": "BAK-CRO-02", "name_tr": "Tereyağlı Kruvasan", "name_en": "Butter Croissant", "cat": 5, "sup": 5, "cost": 25.0, "stock": 60, "reorder": 15, "exp": today + datetime.timedelta(days=2)},
            {"sku": "BAK-BRW-03", "name_tr": "Belçika Çikolatalı Brownie", "name_en": "Belgian Chocolate Brownie", "cat": 5, "sup": 5, "cost": 35.0, "stock": 35, "reorder": 10, "exp": today + datetime.timedelta(days=5)},
            {"sku": "BAK-SMT-04", "name_tr": "Klasik Gevrek Simit", "name_en": "Classic Turkish Bagel", "cat": 5, "sup": 5, "cost": 9.0, "stock": 100, "reorder": 20, "exp": today + datetime.timedelta(days=1)}
        ]
        
        for p in products_data:
            prod = models.Product(
                sku=p["sku"], name_tr=p["name_tr"], name_en=p["name_en"],
                category_id=p["cat"], supplier_id=p["sup"], unit_cost=p["cost"], unit_price=p["cost"]*2.5,
                current_stock=p["stock"], reorder_point=p["reorder"], abc_class="A",
                expiration_date=p["exp"], warehouse_location=f"Blok {random.choice(['A','B','C'])}-Raf {random.randint(1,9)}"
            )
            db.add(prod)
        db.commit()

        # Gerçekçi 3. Nesil Kafe Menüsü (Masa Müşterisine Satılanlar)
        menu_items = [
            models.MenuItem(name="Caffe Latte (12oz)", price=130.0, image_emoji="☕", external_pos_id="LATTE"),
            models.MenuItem(name="Iced Caramel Macchiato", price=165.0, image_emoji="🥤", external_pos_id="ICEMAC"),
            models.MenuItem(name="Filtre Kahve (V60)", price=110.0, image_emoji="☕", external_pos_id="FLT"),
            models.MenuItem(name="Iced Oat Latte", price=175.0, image_emoji="🧊", external_pos_id="OATLATTE"),
            models.MenuItem(name="Flat White (8oz)", price=125.0, image_emoji="☕", external_pos_id="FLAT"),
            models.MenuItem(name="Americano", price=105.0, image_emoji="☕", external_pos_id="AMER"),
            models.MenuItem(name="White Mocha", price=160.0, image_emoji="🥛", external_pos_id="WMOC"),
            models.MenuItem(name="Cortado", price=115.0, image_emoji="☕", external_pos_id="CORT"),
            models.MenuItem(name="San Sebastian Cheesecake", price=190.0, image_emoji="🍰", external_pos_id="SANSEB"),
            models.MenuItem(name="Belçika Brownie", price=145.0, image_emoji="🍫", external_pos_id="BRWN"),
            models.MenuItem(name="Tereyağlı Kruvasan", price=95.0, image_emoji="🥐", external_pos_id="CROI"),
            models.MenuItem(name="Sıcak Çikolata", price=140.0, image_emoji="☕", external_pos_id="HOTCHOC"),
            models.MenuItem(name="Çay (İnce Belli)", price=35.0, image_emoji="🍵", external_pos_id="CAY"),
            models.MenuItem(name="Matcha Latte", price=180.0, image_emoji="🍵", external_pos_id="MATCHA"),
            models.MenuItem(name="Cold Brew Şişe (250ml)", price=150.0, image_emoji="🍾", external_pos_id="COLD")
        ]
        db.add_all(menu_items)
        db.commit()
        
        # Latte Reçetesi (1 = Espresso, 3 = Süt, 9=12ozBardak, 10=Kapak)
        db.add_all([
            models.RecipeIngredient(menu_item_id=1, product_id=1, quantity_required=0.018), 
            models.RecipeIngredient(menu_item_id=1, product_id=3, quantity_required=0.25),
            models.RecipeIngredient(menu_item_id=1, product_id=9, quantity_required=1),
            models.RecipeIngredient(menu_item_id=1, product_id=10, quantity_required=1)
        ])
        
        # San Sebastian Reçetesi (Sadece Tatlı ve Kutu Düşer)
        db.add_all([
            models.RecipeIngredient(menu_item_id=9, product_id=13, quantity_required=1), 
            models.RecipeIngredient(menu_item_id=9, product_id=12, quantity_required=1)
        ])

        # Kruvasan
        db.add_all([
            models.RecipeIngredient(menu_item_id=11, product_id=14, quantity_required=1)
        ])
        
        db.commit()
        print("✅ Genişletilmiş Menü ve Reçeteler (BOM) kuruldu.")

        print("🔄 Yüksek Hacimli (Günde ~35.000₺) Ciro Akışı 7 gün için simüle ediliyor...")
        now = datetime.datetime.utcnow()
        baristas = ["barista_ege", "barista_ayse", "barista_mert", "barista_zeynep"]
        payment_methods = ["Kredi Kartı", "Kredi Kartı", "Kredi Kartı", "Kredi Kartı", "Nakit", "Yemek Kartı"]
        
        menu_items_from_db = db.query(models.MenuItem).all()
        
        for days_ago in range(7, -1, -1):
            target_date = now - datetime.timedelta(days=days_ago)
            # Gerçekçi ve Yoğun bir kafe (Günde 180-250 arası fiş, her fişte 1-3 ürün eklenecek, bu yüzden total satış günlük 30-40k'yı bulacak)
            daily_receipts_count = random.randint(150, 220) 
            
            for _ in range(daily_receipts_count):
                barista = random.choice(baristas)
                pay_met = random.choice(payment_methods)
                sale_time = target_date.replace(hour=random.randint(7, 22), minute=random.randint(0, 59), second=random.randint(0,59))
                
                # Bir müşteri bazen 1 bazen 3 ürün alır
                basket_items = random.randint(1, 3)
                for _ in range(basket_items):
                    m_item = random.choice(menu_items_from_db)
                    
                    sale = models.Sale(
                        menu_item_id=m_item.id, quantity=1, total_price=m_item.price,
                        customer_name=f"Müşteri-{random.randint(1000,9999)}", barista_name=barista,
                        payment_method=pay_met, created_at=sale_time
                    )
                    db.add(sale)
                    
                    recipes = db.query(models.RecipeIngredient).filter(models.RecipeIngredient.menu_item_id == m_item.id).all()
                    for req in recipes:
                        inv_tx = models.InventoryTransaction(
                            product_id=req.product_id, quantity=req.quantity_required, transaction_type="OUT",
                            notes=f"POS Satışı ({pay_met}) - {m_item.name}", processed_by=barista,
                            status="ONAYLANDI", transaction_date=sale_time
                        )
                        db.add(inv_tx)
            
            # Günlük FİRELER (Kruvasan kurur, Süt Dökülür)
            fire_time = target_date.replace(hour=22, minute=30)
            
            # 3 Adet Kruvasan bayatlama firesi
            fire_tx1 = models.InventoryTransaction(product_id=14, quantity=3, transaction_type="OUT", notes="FİRE - Gün Sonu Bayatlayan Ürün (Zayi)", processed_by="admin", status="ONAYLANDI", transaction_date=fire_time)
            # 1 Litre Süt firesi
            fire_tx2 = models.InventoryTransaction(product_id=3, quantity=1, transaction_type="OUT", notes="FİRE - Barista sütte pürüz gördü (Zayi)", processed_by="admin", status="ONAYLANDI", transaction_date=fire_time)
            
            db.add_all([fire_tx1, fire_tx2])
            
            # GÜNLÜK TOPLU COMMİT (Database Kilitlenmesini Önler)
            db.commit()
            print(f"✔️ {days_ago} gün öncesi: {daily_receipts_count} fiş işlendi.")
        
        try:
            if hasattr(models, 'ApiKey'):
                api_key = getattr(models, 'ApiKey')(api_key="DEMO-ADISYO-9988776655", provider_name="Adisyo Kadıköy Şubesi")
                db.add(api_key)
                db.commit()
                print("🔑 Dummy API Key Yüklendi.")
        except Exception:
            pass
            
        print("🎉 DEV SİMÜLASYON TAMAMLANDI! Enterprise Dashboard 30.000₺'lik Hacme Ulaştı!")

    except Exception as e:
        print(f"❌ HATA: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_enterprise_data()
