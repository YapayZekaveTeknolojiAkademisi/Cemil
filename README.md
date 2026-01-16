# Slack App Kurulum ve Yetkilendirme Kılavuzu - CEMIL

Botun çalışması için Slack Developer Portal üzerinde aşağıdaki ayarların yapılması gerekmektedir.

## 1. Uygulama Oluşturma
- https://api.slack.com/apps adresine gidin.
- "Create New App" -> "From an app manifest" (veya "From scratch") seçeneğini kullanın.
- Uygulamayı kuracağınız Workspace'i seçin.

## 2. Socket Mode (Önemli!)
Botun sunucuya (public IP) ihtiyaç duymadan çalışabilmesi için bunu açmalısınız.
- Sol menüden **Socket Mode**'a tıklayın.
- "Enable Socket Mode" anahtarını açın.
- Bir **App-Level Token** oluşturmanızı isteyecek.
  - Token Name: `Socket Token` (veya istediğiniz bir isim)
  - Scopes: `connections:write` (Otomatik eklenir)
  - **Oluşan Token'ı kopyalayın (`xapp-...`) ve `.env` dosyasındaki `SLACK_APP_TOKEN` alanına yapıştırın.**

## 3. Bot Token Scopes (Yetkiler)
Botun yapabileceklerini belirleyen izinler. Sol menüden **OAuth & Permissions** sayfasına gidin ve **Bot Token Scopes** altına şunları ekleyin:

| Scope | Ne İşe Yarar? |
| :--- | :--- |
| `chat:write` | Kanallara mesaj göndermek için (Günün sorusu, uyarılar). |
| `commands` | Slash komutları (`/kahve`) kullanmak için. |
| `mpim:write` | Birden fazla kişiyle Grup DM başlatmak için (Kahve eşleşmesi). |
| `im:write` | Tekil DM atmak için (Opsiyonel). |
| `users:read` | Kullanıcı bilgilerini okumak için. |

> **Not:** Scope ekledikten sonra sayfanın üstündeki **"Install to Workspace"** (veya Reinstall) butonuna basarak yetkileri onaylamayı unutmayın. Bu işlem size `xoxb-...` ile başlayan **Bot User OAuth Token**'ı verecek. Bunu `.env` dosyasındaki `SLACK_BOT_TOKEN` alanına yapıştırın.

## 4. Slash Commands (Komutlar)
Botun çalışması için Slack tarafında şu komutları oluşturun:
- `/kahve`: Kanala interaktif bir kahve daveti gönderir. Başka bir kullanıcı butonla eşleşebilir.
- `/my-id`: Slack ID'nizi gizli (ephemeral) mesaj olarak gösterir.
- `/my-department`: Veritabanındaki akademi/departman bilginizi gösterir.

---

### Özellikler Hakkında Detaylar
- **Günün Sorusu:** Her sabah saat 10:00'da belirlenen kanala (`scheduler.py` içindeki `CHANNEL_ID`) rastgele bir soru gönderilir.
- **İnteraktif Kahve:** `/kahve` yazan kişi için kanala bir davet düşer. Bir başkası "Ben Geliyorum!" dediğinde bot otomatik olarak bir Grup DM başlatır ve sohbeti ısıtacak bir "Buz Kırıcı" soru önerir.
- **Güvenli Bilgi:** `/my-id` ve `/my-department` komutlarının yanıtları sadece komutu yazan kişiye görünür.

---

### Özet Kontrol Listesi
1. [ ] **Socket Mode** açık ve `SLACK_APP_TOKEN` `.env` dosyasına eklendi mi?
2. [ ] **Bot Token Scopes** (chat:write, commands, vb.) eklendi ve App **Reinstall** edildi mi?
3. [ ] `SLACK_BOT_TOKEN` `.env` dosyasına eklendi mi?
4. [ ] `/kahve` komutu oluşturuldu mu?
