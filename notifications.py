import smtplib
import os
import httpx
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("akilli_envanter_notifications")

# SMTP Ayarları
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# Webhook Ayarları
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

async def send_supplier_email(to_email: str, product_name: str, current_stock: int):
    """Tedarikçiye stok kritik seviye uyarısı gönderir."""
    if not SMTP_USER or not SMTP_PASS or not to_email:
        logger.warning(f"SMTP ayarları eksik. {product_name} için e-posta gönderilemedi.")
        return

    subject = f"⚠️ STOK UYARISI: {product_name}"
    body = f"""
    Merhaba,

    Envanter sistemimize göre '{product_name}' ürünü kritik stok seviyesinin altına düşmüştür.
    Mevcut Stok: {current_stock}
    
    Lütfen yeni tedarik süreci için bilgilendirme yapınız veya siparişi teyit ediniz.

    Akıllı Kafe Envanter Sistemi V2
    """

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        logger.info(f"E-posta başarıyla gönderildi: {to_email} -> {product_name}")
    except Exception as e:
        logger.error(f"E-posta gönderim hatası: {str(e)}")

async def trigger_stock_webhook(event_data: dict):
    """Dış sisteme stok hareketi bilgisini push eder."""
    if not WEBHOOK_URL:
        # Test amaçlı logger'a yazalım
        logger.info(f"Webhook URL tanımlı değil. Simüle edilen veri: {event_data}")
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(WEBHOOK_URL, json=event_data, timeout=5.0)
            if response.status_code == 200:
                logger.info(f"Webhook başarıyla tetiklendi: {WEBHOOK_URL}")
            else:
                logger.warning(f"Webhook hatası: {response.status_code}")
    except Exception as e:
        logger.error(f"Webhook gönderim hatası: {str(e)}")

async def send_admin_report(subject: str, report_body: str):
    """Yöneticiye özet rapor gönderir."""
    if not SMTP_USER or not SMTP_PASS or not ADMIN_EMAIL:
        logger.warning("Admin e-posta ayarları eksik.")
        return

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = ADMIN_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(report_body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        logger.info("Yöneticiye rapor e-postası gönderildi.")
    except Exception as e:
        logger.error(f"Admin rapor gönderim hatası: {str(e)}")
