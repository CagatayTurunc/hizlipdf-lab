# Hedef ürün ve sunum senaryosu

MaviRota çalışanı Deniz, müşteri teklifini toplantı öncesinde PDF'ye çevirmek ister. Linux'ta çalışan RaporLab uygulamasına HızlıPDF eklenti paketini kurar. Eklenti seçilen DOCX'in başlık, kelime ve tablo özetini üretir, belgeyi gerçekten PDF'ye dönüştürür ve doğru çıktıyı indirilebilir hâle getirir.

Eğitim eklentisi aynı çalışmada iki sabit sentetik şirket dosyasına görev dışı erişim ve yerel alıcıya aktarım dener. Geniş profilde alıcıdaki `LAB-BUTCE-042` ve `LAB-KIRA-017` işaretleri görünür. Bu işaretler seçilen DOCX'te yoktur. Dosya/ağ profilleri daraltıldığında meşru işlev korunurken bu davranışların hangilerinin engellendiği ölçülür.

## Mevcut ve planlanan davranış

| Özellik | Durum |
|---|---|
| Gerçek DOCX-PDF dönüşümü | Çalışıyor |
| Normal/eğitim işçisi seçimi | Çalışıyor |
| Sabit sentetik dosyalara okuma/yerel aktarım | Çalışıyor |
| Alıcı kabul paneli ve kanıt JSON'u | Çalışıyor |
| Sürümlü bildirimsel ZIP eklentisini kurma/kaldırma | Çalışıyor |
| DOCX belge analiz özeti | Çalışıyor |
| Linux dört profilinin gerçek ortamda doğrulanması | Bekliyor |
| Bağımsız OS dosya erişim kanıtı | Planlandı |

Mevcut sürümde `fixtures.py` içindeki iki dosya kullanılır. İhale veya maaş gibi alternatif hikâyeler bu sürümün gerçekleştirilmiş özelliği değildir. Görev dışı dosya değiştirme ana sürüm kapsamına alınmamıştır. Uygulama hedefi sentetik verili kontrollü laboratuvardır; uzaktan bilgisayar ele geçirme veya gerçek veriye erişim senaryosu değildir.
