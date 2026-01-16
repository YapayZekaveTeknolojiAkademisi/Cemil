# Cemil Bot

Merhabalar herkese! Ben Cemil, topluluk etkileşimini artırmak için buradayım! 🤖

---

## 🚀 Kurulum

### 1. Slack Uygulaması Oluşturma

1. [api.slack.com/apps](https://api.slack.com/apps) adresine gidin
2. **Create New App** → **From scratch** seçin
3. Uygulamayı kuracağınız Workspace'i seçin

### 2. Socket Mode Ayarları

1. Sol menüden **Socket Mode**'a tıklayın
2. **Enable Socket Mode** anahtarını açın
3. App-Level Token oluşturun:
   - Token Name: `Socket Token`
   - Scope: `connections:write`
4. Oluşan `xapp-...` token'ı `.env` dosyasına ekleyin:

```env
SLACK_APP_TOKEN=xapp-...
```

### 3. Bot Yetkileri

**OAuth & Permissions** sayfasından şu scope'ları ekleyin:

| Scope | Açıklama |
|-------|----------|
| `chat:write` | Kanallara mesaj gönderme |
| `commands` | Slash komutları kullanma |
| `mpim:write` | Grup DM başlatma |
| `im:write` | Tekil DM gönderme |
| `users:read` | Kullanıcı bilgilerini okuma |

**Install to Workspace** butonuna basın ve `xoxb-...` token'ı `.env` dosyasına ekleyin:

```env
SLACK_BOT_TOKEN=xoxb-...
```

### 4. Slash Komutlarını Oluşturma

**Slash Commands** sayfasından şu komutları ekleyin:

- `/kahve`
- `/oylama`
- `/save-me`
- `/my-id`
- `/my-department`

---

## 📖 Kullanım

### ☕ Kahve Molası

```
/kahve
```

Rastgele bir çalışma arkadaşınla eşleşmek için kullan. Birisi "Ben Geliyorum!" dediğinde otomatik grup DM başlar.

### 📊 Oylama (Admin)

```
/oylama
```

Ekip içi hızlı anketler başlat.

### 💾 Profil Kaydetme

```
/save-me
```

Departman ve iletişim bilgilerini kaydet.

### 🔍 Bilgi Sorgulama

```
/my-id
```

Slack ID'ni görüntüle (sadece sana görünür).

```
/my-department
```

Kayıtlı departman bilgini görüntüle (sadece sana görünür).

---

## ✅ Kurulum Kontrol Listesi

- [ ] Socket Mode açık ve `SLACK_APP_TOKEN` eklendi
- [ ] Bot Token Scopes eklendi ve App yeniden kuruldu
- [ ] `SLACK_BOT_TOKEN` eklendi
- [ ] Tüm slash komutları oluşturuldu
