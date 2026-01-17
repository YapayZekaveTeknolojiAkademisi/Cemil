#!/usr/bin/env python3
"""
Cemil Bot - Topluluk Etkileşim Asistanı
Ana bot dosyası: Tüm servislerin entegrasyonu ve slash komutları
"""

import os
import asyncio
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# --- Core & Clients ---
from src.core.logger import logger
from src.clients import (
    DatabaseClient,
    GroqClient,
    CronClient,
    VectorClient,
    SMTPClient
)

# --- Commands (Slack API Wrappers) ---
from src.commands import (
    ChatManager,
    ConversationManager,
    UserManager
)

# --- Repositories ---
from src.repositories import (
    UserRepository,
    MatchRepository,
    PollRepository,
    VoteRepository,
    FeedbackRepository
)

# --- Services ---
from src.services import (
    CoffeeMatchService,
    VotingService,
    BirthdayService,
    FeedbackService,
    KnowledgeService
)

# ============================================================================
# KONFIGÜRASYON
# ============================================================================

load_dotenv()

# Slack App Başlatma - Token kontrolü
slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
if not slack_bot_token:
    raise ValueError("SLACK_BOT_TOKEN environment variable is required!")

app = App(token=slack_bot_token)

# ============================================================================
# CLIENT İLKLENDİRME (Singleton Pattern)
# ============================================================================

logger.info("[i] Client'lar ilklendiriliyor...")
db_client = DatabaseClient()
groq_client = GroqClient()
cron_client = CronClient()
vector_client = VectorClient()
smtp_client = SMTPClient()
logger.info("[+] Client'lar hazır.")

# ============================================================================
# COMMAND MANAGER İLKLENDİRME
# ============================================================================

logger.info("[i] Command Manager'lar ilklendiriliyor...")
chat_manager = ChatManager(app.client)
conv_manager = ConversationManager(app.client)
user_manager = UserManager(app.client)
logger.info("[+] Command Manager'lar hazır.")

# ============================================================================
# REPOSITORY İLKLENDİRME
# ============================================================================

logger.info("[i] Repository'ler ilklendiriliyor...")
user_repo = UserRepository(db_client)
match_repo = MatchRepository(db_client)
poll_repo = PollRepository(db_client)
vote_repo = VoteRepository(db_client)
feedback_repo = FeedbackRepository(db_client)
logger.info("[+] Repository'ler hazır.")

# ============================================================================
# SERVİS İLKLENDİRME
# ============================================================================

logger.info("[i] Servisler ilklendiriliyor...")
coffee_service = CoffeeMatchService(
    chat_manager, conv_manager, groq_client, cron_client, match_repo
)
voting_service = VotingService(
    chat_manager, poll_repo, vote_repo, cron_client
)
birthday_service = BirthdayService(
    chat_manager, user_repo, cron_client
)
feedback_service = FeedbackService(
    chat_manager, smtp_client, feedback_repo
)
knowledge_service = KnowledgeService(
    vector_client, groq_client
)
logger.info("[+] Servisler hazır.")

# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

def is_admin(user_id: str) -> bool:
    """Kullanıcının admin olup olmadığını kontrol eder."""
    try:
        res = app.client.users_info(user=user_id)
        if res["ok"]:
            user = res["user"]
            return user.get("is_admin", False) or user.get("is_owner", False)
    except Exception as e:
        logger.error(f"[X] Yetki kontrolü hatası: {e}")
    return False

# ============================================================================
# SLASH KOMUTLARI
# ============================================================================

# --- 1. Kahve Eşleşmesi ---
@app.command("/kahve")
def handle_coffee_command(ack, body):
    """Kahve eşleşmesi isteği gönderir (Bekleme Havuzu Sistemi)."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] /kahve komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id}")
    
    async def process_coffee_request():
        try:
            response_msg = await coffee_service.request_coffee(user_id, channel_id, user_name)
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=response_msg
            )
        except Exception as e:
            logger.error(f"[X] Kahve isteği hatası | Kullanıcı: {user_name} ({user_id}) | Hata: {e}")
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="Kahve makinesinde ufak bir arıza var sanırım ☕😅 Lütfen birazdan tekrar dene."
            )
    
    asyncio.run(process_coffee_request())

# --- Kahve Eşleşmesi Action Handler (Eski sistem uyumluluğu için) ---
@app.action("join_coffee")
def handle_join_coffee(ack, body):
    """
    Eski sistem uyumluluğu için join_coffee action handler.
    Yeni sistemde kahve eşleşmesi otomatik bekleme havuzu ile çalışır.
    """
    ack()
    user_id = body["user"]["id"]  # Tıklayan kişi
    channel_id = body["channel"]["id"]
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] join_coffee action tetiklendi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id}")
    
    # Yeni sistemde kahve eşleşmesi için /kahve komutunu kullanmasını söyle
    chat_manager.post_ephemeral(
        channel=channel_id,
        user=user_id,
        text="☕ Bu buton eski sistem için. Yeni kahve eşleşmesi için `/kahve` komutunu kullanabilirsiniz!"
    )

# --- 2. Oylama Sistemi ---
@app.command("/oylama")
def handle_poll_command(ack, body):
    """Yeni bir oylama başlatır (Sadece adminler)."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    text = body.get("text", "").strip()
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] /oylama komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id} | Parametreler: {text[:50]}...")
    
    if not is_admin(user_id):
        logger.warning(f"[!] Yetkisiz oylama denemesi | Kullanıcı: {user_name} ({user_id})")
        chat_manager.post_ephemeral(
            channel=channel_id, 
            user=user_id, 
            text="🚫 Bu komutu sadece adminler kullanabilir."
        )
        return
    
    try:
        # Format: /oylama 10 Bugün ne yiyelim? | Kebap | Pizza
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            raise ValueError("Eksik parametre")
        
        minutes = int(parts[0])
        content_parts = parts[1].split("|")
        
        if len(content_parts) < 3:
            raise ValueError("En az iki seçenek gerekli")
        
        topic = content_parts[0].strip()
        options = [opt.strip() for opt in content_parts[1:]]
        
        # Async servisi çağır - SYNC WRAPPER KULLANILIYOR
        asyncio.run(
            voting_service.create_poll(
                channel_id, topic, options, user_id, 
                allow_multiple=False, duration_minutes=minutes
            )
        )
        logger.info(f"[?] OYLAMA BAŞLATILDI | Kullanıcı: {user_name} ({user_id}) | Konu: {topic} | Süre: {minutes}dk | Seçenekler: {len(options)} adet")
        
    except ValueError as ve:
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=f"Eyvah, oylama formatı biraz karıştı! 📝 Şöyle dener misin:\n`/oylama [Dakika] [Konu] | Seçenek 1 | Seçenek 2`"
        )
    except Exception as e:
        logger.error(f"[X] Oylama başlatma hatası: {e}")

@app.action("poll_vote_0")
@app.action("poll_vote_1")
@app.action("poll_vote_2")
@app.action("poll_vote_3")
@app.action("poll_vote_4")
def handle_poll_vote(ack, body):
    """Oylama butonlarına tıklamayı işler."""
    ack()
    user_id = body["user"]["id"]
    action_id = body["actions"][0]["action_id"]
    value = body["actions"][0]["value"]
    channel_id = body["channel"]["id"]
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    # value formatı: vote_{poll_id}_{option_index}
    parts = value.split("_")
    if len(parts) != 3:
        return
    
    poll_id = parts[1]
    option_index = int(parts[2])
    
    logger.info(f"[>] OY VERİLDİ | Kullanıcı: {user_name} ({user_id}) | Oylama ID: {poll_id} | Seçenek: {option_index}")
    
    result = voting_service.cast_vote(poll_id, user_id, option_index)
    
    if result.get("success"):
        logger.info(f"[+] OY KAYDEDİLDİ | Kullanıcı: {user_name} ({user_id}) | Oylama ID: {poll_id} | Seçenek: {option_index}")
    else:
        logger.warning(f"[!] OY KAYDEDİLEMEDİ | Kullanıcı: {user_name} ({user_id}) | Oylama ID: {poll_id} | Sebep: {result.get('message', 'Bilinmiyor')}")
    
    chat_manager.post_ephemeral(
        channel=channel_id,
        user=user_id,
        text=result["message"]
    )

# --- 3. Geri Bildirim ---
@app.command("/geri-bildirim")
def handle_feedback_command(ack, body):
    """Anonim geri bildirim gönderir."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    text = body.get("text", "").strip()
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] /geri-bildirim komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id}")
    
    if not text:
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text="🤔 Hangi konuda geri bildirim vermek istersin? Örnek: `/geri-bildirim genel Harika bir topluluk!`"
        )
        return
    
    # Format: /geri-bildirim [kategori] [mesaj]
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        category = "general"
        content = parts[0]
    else:
        category = parts[0]
        content = parts[1]
    
    asyncio.run(feedback_service.submit_feedback(content, category))
    
    chat_manager.post_ephemeral(
        channel=channel_id,
        user=user_id,
        text="✅ Geri bildiriminiz anonim olarak iletildi. Teşekkürler!"
    )
    logger.info(f"[+] GERİ BİLDİRİM ALINDI | Kullanıcı: {user_name} ({user_id}) | Kategori: {category} | Uzunluk: {len(content)} karakter")

# --- 4. Bilgi Küpü (RAG) ---
@app.command("/sor")
def handle_ask_command(ack, body):
    """Bilgi küpünden soru sorar."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    question = body.get("text", "").strip()
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] /sor komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id} | Soru: {question[:100]}...")
    
    if not question:
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text="🤔 Neyi merak ediyorsun? Örnek: `/sor Mentorluk başvuruları ne zaman?`"
        )
        return
    
    chat_manager.post_ephemeral(
        channel=channel_id,
        user=user_id,
        text="🔍 Bilgi küpümü tarıyorum, lütfen bekleyin..."
    )
    
    async def ask_and_respond():
        answer = await knowledge_service.ask_question(question, user_id)
        logger.info(f"[+] SORU CEVAPLANDI | Kullanıcı: {user_name} ({user_id}) | Soru: {question[:50]}... | Cevap uzunluğu: {len(answer)} karakter")
        # Cevabı sadece soran kişiye göster (ephemeral)
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=f"*Soru:* {question}\n\n{answer}"
        )
    
    asyncio.run(ask_and_respond())

@app.command("/cemil-indeksle")
def handle_reindex_command(ack, body):
    """Bilgi küpünü yeniden indeksler (Admin)."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    
    # Kullanıcı bilgisini al
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        user_name = user_data.get('full_name', user_id) if user_data else user_id
    except:
        user_name = user_id
    
    logger.info(f"[>] /cemil-indeksle komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id}")
    
    if not is_admin(user_id):
        logger.warning(f"[!] Yetkisiz indeksleme denemesi | Kullanıcı: {user_name} ({user_id})")
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text="🚫 Bu komutu sadece adminler kullanabilir."
        )
        return
    
    chat_manager.post_ephemeral(
        channel=channel_id,
        user=user_id,
        text="⚙️ Bilgi küpü yeniden taranıyor..."
    )
    
    async def reindex_and_notify():
        await knowledge_service.process_knowledge_base()
        logger.info(f"[+] BİLGİ KÜPÜ YENİDEN İNDEKLENDİ | Kullanıcı: {user_name} ({user_id})")
        chat_manager.post_message(
            channel=channel_id,
            text=f"✅ <@{user_id}> Bilgi küpü güncellendi! Cemil artık en güncel dökümanları biliyor."
        )
    
    asyncio.run(reindex_and_notify())

# --- 5. Profil Görüntüleme ---
@app.command("/profilim")
def handle_profile_command(ack, body):
    """Kullanıcının kendi kayıtlı bilgilerini gösterir."""
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]
    
    logger.info(f"[>] /profilim komutu geldi | Kullanıcı: {user_id} | Kanal: {channel_id}")
    
    try:
        user_data = user_repo.get_by_slack_id(user_id)
        
        if not user_data:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="henüz sistemde kaydın bulunmuyor. � Lütfen yöneticinle iletişime geç."
            )
            return

        # Profil Kartı Oluştur (orta isim varsa dahil et)
        first_name = user_data.get('first_name', '')
        middle_name = user_data.get('middle_name', '')
        surname = user_data.get('surname', '')
        
        if middle_name:
            display_name = f"{first_name} {middle_name} {surname}".strip()
        else:
            display_name = f"{first_name} {surname}".strip()
        
        if not display_name:
            display_name = user_data.get('full_name', 'Bilinmiyor')
        
        text = (
            f"👤 *KİMLİK KARTI*\n"
            f"------------------\n"
            f"*Ad Soyad:* {display_name}\n"
            f"*Cohort:* {user_data.get('cohort', 'Belirtilmemiş')}\n"
            f"*Doğum Tarihi:* {user_data.get('birthday', 'Yok')}\n"
            f"------------------"
        )
        
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=text
        )
        logger.info(f"[+] Profil görüntülendi | Kullanıcı: {user_data.get('full_name', user_id)} ({user_id}) | Cohort: {user_data.get('cohort', 'Yok')}")
        
    except Exception as e:
        logger.error(f"[X] Profil görüntüleme hatası | Kullanıcı: {user_id} | Hata: {e}")
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text="Profil bilgilerine ulaşırken bir sorun yaşadım. 🤕"
        )

# ============================================================================
# GLOBAL HATA YÖNETİMİ
# ============================================================================

@app.error
def global_error_handler(error, body, logger):
    """Tüm beklenmedik hataları yakalar ve loglar."""
    user_id = body.get("user", {}).get("id") or body.get("user_id", "Bilinmiyor")
    channel_id = body.get("channel", {}).get("id") or body.get("channel_id")
    trigger = body.get("command") or body.get("action_id") or "N/A"
    
    logger.error(f"[X] GLOBAL HATA - Kullanıcı: {user_id} - Tetikleyici: {trigger} - Hata: {error}")
    
    # Kullanıcıya bilgi ver (Eğer kanal bilgisi varsa)
    if channel_id and user_id != "Bilinmiyor":
        try:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="Şu an küçük bir teknik aksaklık yaşıyorum, biraz başım döndü. 🤕 Lütfen birkaç dakika sonra tekrar dener misin?"
            )
        except Exception:
            pass # Hata mesajı gönderirken hata oluşursa yut

# ============================================================================
# BOT BAŞLATMA
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("           CEMIL BOT - BAŞLATMA SIRASI")
    print("="*60 + "\n")
    
    # 1. Veritabanı İlklendirme
    logger.info("[>] Veritabanı kontrol ediliyor...")
    db_client.init_db()

    # --- CSV Veri İçe Aktarma Kontrolü ---
    import sys
    
    # Klasörlerin varlığını kontrol et
    os.makedirs("data", exist_ok=True)
    os.makedirs("knowledge_base", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    CSV_PATH = "data/initial_users.csv"
    
    if not os.path.exists(CSV_PATH):
        # Şablon dosya oluştur
        print(f"\n[i] '{CSV_PATH}' dosyası bulunamadı. Şablon oluşturuluyor...")
        try:
            with open(CSV_PATH, 'w', encoding='utf-8') as f:
                f.write("Slack ID,First Name,Surname,Full Name,Birthday,Cohort\n")
                f.write("U12345,Ahmet,Yilmaz,Ahmet Yilmaz,01.01.1990,Yapay Zeka\n")
            print(f"[+] Şablon oluşturuldu: {CSV_PATH}")
            print(f"[i] Not: Şablon içinde örnek veri bulunmaktadır.")
            choice = input("Bu şablonu şimdi kullanmak ister misiniz? (e/h): ").lower().strip()
            
            if choice == 'e':
                print("[i] Veriler işleniyor...")
                try:
                    count = user_repo.import_from_csv(CSV_PATH)
                    print(f"[+] Başarılı! {count} kullanıcı eklendi.")
                except Exception as e:
                    logger.error(f"[X] Import hatası: {e}")
                    print("Hata oluştu, logları kontrol edin.")
            else:
                print("[i] Şablon atlandı. Dosyayı doldurup botu yeniden başlattığınızda kullanabilirsiniz.")
        except Exception as e:
            logger.error(f"Şablon oluşturma hatası: {e}")
    else:
        # Dosya var, kullanıp kullanmayacağını sor
        print(f"\n[?] '{CSV_PATH}' dosyası bulundu.")
        choice = input("Bu CSV dosyasındaki verileri kullanmak ister misiniz? (e/h): ").lower().strip()
        
        if choice == 'e':
            print("[i] Veriler işleniyor...")
            try:
                count = user_repo.import_from_csv(CSV_PATH)
                print(f"[+] Başarılı! {count} kullanıcı eklendi.")
            except Exception as e:
                logger.error(f"[X] Import hatası: {e}")
                print("Hata oluştu, logları kontrol edin.")
        else:
            print("[i] CSV dosyası atlandı, mevcut veritabanı ile devam ediliyor.")
    # -------------------------------------
    
    # 2. Cron Başlatma
    logger.info("[>] Zamanlayıcı başlatılıyor...")
    cron_client.start()
    
    # 3. Birthday Scheduler Ekleme
    logger.info("[>] Günlük doğum günü kontrolü planlanıyor...")
    birthday_service.schedule_daily_check(hour=9, minute=0)
    
    # 4. Vektör Veritabanı Kontrolü
    VECTOR_INDEX_PATH = "data/vector_store.index"
    VECTOR_PKL_PATH = "data/vector_store.pkl"
    
    vector_index_exists = os.path.exists(VECTOR_INDEX_PATH) and os.path.exists(VECTOR_PKL_PATH)
    
    if vector_index_exists:
        # Mevcut veriler var
        print(f"\n[?] Vektör veritabanı bulundu (mevcut veriler: {len(vector_client.documents) if vector_client.documents else 0} parça).")
        choice = input("Vektör veritabanını yeniden oluşturmak ister misiniz? (e/h): ").lower().strip()
        
        if choice == 'e':
            print("[i] Vektör veritabanı yeniden oluşturuluyor...")
            logger.info("[>] Bilgi Küpü indeksleniyor...")
            asyncio.run(knowledge_service.process_knowledge_base())
            print("[+] Vektör veritabanı başarıyla güncellendi.")
        else:
            print("[i] Mevcut vektör veritabanı kullanılıyor.")
            logger.info("[i] Mevcut vektör veritabanı yüklendi.")
    else:
        # Vektör veritabanı yok, oluştur
        print(f"\n[i] Vektör veritabanı bulunamadı. Oluşturuluyor...")
        logger.info("[>] Bilgi Küpü indeksleniyor...")
        asyncio.run(knowledge_service.process_knowledge_base())
        print("[+] Vektör veritabanı başarıyla oluşturuldu.")
    
    # 5. Slack Socket Mode Başlatma
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        logger.error("[X] SLACK_APP_TOKEN bulunamadı!")
        exit(1)
    
    logger.info("[>] Slack Socket Mode başlatılıyor...")
    
    # Başlangıç Mesajı Kontrolü
    startup_channel = os.environ.get("SLACK_STARTUP_CHANNEL")
    github_repo = os.environ.get("GITHUB_REPO")
    
    if startup_channel:
        print(f"\n[?] Başlangıç kanalı bulundu: {startup_channel}")
        choice = input("Başlangıç mesajı (welcome) gönderilsin mi? (e/h): ").lower().strip()
        
        if choice == 'e':
            try:
                startup_text = (
                    "👋 *Merhabalar! Ben Cemil, göreve hazırım!* ☀️\n\n"
                    "Topluluk etkileşimini artırmak için buradayım. İşte güncel yeteneklerim:\n\n"
                    "☕ *`/kahve`* - Kahve molası eşleşmesi için havuza katıl.\n"
                    "🗳️ *`/oylama`* - Hızlı anketler başlat (Admin).\n"
                    "📝 *`/geri-bildirim`* - Yönetime anonim mesaj gönder.\n"
                    "🧠 *`/sor`* - Dökümanlara ve bilgi küpüne soru sor.\n"
                    "👤 *`/profilim`* - Kayıtlı bilgilerini görüntüle.\n\n"
                    "Güzel bir gün dilerim! ✨"
                )
                
                if github_repo and "SİZİN_KULLANICI_ADINIZ" not in github_repo:
                    startup_text += f"\n\n📚 *Kaynaklar:*\n"
                    startup_text += f"• <{github_repo}/blob/main/README.md|Kullanım Kılavuzu>\n"
                    startup_text += f"• <{github_repo}/blob/main/CHANGELOG.md|Neler Yeni?>\n"
                    startup_text += f"• <{github_repo}/blob/main/CONTRIBUTING.md|Katkıda Bulun>"

                startup_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": startup_text + "\n<!channel>"
                        }
                    }
                ]

                chat_manager.post_message(
                    channel=startup_channel,
                    text=startup_text,
                    blocks=startup_blocks
                )
                logger.info(f"[+] Başlangıç mesajı gönderildi: {startup_channel}")
                print(f"[+] Başlangıç mesajı gönderildi: {startup_channel}")
            except Exception as e:
                logger.error(f"[X] Başlangıç mesajı gönderilemedi: {e}")
                print(f"[X] Başlangıç mesajı gönderilemedi: {e}")
        else:
            print("[i] Başlangıç mesajı atlandı.")
            logger.info("[i] Başlangıç mesajı kullanıcı tarafından atlandı.")
    else:
        print("[i] SLACK_STARTUP_CHANNEL tanımlı değil, başlangıç mesajı gönderilmeyecek.")
    
    print("\n" + "="*60)
    print("           BOT HAZIR - BAĞLANTI KURULUYOR")
    print("="*60 + "\n")
    
    handler = SocketModeHandler(app, app_token)
    handler.start()
