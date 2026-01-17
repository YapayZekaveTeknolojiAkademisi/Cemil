from typing import List, Optional, Dict, Any
from src.core.logger import logger
from src.core.exceptions import SlackClientError

class SearchManager:
    """
    Slack Arama (Search) işlemlerini merkezi olarak yöneten sınıf.
    Dökümantasyon: https://api.slack.com/methods?filter=search
    """

    def __init__(self, client):
        self.client = client

    def search_all(self, query: str, sort: str = "score", sort_dir: str = "desc", **kwargs) -> Dict[str, Any]:
        """Hem mesajlar hem de dosyalar içinde arama yapar (search.all)."""
        try:
            response = self.client.search_all(query=query, sort=sort, sort_dir=sort_dir, **kwargs)
            if response["ok"]:
                total_messages = response.get("messages", {}).get("total", 0)
                total_files = response.get("files", {}).get("total", 0)
                logger.info(f"[i] Genel arama tamamlandı: '{query}' -> {total_messages} mesaj, {total_files} dosya bulundu.")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] search.all hatası: {e}")
            raise SlackClientError(str(e))

    def search_messages(self, query: str, sort: str = "timestamp", sort_dir: str = "desc", **kwargs) -> Dict[str, Any]:
        """Sadece mesajlar içinde arama yapar (search.messages)."""
        try:
            response = self.client.search_messages(query=query, sort=sort, sort_dir=sort_dir, **kwargs)
            if response["ok"]:
                total = response.get("messages", {}).get("total", 0)
                logger.info(f"[i] Mesaj araması tamamlandı: '{query}' -> {total} sonuç bulundu.")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] search.messages hatası: {e}")
            raise SlackClientError(str(e))

    def search_files(self, query: str, sort: str = "timestamp", sort_dir: str = "desc", **kwargs) -> Dict[str, Any]:
        """Sadece dosyalar içinde arama yapar (search.files)."""
        try:
            response = self.client.search_files(query=query, sort=sort, sort_dir=sort_dir, **kwargs)
            if response["ok"]:
                total = response.get("files", {}).get("total", 0)
                logger.info(f"[i] Dosya araması tamamlandı: '{query}' -> {total} sonuç bulundu.")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] search.files hatası: {e}")
            raise SlackClientError(str(e))
