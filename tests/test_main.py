"""
Akıllı Envanter Sistemi V2 — Enterprise Test Suite
TDD prensibiyle yazılmış; Authentication, Authorization, Core Business Logic ve Webhook testlerini kapsar.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================
_admin_token = None

def get_admin_token() -> str:
    """Admin JWT token alır (Rate limitten kaçmak için önbelleğe alır)."""
    global _admin_token
    if _admin_token:
        return _admin_token
    res = client.post("/token", json={"username": "admin", "password": "123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    _admin_token = res.json()["access_token"]
    return _admin_token

def admin_headers() -> dict:
    return {"Authorization": f"Bearer {get_admin_token()}"}



# ============================================================
# 1. KİMLİK DOĞRULAMA (AUTHENTICATION) TESTLERİ
# ============================================================
class TestAuthentication:
    def test_login_yanlis_sifre_401(self):
        """Yanlış şifre → JWT verilmemeli."""
        res = client.post("/token", json={"username": "yanlis", "password": "yanlis"})
        assert res.status_code == 401
        assert "detail" in res.json()

    def test_login_basarili_token_doner(self):
        """Doğru kimlik → access_token ve role dönmeli."""
        res = client.post("/token", json={"username": "admin", "password": "123"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "role" in data
        assert data["role"] == "Admin"

    def test_tokensiz_dashboard_erisimi_401(self):
        """Token olmadan korunan endpoint → 401."""
        assert client.get("/dashboard-ozet").status_code == 401

    def test_tokensiz_urunler_401(self):
        """Token olmadan ürün listesi → 401."""
        assert client.get("/urunler").status_code == 401

    def test_tokensiz_inventory_summary_401(self):
        """Token olmadan inventory summary → 401."""
        assert client.get("/dashboard/inventory-summary").status_code == 401

    def test_tokensiz_audit_logs_401(self):
        """Token olmadan audit log → 401."""
        assert client.get("/audit-logs").status_code == 401


# ============================================================
# 2. YETKİLENDİRME (AUTHORIZATION) TESTLERİ
# ============================================================
class TestAuthorization:
    def test_tokensiz_stok_log_401(self):
        """Token olmadan stok log → 401."""
        assert client.get("/stok-log").status_code == 401

    def test_tokensiz_skt_analizi_401(self):
        """Token olmadan SKT analizi → 401."""
        assert client.get("/skt-analizi").status_code == 401


# ============================================================
# 3. ÇEKIRDEK İŞ MANTIĞI TESTLERİ
# ============================================================
class TestCoreBusinessLogic:
    def test_dashboard_ozet_yapisal_kontrol(self):
        """Dashboard özet yanıtı beklenen anahtarları içermeli."""
        res = client.get("/dashboard-ozet", headers=admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert "kritik_stok_uyari_sayisi" in data
        assert "finansal_durum" in data
        assert isinstance(data["kritik_stok_uyari_sayisi"], int)

    def test_urunler_paginasyon(self):
        """Ürün listesi skip/limit paginasyonu çalışmalı."""
        hdrs = admin_headers()
        res_5 = client.get("/urunler?skip=0&limit=5", headers=hdrs)
        res_2 = client.get("/urunler?skip=0&limit=2", headers=hdrs)
        assert res_5.status_code == 200
        assert res_2.status_code == 200
        data_5 = res_5.json()["data"]
        data_2 = res_2.json()["data"]
        assert len(data_2) <= 2
        assert len(data_5) <= 5

    def test_urunler_yapisal_kontrol(self):
        """Her ürün kaydı zorunlu alanları içermeli."""
        res = client.get("/urunler?limit=1", headers=admin_headers())
        assert res.status_code == 200
        data = res.json()["data"]
        if data:
            urun = data[0]
            for field in ["product_id", "name_tr", "name_en", "current_stock", "sku"]:
                assert field in urun, f"Eksik alan: {field}"

    def test_skt_analizi_yapi(self):
        """SKT analizi beklenen alanları döndürmeli."""
        res = client.get("/skt-analizi", headers=admin_headers())
        assert res.status_code == 200
        assert "skt_riskli_urunler" in res.json()

    def test_talep_tahmini_siralama(self):
        """Haftalık talep tahmini azalan sırada sıralanmış olmalı."""
        res = client.get("/talep-tahmini", headers=admin_headers())
        assert res.status_code == 200
        tahminler = res.json()["haftalik_talep_tahmini"]
        if len(tahminler) > 1:
            talepler = [t["gelecek_hafta_tahmini_talep"] for t in tahminler]
            assert talepler == sorted(talepler, reverse=True), "Tahminler azalan sırada değil!"

    def test_sevk_raporu_yapi(self):
        """Sevk raporu hem pasta hem çizgi grafik verisi içermeli."""
        res = client.get("/sevk-raporu", headers=admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert "grafik_1_pasta" in data
        assert "grafik_2_cizgi" in data
        assert "veriler" in data["grafik_1_pasta"]
        assert "veriler" in data["grafik_2_cizgi"]

    def test_audit_logs_admin_erisim(self):
        """Admin audit logları görüntüleyebilmeli."""
        res = client.get("/audit-logs", headers=admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert "logs" in data
        assert "total" in data
        assert isinstance(data["logs"], list)

    def test_audit_logs_paginasyon(self):
        """Audit log paginasyonu çalışmalı."""
        res = client.get("/audit-logs?skip=0&limit=5", headers=admin_headers())
        assert res.status_code == 200
        assert len(res.json()["logs"]) <= 5

    def test_bekleyen_talepler_yapi(self):
        """Bekleyen talepler listesi 'talepler' anahtarı içermeli."""
        res = client.get("/bekleyen-talepler", headers=admin_headers())
        assert res.status_code == 200
        assert "talepler" in res.json()

    def test_tedarikci_siparis_yapi(self):
        """Tedarikçi sipariş listesi yapısal kontrol."""
        res = client.get("/tedarikci-siparis", headers=admin_headers())
        assert res.status_code == 200
        assert "bekleyen_siparis_listesi" in res.json()


# ============================================================
# 4. DASHBOARD INVENTORY SUMMARY TESTLERİ
# ============================================================
class TestDashboardInventorySummary:
    def test_tokensiz_inventory_summary_401(self):
        """Token olmadan inventory summary → 401."""
        assert client.get("/dashboard/inventory-summary").status_code == 401

    def test_inventory_summary_yapisal_kontrol(self):
        """Authenticated inventory summary → expected keys."""
        res = client.get("/dashboard/inventory-summary", headers=admin_headers())
        assert res.status_code == 200
        data = res.json()
        for key in ["total_skus", "total_stock_value", "low_stock_count",
                     "out_of_stock_count", "near_expiry_count",
                     "category_breakdown", "stock_movement_7d"]:
            assert key in data, f"Missing key: {key}"
        assert isinstance(data["total_skus"], int)
        assert isinstance(data["total_stock_value"], (int, float))
        assert isinstance(data["category_breakdown"], list)
        assert isinstance(data["stock_movement_7d"], list)


# ============================================================
# 5. ANA SAYFA ERİŞİM TESTİ
# ============================================================
class TestGeneralAccess:
    def test_anasayfa_html_donuyor(self):
        """GET / → HTML döndürmeli."""
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
