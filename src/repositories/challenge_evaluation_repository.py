from typing import Optional, Dict, Any, List
from src.repositories.base_repository import BaseRepository
from src.clients.database_client import DatabaseClient
from src.core.logger import logger


class ChallengeEvaluationRepository(BaseRepository):
    """Challenge değerlendirmeleri için veritabanı erişim sınıfı."""

    def __init__(self, db_client: DatabaseClient):
        super().__init__(db_client, "challenge_evaluations")

    def get_by_challenge(self, challenge_hub_id: str) -> Optional[Dict[str, Any]]:
        """Challenge'a ait değerlendirmeyi getirir."""
        evaluations = self.list(filters={"challenge_hub_id": challenge_hub_id})
        return evaluations[0] if evaluations else None

    def get_by_channel_id(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Kanal ID'sine göre değerlendirme getirir."""
        evaluations = self.list(filters={"evaluation_channel_id": channel_id})
        return evaluations[0] if evaluations else None

    def get_pending_evaluations(self) -> List[Dict[str, Any]]:
        """Deadline'ı geçmiş ve tamamlanmamış değerlendirmeleri getirir."""
        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM challenge_evaluations
                    WHERE status = 'evaluating' 
                    AND deadline_at IS NOT NULL
                    AND deadline_at <= datetime('now')
                    ORDER BY deadline_at ASC
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[X] Pending evaluations getirme hatası: {e}")
            return []

    def update_votes(self, evaluation_id: str, true_votes: int, false_votes: int):
        """Oyları günceller."""
        self.update(evaluation_id, {
            "true_votes": true_votes,
            "false_votes": false_votes
        })
