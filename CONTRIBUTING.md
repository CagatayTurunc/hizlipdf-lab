# Ekip olarak geliştirme

## İlk kurulum

Depoyu klonladıktan sonra kök dizinde README'deki sanal ortam kurulumunu tamamlayın. LibreOffice ayrıca kurulmuş olmalıdır. `./start.sh` ile başlatın ve `http://127.0.0.1:8765` adresini açın. İlk denemede yalnızca uygulamanın ürettiği sentetik DOCX'i kullanın.

## İş akışı

1. Güncel `main` dalından küçük bir iş için yeni dal açın.
2. Tek bir davranışa odaklanın; README/ROADMAP durumunu gerçek uygulamayla eşleştirin.
3. `python -m unittest discover -s tests -v` çalıştırın. Atlanan Linux testini geçmiş gibi raporlamayın.
4. Açıklayıcı bir commit ve pull request oluşturun; ne değiştiğini ve nasıl doğrulandığını yazın.
5. Diğer ekip üyesi inceledikten sonra birleştirin.

## İş paylaşımı

- Arayüz/dönüşüm: RaporLab eklenti ekranı, gerçek paket kurulum deneyimi, DOCX analiz özeti ve PDF doğrulaması.
- Laboratuvar/izolasyon: Linux VM, bubblewrap profilleri, OS dosya gözlemi ve alıcı kanıtı.
- Ortak: Paket manifesti, olay sözleşmesi, tekrarlı deneyler ve sunum.

## Depoya eklenmeyecekler

Sanal ortam, `__pycache__`, çalışma dizinleri, gerçek belgeler, çalışma anahtarları ve canlı `config.json` dosyaları. Kanıt paylaşılacaksa önce hassas alanlar denetlenmeli; yalnızca sentetik veri ve anahtarsız sonuç paylaşılmalıdır. Depodaki `VERIFICATION.md` geçmişte yürütülmüş kontrollerin kaydıdır; güncel test sonucunun yerine geçmez.
