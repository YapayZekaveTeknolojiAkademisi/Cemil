import os
import asyncio
from typing import List, Optional
from src.core.logger import logger
from src.core.exceptions import CemilBotError
from src.commands import ChatManager, ConversationManager
from src.clients import GroqClient, CronClient
from src.repositories import MatchRepository

class CoffeeMatchService:
    """
    Kullanıcılar arasında kahve eşleşmesi ve moderasyonunu yöneten servis.
    Yalnızca ASCII karakterler kullanır.
    """

    def __init__(
        self, 
        chat_manager: ChatManager, 
        conv_manager: ConversationManager, 
        groq_client: GroqClient, 
        cron_client: CronClient,
        match_repo: MatchRepository
    ):
        self.chat = chat_manager
        self.conv = conv_manager
        self.groq = groq_client
        self.cron = cron_client
        self.match_repo = match_repo
        self.admin_channel = os.environ.get("ADMIN_CHANNEL_ID")

    async def start_match(self, user_id1: str, user_id2: str):
        """
        İki kullanıcıyı eşleştirir, grup açar ve buzları eritir.
        Bilgileri veritabanına kaydeder.
        """
        try:
            logger.info(f"[>] Kahve eşleşmesi başlatılıyor: {user_id1} & {user_id2}")
            
            # 1. Grup konuşması aç
            channel = self.conv.open_conversation(users=[user_id1, user_id2])
            channel_id = channel["id"]
            logger.info(f"[+] Özel grup oluşturuldu: {channel_id}")

            # 2. Veritabanına kaydet
            match_id = self.match_repo.create({
                "channel_id": channel_id,
                "user1_id": user_id1,
                "user2_id": user_id2,
                "status": "active"
            })

            # 3. Ice Breaker (Buzkıran) mesajı oluştur
            system_prompt = (
                "Sen Cemil'sin, bir topluluk asistanısın. Görevin birbiriyle eşleşen iki iş arkadaşı için "
                "kısa, eğlenceli ve samimi bir tanışma mesajı yazmak. "
                "ÖNEMLİ: Hiçbir emoji veya ASCII olmayan karakter kullanma. "
                "Sadece ASCII (Harfler, sayılar ve [i], [c], [>], == gibi işaretler) kullan."
            )
            user_prompt = f"Şu iki kullanıcı az önce kahve için eşleşti: <@{user_id1}> ve <@{user_id2}>. Onlara güzel bir selam ver."
            
            ice_breaker = await self.groq.quick_ask(system_prompt, user_prompt)

            # 4. Mesajı kanala gönder (ASCII Simgeleriyle)
            self.chat.post_message(
                channel=channel_id,
                text=ice_breaker,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"[c] *Kahve Eşleşmesi:* \n\n{ice_breaker}"}
                    },
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "[i] Bu kanal 5 dakika sonra otomatik olarak kapatılacaktır."}]
                    }
                ]
            )

            # 5. 5 dakika sonra kapatma görevini planla
            self.cron.add_once_job(
                func=self.close_match,
                delay_minutes=5,
                job_id=f"close_match_{channel_id}",
                args=[channel_id, match_id]
            )
            logger.info(f"[i] 5 dakika sonra kapatma görevi planlandı: {channel_id}")

        except Exception as e:
            logger.error(f"[X] CoffeeMatchService.start_match hatası: {e}")
            raise CemilBotError(f"Eşleşme başlatılamadı: {e}")

    async def close_match(self, channel_id: str, match_id: str):
        """
        Sohbet özetini çıkarır, admini bilgilendirir ve grubu kapatır.
        """
        try:
            logger.info(f"[>] Eşleşme grubu özeti hazırlanıyor: {channel_id}")
            
            # 1. Sohbet geçmişini al
            messages = self.conv.get_history(channel_id=channel_id, limit=50)
            
            # 2. Mesajları temizle (Bot dışındakileri al)
            # Slack'te 'bot_id' veya 'subtype' kontrol edilebilir.
            user_messages = []
            for msg in messages:
                if not msg.get("bot_id") and msg.get("type") == "message":
                    user_text = msg.get("text", "")
                    user_messages.append(f"Kullanıcı: {user_text}")

            conversation_text = "\n".join(user_messages) if user_messages else "Konuşma yapılmadı."

            # 3. LLM ile Özet Çıkar
            summary = "Eşleşme süresince herhangi bir konuşma gerçekleşmedi."
            if user_messages:
                system_prompt = "Sen bir analiz asistanısın. Sana sunulan sohbet geçmişini analiz et ve konuşulan konuları bir cümleyle özetle. Sadece ASCII karakterler kullan."
                summary = await self.groq.quick_ask(system_prompt, f"Sohbet Geçmişi:\n{conversation_text}")

            # 4. Veritabanını Güncelle
            self.match_repo.update(match_id, {
                "status": "closed",
                "summary": summary
            })

            # 5. Admin Kanalını Bilgilendir
            if self.admin_channel:
                match_data = self.match_repo.get(match_id)
                admin_msg = (
                    f"[!] *EŞLEŞME ÖZETİ RAPORU*\n"
                    f"== Kanal: {channel_id}\n"
                    f"== Katılımcılar: <@{match_data['user1_id']}> & <@{match_data['user2_id']}>\n"
                    f"== Özet: {summary}"
                )
                self.chat.post_message(channel=self.admin_channel, text=admin_msg)

            # 6. Kapanış mesajı gönder ve grubu kapat
            self.chat.post_message(
                channel=channel_id,
                text="[>] Süremiz doldu. Bu sohbet sona erdi. Görüşmek üzere!"
            )
            
            await asyncio.sleep(1) # Mesajın gitmesi için kısa bir bekleme
            self.conv.close_conversation(channel_id=channel_id)
            logger.info(f"[+] Grup kapatıldı ve raporlandı: {channel_id}")

        except Exception as e:
            logger.error(f"[X] CoffeeMatchService.close_match hatası: {e}")
