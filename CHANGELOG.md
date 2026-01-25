# Değişiklik Günlüğü (Changelog)

Projede yapılan tüm önemli değişiklikler bu dosyada belgelenecektir.

## [1.0.1] - 2026-01-22

### 🐛 Hata Düzeltmeleri (Bug Fixes)
- **Challenge Değerlendirme Kanalı**: Değerlendirme kanalından ayrılan kullanıcıların `challenge_evaluators` tablosundan kaydı silinmiyordu. Bu durum değerlendirici sayısının yanlış hesaplanmasına ve maksimum 3 değerlendirici limitinin erken dolmasına neden oluyordu.
  - `member_left_channel` event handler'ı eklendi
  - `ChallengeEvaluationRepository.get_by_channel_id()` metodu eklendi
  - Kullanıcı kanaldan ayrıldığında değerlendirici kaydı otomatik olarak siliniyor
  - README.md'de Slack App ayarlarına `member_left_channel` event'i eklendi


## [1.0.0] - 2026-01-17

### 🚀 Yeni Özellikler (Features)
- **Ana Bot Entegrasyonu**: Tüm servisler (RAG, Voting, Birthday, Feedback, Coffee) tek bir bot yapısında toplandı.
- **Akıllı Kahve Eşleşmesi**: 
  - Bekleme havuzu (Waiting Pool) sistemi eklendi.
  - Spam koruması için Rate Limiting (5dk) getirildi.
  - 5 dakika içinde eşleşme olmazsa otomatik iptal mekanizması kuruldu.
- **Gelişmiş RAG (Bilgi Küpü)**:
  - `.docx`, `.md`, `.xlsx`, `.csv` dosya formatları için destek eklendi.
  - Cevaplara kaynak (source) gösterme özelliği eklendi.
  - Vektör mesafe eşiği (threshold) ile halüsinasyon önleme sistemi kuruldu.
- **Oylama Sistemi İyileştirmeleri**:
  - "Toggle" özelliği: Aynı seçeneğe tekrar basınca oy geri alma.
  - "Switch" özelliği: Tekli seçimde farklı seçeneğe basınca oyu değiştirme.
- **Kullanıcı Yönetimi**:
  - Bot başlangıcında CSV dosyasından toplu kullanıcı yükleme desteği eklendi.
  - `/kayit` komutu ile kullanıcıların kendi profillerini güncellemesi sağlandı.
- **Geri Bildirim Sistemi**: Anonim geri bildirimlerin e-posta veya Slack DM yoluyla iletilmesi eklendi.
- **Doğum Günü Kutlaması**: Her sabah 09:00'da otomatik kontrol ve kutlama sistemi eklendi.

### 🛠️ İyileştirmeler ve Düzenlemeler (Improvements)
- **Hata Mesajları**: Kullanıcıya dönen hata mesajları daha samimi ve "Cemil" kişiliğine uygun hale getirildi.
- **Güvenlik**: Kayıt ve güncelleme işlemlerinde `user_id` doğrulaması eklendi.
- **Loglama**: Renkli ve detaylı loglama altyapısı kuruldu.
- **Veritabanı**: SQLite mimarisi Repository desenine (Repository Pattern) taşındı.
- **Mimari**: Tüm client'lar (DB, Groq, Slack) Singleton deseni ile thread-safe hale getirildi.

### 🧹 Temizlik ve Bakım (Chores)
- `database.py`, `scheduler.py` gibi legacy dosyalar kaldırıldı.
- `.gitignore` dosyası güncellendi (`data/`, `logs/`, `knowledge_base/` eklendi).
- `.env.example` güncel bağımlılıklarla yenilendi.
- `README.md` detaylı kullanım talimatlarıyla baştan yazıldı.

---
*Bu sürüm, Cemil Bot'un ilk tam kararlı sürümüdür.*
