# HızlıPDF sunum akışı

**Deney sorusu.** Aynı DOCX doğru PDF'ye dönüştürülürken Linux, eklentinin görev dışı iki sentetik dosyaya ve yerel alıcıya erişimini nasıl değiştiriyor?

## Sunumdan önce

- Ubuntu'da `feature/plugin-install-analysis` dalını güncelleyin ve `./start.sh --port 8765` ile sunucuyu başlatın.
- **Eklentiler** ekranında normal ve eğitim paketlerini kurun. Çekirdek kayıtları için Ubuntu'da `strace` bulunmalı.
- **Karşılaştırma & Benchmark** ekranında yeni bir seri tamamlayın ve **Kanıt paketini indir** bağlantısını deneyin. Sunum ekranı aynı veri dizinindeki en yeni kayıtlı seriyi açar.
- Önceki seriler, ölçüldükleri sürümün kayıtlarını korur. Yeni soket sonuçlarını sunmak için bu sürümle oluşturulan seriyi kullanın.

## 1. Kontrol deneyi ve A/D karşılaştırması · 2–3 dakika

**Sunum akışı → Kontrol deneyini aç** üzerinden **Normal ve eğitim eklentisini karşılaştır** düğmesine basın. İki çalışma da aynı müşteri teklifini Profil A ile işler. Başlıkları, tek sayfayı ve `12.000`, `8.000`, `20.000` değerlerini gösterin.

Normal referans sütununda ek adım **Denenmedi** görünür. Eğitim sütununda dosya açma çağrılarını ve varsa yerel alıcının kabul ettiği sentetik içeriği açın. Ardından **A ve D’yi karşılaştır** üzerinden eğitim eklentisini sabit tutup iki profilin sonuçlarını karşılaştırın.

## 2. B/C sorusu · 2–3 dakika

“B ve C’de alıcı içerik kabul etmezse hangi kısıt devrede?” sorusunu sorun. **İzolasyon inceleyicisi** ekranında önce B’yi, sonra C’yi çalıştırın.

- **B.** İşçinin bağlama kaydında `/lab/targets` için ayrı bir giriş olmaması, iki dosyanın `ENOENT` sonucu ve alıcının `LAB-PING` kabulü birlikte incelenir.
- **C.** Salt okunur bağlama ve başarılı dosya açma kayıtları görülür. İşçi ile yerel alıcının ağ ad alanı kimlikleri karşılaştırılır. `connect()` ve eşleşen `SO_ERROR` sonucu varsa ikisini birlikte açın.

`EINPROGRESS` bağlantı girişiminin sürdüğünü, nihai soket sonucu ise girişimin nasıl sonlandığını gösterir. Panel, sonuç eksik kaldığında **Doğrulanmadı** gösterir. Ağ ad alanı, soket sonucu ve alıcı kaydı ayrı bulgulardır.

## 3. Tekrarlı ölçüm · 1–2 dakika

**Sunum akışı → Son kayıtlı deneyi aç** üzerinden her profilin geçerli PDF sayısını ve alıcının kabul ettiği içerik medyanını gösterin. Isınma turları ölçüm özetinin dışında kalır. Süreleri medyan, minimum–maksimum aralığı ve örneklem sayısıyla sunun. A/D medyan farkı bu ortamda ve bu seride gözlemlenen toplam süre farkıdır.

İstenirse bir profilin **Çalışma kayıtları** listesinden ilgili raporu açın veya seriyi tek JSON dosyası olarak indirin.
