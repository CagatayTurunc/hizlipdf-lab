# 🛡️ HızlıPDF · Adli Bilişim & Çekirdek İzolasyon Laboratuvarı

> **Linux Üzerinde İşlevini Sürdüren Trojan Davranışlı Belge Analiz Eklentisinin Simülasyonu ve Çekirdek Seviyesinde Bubblewrap İzolasyon Mimarisi**

[![Linux](https://img.shields.io/badge/OS-Linux%20Kernel%206.8%2B%20%7C%20ARM64-blue?logo=linux)](https://github.com/CagatayTurunc/hizlipdf-lab)
[![Bubblewrap](https://img.shields.io/badge/Isolation-Bubblewrap%20Namespaces-green)](https://github.com/containers/bubblewrap)
[![MITRE ATT&CK](https://img.shields.io/badge/Security-MITRE%20ATT%26CK-red)](https://attack.mitre.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B%20%7C%203.12-yellow?logo=python)](https://python.org)
[![Forensics](https://img.shields.io/badge/Audit-SHA--256%20Cryptographic%20Forensics-purple)](#5-resmi-adli-bilişim-kanıt-raporu-forensic-audit-report)

Bu proje; modern ofis ve belge işleme yazılımlarında (Word, LibreOffice, bulut PDF dönüştürücüler) üçüncü parti eklentilerin oluşturduğu **Tedarik Zinciri (Supply Chain)** tehditlerini ve **Trojan (Truva Atı)** davranışlarını adli bilişim standartlarında simüle etmek; bu tehditleri Linux çekirdeği (Kernel) seviyesinde **Bubblewrap User Namespaces** teknolojisiyle sıfır ek yetkiyle (non-root) izole etmek amacıyla geliştirilmiş akademik bir siber güvenlik laboratuvarıdır.

---

## 🎯 Projenin Temel Senaryosu ve Tehdit Modeli

1. **Görünür Görev (Kullanıcının İstediği):** Kullanıcı bir `DOCX` belgesi yükler. Eklenti bu belgeyi analiz eder (kelime, tablo, başlık sayılarını çıkarır) ve geçerli bir `PDF` üretir.
2. **Gizli Görev (Trojan Davranışı):** Eklenti normal dönüşümü yaparken arka planda gizlice diski tarar; görev dışı şirket sırlarını (`Sirket_Butcesi_TEST.csv` ve `Kira_Sozlesmesi_TEST.txt`) okur ve yerel ağdaki Komuta Kontrol (C2) dinleyicisine (`POST /collect`) sızdırır.
3. **Çözüm (Çekirdek İzolasyonu):** Linux çekirdeğinin Mount, Network, PID ve IPC ad alanları kullanılarak eklenti hapsedilir. Sisteme yalnızca **~20 milisaniye** ek yükle veri sızıntısı **0 bayta** indirilir.

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

## 🔥 Projede Geliştirilen 5 Büyük Güvenlik & Adli Bilişim Yeteneği

Laboratuvar paneli, klasik web uygulamalarının çok ötesinde işletim sistemi çekirdeği ve adli bilişim derinliğine sahiptir:

### 1. ⚙️ Linux Çekirdek Sistem Çağrısı Telemetrisi (Kernel Syscall Audit)
* Uygulamanın beyanından bağımsız olarak, Linux çekirdeğinin sistem çağrıları `strace` ile denetlenir.
* Eklentinin diskteki dosyalara erişimi `openat()` ve ağ soketi istekleri `connect()` seviyesinde yakalanır.
* Dosya Tanımlayıcısı (FD = 3, FD = 5) seviyesinde `[İZİN VERİLDİ]` / `[ENGELLEME]` rozetleriyle koyu temalı terminal arayüzünde canlı olarak gösterilir.

### 2. 🛡️ MITRE ATT&CK® Tehdit Matrisi Entegrasyonu
* Simüle edilen zararlı davranışlar siber güvenlik dünyasının kurumsal standardı MITRE ATT&CK ile haritalanmıştır:
  * **`T1204.002`**: User Execution - Malicious File
  * **`T1059.006`**: Command & Scripting Interpreter: Python
  * **`T1005`**: Data from Local System (Veri Toplama)
  * **`T1041`**: Exfiltration Over C2 Channel (Veri Sızdırma)
* Deney profiline göre ihlaller kırmızı `İHLAL EDİLDİ`, korumalar yeşil `ENGELLENDİ` rozetleriyle gösterilir.

### 3. 📈 Tek Tıkla 4 Profil Otomatik Kıyaslama ve Gecikme (Overhead) Analizi
* Sol menüdeki **"📈 Karşılaştırma & Benchmark"** sekmesinden tek tıkla Profil A, B, C ve D ardışık olarak çalıştırılır.
* Sızan veri (122 B vs 0 B) ve gecikme overhead'i (ms) CSS çubuk grafiklerine dökülür.
* **Bilimsel Çıkarım:** Bubblewrap namespace izolasyonunun sisteme getirdiği ek maliyet yalnızca **~20 milisaniyedir (%0-3 overhead)**. Ağır sanal makineler veya Docker'a kıyasla neredeyse sıfır gecikmeyle tam güvenlik sağlanır.

### 4. 🌐 Canlı Ham Ağ Paketi ve Hex Dökümü İnceleyicisi (Wireshark Seviyesi)
* C2 dinleyicisine vuran paketler Wireshark / Burp Suite tarzı formatlı dökülür:
  * **Formatlı HTTP:** `POST /collect HTTP/1.1`, Host, User-Agent, Content-Length ve çalınan JSON verisi.
  * **Hex Dökümü (Hexdump):** 16 baytlık ofsetlerle çalınan şirket bütçesinin bellek seviyesindeki ikili (`00000000: 50 4f 53 54...`) gösterimi.
* Profil C ve D'de soketin çekirdek seviyesinde `connect() = -1 ENETUNREACH` ile reddedildiği paket düzeyinde ispatlanır.

### 5. 📑 Resmi Adli Bilişim Kanıt Raporu (Forensic Audit Report)
* Deney Gözlemcisi'ndeki **"📑 Adli Bilişim Raporu (.html / .pdf)"** butonu ile mahkeme ve jüri standartlarında resmi bir denetim tutanağı açılır.
* Linux çekirdek sürümü (`uname -r`), `aarch64` (ARM64) mimarisi ve zaman damgası yer alır.
* Girdi DOCX belgesinin, eklenti paketinin ve üretilen PDF'in **SHA-256 Kriptografik Hash Tablosu** mühürlenir.
* Üstteki butonla tek tıkla resmi **A4 PDF** çıktısı alınabilir.

---

## 📊 4 Güvenlik Profilinin Karşılaştırma Matrisi

| Profil | Profil Adı | Dosya İzni | Ağ İzni | Sızan Veri | İşlem Süresi | Güvenlik Skoru |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Profil A** | Geniş Yetki (İzolesiz) | AÇIK | AÇIK | **122 Bayt** | ~920 ms | **%0 (İHLAL)** |
| **Profil B** | Dosya Kısıtlı | KISITLI | AÇIK | **0 Bayt** | ~935 ms (+15ms) | **%50 (Kısmi)** |
| **Profil C** | Ağ Kısıtlı | AÇIK | KISITLI | **0 Bayt** | ~915 ms (+0ms) | **%50 (Kısmi)** |
| **Profil D** | Tam İzolasyon | KISITLI | KISITLI | **0 Bayt** | ~945 ms (+25ms) | **%100 (TAM KORUMA)** |

---

## 🧪 Laboratuvarda Adım Adım Deney Yapma Rehberi

1. **Eklentileri İnceleyin:** Sol menüden **"Eklentiler"** sekmesine gidin. `HızlıPDF · Normal referans` ve `HızlıPDF · Eğitim eklentisi (Trojan)` paketlerinin kurulu olduğunu görün.
2. **Saldırıyı Simüle Edin:** Sol menüden **"Belge dönüştür"** sekmesine dönün.
   - Örnek belgeyi seçin.
   - Eklenti olarak: `HızlıPDF · Eğitim eklentisi` seçin.
   - Profil olarak: `A · Geniş laboratuvar yetkisi` seçin ve **"PDF'ye dönüştür"**e basın.
3. **Adli Kanıtları İnceleyin:**
   - Sayfa otomatik olarak **"Deney gözlemcisi"**ne yönlenir.
   - Aşağı inip **"Ağ Trafik İnceleyicisi"**nde çalınan bütçe verisini ve **Hex Dökümünü** görün.
   - **Kernel Syscall** alanında `openat() = 3` (izin verildi) kayıtlarını inceleyin.
4. **İzolasyonu Devreye Sokun:** Aynı eklentiyi **Profil D (Tam Kısıtlı)** ile çalıştırın.
   - Sızan verinin **0 Bayt** olduğunu,
   - Ağın `connect() = -1 ENETUNREACH` ile engellendiğini,
   - Dosya erişiminin `ENOENT` ile kesildiğini görün!
5. **Otomatik Benchmark:** Sol menüden **"📈 Karşılaştırma & Benchmark"** sekmesine geçip tek tıkla 4 profili kıyaslayın.
6. **Resmi Rapor:** Deney gözlemcisinde sağ üstteki yeşil **"📑 Adli Bilişim Raporu (.html / .pdf)"** butonuna basarak resmi tutanağı inceleyin ve PDF olarak kaydedin!

---

## 📁 Proje Dokümantasyonu & Ek Kaynaklar

* 📄 **[PROJE_KAPSAMLI_RAPORU.pdf](PROJE_KAPSAMLI_RAPORU.pdf)** — Projenin baştan sona tüm detaylarını, yaşanan krizleri ve jüri savunma metinlerini içeren 4 sayfalık resmi PDF bitirme raporu.
* 🌐 **[PROJE_KAPSAMLI_RAPORU.html](PROJE_KAPSAMLI_RAPORU.html)** — Tarayıcıda açılabilen ve yazdırılabilen interaktif rapor versiyonu.
* 🏗️ **[ARCHITECTURE.md](ARCHITECTURE.md)** — Sistem mimarisi ve bileşenler arası veri akışı.

---
**Geliştirici:** Çağatay Turunç  
**Lisans:** MIT Academic Research License
