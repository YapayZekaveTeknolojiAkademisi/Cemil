"""
Topluluk yardımlaşma servisi.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from src.core.logger import logger
from src.core.exceptions import CemilBotError
from src.commands import ChatManager, ConversationManager, UserManager
from src.repositories import HelpRepository, UserRepository
from src.clients import CronClient, GroqClient


class HelpService:
    """
    Topluluk yardımlaşma isteklerini yöneten servis.
    """
    
    def __init__(
        self,
        chat_manager: ChatManager,
        conv_manager: ConversationManager,
        user_manager: UserManager,
        help_repo: HelpRepository,
        user_repo: UserRepository,
        groq_client: Optional[GroqClient] = None,
        cron_client: Optional[CronClient] = None
    ):
        self.chat = chat_manager
        self.conv = conv_manager
        self.user_manager = user_manager
        self.repo = help_repo
        self.user_repo = user_repo
        self.groq = groq_client
        self.cron_client = cron_client
    
    def _get_workspace_owner(self) -> Optional[str]:
        """Workspace owner veya admin kullanıcıyı bulur."""
        try:
            # Tüm kullanıcıları listele
            response = self.user_manager.list_users(limit=1000)
            if response.get("ok"):
                members = response.get("members", [])
                # Önce owner'ı bul
                for member in members:
                    if member.get("is_owner", False):
                        owner_id = member.get("id")
                        logger.info(f"[i] Workspace owner bulundu: {owner_id}")
                        return owner_id
                # Owner yoksa admin'i bul
                for member in members:
                    if member.get("is_admin", False):
                        admin_id = member.get("id")
                        logger.info(f"[i] Workspace admin bulundu: {admin_id}")
                        return admin_id
            logger.warning("[!] Workspace owner/admin bulunamadı")
            return None
        except Exception as e:
            logger.error(f"[X] Workspace owner bulunurken hata: {e}")
            return None
    
    async def create_help_request(
        self,
        requester_id: str,
        channel_id: str,
        topic: str,
        description: str
    ) -> str:
        """
        Yardım isteği oluşturur ve kanala block mesajı gönderir.
        
        Returns:
            help_id: Oluşturulan yardım isteğinin ID'si
        """
        try:
            # 0. Kullanıcıyı users tablosunda garanti altına al (foreign key için)
            try:
                user_record = self.user_repo.get_by_slack_id(requester_id)
                if not user_record:
                    # Slack'ten gerçek isim bilgisini almaya çalış
                    full_name = requester_id
                    try:
                        user_info = self.user_manager.get_user_info(requester_id)
                        full_name = user_info.get("real_name") or user_info.get("profile", {}).get("real_name") or requester_id
                    except Exception:
                        # Slack API'den bilgi alınamazsa, sadece Slack ID ile devam et
                        full_name = requester_id
                    
                    self.user_repo.create({
                        "slack_id": requester_id,
                        "full_name": full_name
                    })
                    logger.info(f"[i] HelpService: Kullanıcı users tablosuna eklendi: {requester_id} ({full_name})")
            except Exception as user_err:
                logger.warning(f"[!] HelpService: Kullanıcı kontrol/ekleme hatası: {user_err}")
            
            # 1. Veritabanına kaydet
            help_id = self.repo.create({
                "requester_id": requester_id,
                "topic": topic,
                "description": description,
                "channel_id": channel_id,
                "status": "open"
            })
            
            # 2. Kullanıcı bilgisini al
            user_data = self.user_repo.get_by_slack_id(requester_id)
            requester_name = user_data.get('full_name', requester_id) if user_data else requester_id
            
            logger.info(f"[>] Yardım isteği oluşturuldu | Kullanıcı: {requester_name} ({requester_id}) | Konu: {topic}")
            
            # 3. Yeni yardım kanalı oluştur
            channel_name = f"yardim-{help_id[:8]}"
            try:
                help_channel = self.conv.create_channel(
                    name=channel_name,
                    is_private=False
                )
                help_channel_id = help_channel["id"]
                logger.info(f"[+] Yardım kanalı oluşturuldu: #{channel_name} (ID: {help_channel_id})")
                
                # Akademi owner'ı bul
                owner_id = self._get_workspace_owner()
                
                # Kanalı davet et: owner + requester
                invite_users = [requester_id]
                if owner_id and owner_id != requester_id:
                    invite_users.append(owner_id)
                
                if invite_users:
                    try:
                        self.conv.invite_users(help_channel_id, invite_users)
                        logger.info(f"[+] Kullanıcılar kanala davet edildi: {invite_users}")
                    except Exception as e:
                        logger.warning(f"[!] Kullanıcılar davet edilemedi: {e}")
                
                # Kanal açılış mesajı gönder
                welcome_blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🆘 Yardım İsteği: {topic}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*<@{requester_id}>* yardım istiyor:\n\n"
                                f"*{description}*\n\n"
                                f"Bu kanal 10 dakika sonra otomatik olarak kapatılacak. "
                                f"Yardım etmek isteyenler 'Yardım Et' butonuna tıklayarak bu kanala katılabilir."
                            )
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"🆔 Yardım ID: `{help_id[:8]}...` | ⏰ Kanal 10 dakika sonra kapanacak"
                            }
                        ]
                    }
                ]
                
                # Mesajlar bot token ile gönderilir (bot olarak görünür)
                self.chat.post_message(
                    channel=help_channel_id,
                    text=f"🆘 Yardım İsteği: {topic}",
                    blocks=welcome_blocks
                )
                
                # Veritabanına help_channel_id kaydet
                self.repo.update(help_id, {"help_channel_id": help_channel_id})
                
                # 10 dakika sonra kanalı kapatmak için scheduled task ekle
                if self.cron_client:
                    try:
                        job_id = f"close_help_channel_{help_id}"
                        self.cron_client.add_once_job(
                            func=self._close_help_channel,
                            delay_minutes=10,
                            job_id=job_id,
                            args=[help_id, help_channel_id]
                        )
                        logger.info(f"[+] Kanal kapatma görevi planlandı: {job_id} (10 dakika sonra)")
                    except Exception as e:
                        logger.warning(f"[!] Kanal kapatma görevi planlanamadı: {e}")
                
            except Exception as e:
                logger.error(f"[X] Yardım kanalı oluşturulamadı: {e}")
                help_channel_id = None
            
            # 4. Block mesajı oluştur (pop-up butonu ile)
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🆘 Yardım İsteği: {topic}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*<@{requester_id}>* yardım istiyor:\n\n{description}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "💚 Kanala Katıl",
                                "emoji": True
                            },
                            "style": "primary",
                            "action_id": "help_join_channel",
                            "value": help_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📋 Detaylar",
                                "emoji": True
                            },
                            "action_id": "help_details",
                            "value": help_id
                        }
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"🆔 ID: `{help_id[:8]}...` | 📅 {datetime.now().strftime('%d.%m.%Y %H:%M')} | ⏰ 10 dakika sonra kapanacak"
                        }
                    ]
                }
            ]
            
            # 5. Mesajı kanala gönder
            response = self.chat.post_message(
                channel=channel_id,
                text=f"🆘 Yardım İsteği: {topic}",
                blocks=blocks
            )
            
            # 6. Message TS'yi kaydet (güncelleme için)
            if response.get("ok"):
                message_ts = response.get("ts")
                self.repo.update(help_id, {"message_ts": message_ts})
                logger.info(f"[+] Yardım isteği mesajı gönderildi | Kanal: {channel_id} | TS: {message_ts}")
            
            return help_id
            
        except Exception as e:
            logger.error(f"[X] HelpService.create_help_request hatası: {e}", exc_info=True)
            raise CemilBotError(f"Yardım isteği oluşturulamadı: {e}")
    
    async def join_help_channel(self, help_id: str, user_id: str) -> Dict[str, Any]:
        """
        Birisi 'Kanala Katıl' butonuna tıkladığında çağrılır.
        Kullanıcıyı yardım kanalına davet eder.
        
        Returns:
            Dict with success status and message
        """
        try:
            # 1. Yardım isteğini al
            help_request = self.repo.get(help_id)
            if not help_request:
                return {"success": False, "message": "❌ Yardım isteği bulunamadı."}
            
            # 2. Durum kontrolü
            if help_request["status"] == "closed":
                return {"success": False, "message": "❌ Bu yardım kanalı kapatılmış."}
            
            # 3. Yardım kanalı kontrolü
            help_channel_id = help_request.get("help_channel_id")
            if not help_channel_id:
                return {"success": False, "message": "❌ Yardım kanalı bulunamadı."}
            
            # 4. Kullanıcı bilgisini al
            user_data = self.user_repo.get_by_slack_id(user_id)
            user_name = user_data.get('full_name', user_id) if user_data else user_id
            
            logger.info(f"[>] Kanala katılma isteği | Kullanıcı: {user_name} ({user_id}) | Yardım ID: {help_id}")
            
            # 5. Kullanıcının zaten kanalda olup olmadığını kontrol et
            try:
                channel_members = self.conv.get_members(help_channel_id)
                if user_id in channel_members:
                    logger.info(f"[i] Kullanıcı zaten kanalda: {user_id} | Kanal: {help_channel_id}")
                    return {
                        "success": True,
                        "message": f"✅ Zaten kanaldasınız! <#{help_channel_id}> kanalına gidebilirsiniz.",
                        "channel_id": help_channel_id,
                        "already_joined": True
                    }
            except Exception as e:
                logger.debug(f"[i] Kanal üyeleri kontrol edilemedi, devam ediliyor: {e}")
            
            # 6. Kullanıcıyı kanala davet et
            try:
                self.conv.invite_users(help_channel_id, [user_id])
                logger.info(f"[+] Kullanıcı kanala davet edildi: {user_id} | Kanal: {help_channel_id}")
                
                # Yardım kanalına bilgilendirme mesajı gönder (sadece yeni katılımda)
                # Mesajlar bot token ile gönderilir (bot olarak görünür)
                self.chat.post_message(
                    channel=help_channel_id,
                    text=f"✅ <@{user_id}> kanala katıldı!",
                    blocks=[{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *<@{user_name}>* kanala katıldı ve yardım etmek istiyor! 🎉"
                        }
                    }]
                )
                
                return {
                    "success": True,
                    "message": f"✅ Kanala katıldınız! <#{help_channel_id}> kanalına gidebilirsiniz.",
                    "channel_id": help_channel_id,
                    "already_joined": False
                }
            except Exception as e:
                error_msg = str(e).lower()
                if "already_in_channel" in error_msg or "already_in team" in error_msg or "cant_invite_self" in error_msg:
                    logger.info(f"[i] Kullanıcı zaten kanalda (hata mesajından): {user_id}")
                    return {
                        "success": True,
                        "message": f"✅ Zaten kanaldasınız! <#{help_channel_id}> kanalına gidebilirsiniz.",
                        "channel_id": help_channel_id,
                        "already_joined": True
                    }
                else:
                    logger.warning(f"[!] Kullanıcı kanala davet edilemedi: {e}")
                    return {"success": False, "message": "❌ Kanala katılamadınız. Lütfen tekrar deneyin."}
            
        except Exception as e:
            logger.error(f"[X] HelpService.join_help_channel hatası: {e}", exc_info=True)
            return {"success": False, "message": "Kanala katılırken bir hata oluştu."}
    
    async def _close_help_channel(self, help_id: str, help_channel_id: str):
        """Yardım kanalını kapatır, mesajları analiz eder ve DM/Admin'e gönderir (10 dakika sonra otomatik çağrılır)."""
        try:
            logger.info(f"[>] Yardım kanalı kapatılıyor | Help ID: {help_id} | Kanal: {help_channel_id}")
            
            # 1. Yardım isteği bilgilerini al
            help_request = self.repo.get(help_id)
            if not help_request:
                logger.error(f"[X] Yardım isteği bulunamadı: {help_id}")
                return
            
            # 2. Sohbet geçmişini al
            messages = self.conv.get_history(channel_id=help_channel_id, limit=100)
            
            # 3. Mesajları temizle (bot mesajları hariç)
            user_messages = []
            participants = set()
            for msg in messages:
                if not msg.get("bot_id") and msg.get("type") == "message":
                    user_id = msg.get("user", "")
                    user_text = msg.get("text", "")
                    if user_id:
                        participants.add(user_id)
                        user_messages.append(f"<@{user_id}>: {user_text}")
            
            conversation_text = "\n".join(user_messages) if user_messages else "Konuşma yapılmadı."
            
            # 4. LLM ile Analiz ve Yorumlama
            summary = "Yardım kanalında herhangi bir konuşma gerçekleşmedi."
            detailed_analysis = summary
            
            if user_messages and self.groq:
                try:
                    # Kısa özet
                    summary_prompt = "Sana sunulan yardım kanalı sohbet geçmişini analiz et ve bir cümleyle özetle. Sadece Türkçe kullan."
                    summary = await self.groq.quick_ask(summary_prompt, f"Yardım Kanalı Sohbet Geçmişi:\n{conversation_text}")
                    
                    # Detaylı analiz
                    analysis_prompt = (
                        "Sen bir topluluk analiz asistanısın. Sana sunulan yardım kanalı sohbet geçmişini analiz et ve "
                        "şu konularda değerlendirme yap:\n"
                        "1. Yardım isteğinin çözülüp çözülmediği\n"
                        "2. Konuşmanın genel tonu ve atmosferi\n"
                        "3. Yardım eden kişilerin katkıları\n"
                        "4. Çözüm önerileri veya paylaşılan bilgiler\n"
                        "5. Öne çıkan noktalar veya önemli paylaşımlar\n\n"
                        "Kısa, net ve yapıcı bir analiz yap. Sadece Türkçe kullan."
                    )
                    detailed_analysis = await self.groq.quick_ask(
                        analysis_prompt,
                        f"Yardım Kanalı Sohbet Geçmişi:\n{conversation_text}"
                    )
                except Exception as e:
                    logger.error(f"[X] LLM analizi hatası: {e}")
                    detailed_analysis = summary
            
            # 5. Tüm katılımcılara DM gönder
            all_participants = list(participants)
            if help_request.get("requester_id") and help_request["requester_id"] not in all_participants:
                all_participants.append(help_request["requester_id"])
            if help_request.get("helper_id") and help_request["helper_id"] not in all_participants:
                all_participants.append(help_request["helper_id"])
            
            for participant_id in all_participants:
                try:
                    dm_channel = self.conv.open_conversation(users=[participant_id])
                    dm_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"🆘 *Yardım Kanalı Sonlandı*\n\n"
                                    f"*Konu:* {help_request['topic']}\n"
                                    f"*Kanal:* <#{help_channel_id}>\n\n"
                                    f"*📊 Sohbet Analizi:*\n{detailed_analysis}\n\n"
                                    f"Yeni bir yardım isteği için `/yardim-iste` komutunu kullanabilirsiniz!"
                                )
                            }
                        }
                    ]
                    self.chat.post_message(
                        channel=dm_channel["id"],
                        text="🆘 Yardım Kanalı Sonlandı",
                        blocks=dm_blocks
                    )
                    logger.info(f"[+] Analiz DM'i gönderildi | Kullanıcı: {participant_id}")
                except Exception as e:
                    logger.warning(f"[!] Kullanıcıya DM gönderilemedi ({participant_id}): {e}")
            
            # 6. Admin kanalına özet gönder (settings'den al)
            from src.core.settings import get_settings
            settings = get_settings()
            admin_channel = settings.admin_channel_id
            
            if admin_channel:
                admin_msg = (
                    f"[!] *YARDIM KANALI ÖZETİ RAPORU*\n"
                    f"== Kanal: {help_channel_id}\n"
                    f"== Yardım ID: {help_id[:8]}...\n"
                    f"== Konu: {help_request['topic']}\n"
                    f"== İstek Sahibi: <@{help_request['requester_id']}>\n"
                )
                if help_request.get("helper_id"):
                    admin_msg += f"== Yardım Eden: <@{help_request['helper_id']}>\n"
                admin_msg += (
                    f"== Katılımcılar: {len(all_participants)} kişi\n"
                    f"== Mesaj Sayısı: {len(user_messages)}\n"
                    f"== Kısa Özet: {summary}\n\n"
                    f"*📊 Detaylı Analiz:*\n{detailed_analysis}"
                )
                try:
                    self.chat.post_message(channel=admin_channel, text=admin_msg)
                    logger.info(f"[+] Admin kanalına özet gönderildi | Kanal: {admin_channel}")
                except Exception as e:
                    logger.warning(f"[!] Admin kanalına özet gönderilemedi: {e}")
            
            # 7. Kanal kapatıldı mesajı gönder (eğer hala açıksa)
            try:
                # Mesajlar bot token ile gönderilir (bot olarak görünür)
                self.chat.post_message(
                    channel=help_channel_id,
                    text="⏰ Bu yardım kanalı 10 dakika sonra otomatik olarak kapatıldı.",
                    blocks=[{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⏰ *Kanal Kapatıldı*\n\nBu yardım kanalı 10 dakika sonra otomatik olarak kapatıldı. "
                                    "Yardıma devam etmek isterseniz, yeni bir yardım isteği oluşturabilirsiniz."
                        }
                    }]
                )
            except Exception as e:
                logger.debug(f"[i] Kanal zaten kapatılmış, mesaj gönderilemedi: {e}")
            
            # 8. Kanalı arşivle (kapat)
            try:
                success = self.conv.archive_channel(help_channel_id)
                if success:
                    # Yardım isteğini kapatılmış olarak işaretle
                    self.repo.update(help_id, {"status": "closed"})
                    logger.info(f"[+] Yardım kanalı arşivlendi (kapatıldı) | Help ID: {help_id}")
                else:
                    logger.warning(f"[!] Yardım kanalı arşivlenemedi | Help ID: {help_id}")
            except Exception as e:
                logger.warning(f"[!] Yardım kanalı arşivlenirken hata: {e}")
                # Hata olsa bile durumu güncelle
                self.repo.update(help_id, {"status": "closed"})
                
        except Exception as e:
            logger.error(f"[X] Yardım kanalı kapatılırken hata: {e}", exc_info=True)
    
    def get_help_details(self, help_id: str) -> Dict[str, Any]:
        """Yardım isteği detaylarını getirir."""
        help_request = self.repo.get(help_id)
        if not help_request:
            return None
        
        return help_request
