"""
Cliente Redis - Cache de sessões e fila de mensagens não entregues
"""
import json
from typing import Any, Optional
from redis import asyncio as aioredis
from app.config import settings

class RedisClient:
    """Cliente Redis para cache e pub/sub"""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Conecta ao Redis"""
        if self.redis is None:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                encoding="utf-8"
            )

    async def ping(self):
        """Teste conexão"""
        if self.redis is None:
            await self.connect()
        return await self.redis.ping()

    async def close(self):
        """Fecha conexão"""
        if self.redis:
            await self.redis.close()

    # -- Sessões de Usuários
    async def set_user_session(self, user_id: str, socket_id: str, data: dict, ttl: int = 86400):
        """Salva sessão do usuário (socket_id -> user_data)"""
        if self.redis is None:
            await self.connect()

        key = f"session:{user_id}:{socket_id}"
        await self.redis.setex(key, ttl, json.dump(data))

    async def get_user_session(self, user_id: str, socket_id: str) -> Optional[dict]:
        """Busca sessão do usuário"""
        if self.redis is None:
            await self.connect()

        key = f"session:{user_id}:{socket_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def delete_user_session(self, user_id: str, socket_id: str):
        """Remove sessão"""
        if self.redis is None:
            await self.connect()

        key = f"session:{user_id}:{socket_id}"
        await self.redis.delete(key)

    async def get_user_sockets(self, user_id: str):
        """Retorna todos os socket_ids de um usuario"""
        if self.redis is None:
            await self.connect()

        pattern = f"session:{user_id}*"
        keys = await self.redis.keys(pattern)
        return [k.split(':')[-1] for k in keys]

    # Presença (Online/Offline)
    async def set_user_online(self, user_id: str, status: str = "online"):
        """Marca usuário como online"""
        if self.redis is None:
            await self.connect()

        await self.redis.setex(f"presence:{user_id}", 300, status)  # 5 min TTL

    async def set_user_offline(self, user_id: str):
        """Marca usuário como offline"""
        if self.redis is None:
            await self.connect()

        await self.redis.delete(f"presence:{user_id}")

    async def is_user_online(self, user_id: str) -> bool:
        """Verifica se usuário está online"""
        if self.redis is None:
            await self.connect()

        return await self.redis.exists(f"presence:{user_id}") > 0

    async def get_user_status(self, user_id: str) -> str:
        """Retorna status do usuário (online/offline/away/busy)"""
        if self.redis is None:
            await self.connect()

        status = await self.redis.get(f"presence:{user_id}")
        return status if status else "offline"

    # --- Fila de mensagens não entregues

    async def queue_message(self, user_id: str, message_data: dict):
        """Adiciona mensagem na fila do usuário offline"""
        if self.redis is None:
            await self.connect()

        key = f"queue:{user_id}"
        await self.redis.lpush(key, json.dumps(message_data))
        await self.redis.expire(key, settings.MESSAGE_QUEUE_RETENTION)

    async def get_queued_messages(self, user_id: str) -> list[dict]:
        """Busca todas as mensagens enfileiradas"""
        if self.redis is None:
            await self.connect()

        key = f"queue:{user_id}"
        messages = await self.redis.lrange(key, 0, -1)
        await self.redis.delete(key) # Limpa a fila

        return [json.loads(m) for m in messages]

    # --- Rate Limiting
    async def check_rate_limit(self, user_id: str, limit: int, window: int = 60) -> bool:
        """
        Verifica se usuário excedeu rate limit
        Args:
            user_id: ID do usuário
            limit: Número máximo de requisições
            window: Janela de tempo em segundos
        Returns:
            True se pode prosseguir, False se excedeu limite
        """
        if self.redis is None:
            await self.connect()

        key = f"ratelimit:{user_id}"
        current = await self.redis.get(key)

        if current is None:
            await self.redis.setex(key, window, 1)
            return True

        if int(current) >= limit:
            return False

        await self.redis.incr(key)
        return True

    # --- Typing Indicators
    async def set_typing(self, room_id: str, user_id: str, ttl: int = 10):
        """Marca usuário como digitando em uma sala"""
        if self.redis is None:
            await self.connect()

        key = f"typing:{room_id}"
        await self.redis.sadd(key, user_id)
        await self.redis.expire(key, ttl)

    async def remove_typing(self, room_id: str, user_id: str):
        """Remove indicador de digitação"""
        if self.redis is None:
            await self.connect()

        key = f"typing:{room_id}"
        await self.redis.srem(key, user_id)

    async def get_typing_users(self, room_id: str) -> list[str]:
        """Retorna lista de usuários digitando"""
        if self.redis is None:
            await self.connect()

        key = f"typing:{room_id}"
        return list(await self.redis.smembers(key))

    # -- Room Membership Cache
    async def cache_room_members(self, room_id: str, member_ids: list[str], ttl: int = 300):
        """Cacheia membros de uma sala"""
        if self.redis is None:
            await self.connect()

        key = f"room_members:{room_id}"
        await self.redis.delete(key)  # Limpa cache antigo
        if member_ids:
            await self.redis.sadd(key, *member_ids)
            await self.redis.expire(key, ttl)

    async def get_cached_room_members(self, room_id: str) -> Optional[list[str]]:
        """Busca membros cacheados"""
        if self.redis is None:
            await self.connect()

        key = f"room_members:{room_id}"
        if await self.redis.exists(key):
            return list(await self.redis.smembers(key))
        return None


# Singleton
redis_client = RedisClient()