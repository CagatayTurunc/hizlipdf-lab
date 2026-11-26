# Doğrulama kaydı · 26 Kasım 2026

Ortam: macOS (Darwin), python-docx 1.2.0, pypdf 6.21.4 ve mevcut LibreOffice dönüştürme motoru.

## Gerçek çalıştırılan kontroller

- `python -m unittest discover -s tests -v`: 7 test; 6 geçti, 1 atlandı.
- DOCX biçimi ve açılmış arşiv boyutu sınırları doğrulandı.
- Destek olmayan izolasyon profili çalıştırılmadan reddedildi.
- Alıcı, yanlış anahtarı ve sentetik olmayan içeriği reddetti; yinelenen kaydı saymadı.
- Normal ve eğitim eklentileri gerçek PDF üretti. Çıkarılan metinler eşleşti; `Müşteri Teklifi` ve `20.000` korundu.
- Normal eklentide alıcı kaydı yoktu.
- Eğitim A profilinde 2 sentetik kaynak ve toplam 122 bayt içerik kabul edildi. Bağımsız LAB-PING içerik baytına dahil edilmedi.
- Tarayıcıda örnek DOCX seçimi, dönüşüm, PDF önizlemesi/indirme bağlantısı ve alıcı paneli doğrulandı. Ekran görüntüleri proje paketinin yanında bulunur.

## Henüz doğrulanmayanlar

- Linux bubblewrap A/B/C/D matrisi: macOS ortamında ilgili test atlandı. Linux kurulumunda çalıştırılmadan tamamlanmış sayılmaz.
- Bağımsız OS dosya erişim gözlemi, genel DOCX içerik eşitliği ve otomatik görsel karşılaştırma.
- Tekrarlı performans karşılaştırması ve OS düzeyinde alıcı hedefiyle sınırlı ağ çıkışı.

Bu sonuçlar bir performans veya genel zararlı yazılım tespiti iddiası değildir.
