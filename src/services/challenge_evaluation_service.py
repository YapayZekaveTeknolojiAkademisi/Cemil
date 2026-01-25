"""
Challenge değerlendirme servisi.
"""

import uuid
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from src.core.logger import logger
from src.commands import ChatManager, ConversationManager
from src.repositories import (
    ChallengeEvaluationRepository,
    ChallengeEvaluatorRepository,
    ChallengeHubRepository,
    ChallengeParticipantRepository
)
from src.clients import CronClient
from src.core.settings import get_settings


class ChallengeEvaluationService:
    """Challenge değerlendirme yönetim servisi."""

    def __init__(
        self,
        chat_manager: ChatManager,
        conv_manager: ConversationManager,
        evaluation_repo: ChallengeEvaluationRepository,
        evaluator_repo: ChallengeEvaluatorRepository,
        hub_repo: ChallengeHubRepository,
        participant_repo: ChallengeParticipantRepository,
        cron_client: CronClient
    ):
        self.chat = chat_manager
        self.conv = conv_manager
        self.evaluation_repo = evaluation_repo
        self.evaluator_repo = evaluator_repo
        self.hub_repo = hub_repo
        self.participant_repo = participant_repo
        self.cron = cron_client

    async def start_evaluation(
        self,
        challenge_id: str,
        trigger_channel_id: str
    ) -> Dict[str, Any]:
        """
        Challenge için değerlendirme başlatır.
        Değerlendirme kanalını otomatik oluşturur ve tüm katılımcıları ekler.
        """
        try:
            # Challenge kontrolü
            challenge = self.hub_repo.get(challenge_id)
            if not challenge:
                return {
                    "success": False,
                    "message": "❌ Challenge bulunamadı."
                }

            # Zaten değerlendirme başlatılmış mı?
            existing = self.evaluation_repo.get_by_challenge(challenge_id)
            if existing:
                return {
                    "success": False,
                    "message": "⚠️ Bu challenge için değerlendirme zaten başlatılmış."
                }

            # Değerlendirme kaydı oluştur
            evaluation_id = str(uuid.uuid4())
            deadline = datetime.now() + timedelta(hours=48)
            
            evaluation_data = {
                "id": evaluation_id,
                "challenge_hub_id": challenge_id,
                "status": "pending",
                "deadline_at": deadline.isoformat()
            }
            self.evaluation_repo.create(evaluation_data)

            # 1. Değerlendirme kanalını HEMEN oluştur
            channel_suffix = str(uuid.uuid4())[:8]
            channel_name = f"challenge-evaluation-{channel_suffix}"
            
            try:
                eval_channel = self.conv.create_channel(
                    name=channel_name,
                    is_private=True
                )
                eval_channel_id = eval_channel["id"]
                
                # Değerlendirme kaydını güncelle
                self.evaluation_repo.update(evaluation_id, {
                    "evaluation_channel_id": eval_channel_id,
                    "status": "evaluating"
                })
                
                logger.info(f"[+] Değerlendirme kanalı oluşturuldu: {eval_channel_id} | Challenge: {challenge_id}")
            except Exception as e:
                logger.error(f"[X] Değerlendirme kanalı oluşturulamadı: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": "❌ Değerlendirme kanalı oluşturulamadı."
                }

            # 2. Tüm katılımcıları kanala ekle (creator + participants + admin)
            settings = get_settings()
            ADMIN_USER_ID = settings.admin_slack_id
            creator_id = challenge.get("creator_id")
            participants = self.participant_repo.list(filters={"challenge_hub_id": challenge_id})
            participant_ids = [p["user_id"] for p in participants]
            
            # Tüm kullanıcıları birleştir (tekrarları önle)
            all_user_ids = set()
            if creator_id:
                all_user_ids.add(creator_id)
            for pid in participant_ids:
                all_user_ids.add(pid)
            if ADMIN_USER_ID:
                all_user_ids.add(ADMIN_USER_ID)
            
            # Kullanıcıları kanala davet et
            try:
                self.conv.invite_users(eval_channel_id, list(all_user_ids))
                logger.info(f"[+] {len(all_user_ids)} kullanıcı değerlendirme kanalına eklendi | Evaluation: {evaluation_id}")
            except Exception as e:
                logger.warning(f"[!] Kullanıcılar kanala davet edilirken hata: {e}")

            # 3. 48 saat sonra otomatik kapatma görevi planla
            self.cron.add_once_job(
                func=self.finalize_evaluation,
                delay_minutes=48 * 60,
                job_id=f"finalize_evaluation_{evaluation_id}",
                args=[evaluation_id]
            )
            logger.info(f"[+] 48 saatlik değerlendirme timer'ı başlatıldı | Evaluation: {evaluation_id}")

            # 4. Kanal açılış mesajını gönder
            welcome_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Challenge Değerlendirme",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "Bu kanal 48 saat açık kalacak.\n\n"
                            "*Komutlar:*\n"
                            "• `/challenge set True` - Proje başarılı\n"
                            "• `/challenge set False` - Proje başarısız\n"
                            "• `/challenge set github <link>` - GitHub repo linki\n\n"
                            "💡 *Not:* Başarılı sayılması için True > False ve public GitHub repo gerekli.\n\n"
                            "⚠️ *Proje ekibi (creator + katılımcılar) oy veremez.* Sadece harici değerlendiriciler oy kullanabilir."
                        )
                    }
                }
            ]
            
            try:
                self.chat.post_message(
                    channel=eval_channel_id,
                    text="📊 Challenge Değerlendirme - Hoş geldiniz!",
                    blocks=welcome_blocks
                )
            except Exception as e:
                logger.warning(f"[!] Değerlendirme açılış mesajı gönderilemedi: {e}")

            # 5. Hub kanalına bilgilendirme mesajı gönder (jüri için butonlu)
            target_channel = challenge.get("hub_channel_id") or trigger_channel_id
            info_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🎯 Challenge Tamamlandı!",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"Değerlendirme kanalı oluşturuldu ve proje ekibi otomatik eklendi.\n\n"
                            f"📊 *Değerlendirme Kanalı:* <#{eval_channel_id}>\n\n"
                            "💡 *Değerlendirme Süreci:*\n"
                            "• Değerlendirme kanalı 48 saat açık kalacak\n"
                            "• Max 3 harici değerlendirici (jüri) alınacak\n"
                            "• Her değerlendirici `/challenge set True` veya `/challenge set False` yazacak\n"
                            "• Başarılı sayılması için True > False ve public GitHub repo gerekli"
                        )
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📊 Projeyi Değerlendir (Jüri)",
                                "emoji": True
                            },
                            "style": "primary",
                            "action_id": "evaluate_challenge_button",
                            "value": evaluation_id
                        }
                    ]
                }
            ]

            self.chat.post_message(
                channel=target_channel,
                text="🎯 Challenge Tamamlandı! Değerlendirme kanalı oluşturuldu.",
                blocks=info_blocks
            )

            logger.info(f"[+] Değerlendirme başlatıldı | Challenge: {challenge_id} | Evaluation: {evaluation_id}")

            return {
                "success": True,
                "evaluation_id": evaluation_id,
                "message": "✅ Değerlendirme başlatıldı!"
            }

        except Exception as e:
            logger.error(f"[X] Değerlendirme başlatma hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": "❌ Değerlendirme başlatılırken bir hata oluştu."
            }

    async def join_evaluation(
        self,
        evaluation_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Kullanıcıyı değerlendirme kanalına ekler.
        Max 3 harici değerlendirici kontrolü yapar.
        Proje sahipleri (creator + participants) ve Akademi owner kanala
        girebilir ancak 3 kişilik değerlendirici sınırına dahil edilmez.
        """
        try:
            evaluation = self.evaluation_repo.get(evaluation_id)
            if not evaluation:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme bulunamadı."
                }

            # Challenge'ı getir (proje üyesi kontrolü için)
            challenge = self.hub_repo.get(evaluation["challenge_hub_id"])
            if not challenge:
                return {
                    "success": False,
                    "message": "❌ Challenge bulunamadı."
                }

            # Proje ekibi & owner bilgisi
            settings = get_settings()
            ADMIN_USER_ID = settings.admin_slack_id
            creator_id = challenge.get("creator_id")
            participants = self.participant_repo.list(filters={"challenge_hub_id": challenge["id"]})
            participant_ids = [p["user_id"] for p in participants]

            is_admin = user_id == ADMIN_USER_ID
            is_project_member = (user_id == creator_id) or (user_id in participant_ids)

            # Değerlendirme kanalı var mı kontrol et (DB'den gerçek değer - race condition için güvenli)
            eval_channel_id = evaluation.get("evaluation_channel_id")
            is_new_channel = False
            welcome_blocks = None
            
            # Kanal yoksa oluştur (evaluator_count yerine eval_channel_id kontrolü daha güvenli)
            if not eval_channel_id:
                # Kanal oluştur (challenge zaten yukarıda çekildi)
                channel_suffix = str(uuid.uuid4())[:8]
                channel_name = f"challenge-evaluation-{channel_suffix}"
                
                try:
                    eval_channel = self.conv.create_channel(
                        name=channel_name,
                        is_private=True
                    )
                    eval_channel_id = eval_channel["id"]
                    
                    # Değerlendirme kaydını güncelle
                    self.evaluation_repo.update(evaluation_id, {
                        "evaluation_channel_id": eval_channel_id,
                        "status": "evaluating"
                    })
                    
                    # Açılış mesajını daha sonra (bot kanala davet edildikten sonra) göndermek için sakla
                    welcome_blocks = [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "📊 Challenge Değerlendirme",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "Bu kanal 48 saat açık kalacak.\n\n"
                                    "*Komutlar:*\n"
                                    "• `/challenge set True` - Proje başarılı\n"
                                    "• `/challenge set False` - Proje başarısız\n"
                                    "• `/challenge set github <link>` - GitHub repo linki\n\n"
                                    "💡 *Not:* Başarılı sayılması için True > False ve public GitHub repo gerekli."
                                )
                            }
                        }
                    ]
                    is_new_channel = True

                    # 48 saat sonra otomatik kapatma görevi planla (sadece kanal ilk açıldığında)
                    self.cron.add_once_job(
                        func=self.finalize_evaluation,
                        delay_minutes=48 * 60,
                        job_id=f"finalize_evaluation_{evaluation_id}",
                        args=[evaluation_id]
                    )

                    logger.info(f"[+] Değerlendirme kanalı oluşturuldu: {eval_channel_id} | Challenge: {challenge['id']} | 48 saatlik timer başlatıldı")
                except Exception as e:
                    logger.error(f"[X] Değerlendirme kanalı oluşturulamadı: {e}", exc_info=True)
                    return {
                        "success": False,
                        "message": "❌ Değerlendirme kanalı oluşturulamadı."
                    }
            else:
                # Kanal zaten var, mevcut kanala eklenecek
                logger.info(f"[i] Mevcut değerlendirme kanalı kullanılıyor: {eval_channel_id} | User: {user_id}")

            # Kullanıcıyı kanala ekle
            if not eval_channel_id:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme kanalı bulunamadı."
                }

            # 1) Proje ekibi (creator + participants) ve admin:
            #    - Her zaman kanala girebilir
            #    - 3 kişilik değerlendirici limitine dahil edilmez
            if is_project_member or is_admin:
                try:
                    self.conv.invite_users(eval_channel_id, [user_id])
                except Exception as e:
                    logger.warning(f"[!] Kullanıcı kanala davet edilemedi (ekip/admin): {e}")

                # Yeni kanal ilk kez açıldıysa açılış mesajını gönder
                if is_new_channel and welcome_blocks:
                    try:
                        self.chat.post_message(
                            channel=eval_channel_id,
                            text="📊 Challenge Değerlendirme",
                            blocks=welcome_blocks
                        )
                    except Exception as e:
                        logger.warning(f"[!] Değerlendirme açılış mesajı gönderilemedi: {e}")

                logger.info(f"[+] Proje ekibi/admin değerlendirme kanalına eklendi: {user_id} | Evaluation: {evaluation_id}")

                return {
                    "success": True,
                    "message": f"✅ Değerlendirme kanalına eklendiniz! <#{eval_channel_id}>"
                }

            # 2) Harici değerlendiriciler:
            # Max 3 kişi kontrolü (sadece harici değerlendiriciler sayılır)
            evaluator_count = self.evaluator_repo.count_evaluators(evaluation_id)
            if evaluator_count >= 3:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme kanalı dolu (max 3 değerlendirici)."
                }

            # Zaten değerlendirici olarak eklenmiş mi?
            existing = self.evaluator_repo.get_by_evaluation_and_user(evaluation_id, user_id)
            if existing:
                return {
                    "success": False,
                    "message": "⚠️ Zaten değerlendirme kanalındasınız."
                }

            # Kullanıcıyı (ve ConversationManager içindeki mantıkla botu) kanala davet et
            try:
                self.conv.invite_users(eval_channel_id, [user_id])
            except Exception as e:
                logger.warning(f"[!] Kullanıcı kanala davet edilemedi: {e}")

            # Değerlendirici kaydı oluştur (harici kullanıcı için)
            evaluator_id = str(uuid.uuid4())
            self.evaluator_repo.create({
                "id": evaluator_id,
                "evaluation_id": evaluation_id,
                "user_id": user_id
            })

            # Yeni kanal oluşturulduysa, açılış mesajını şimdi gönder (bot artık kanalda)
            if is_new_channel and welcome_blocks:
                try:
                    self.chat.post_message(
                        channel=eval_channel_id,
                        text="📊 Challenge Değerlendirme",
                        blocks=welcome_blocks
                    )
                except Exception as e:
                    logger.warning(f"[!] Değerlendirme açılış mesajı gönderilemedi: {e}")

            logger.info(f"[+] Değerlendirici eklendi: {user_id} | Evaluation: {evaluation_id}")

            return {
                "success": True,
                "message": f"✅ Değerlendirme kanalına eklendiniz! <#{eval_channel_id}>"
            }

        except Exception as e:
            logger.error(f"[X] Değerlendirme katılma hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": "❌ Değerlendirme kanalına eklenirken bir hata oluştu."
            }

    async def submit_vote(
        self,
        evaluation_id: str,
        user_id: str,
        vote: str
    ) -> Dict[str, Any]:
        """
        Kullanıcının oyunu kaydeder.
        Sadece harici değerlendiriciler (max 3 kişi) oy verebilir.
        Proje üyeleri ve admin oy veremez (admin sadece onay verebilir).
        """
        try:
            evaluation = self.evaluation_repo.get(evaluation_id)
            if not evaluation:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme bulunamadı."
                }

            # Challenge'ı getir (proje üyesi kontrolü için)
            challenge = self.hub_repo.get(evaluation["challenge_hub_id"])
            if not challenge:
                return {
                    "success": False,
                    "message": "❌ Challenge bulunamadı."
                }

            # Admin oy veremez, sadece onay verebilir
            settings = get_settings()
            ADMIN_USER_ID = settings.admin_slack_id
            if user_id == ADMIN_USER_ID:
                return {
                    "success": False,
                    "message": "❌ Admin olarak oy veremezsiniz. Sadece 'Onayla ve Bitir' / 'Reddet ve Bitir' butonlarını kullanabilirsiniz."
                }

            # Proje ekibi (creator + participants) oy veremez - EN ÜSTTE KONTROL ET
            creator_id = challenge.get("creator_id")
            participants = self.participant_repo.list(filters={"challenge_hub_id": challenge["id"]})
            participant_ids = [p["user_id"] for p in participants]
            
            # Creator kontrolü
            if user_id == creator_id:
                return {
                    "success": False,
                    "message": "❌ Proje sahibi olarak oy veremezsiniz. Sadece harici değerlendiriciler oy kullanabilir."
                }
            
            # Participant kontrolü
            if user_id in participant_ids:
                return {
                    "success": False,
                    "message": "❌ Proje ekibi üyesi olarak oy veremezsiniz. Sadece harici değerlendiriciler oy kullanabilir."
                }

            # Değerlendirici kontrolü (sadece harici değerlendiriciler oy verebilir)
            evaluator = self.evaluator_repo.get_by_evaluation_and_user(evaluation_id, user_id)
            if not evaluator:
                return {
                    "success": False,
                    "message": "❌ Bu değerlendirmenin değerlendiricisi değilsiniz."
                }

            # Zaten oy vermiş mi?
            if evaluator.get("vote"):
                return {
                    "success": False,
                    "message": "⚠️ Zaten oy verdiniz. Oyunuzu değiştiremezsiniz."
                }

            # Oyu kaydet
            self.evaluator_repo.update(evaluator["id"], {
                "vote": vote.lower(),
                "voted_at": datetime.now().isoformat()
            })

            # Oyları güncelle
            votes = self.evaluator_repo.get_votes(evaluation_id)
            self.evaluation_repo.update_votes(
                evaluation_id,
                votes["true"],
                votes["false"]
            )

            logger.info(f"[+] Oy kaydedildi: {user_id} | Vote: {vote} | Evaluation: {evaluation_id}")

            # 3 kişi oy verdiyse kontrol et
            total_votes = votes["true"] + votes["false"]
            if total_votes >= 3:
                logger.info(f"[i] 3 değerlendirici oy verdi | Evaluation: {evaluation_id}")
                
                # GitHub repo var mı ve public mi kontrol et
                github_url = evaluation.get("github_repo_url")
                github_public = evaluation.get("github_repo_public", 0)
                
                eval_channel_id = evaluation.get("evaluation_channel_id")
                
                if github_url and github_public == 1:
                    # Repo var ve public → Admin onayı iste
                    logger.info(f"[+] Tüm oylar alındı ve repo public → Admin onayı bekleniyor | Evaluation: {evaluation_id}")
                    
                    # Kanala admin onay butonu gönder
                    if eval_channel_id:
                        try:
                            self.chat.post_message(
                                channel=eval_channel_id,
                                text="✅ Tüm değerlendiriciler oy verdi ve GitHub repo public! Admin onayı bekleniyor...",
                                blocks=[
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": (
                                                "✅ *Tüm değerlendiriciler oy verdi ve GitHub repo public!*\n\n"
                                                f"📊 Oylar: True={votes['true']}, False={votes['false']}\n"
                                                f"🔗 GitHub: {github_url}\n\n"
                                                "👤 **Admin onayı bekleniyor...**"
                                            )
                                        }
                                    },
                                    {
                                        "type": "actions",
                                        "elements": [
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "✅ Onayla ve Bitir",
                                                    "emoji": True
                                                },
                                                "style": "primary",
                                                "action_id": "admin_approve_evaluation",
                                                "value": evaluation_id
                                            },
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "❌ Reddet ve Bitir",
                                                    "emoji": True
                                                },
                                                "style": "danger",
                                                "action_id": "admin_reject_evaluation",
                                                "value": evaluation_id
                                            }
                                        ]
                                    }
                                ]
                            )
                            logger.info(f"[i] Admin onay butonu gönderildi | Evaluation: {evaluation_id}")
                        except Exception as e:
                            logger.warning(f"[!] Admin onay butonu gönderilemedi: {e}")
                else:
                    # Repo yok veya private → Bilgilendirme mesajı gönder
                    if eval_channel_id:
                        try:
                            if not github_url:
                                message = (
                                    "✅ *Tüm değerlendiriciler oy verdi!*\n\n"
                                    "🔗 Şimdi GitHub repo linki eklemeniz gerekiyor:\n"
                                    "`/challenge set github <link>`\n\n"
                                    "Repo eklendikten ve public olduğu doğrulandıktan sonra değerlendirme sonuçlanacak."
                                )
                            else:
                                message = (
                                    "✅ *Tüm değerlendiriciler oy verdi!*\n\n"
                                    "⚠️ GitHub repo linki eklendi ancak repo *private* görünüyor.\n"
                                    "Lütfen repo'yu public yapın veya doğru linki ekleyin:\n"
                                    "`/challenge set github <link>`\n\n"
                                    "Repo public olduktan sonra değerlendirme sonuçlanacak."
                                )
                            
                            self.chat.post_message(
                                channel=eval_channel_id,
                                text="✅ Tüm değerlendiriciler oy verdi!",
                                blocks=[
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": message
                                        }
                                    }
                                ]
                            )
                            logger.info(f"[i] Repo bekleme mesajı gönderildi | Evaluation: {evaluation_id}")
                        except Exception as e:
                            logger.warning(f"[!] Repo bekleme mesajı gönderilemedi: {e}")

            return {
                "success": True,
                "message": f"✅ Oyunuz kaydedildi: *{vote}*"
            }

        except Exception as e:
            logger.error(f"[X] Oy kaydetme hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": "❌ Oy kaydedilirken bir hata oluştu."
            }

    async def submit_github_link(
        self,
        evaluation_id: str,
        github_url: str
    ) -> Dict[str, Any]:
        """GitHub repo linkini kaydeder ve public kontrolü yapar."""
        try:
            evaluation = self.evaluation_repo.get(evaluation_id)
            if not evaluation:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme bulunamadı."
                }

            # GitHub URL formatını kontrol et
            if not self._is_valid_github_url(github_url):
                return {
                    "success": False,
                    "message": "❌ Geçersiz GitHub URL formatı. Örnek: https://github.com/user/repo"
                }

            # Repo public mi kontrol et
            is_public = await self.check_github_repo_public(github_url)

            # Linki kaydet
            self.evaluation_repo.update(evaluation_id, {
                "github_repo_url": github_url,
                "github_repo_public": 1 if is_public else 0
            })

            # Eğer repo public ve 3 kişi oy verdiyse admin onayı iste
            if is_public:
                votes = self.evaluator_repo.get_votes(evaluation_id)
                total_votes = votes["true"] + votes["false"]
                
                if total_votes >= 3:
                    logger.info(f"[+] GitHub repo public ve 3 oy var → Admin onayı bekleniyor | Evaluation: {evaluation_id}")
                    
                    # Kanala admin onay butonu gönder
                    eval_channel_id = evaluation.get("evaluation_channel_id")
                    if eval_channel_id:
                        try:
                            self.chat.post_message(
                                channel=eval_channel_id,
                                text="✅ GitHub repo public ve tüm oylar alındı! Admin onayı bekleniyor...",
                                blocks=[
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": (
                                                "✅ *GitHub repo public doğrulandı ve tüm oylar alındı!*\n\n"
                                                f"📊 Oylar: True={votes['true']}, False={votes['false']}\n"
                                                f"🔗 GitHub: {github_url}\n\n"
                                                "👤 **Admin onayı bekleniyor...**"
                                            )
                                        }
                                    },
                                    {
                                        "type": "actions",
                                        "elements": [
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "✅ Onayla ve Bitir",
                                                    "emoji": True
                                                },
                                                "style": "primary",
                                                "action_id": "admin_approve_evaluation",
                                                "value": evaluation_id
                                            },
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "❌ Reddet ve Bitir",
                                                    "emoji": True
                                                },
                                                "style": "danger",
                                                "action_id": "admin_reject_evaluation",
                                                "value": evaluation_id
                                            }
                                        ]
                                    }
                                ]
                            )
                            logger.info(f"[i] Admin onay butonu gönderildi | Evaluation: {evaluation_id}")
                        except Exception as e:
                            logger.warning(f"[!] Admin onay butonu gönderilemedi: {e}")
                    
                    return {
                        "success": True,
                        "message": f"✅ GitHub repo linki kaydedildi ve public doğrulandı. Admin onayı bekleniyor: {github_url}"
                    }
                else:
                    return {
                        "success": True,
                        "message": f"✅ GitHub repo linki kaydedildi ve public olarak doğrulandı: {github_url}\n\n💡 Tüm değerlendiriciler oy verdiğinde değerlendirme tamamlanacak."
                    }
            else:
                return {
                    "success": True,
                    "message": f"⚠️ GitHub repo linki kaydedildi ancak repo private görünüyor: {github_url}\n\n💡 Başarılı sayılması için repo public olmalı."
                }

        except Exception as e:
            logger.error(f"[X] GitHub link kaydetme hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": "❌ GitHub linki kaydedilirken bir hata oluştu."
            }

    async def check_github_repo_public(self, github_url: str) -> bool:
        """GitHub repo'nun public olup olmadığını kontrol eder."""
        try:
            # GitHub URL'ini parse et
            # https://github.com/user/repo -> https://api.github.com/repos/user/repo
            match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', github_url)
            if not match:
                return False

            user, repo = match.groups()
            api_url = f"https://api.github.com/repos/{user}/{repo}"

            # API'ye istek at
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return not data.get("private", True)
            elif response.status_code == 404:
                # Repo bulunamadı veya private
                return False
            else:
                logger.warning(f"[!] GitHub API hatası: {response.status_code}")
                return False

        except Exception as e:
            logger.warning(f"[!] GitHub repo kontrolü hatası: {e}")
            return False

    def _is_valid_github_url(self, url: str) -> bool:
        """GitHub URL formatını kontrol eder."""
        pattern = r'^https?://github\.com/[^/]+/[^/]+/?$'
        return bool(re.match(pattern, url))

    async def admin_finalize_evaluation(
        self,
        evaluation_id: str,
        admin_user_id: str,
        approval: str  # "approved" veya "rejected"
    ) -> Dict[str, Any]:
        """
        Admin onayı ile değerlendirmeyi sonlandırır.
        Sadece admin çağırabilir.
        """
        try:
            settings = get_settings()
            ADMIN_USER_ID = settings.admin_slack_id
            if admin_user_id != ADMIN_USER_ID:
                return {
                    "success": False,
                    "message": "❌ Sadece admin bu işlemi yapabilir."
                }
            
            evaluation = self.evaluation_repo.get(evaluation_id)
            if not evaluation:
                return {
                    "success": False,
                    "message": "❌ Değerlendirme bulunamadı."
                }
            
            if evaluation.get("status") == "completed":
                return {
                    "success": False,
                    "message": "⚠️ Bu değerlendirme zaten tamamlanmış."
                }
            
            # Admin onayını kaydet
            self.evaluation_repo.update(evaluation_id, {
                "admin_approval": approval
            })
            
            logger.info(f"[+] Admin onayı: {approval} | Evaluation: {evaluation_id} | Admin: {admin_user_id}")
            
            # Değerlendirmeyi finalize et
            await self.finalize_evaluation(evaluation_id, admin_approval=approval)
            
            if approval == "approved":
                return {
                    "success": True,
                    "message": "✅ Değerlendirme admin tarafından onaylandı ve tamamlandı."
                }
            else:
                return {
                    "success": True,
                    "message": "❌ Değerlendirme admin tarafından reddedildi ve tamamlandı."
                }
            
        except Exception as e:
            logger.error(f"[X] Admin finalize hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": "❌ Admin onayı kaydedilirken bir hata oluştu."
            }

    async def finalize_evaluation(self, evaluation_id: str, admin_approval: str = None):
        """48 saat sonunda değerlendirmeyi finalize eder."""
        try:
            evaluation = self.evaluation_repo.get(evaluation_id)
            if not evaluation:
                logger.error(f"[X] Finalize: Değerlendirme bulunamadı: {evaluation_id}")
                return

            if evaluation.get("status") != "evaluating":
                logger.warning(f"[!] Finalize: Değerlendirme zaten tamamlanmış: {evaluation_id}")
                return

            # Oyları al
            votes = self.evaluator_repo.get_votes(evaluation_id)
            true_votes = votes["true"]
            false_votes = votes["false"]

            # Sonucu hesapla
            github_public = evaluation.get("github_repo_public", 0) == 1
            github_url = evaluation.get("github_repo_url")

            # Admin reddetmişse otomatik olarak başarısız
            if admin_approval == "rejected":
                final_result = "failed"
                result_message = "❌ *Challenge Başarısız*\n\n*Nedenler:*\n• Admin tarafından reddedildi"
            elif true_votes > false_votes and github_public and github_url:
                final_result = "success"
                result_message = "🎉 *Challenge Başarılı!*"
            else:
                final_result = "failed"
                reasons = []
                if true_votes <= false_votes:
                    reasons.append(f"True oyları ({true_votes}) False oylarından ({false_votes}) fazla değil")
                if not github_url:
                    reasons.append("GitHub repo linki eklenmemiş")
                elif not github_public:
                    reasons.append("GitHub repo public değil")
                result_message = f"❌ *Challenge Başarısız*\n\n*Nedenler:*\n" + "\n".join(f"• {r}" for r in reasons)

            # Değerlendirmeyi güncelle
            self.evaluation_repo.update(evaluation_id, {
                "status": "completed",
                "final_result": final_result,
                "completed_at": datetime.now().isoformat()
            })

            # Challenge'ı güncelle
            challenge_id = evaluation["challenge_hub_id"]
            challenge = self.hub_repo.get(challenge_id)
            if challenge:
                # Challenge'ın status'unu güncelle (değerlendirme tamamlandı)
                self.hub_repo.update(challenge_id, {
                    "status": "completed",
                    "completed_at": datetime.now().isoformat()
                })
                logger.info(f"[+] Challenge status güncellendi: {challenge_id} | Status: completed")
                
                # Sonuç mesajını hem challenge kanalına hem ana kanala gönder
                result_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": result_message
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"📊 Oylar: True={true_votes}, False={false_votes} | GitHub: {'✅ Public' if github_public else '❌ Private/Missing'}"
                            }
                        ]
                    }
                ]
                
                # Ana kanala (hub_channel_id) sonuç mesajı gönder
                hub_channel_id = challenge.get("hub_channel_id")
                if hub_channel_id:
                    try:
                        self.chat.post_message(
                            channel=hub_channel_id,
                            text=result_message,
                            blocks=result_blocks
                        )
                        logger.info(f"[+] Değerlendirme sonucu ana kanala gönderildi: {hub_channel_id}")
                    except Exception as e:
                        logger.warning(f"[!] Ana kanala sonuç mesajı gönderilemedi: {e}")
                
                # Challenge kanalına da gönder (kanal arşivlenmiş olabilir, hata kontrolü yap)
                challenge_channel_id = challenge.get("challenge_channel_id")
                if challenge_channel_id:
                    try:
                        self.chat.post_message(
                            channel=challenge_channel_id,
                            text=result_message,
                            blocks=result_blocks
                        )
                    except Exception as e:
                        logger.warning(f"[!] Challenge kanalına sonuç mesajı gönderilemedi (kanal arşivlenmiş olabilir): {e}")

            # Değerlendirme kanalını kapat
            eval_channel_id = evaluation.get("evaluation_channel_id")
            if eval_channel_id:
                try:
                    self.conv.archive_channel(eval_channel_id)
                    logger.info(f"[+] Değerlendirme kanalı arşivlendi: {eval_channel_id}")
                except Exception as e:
                    logger.warning(f"[!] Değerlendirme kanalı arşivlenemedi: {e}")

            logger.info(f"[+] Değerlendirme finalize edildi: {evaluation_id} | Sonuç: {final_result}")

        except Exception as e:
            logger.error(f"[X] Değerlendirme finalize hatası: {e}", exc_info=True)
