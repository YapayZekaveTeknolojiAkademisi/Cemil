import os
from typing import Optional
from src.core.logger import logger
from src.commands import ChatManager
from src.clients import SMTPClient
from src.repositories import FeedbackRepository

class FeedbackService:
    """
    Anonim geri bildirimleri yöneten ve yöneticilere ileten servis.
    """

    def __init__(
        self, 
        chat_manager: ChatManager, 
        smtp_client: SMTPClient, 
        feedback_repo: FeedbackRepository
    ):
        self.chat = chat_manager
        self.smtp = smtp_client
        self.repo = feedback_repo
        self.admin_channel = os.environ.get("ADMIN_CHANNEL_ID")
        self.admin_email = os.environ.get("ADMIN_EMAIL")

    async def submit_feedback(self, content: str, category: str = "general"):
        """
        Yeni bir anonim geri bildirim alır, kaydeder ve yöneticileri bilgilendirir.
        """
        try:
            logger.info(f"[>] Yeni bir anonim geri bildirim alındı (Kategori: {category})")

            # 1. Veritabanına kaydet (Kullanıcı ID kaydedilmiyor - Anonimlik)
            feedback_id = self.repo.create({
                "content": content,
                "category": category
            })

            # 2. Slack üzerinden yöneticilere bildir
            if self.admin_channel:
                admin_msg = (
                    "*****************************************\n"
                    "     [!] YENI ANONIM GERI BILDIRIM [!]    \n"
                    "*****************************************\n\n"
                    f"== Kategori: {category}\n"
                    f"== ID: {feedback_id}\n"
                    f"== Mesaj: {content}\n\n"
                    "*****************************************"
                )
                self.chat.post_message(
                    channel=self.admin_channel,
                    text="Yeni bir anonim geri bildirim var!",
                    blocks=[
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"```\n{admin_msg}\n```"}
                        }
                    ]
                )
                logger.debug("[+] Slack üzerinden admin kanalına bildirildi.")

            # 3. E-posta üzerinden yöneticilere bildir
            if self.admin_email:
                subject = f"Anonim Geri Bildirim: {category}"
                email_body = (
                    f"Sayın Yönetici,\n\n"
                    f"Cemil Bot üzerinden yeni bir anonim geri bildirim alındı.\n\n"
                    f"Kategori: {category}\n"
                    f"İçerik: {content}\n\n"
                    f"Tarih: {os.popen('date').read().strip()}\n\n"
                    f"İyi çalışmalar,\nCemil Bot"
                )
                self.smtp.send_email(
                    to_emails=self.admin_email,
                    subject=subject,
                    body=email_body
                )
                logger.debug(f"[+] E-posta üzerinden {self.admin_email} adresine bildirildi.")

            return True

        except Exception as e:
            logger.error(f"[X] FeedbackService.submit_feedback hatası: {e}")
            return False
