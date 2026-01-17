from typing import List, Optional, Dict, Any, Union
from src.core.logger import logger
from src.core.exceptions import SlackClientError

class ConversationManager:
    """
    Slack Konuşma/Kanal (Conversations) işlemlerini merkezi olarak yöneten sınıf.
    Dökümantasyon: https://api.slack.com/methods?filter=conversations
    """

    def __init__(self, client):
        self.client = client

    def create_channel(self, name: str, is_private: bool = False, **kwargs) -> Dict[str, Any]:
        """Yeni bir kanal oluşturur (conversations.create)."""
        try:
            response = self.client.conversations_create(name=name, is_private=is_private, **kwargs)
            if response["ok"]:
                channel = response["channel"]
                logger.info(f"[+] Kanal oluşturuldu: #{name} (ID: {channel['id']})")
                return channel
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.create hatası: {e}")
            raise SlackClientError(str(e))

    def get_info(self, channel_id: str, **kwargs) -> Dict[str, Any]:
        """Kanal hakkında bilgi getirir (conversations.info)."""
        try:
            response = self.client.conversations_info(channel=channel_id, **kwargs)
            if response["ok"]:
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.info hatası: {e}")
            raise SlackClientError(str(e))

    def list_channels(self, types: str = "public_channel,private_channel", limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Workspace'teki kanalları listeler (conversations.list)."""
        try:
            response = self.client.conversations_list(types=types, limit=limit, **kwargs)
            if response["ok"]:
                channels = response.get("channels", [])
                logger.info(f"[i] Kanallar listelendi: {len(channels)} adet")
                return channels
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.list hatası: {e}")
            raise SlackClientError(str(e))

    def join_channel(self, channel_id: str) -> Dict[str, Any]:
        """Mevcut bir kanala katılır (conversations.join)."""
        try:
            response = self.client.conversations_join(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanala katılım başarılı: {channel_id}")
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.join hatası: {e}")
            raise SlackClientError(str(e))

    def invite_users(self, channel_id: str, user_ids: List[str]) -> Dict[str, Any]:
        """Kanala kullanıcıları davet eder (conversations.invite)."""
        try:
            response = self.client.conversations_invite(channel=channel_id, users=user_ids)
            if response["ok"]:
                logger.info(f"[+] Davet gönderildi: {len(user_ids)} kullanıcı (Kanal: {channel_id})")
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.invite hatası: {e}")
            raise SlackClientError(str(e))

    def kick_user(self, channel_id: str, user_id: str) -> bool:
        """Kullanıcıyı kanaldan çıkarır (conversations.kick)."""
        try:
            response = self.client.conversations_kick(channel=channel_id, user=user_id)
            if response["ok"]:
                logger.info(f"[-] Kullanıcı çıkarıldı: {user_id} (Kanal: {channel_id})")
                return True
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.kick hatası: {e}")
            raise SlackClientError(str(e))

    def leave_channel(self, channel_id: str) -> bool:
        """Kanaldan veya grup DM'den ayrılır (conversations.leave)."""
        try:
            response = self.client.conversations_leave(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanaldan ayrıldı: {channel_id}")
                return True
            else:
                error = response.get("error", "Bilinmeyen hata")
                logger.warning(f"[!] Kanaldan ayrılamadı: {channel_id} | Hata: {error}")
                return False
        except Exception as e:
            logger.error(f"[X] conversations.leave hatası: {channel_id} | {e}")
            return False

    def archive_channel(self, channel_id: str) -> bool:
        """Kanalı arşivler (conversations.archive)."""
        try:
            response = self.client.conversations_archive(channel=channel_id)
            if response["ok"]:
                logger.info(f"[-] Kanal arşivlendi: {channel_id}")
                return True
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.archive hatası: {e}")
            raise SlackClientError(str(e))

    def unarchive_channel(self, channel_id: str) -> bool:
        """Kanal arşivini geri alır (conversations.unarchive)."""
        try:
            response = self.client.conversations_unarchive(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanal arşivi kaldırıldı: {channel_id}")
                return True
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.unarchive hatası: {e}")
            raise SlackClientError(str(e))

    def rename_channel(self, channel_id: str, name: str) -> Dict[str, Any]:
        """Kanalı yeniden adlandırır (conversations.rename)."""
        try:
            response = self.client.conversations_rename(channel=channel_id, name=name)
            if response["ok"]:
                logger.info(f"[+] Kanal adı güncellendi: #{name}")
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.rename hatası: {e}")
            raise SlackClientError(str(e))

    def set_topic(self, channel_id: str, topic: str) -> bool:
        """Kanal konusunu ayarlar (conversations.setTopic)."""
        try:
            response = self.client.conversations_setTopic(channel=channel_id, topic=topic)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.setTopic hatası: {e}")
            return False

    def set_purpose(self, channel_id: str, purpose: str) -> bool:
        """Kanal amacını/açıklamasını ayarlar (conversations.setPurpose)."""
        try:
            response = self.client.conversations_setPurpose(channel=channel_id, purpose=purpose)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.setPurpose hatası: {e}")
            return False

    def get_history(self, channel_id: str, limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Kanal geçmişini getirir (conversations.history)."""
        try:
            response = self.client.conversations_history(channel=channel_id, limit=limit, **kwargs)
            if response["ok"]:
                return response.get("messages", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.history hatası: {e}")
            raise SlackClientError(str(e))

    def get_replies(self, channel_id: str, ts: str, **kwargs) -> List[Dict[str, Any]]:
        """Bir mesaj dizisindeki (thread) cevapları getirir (conversations.replies)."""
        try:
            response = self.client.conversations_replies(channel=channel_id, ts=ts, **kwargs)
            if response["ok"]:
                return response.get("messages", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.replies hatası: {e}")
            raise SlackClientError(str(e))

    def get_members(self, channel_id: str, limit: int = 100, **kwargs) -> List[str]:
        """Kanal üyelerinin ID listesini getirir (conversations.members)."""
        try:
            response = self.client.conversations_members(channel=channel_id, limit=limit, **kwargs)
            if response["ok"]:
                return response.get("members", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.members hatası: {e}")
            raise SlackClientError(str(e))

    def open_conversation(self, users: List[str], **kwargs) -> Dict[str, Any]:
        """DM veya grup DM başlatır (conversations.open)."""
        try:
            response = self.client.conversations_open(users=users, **kwargs)
            if response["ok"]:
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.open hatası: {e}")
            raise SlackClientError(str(e))

    def close_conversation(self, channel_id: str) -> bool:
        """DM veya grup DM'i kapatır (conversations.close)."""
        try:
            response = self.client.conversations_close(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Konuşma kapatıldı: {channel_id}")
                return True
            else:
                error = response.get("error", "Bilinmeyen hata")
                logger.warning(f"[!] Konuşma kapatılamadı: {channel_id} | Hata: {error}")
                # Bazı durumlarda (örneğin grup DM'ler) kapatılamayabilir
                return False
        except Exception as e:
            logger.error(f"[X] conversations.close hatası: {channel_id} | {e}")
            return False

    def mark_read(self, channel_id: str, ts: str) -> bool:
        """Kanalda okunma imlecini ayarlar (conversations.mark)."""
        try:
            response = self.client.conversations_mark(channel=channel_id, ts=ts)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.mark hatası: {e}")
            return False

    # Slack Connect / Paylaşılan Kanal Metodları
    def accept_shared_invite(self, invite_id: str, channel_name: str, **kwargs) -> bool:
        """Slack Connect davetini kabul eder (conversations.acceptSharedInvite)."""
        try:
            response = self.client.conversations_acceptSharedInvite(invite_id=invite_id, channel_name=channel_name, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.acceptSharedInvite hatası: {e}")
            return False

    def approve_shared_invite(self, invite_id: str, **kwargs) -> bool:
        """Slack Connect davetini onaylar (conversations.approveSharedInvite)."""
        try:
            response = self.client.conversations_approveSharedInvite(invite_id=invite_id, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.approveSharedInvite hatası: {e}")
            return False

    def decline_shared_invite(self, invite_id: str, **kwargs) -> bool:
        """Slack Connect davetini reddeder (conversations.declineSharedInvite)."""
        try:
            response = self.client.conversations_declineSharedInvite(invite_id=invite_id, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.declineSharedInvite hatası: {e}")
            return False

    def invite_shared_channel(self, channel_id: str, emails: Optional[List[str]] = None, user_ids: Optional[List[str]] = None, **kwargs) -> bool:
        """Paylaşılan kanal daveti gönderir (conversations.inviteShared)."""
        try:
            response = self.client.conversations_inviteShared(channel=channel_id, emails=emails, user_ids=user_ids, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.inviteShared hatası: {e}")
            return False

    # Canvas (Kanal Bazlı)
    def create_channel_canvas(self, channel_id: str) -> Dict[str, Any]:
        """Kanal için canvas oluşturur (conversations.canvases.create)."""
        try:
            response = self.client.conversations_canvases_create(channel_id=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanal canvas'ı oluşturuldu (Kanal: {channel_id})")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.canvases.create hatası: {e}")
            raise SlackClientError(str(e))
