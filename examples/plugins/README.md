# Kurulabilir laboratuvar paketleri

`hizlipdf.normal.zip` ve `hizlipdf.education.zip` dosyalarını RaporLab'ın **Eklentiler → ZIP paketi seç ve kur** akışında kullanabilirsiniz. Dosyalar `packages.build_package()` ile üretilmiştir. Aynı paketler çalışan uygulamanın katalog ekranından da indirilebilir.

Paketler yalnızca `manifest.json` ve `pipeline.json` taşır. Normal paket analiz/dönüşüm; eğitim paketi bunlara ek olarak sabit sentetik laboratuvar denemesini seçer. Paketlerin kurulması Linux izolasyonunun uygulandığı anlamına gelmez. Uygulama yalnızca kendi güvenilen katalog tanımlarıyla eşleşen içerikleri kabul eder.
