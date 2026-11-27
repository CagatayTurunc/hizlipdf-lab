# 🛡️ HızlıPDF · Adli Bilişim & Çekirdek İzolasyon Laboratuvarı

> **Linux Üzerinde İşlevini Sürdüren Trojan Davranışlı Belge Analiz Eklentisinin Simülasyonu ve Çekirdek Seviyesinde Bubblewrap İzolasyon Mimarisi**

[![Linux](https://img.shields.io/badge/OS-Linux%20Kernel%206.8%2B%20%7C%20ARM64-blue?logo=linux)](https://github.com/CagatayTurunc/hizlipdf-lab)
[![Bubblewrap](https://img.shields.io/badge/Isolation-Bubblewrap%20Namespaces-green)](https://github.com/containers/bubblewrap)
[![MITRE ATT&CK](https://img.shields.io/badge/Security-MITRE%20ATT%26CK-red)](https://attack.mitre.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B%20%7C%203.12-yellow?logo=python)](https://python.org)
[![Forensics](https://img.shields.io/badge/Audit-SHA--256%20Cryptographic%20Forensics-purple)](#5-yazdırılabilir-deney-raporu)

Bu proje; modern ofis ve belge işleme yazılımlarında (Word, LibreOffice, bulut PDF dönüştürücüler) üçüncü parti eklentilerin oluşturduğu **Tedarik Zinciri (Supply Chain)** tehditlerini ve **Trojan (Truva Atı)** davranışlarını adli bilişim standartlarında simüle etmek; bu tehditleri Linux çekirdeği (Kernel) seviyesinde **Bubblewrap User Namespaces** teknolojisiyle sıfır ek yetkiyle (non-root) izole etmek amacıyla geliştirilmiş akademik bir siber güvenlik laboratuvarıdır.

---

## 🎯 Projenin Temel Senaryosu ve Tehdit Modeli

1. **Görünür Görev (Kullanıcının İstediği):** Kullanıcı bir `DOCX` belgesi yükler. Eklenti bu belgeyi analiz eder (kelime, tablo, başlık sayılarını çıkarır) ve geçerli bir `PDF` üretir.
2. **Ek deney adımı:** Eğitim paketi iki sabit sentetik dosyayı okumayı ve içeriği yalnızca yerel laboratuvar alıcısına iletmeyi dener.
3. **Çekirdek izolasyonu:** Dört profil sentetik dosya bağlamalarını ve ağ ad alanını değiştirir. Deney, aynı belge işlenirken dosya açma ve alıcıya erişim sonuçlarını karşılaştırır.

---

## 🚀 Kendi Bilgisayarınızda Çalıştırma Talimatı (Hızlı Kurulum)

Projeyi kendi Linux (Ubuntu 22.04 / 24.04, Debian vb.) sisteminizde veya sanal makinenizde çalıştırmak için aşağıdaki adımları izleyin:

### 1. Sistem Gereksinimlerini Yükleyin
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libreoffice bubblewrap strace
```

> [!IMPORTANT]
> **Ubuntu 24.04 Kullananlar İçin Kritik Çekirdek Ayarı:**  
> Ubuntu 24.04 varsayılan olarak kısıtlı kullanıcıların namespace açmasını engeller. Bubblewrap'in izole alan oluşturabilmesi için şu komutu bir defa çalıştırın:
> ```bash
> sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
> ```

### 2. Depoyu Klonlayın ve Sanal Ortamı Kurun
```bash
git clone https://github.com/CagatayTurunc/hizlipdf-lab.git
cd hizlipdf-lab

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 3. Laboratuvar Sunucusunu Başlatın
```bash
./start.sh --port 8765
```

Tarayıcınızı açın ve adrese gidin:  
👉 **`http://127.0.0.1:8765`**

---

## Deney kayıtları ve ölçüm

### 1. Linux sistem çağrısı kayıtları

Linux'ta `strace` varsa panel, yalnızca iki sentetik dosya ve çalışmanın gerçek yerel alıcı adresiyle eşleşen `openat()` ve `connect()` kayıtlarını gösterir. Dosyanın açılması, işçinin bildirdiği içerik okumasından ayrı değerlendirilir. İlgili kayıt eksikse veya çalışma başarısızsa deney sonucu **Doğrulanmadı** olarak gösterilir.

### 2. MITRE ATT&CK® eşlemesi

Deneyin dosya gözlemleri **T1005**, yerel alıcıdaki sentetik içerik kabulü ve bağlantı gözlemleri **T1041** kapsamında gösterilir. Rozetler ilgili kaydın sonucunu yansıtır.

### 3. Dört profilli karşılaştırma

**Karşılaştırma & Benchmark** görünümü aynı DOCX ve eğitim paketiyle dört profilde birer ısınma ve beşer ölçüm yapar. Her tur başlangıç profili değişir. Geçerli PDF üreten çalışmalar için toplam süre, dönüşüm ve işçinin ek deney adımının medyanı, minimum–maksimum aralığı ve örneklem sayısı görünür. Başarısız turlar çalışma kayıtlarında kalır. Alıcı ölçümleri kabul kaydı veya deney öncesi ve sonrası sağlık kontrolüyle desteklenir. A ile D arasındaki medyan farkı, iki profilin toplam çalışma süresini karşılaştırır.

### 4. Alıcı tarafı HTTP kaydı

Alıcının kabul ettiği HTTP isteği, çalışma anahtarı çıkarılarak okunabilir biçimde yeniden oluşturulur. Hex dökümü bu görünümün ilk 512 baytını gösterir. Yerel alıcıya yönelik bağlantı hataları ayrı `strace` kayıtlarında görünür. Alıcıdaki sıfır kabul, tek başına ağ kısıtını doğrulamaya yetmez.

### 5. Yazdırılabilir deney raporu

Deney gözlemcisindeki **Adli Bilişim Raporu (.html / .pdf)** bağlantısı çalışma ortamını, dosya özetlerini, gözlemleri ve kabul kayıtlarını gösterir. Üstteki düğme tarayıcının A4 PDF çıktısını açar. Ölçüm kayıtları ayrıca JSON olarak indirilebilir.

## Profil yapılandırmaları

| Profil | Sentetik hedef dosyalar | Yerel ağ deneyi |
| :--- | :--- | :--- |
| **A · Geniş laboratuvar yetkisi** | Bağlanır | VM ağ ad alanını kullanır |
| **B · Dosya erişimi dar** | Bağlanmaz | VM ağ ad alanını kullanır |
| **C · Ağ bağlantısı kapalı** | Bağlanır | Ayrı ağ ad alanı |
| **D · Dosya ve ağ kısıtlı** | Bağlanmaz | Ayrı ağ ad alanı |

## Deneyi çalıştırma

1. **Eklentiler** ekranından eğitim paketini kurun.
2. **Belge dönüştür** ekranında örnek DOCX'i seçin ve Profil A altında PDF üretin.
3. **Deney gözlemcisi** ekranında alıcı tarafı HTTP kaydını ve sistem çağrılarını inceleyin.
4. Aynı dönüşümü Profil D'de çalıştırın. PDF durumunu, iki sentetik hedefe ilişkin dosya açma kayıtlarını ve yerel alıcıya bağlantı sonucunu karşılaştırın.
5. Tekrarlı ölçüm için **Karşılaştırma & Benchmark** sekmesini açın. Rapor bağlantıları her profilin çalışma kayıtlarında bulunur.

---

## 📁 Proje Dokümantasyonu & Ek Kaynaklar

* 📄 **[PROJE_KAPSAMLI_RAPORU.pdf](PROJE_KAPSAMLI_RAPORU.pdf)** — Projenin baştan sona tüm detaylarını, yaşanan krizleri ve jüri savunma metinlerini içeren PDF proje raporu ve deney yöntemi.
* 🌐 **[PROJE_KAPSAMLI_RAPORU.html](PROJE_KAPSAMLI_RAPORU.html)** — Tarayıcıda açılabilen ve yazdırılabilen interaktif rapor versiyonu.
* 🏗️ **[ARCHITECTURE.md](ARCHITECTURE.md)** — Sistem mimarisi ve bileşenler arası veri akışı.

---
**Geliştirici:** Çağatay Turunç  
**Lisans:** MIT Academic Research License
