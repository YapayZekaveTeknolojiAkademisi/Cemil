"""
Challenge değerlendirme handler'ları.
"""

import asyncio
import re
from slack_bolt import App
from src.core.logger import logger
from src.services import ChallengeEvaluationService, ChallengeHubService
from src.commands import ChatManager
from src.repositories import UserRepository, ChallengeHubRepository, ChallengeEvaluationRepository
from src.clients import DatabaseClient
from src.core.settings import get_settings


def setup_challenge_evaluation_handlers(
    app: App,
    evaluation_service: ChallengeEvaluationService,
    challenge_service: ChallengeHubService,
    chat_manager: ChatManager,
    user_repo: UserRepository
):
    """Challenge değerlendirme handler'larını kaydeder."""

    @app.action("evaluate_challenge_button")
    def handle_evaluate_button(ack, body):
        """Projeyi Değerlendir butonuna tıklama."""
        ack()
        
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        
        actions = body.get("actions", [])
        if not actions:
            return
        
        evaluation_id = actions[0].get("value")
        
        async def process_join():
            result = await evaluation_service.join_evaluation(evaluation_id, user_id)
            
            if result["success"]:
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )
            else:
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )
        
        asyncio.run(process_join())

    @app.action("admin_approve_evaluation")
    def handle_admin_approve(ack, body):
        """Admin Onayla butonuna tıklama."""
        ack()
        
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        
        actions = body.get("actions", [])
        if not actions:
            return
        
        evaluation_id = actions[0].get("value")
        
        async def process_approve():
            result = await evaluation_service.admin_finalize_evaluation(
                evaluation_id,
                user_id,
                "approved"
            )
            
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=result["message"]
            )
        
        asyncio.run(process_approve())

    @app.action("admin_reject_evaluation")
    def handle_admin_reject(ack, body):
        """Admin Reddet butonuna tıklama."""
        ack()
        
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        
        actions = body.get("actions", [])
        if not actions:
            return
        
        evaluation_id = actions[0].get("value")
        
        async def process_reject():
            result = await evaluation_service.admin_finalize_evaluation(
                evaluation_id,
                user_id,
                "rejected"
            )
            
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=result["message"]
            )
        
        asyncio.run(process_reject())

    @app.message(re.compile(r"(?i)\b(bitir|tamamla|finish|done)\b"))
    def handle_finish_message(event, say):
        """Challenge kanalında 'bitir' mesajı algılama."""
        try:
            channel_id = event.get("channel")
            user_id = event.get("user")
            text = event.get("text", "").lower()
            
            # "bitir" kelimesi var mı kontrol et
            if "bitir" not in text and "tamamla" not in text and "finish" not in text and "done" not in text:
                return
            
            # Bu kanal bir challenge kanalı mı?
            settings = get_settings()
            db_client = DatabaseClient(db_path=settings.database_path)
            hub_repo = ChallengeHubRepository(db_client)
            
            challenge = hub_repo.get_by_channel_id(channel_id)
            if not challenge:
                return
            
            # Challenge aktif mi?
            if challenge.get("status") != "active":
                return
            
            # Zaten değerlendirme başlatılmış mı?
            eval_repo = ChallengeEvaluationRepository(db_client)
            existing = eval_repo.get_by_challenge(challenge["id"])
            if existing:
                return
            
            # Değerlendirme başlat
            async def start_eval():
                result = await evaluation_service.start_evaluation(
                    challenge["id"],
                    channel_id
                )
                if not result["success"]:
                    logger.warning(f"[!] Değerlendirme başlatılamadı: {result.get('message')}")
            
            asyncio.run(start_eval())
            
        except Exception as e:
            logger.error(f"[X] Finish message handler hatası: {e}", exc_info=True)

    @app.event("member_left_channel")
    def handle_member_left_evaluation(event):
        """Değerlendirme kanalından kullanıcı ayrıldığında."""
        try:
            channel_id = event.get("channel")
            user_id = event.get("user")
            
            # Bu kanal bir değerlendirme kanalı mı?
            settings = get_settings()
            db_client = DatabaseClient(db_path=settings.database_path)
            eval_repo = ChallengeEvaluationRepository(db_client)
            
            evaluation = eval_repo.get_by_channel_id(channel_id)
            if not evaluation:
                return
            
            # Kullanıcı değerlendirici mi kontrol et
            from src.repositories import ChallengeEvaluatorRepository
            evaluator_repo = ChallengeEvaluatorRepository(db_client)
            
            evaluator = evaluator_repo.get_by_evaluation_and_user(
                evaluation["id"], 
                user_id
            )
            
            if evaluator:
                # Değerlendirici kaydını sil
                evaluator_repo.delete(evaluator["id"])
                logger.info(f"[+] Değerlendirici kanaldan ayrıldı ve kaydı silindi: {user_id} | Evaluation: {evaluation['id']}")
            
        except Exception as e:
            logger.error(f"[X] Member left handler hatası: {e}", exc_info=True)
