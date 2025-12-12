"""
Presence Service - Gerencia status online/offline/away/busy
"""
from datetime import datetime
from app.database.redis_client import redis_client
from app.database.supabase import supabase_client

class PresenceService:
    """Service para gerenciar presença de usuários"""
    @staticmethod
    async def set_online(user_id: str, status: str = "online"):
        """Marcar usuário como online"""
        try:
            # Atualizar Redis (cache rápido)
            await redis_client.set_user_online(user_id, status)

            # Atualizar banco
            db = supabase_client.get_admin()
            db.table('profiles').update({
                'status': status,
                'last_seen': datetime.utcnow().isoformat()
            }).eq('id', user_id).execute()

            return True

        except Exception as e:
            print(f"Error setting user online: {e}")
            return False

    @staticmethod
    async def set_offline(user_id: str):
        """Marca usuário como offline"""
        try:
            # Atualizar Redis
            await redis_client.set_user_offline(user_id)

            # Atualizar banco
            db = supabase_client.get_admin()
            db.table('profiles').update({
                'status': 'offline',
                'last_seen': datetime.utcnow().isoformat()
            }).eq('id', user_id).execute()

            return True

        except Exception as e:
            print(f"Error setting user offline: {e}")
            return False

    @staticmethod
    async def update_status(user_id: str, status: str):
        """Atualiza status do usuário"""
        try:
            # Validar status
            if status not in ['online', 'offline', 'away', 'busy']:
                return False

            # Atualizar Redis
            if status == 'offline':
                await redis_client.set_user_offline(user_id)
            else:
                await redis_client.set_user_online(user_id, status)

            # Atualizar banco
            db = supabase_client.get_admin()
            db.table('profiles').update({
                'status': status,
                'last_seen': datetime.utcnow().isoformat()
            }).eq('id', user_id).execute()

            return True

        except Exception as e:
            print(f"Error updating status: {e}")
            return False

    @staticmethod
    async def get_user_status(user_id: str) -> str:
        """Retorna status atual do usuário"""
        try:
            # Tentar buscar do Redis primeiro (cache)
            status = await redis_client.get_user_status(user_id)

            if status and status != "offline":
                return status

            # Se não estiver no Redis, buscar do banco
            db = supabase_client.get_admin()
            result = db.table('profiles').select('status').eq('id', user_id).execute()

            if result.data:
                return result.data[0]['status']

            return "offline"

        except Exception as e:
            print(f"Error getting user status: {e}")
            return "offline"