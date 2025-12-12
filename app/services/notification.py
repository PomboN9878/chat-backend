"""
Notification Service - Cria notificações e integra com push (FCM/APNs)
"""

from typing import Optional
from app.database.supabase import supabase_client

class NotificaitonService:
    """Service para gerenciar notificações"""

    @staticmethod
    async def create_notification(
            user_id: str,
            title: str,
            body: Optional[str],
            notification_type: str,
            reference_id: Optional[str] = None
    ) -> Optional[dict]:
        """Cria notificação no banco"""
        try:
            db = supabase_client.get_admin()

            result = db.table('notifications').insert({
                'user_id': user_id,
                'title': title,
                'body': body,
                'notification_type': notification_type,
                'reference_id': reference_id,
                'is_read': False
            })

            if result.data:
                notification = result.data[0]

                # TODO: Integrar com FCM/APNs para push notification
                # await NotificationService.send_push_notification(user_id, title, body)

                return notification

            return None

        except Exception as e:
            print(f"Error creating notification: {e}")
            return None

    @staticmethod
    async def mark_as_read(notification_id: str, user_id: str) -> bool:
        """Marca notificação como lida"""
        try:
            db = supabase_client.get_admin()

            result = db.table('notifications').update({
                'is_read': True
            }).eq('id', notification_id).eq('user_id', user_id).execute()

            return len(result.data) > 0

        except Exception as e:
            print(f"❌ Error marking notification as read: {e}")
            return False

    @staticmethod
    async def get_unread_count(user_id: str) -> int:
        """Retorna contagem de notificações não lidas"""
        try:
            db = supabase_client.get_admin()

            result = db.table('notifications').select('id', count='exact').eq('user_id', user_id).eq('is_read',
                                                                                                     False).execute()

            return result.count if result.count else 0

        except Exception as e:
            print(f"❌ Error getting unread count: {e}")
            return 0

    # TODO: Implementar quando tiver credenciais FCM/APNs
    # @staticmethod
    # async def send_push_notification(user_id: str, title: str, body: str):
    #     """Envia push notification via FCM (Android) ou APNs (iOS)"""
    #     pass