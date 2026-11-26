# Yol haritası

## Aşama 1 · Çalışan temel (v0.1)

- [x] Çalışan görünümü ve deney gözlemcisi.
- [x] DOCX yükleme, gerçek LibreOffice dönüşümü, önizleme/indirme.
- [x] Normal ve eğitim eklentisi; ayrı süreç ve özel çalışma alanı.
- [x] İki sabit sentetik dosya; şema/içerik doğrulayan yerel alıcı.
- [x] Çalışma kimliği, kanıt JSON'u, alıcı içerik baytı.
- [x] Linux bubblewrap çalıştırma kodu ve destek yokken B/C/D reddi.
- [ ] Linux'ta dört profilin gerçek çalıştırılarak kabul edilmesi.

Kabul: Normal sürüm doğru PDF üretir ve aktarım yapmaz. Eğitim A sürümü aynı içeriği koruyan PDF üretir; alıcı iki sentetik kaydı gerçekten kabul eder.

## Eklenti ürünü · v0.2 tamamlandı

- [x] RaporLab ana uygulaması içinde kurulu eklentiler ekranı.
- [x] Laboratuvarda hazırlanan sabit eklenti paketi için manifest ve kurulum/kaldırma akışı.
- [x] Paket kimliği ve sürümüyle doğru normal/eğitim işlem planının işçide yüklenmesi.
- [x] Seçilen DOCX için başlıklar, kelime ve tablo sayısını içeren analiz özeti.
- [x] Paket kurmak ile belge seçmek arasındaki yetki farkının panelde açıklanması.

Kabul doğrulandı: yeni kurulumda eklenti yok; gerçek ZIP doğrulanıp kalıcı olarak kurulur; işçi manifest ve işlem planını çalışma kopyasından yükler. Kaldırılan paket yeni çalışmada kullanılamaz, başlamış iş kendi kopyasıyla tamamlanır. Paketler bildirimsel plan taşır; keyfi kod yükleyici değildir. Ayrıntılar `docs/PLUGIN_PACKAGES.md` içindedir.

## Aşama 2 · Linux deney ortamı (v0.3, sıradaki iş)

1. Temiz Linux VM, normal kullanıcı, sistem Python'u, LibreOffice ve bubblewrap kurulumunu sabitle.
2. Dönüşüm motorunun font/geçici profil ihtiyaçlarını dört profilde doğrula.
3. Test matrisini çalıştır: A okur/gönderir; B okuyamaz ama ping atar; C okur ama bağlanamaz; D ikisini de yapamaz. Hepsinde PDF oluşmalı.
4. Ağ açık A/B profillerini yalnızca laboratuvar alıcısına ulaşabilecek şekilde işletim sistemi düzeyinde sınırla; VM'nin dış internet erişimini kapat.
5. Kısıt başarısızsa sonuç “doğrulanmadı” olsun; uygulama sahte bir engelleme göstermesin.

Kabul: Dört profil için gerçek PDF + alıcı + dosya gözlem kanıtı. Ağ yapılandırması deney paketine eklenir.

## Aşama 3 · Bağımsız dosya gözlemi ve doğruluk (v0.4)

- Linux sistem çağrısı/denetim gözlemini eklenti dışından topla.
- Açma, okuma ve başarısız erişimleri ayrı değerlendir; PID/run_id ile bağla.
- Referans PDF için beklenen metin, tablo değerleri ve sayfa render karşılaştırması ekle.
- Alıcı sağlığını ağ kapalı profilden önce ayrı yönetim yoluyla kaydet.
- Deney geçmişini diskteki kanıtlardan geri yükle; eski/yeni çalışmaları ayır.

Kabul: İşçinin beyanı olmadan görev dışı erişim sonucu açıklanabilsin. Yapısal geçerlilik, içerik doğruluğu ve görsel kontrol ayrı raporlansın.

## Aşama 4 · Ölçüm ve sunum (v1.0)

- Profil başına en az beş tekrar, dönüşümlü sıra, sıcak/soğuk başlangıç ayrımı.
- Dönüşüm, ek davranış ve toplam bekleme süreleri için medyan ve aralık.
- Profil karşılaştırması ve tek tık kanıt paketi.
- Sunum: doğru PDF → alıcıdaki işaret → D profilinde aynı işlevin sürmesi.
- Kurulum/sıfırlama açıklaması ve sonuç raporu.

## Kapsam dışında

Gerçek kişi belgeleri, keyfi dosya tarama, keyfi alıcı adresi, parola toplama, kalıcılık, güvenlik aracından kaçınma, gerçek bir eklenti mağazasında dağıtım. Bu ilk sürümde görev dışı dosya değiştirme de yoktur.
