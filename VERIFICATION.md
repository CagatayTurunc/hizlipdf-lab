# Doğrulama kaydı · 26 Kasım 2026

## v0.2 · Eklenti ürünü aşaması

- `python -m unittest discover -s tests -v`: 13 test; 12 geçti, Linux matrisi için 1 test atlandı.
- Kurulum → yeniden açılan kayıt alanından yükleme → kaldırma ve kaldırılmış paketin reddi doğrulandı.
- Bilinmeyen sürüm, işlem, yanlış API türü, ek arşiv girdisi ve dizin geçişi içeren paketler reddedildi. Başarısız kurulum önceki geçerli paketi bozmadı.
- Kurulu paketin kimliği, sürümü, SHA-256 özeti ve çalışmaya özel ZIP kopyası gerçek dönüşümde kontrol edildi.
- Çalışma sırasında kaldırma, başlamış işin kopyasını etkilemedi; sonraki iş reddedildi.
- Normal ve eğitim paketleri aynı analiz ve çıkarılabilir PDF metnini üretti; normal paket aktarım yapmadı, eğitim A paketi iki kaynağı ve 122 içerik baytını alıcıya ulaştırdı.
- Ayrı hazırlanmış küçük DOCX'te bölünmüş metin parçaları, tablo hücreleri, boş paragraflar ve üstbilginin kapsam dışı kalması doğrulandı: 8 kelime/sayı grubu, 4 dolu paragraf, 1 tablo, 1 başlık.
- Tarayıcıda dosyadan ZIP kurma, katalogdan kurma, kaldırıp yeniden kurma ve gerçek dönüşüm/analiz doğrulandı. Örnek müşteri belgesinde 47 kelime/sayı grubu, 1 tablo ve 2 başlık gösterildi.
- Linux B/C/D ve OS düzeyinde ağ hedef kısıtı hâlâ doğrulanmış değildir.

## v0.1 · Önceki temel doğrulaması

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
