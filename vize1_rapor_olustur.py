from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Font Ayarları (Türkçe karakter desteği için sistemdeki Arial fontu kullanılmaktadır)
font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
font_bold_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont('Arial', font_path))
    pdfmetrics.registerFont(TTFont('Arial-Bold', font_bold_path))
else:
    print("Arial fontu bulunamadı, varsayılan fontlar kullanılacaktır.")

def generate_report():
    doc = SimpleDocTemplate("vize1_raporu.pdf", pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Profesyonel Stil Tanımlamaları
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='Arial-Bold' if os.path.exists(font_path) else 'Helvetica-Bold',
        fontSize=22,
        alignment=1, # Orta
        spaceAfter=30,
        leading=28
    )
    
    h1_style = ParagraphStyle(
        'H1Style',
        parent=styles['Heading1'],
        fontName='Arial-Bold' if os.path.exists(font_path) else 'Helvetica-Bold',
        fontSize=16,
        spaceBefore=18,
        spaceAfter=10,
        color=colors.HexColor("#2C3E50")
    )
    
    h2_style = ParagraphStyle(
        'H2Style',
        parent=styles['Heading2'],
        fontName='Arial-Bold' if os.path.exists(font_path) else 'Helvetica-Bold',
        fontSize=13,
        spaceBefore=12,
        spaceAfter=8,
        color=colors.HexColor("#2980B9")
    )
    
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontName='Arial' if os.path.exists(font_path) else 'Helvetica',
        fontSize=10.5,
        leading=14,
        alignment=4, # İki yana yasla
        spaceAfter=8
    )

    elements = []

    # KAPAK SAYFASI
    elements.append(Spacer(1, 120))
    elements.append(Paragraph("AKILLI KAFE ENVANTER YÖNETİM SİSTEMİ V2", title_style))
    elements.append(Paragraph("VİZE 1: TEKNİK ANALİZ VE İLERLEME RAPORU", title_style))
    elements.append(Spacer(1, 60))
    elements.append(Paragraph("<b>Hazırlayan:</b> Ege Argun / Kaan Karaağaç", body_style))
    elements.append(Paragraph("<b>Tarih:</b> 4 Nisan 2026", body_style))
    elements.append(Paragraph("<b>Kapsam:</b> Sistem Mimarisi, Kod Analizi ve Bulut Bilişim Entegrasyonu", body_style))
    elements.append(PageBreak())

    # 1. GİRİŞ VE PROJE VİZYONU
    elements.append(Paragraph("1. Giriş ve Proje Vizyonu", h1_style))
    elements.append(Paragraph(
        "Akıllı Kafe Envanter Sistemi V2, klasik stok takip algoritmalarının ötesine geçerek, "
        "operasyonel verimliliği maksimize eden bir <b>Merkezi Lojistik Platformu (Headless SaaS)</b> olarak tasarlanmıştır. "
        "Sistemimiz, kafe ekosistemindeki tüm bileşenleri (envanter hareketleri, satış verileri, zayi takibi ve tedarik zinciri) "
        "modüler ve ölçeklenebilir bir mimari ile tek bir merkezden yönetmektedir.", body_style))
    
    elements.append(Paragraph(
        "Proje; baristaların operasyonel yükünü hafifletmeyi ve işletme sahiplerlerine veri zekası (AI) aracılığıyla "
        "stratejik karar verme yetkinliği kazandırmayı hedeflemektedir. Bu kapsamda fire oranlarının düşürülmesi ve "
        "tedarik süreçlerinin otomatize edilmesi temel öncelikler arasındadır.", body_style))

    # 2. TEKNOLOJİ KATMANLARI (TECH STACK)
    elements.append(Paragraph("2. Teknoloji Katmanlari (Technical Stack)", h1_style))
    
    def tr_to_en(text):
        mapping = {
            'İ': 'I', 'ı': 'i', 'Ş': 'S', 'ş': 's', 'Ğ': 'G', 'ğ': 'g',
            'Ü': 'U', 'ü': 'u', 'Ö': 'O', 'ö': 'o', 'Ç': 'C', 'ç': 'c'
        }
        for tr, en in mapping.items():
            text = text.replace(tr, en)
        return text

    tech_data = [
        ["Katman", "Teknoloji", "Fonksiyonel Rol"],
        ["Backend", "FastAPI (Python)", "Asenkron islem kapasitesi ve yuksek performansli API mimarisi."],
        ["Veri Yonetimi", "SQLAlchemy ORM", "Iliskisel veritabani modellemesi ve veri butunlugu denetimi."],
        ["Guvenlik", "OAuth2 + JWT", "Kimlik dogrulama, yetkilendirme ve rol bazli erisim kontrolu (RBAC)."],
        ["Veri Bilimi", "Scikit-Learn", "Lineer Regresyon analizi ile ileriye donuk talep tahmini."],
        ["Arayuz", "Vanilla JS + PWA", "Cihaz bagimsiz calisabilen, hizli ve kurulabilir web arayuzu."],
        ["Iletisim", "WebSockets", "Sunucu ile istemci arasinda gercek zamanli (Real-time) veri senkronizasyonu."]
    ]
    
    # Tabloyu tr_to_en'den geçiriyoruz
    clean_tech_data = [[tr_to_en(str(cell)) for cell in row] for row in tech_data]

    t = Table(clean_tech_data, colWidths=[90, 110, 250])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        # Header:
        ('FONTNAME', (0, 0), (-1, 0), 'Arial-Bold' if os.path.exists(font_path) else 'Helvetica-Bold'),
        # Body (Tüm hücrelere fontu yayıyoruz):
        ('FONTNAME', (0, 0), (-1, -1), 'Arial' if os.path.exists(font_path) else 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))

    elements.append(t)
    elements.append(Spacer(1, 15))

    # 3. TEKNİK KOD ANALİZİ VE MODÜLER YAPI
    elements.append(Paragraph("3. Teknik Kod Analizi ve Modüler Yapı", h1_style))
    
    # auth.py
    elements.append(Paragraph("3.1 Kimlik Doğrulama ve Güvenlik (auth.py)", h2_style))
    elements.append(Paragraph(
        "Sistemin güvenlik omurgasını oluşturmaktadır. Kullanıcı parolaları, <b>Bcrypt</b> hashing algoritması ile "
        "en üst seviye güvenlik standartlarında korunmaktadır. <b>JWT (JSON Web Token)</b> kullanımı sayesinde "
        "durumsuz (stateless) bir oturum yönetimi sağlanmıştır. Sisteme entegre edilen 'Role-Based Access Control' "
        "mekanizması, 'Barista', 'Depo Müdürü' ve 'Admin' rolleri için farklı yetki seviyeleri tanımlamaktadır.", body_style))

    # models.py
    elements.append(Paragraph("3.2 Veri Modelleme ve İlişkisel Yapı (models.py)", h2_style))
    elements.append(Paragraph(
        "Veri tabanı mimarisi, nesne ilişkisel eşleme (ORM) prensipleri doğrultusunda SQLAlchemy ile inşa edilmiştir. "
        "<b>Product</b>, <b>InventoryTransaction</b>, <b>Sale</b> ve <b>AuditLog</b> tabloları arasındaki "
        "ilişkiler, veri bütünlüğünü (referential integrity) korumak üzere kurgulanmıştır. Özellikle AuditLog modülü, "
        "gerçekleştirilen tüm kritik işlemlerin dijital ayak izini (timestamp, IP, actor) kayıt altına almaktadır.", body_style))

    # main.py
    elements.append(Paragraph("3.3 Uygulama Mantığı ve API Servisleri (main.py)", h2_style))
    elements.append(Paragraph(
        "Uygulamanın operasyonel merkezidir. Satış süreçleri (<b>/satis-yap</b>), otomatik olarak <b>BOM (Ürün Reçetesi)</b> "
        "üzerinden hammadde envanterini güncellemektedir. Stok seviyesi kritik eşiğin altına düştüğünde, "
        "<b>BackgroundTasks</b> aracılığıyla otomatik tedarik talepleri ve e-posta bildirimleri tetiklenmektedir.", body_style))

    # AI
    elements.append(Paragraph("3.4 Veri Bilimi: Tahminsel Analiz Modeli", h2_style))
    elements.append(Paragraph(
        "Sistem, geçmiş 30 günlük tüketim verilerini analiz ederek <b>Lineer Regresyon</b> modeli üzerinden "
        "gelecek haftanın tahmini talebini hesaplamaktadır. Bu algoritmik yaklaşım, işletmenin stok yetersizliği "
        "veya aşırı stoklama risklerini önceden saptamasına olanak tanır.", body_style))

    elements.append(PageBreak())

    # 4. AWS BULUT ALTYAPISI VE KURULUM SÜRECİ
    elements.append(Paragraph("4. AWS Bulut Altyapısı ve Kurulum Süreci", h1_style))
    elements.append(Paragraph(
        "Sistemin yüksek erişilebilirlik ve ölçeklenebilirlik standartlarında çalışması için AWS (Amazon Web Services) "
        "ekosistemi tercih edilmiştir. Aşağıda projenin canlıya alınması için izlenen teknik adımlar yer almaktadır:", body_style))
    
    aws_steps = [
        "<b>Adım 1: Sunucu (EC2) Yapılandırması:</b> AWS üzerinden t3.micro ücretsiz kullanım paketi seçilerek Ubuntu 22.04 LTS işletim sistemine sahip bir sanal sunucu oluşturulmuştur.",
        "<b>Adım 2: Güvenlik Duvarı Ayarları:</b> VPC Security Group katmanında SSH (22), API (8000) ve Standart Web (80) portları için erişim kuralları tanımlanmıştır.",
        "<b>Adım 3: Docker Ortam Hazırlığı:</b> Sunucu üzerinde <i>docker.io</i> ve <i>docker-compose</i> paketleri kurulmuş, uygulama konteynır mimarisine hazır hale getirilmiştir.",
        "<b>Adım 4: Dağıtım (Deployment):</b> Proje kaynak kodları Git aracılığıyla sunucuya aktarılmış ve <i>docker-compose up -d --build</i> komutu ile servisler ayağa kaldırılmıştır.",
        "<b>Adım 5: İzleme (Monitoring):</b> Uygulama logları ve sunucu kaynak kullanımı AWS CloudWatch prensipleri doğrultusunda takibe alınmıştır."
    ]
    
    for step in aws_steps:
        elements.append(Paragraph(step, body_style))
        elements.append(Spacer(1, 4))

    # 5. PROFESYONEL GELİŞTİRME VE DENETİM ARAÇLARI
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("5. Profesyonel Geliştirme ve Denetim Araçları", h1_style))
    
    elements.append(Paragraph("5.1 DBeaver (Veri Tabanı Yönetimi)", h2_style))
    elements.append(Paragraph(
        "Veri tabanı şemasının görselleştirilmesi, ER diyagramlarının oluşturulması ve kompleks sorguların "
        "performans analizi için DBeaver arayüzü kullanılmaktadır. SQL standardizasyonu bu araçla sağlanmıştır.", body_style))

    elements.append(Paragraph("5.2 VS Code ve Geliştirici Ekosistemi", h2_style))
    elements.append(Paragraph(
        "Yazılım geliştirme süreci VS Code üzerinden; Pylance (statik tür denetimi), Docker ve Git entegrasyonları ile "
        "yürütülmektedir. Bu araç seti, kod kalitesini (clean code) ve sürdürülebilirliği desteklemektedir.", body_style))

    # 6. SONUÇ VE İLERLEME PLANI
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("6. Sonuç ve İlerleme Planı", h1_style))
    elements.append(Paragraph(
        "Akıllı Kafe Envanter Sistemi V2, teknik mimari ve veri odaklı yaklaşımıyla hedeflenen vize aşamasına "
        "başarıyla ulaşmıştır. Bir sonraki fazda, çoklu mağaza desteği ve derin öğrenme modelleri ile sistemin "
        "tahminleme yeteneklerinin artırılması hedeflenmektedir.", body_style))

    # Raporu Oluştur
    doc.build(elements)

if __name__ == "__main__":
    try:
        generate_report()
        print("vize1_raporu.pdf başarıyla güncellendi ve optimize edildi!")
    except Exception as e:
        print(f"Rapor oluşturma hatası: {str(e)}")
