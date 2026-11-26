# HızlıPDF paket sözleşmesi · API 1

Paketler bir işletim sistemi veya tarayıcı eklentisi yüklemez. RaporLab'ın yerel kayıt alanına kurulan ve ayrı işçide yorumlanan bildirimsel eklentilerdir. Keyfi Python/JavaScript betikleri, kurulum komutları ve uzak kaynak indirme desteklenmez.

## Yapı

ZIP tam olarak `manifest.json` ve `pipeline.json` içerir. Sıkıştırılmış boyut en fazla 32 KiB, toplam açılmış boyut en fazla 16 KiB'dir. Fazladan, yinelenmiş veya dizin geçişi içeren girdiler reddedilir; arşiv diske açılmaz.

```json
{"id":"hizlipdf.normal","name":"HızlıPDF · Normal referans","version":"0.2.0","api_version":1,"engine":"declarative-v1","entry":"pipeline.json"}
```

Normal plan: `analyze_docx → convert_pdf`. Eğitim planı: `analyze_docx → convert_pdf → synthetic_lab_probe`. Manifest ve plan, uygulamanın bilinen kataloğuyla eşleşmelidir. Bilinmeyen sürüm, kimlik veya işlem reddedilir. Aynı geçerli paketi yeniden kurmak güvenle tekrarlanabilir.

## Çalışma ömrü

1. Yeni veri dizininde kurulu paket yoktur.
2. Kullanıcı paket indirip dosyadan kurar veya katalogdaki kur düğmesini kullanır.
3. Doğrulanan paket `_plugins/<id>.zip` konumunda kalıcı tutulur.
4. İş başlarken kurulu paket tekrar doğrulanır ve çalışmaya özel kopyası alınır.
5. İşçi bu kopyadan planı yükler; kimlik, sürüm ve SHA-256 kanıta eklenir.
6. Paket kaldırılırsa yeni işler reddedilir; başlamış iş kendi kopyasıyla sürer.

SHA-256, o çalışmada kullanılan ZIP'i belirler; tek başına yayıncı güveni veya dijital imza sağlamaz. Kurulum işletim sistemi dosya/ağ izinlerinin daraltıldığı anlamına gelmez.

## Analiz kapsamı

`word/document.xml` gövdesindeki metin kullanılır. Tablo hücrelerindeki paragraflar dahil edilir; boş paragraflar, üst/alt bilgiler ve yorumlar sayılmaz. `Title`, `Subtitle`, `Heading1`–`Heading9` stilleri başlık kabul edilir. Özel stillerde görsel olarak başlık görünen metinler otomatik tanınmayabilir. Unicode kelime/sayı grubu sayımı Word uygulamasının sayacıyla aynı olmak zorunda değildir.
