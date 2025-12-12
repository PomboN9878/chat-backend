"""
Socket.IO Eventes Handlers - Gerencia todos os eventso de WebSocket
"""

import socketio

from app.middleware.auth import extract_token_from_handshake, verify_jwt_token
from app.database.redis_client import redis_client
from app.database.supabase import supabase_client
from app.services.message import MessageService
from app.services.presence import PresenceService
from app.services.notification import NotificaitonService
from app.config import settings

# Armaena user_id -> socket_id mapping
connected_user = {}

def register_socket_events(sio: socketio.AsyncServer):
    """Registra todos os event handlers do Socket.IO"""
    # CONEXÃO E AUTENTICAÇÃO

    @sio.event
    async def connect(sid, envrion, auth):
        """Cliente conectou - validar JWT"""
        print(f" Connection attempt: {sid}")

        # Extrair token do handshake
        token = extract_token_from_handshake(auth or {})

        if not token:
            print(f"No token provided: {sid}")
            await sio.disconnect(sid)
            return False

        # validar token
        user_data = verify_jwt_token(token)
        if not user_data:
            print(f"Invalid Token: {sid}")
            await sio.disconnect(sid)
            return False

        user_id = user_data["user_id"]

        # Salvar sessão no Redis
        await redis_client.set_user_session(user_id, sid, user_data)

        # Atualizar presença
        await PresenceService.set_online(user_id, "online")

        # Mapear user_id -> socket_id
        if user_id not in connected_user:
            connected_user[user_id] = []
        connected_user[user_id].append(sid)

        print(f"User connected: {user_id} ({sid})")

        # Enciar mesnagens enfileiradas (caso tenho ficado offline)
        queued_messages = await redis_client.get_queued_messages(user_id)
        if queued_messages:
            for msg in queued_messages:
                await sio.emit('message', msg, room=sid)
            print(f"Delivered {len(queued_messages)} queued messages to {user_id}")

        # Notificar outros usuarios que este user ficou online
        await sio.emit('user_online', {'user_id': user_id}, skip_sid=sid)

        return True

    @sio.event
    async def disconnect(sid):
        """Cliente desconectou"""
        print(f"Disconnect: {sid}")

        # Buscar user_id da sessão
        user_id = None
        for uid, sockets in connected_user.items():
            if sid in sockets:
                user_id = uid
                sockets.romove(sid)
                if not sockets:
                    del connected_user[uid]
                break

        if user_id:
            # Remvoer sessão do Redis
            await redis_client.delete_user_session(user_id, sid)

            # Se não tem mais sockets conectaos, marcar como offline
            if user_id not in connected_user or not connected_user[user_id]:
                await PresenceService.set_offline(user_id)
                await sio.emit('user_offline', {'user_id': user_id})
                print(f"User offline: {user_id}")


    # --- Salas (Rooms)
    @sio.event
    async def join_room(sid, data):
        """Entrar em uma sala"""
        try:
            room_id = data.get('room_id')
            if not room_id:
                await sio.emit('error', {'message': 'room_id required'}, room=sid)
                return

            # Buscar user_id da sessão
            user_id = await _get_user_id_from_sid(sid)
            if not user_id:
                await sio.emit('error', {'message': 'Unauthorized'}, room=sid)
                return

            # Verificar se user é membro da sala
            is_member = await _check_room_membership(user_id, room_id)
            if not is_member:
                await sio.emit('error', {'message': 'Not a member of this room'}, room=sid)
                return

            # Entrar na sala(Socket.IO room)
            sio.enter_room(sid, room_id)

            # Notificar outros na sala
            await sio.emit('user_joined_room', {
                'user_id': user_id,
                'room_id': room_id
            }, room=room_id, skip_sid=sid)

            # Confirmar para o cliente
            await sio.emit('room_joined', {'room_id': room_id}, room_id)

            print(f"User {user_id} joined room {room_id}")

        except Exception as e:
            print(f"Error joining room: {e}")
            await sio.emit('error', {'message': str(e)}, room=sid)

    @sio.event
    async def leave_room(sid, data):
        """Sair de uma sala"""
        try:
            room_id = data.get('room_id')
            if not room_id:
                return

            user_id = await _get_user_id_from_sid(sid)

            # Sair da sala
            sio.leave_room(sid, room_id)

            # Notificar outros
            if user_id:
                await sio.emit('user_left_room', {
                    'user_id': user_id,
                    'room_id': room_id
                }, room=room_id)

            print(f"🚪 User {user_id} left room {room_id}")

        except Exception as e:
            print(f"❌ Error leaving room: {e}")

    # --- Mensagens

    @sio.event
    async def send_message(sid, data):
        """Enviar mensagem"""
        try:
            # Validar dados
            room_id = data.get('room_id')
            content = data.get('content')
            message_type = data.get('message_type', 'text')
            reply_to = data.get('reply_to')

            if not room_id:
                await sio.emit('error', {'message': 'room_id required'}, room=sid)
                return

            # Buscar user_id
            user_id = await _get_user_id_from_sid(sid)
            if not user_id:
                await sio.emit('error', {'message': 'Unauthorized'}, room=sid)
                return

            # Rate limiting
            can_send = await redis_client.check_rate_limit(
                user_id,
                settings.MAX_MESSAGES_PER_MINUTE
            )
            if not can_send:
                await sio.emit('error', {'message': 'Rate limit exceeded'}, room=sid)
                return

            # Verificar membership
            is_member = await _check_room_membership(user_id, room_id)
            if not is_member:
                await sio.emit('error', {'message': 'Not a member'}, room=sid)
                return

            # Salvar mensagem no banco
            message = await MessageService.create_message(
                room_id=room_id,
                sender_id=user_id,
                content=content,
                message_type=message_type,
                reply_to=reply_to
            )

            if not message:
                await sio.emit('error', {'message': 'Failed to save message'}, room=sid)
                return

            # Broadcast para todos na sala
            await sio.emit('message', message, room=room_id)

            # Enviar notificações para membros offline
            await _notify_offline_members(room_id, user_id, message)

            print(f"Message sent in room {room_id} by {user_id}")

        except Exception as e:
            print(f"Error sending message: {e}")
            await sio.emit('error', {'message': str(e)}, room=sid)

    @sio.event
    async def edit_message(sid, data):
        """Editar mensagem"""
        try:
            message_id = data.get('message_id')
            content = data.get('content')

            if not message_id or not content:
                await sio.emit('error', {'message': 'message_id and content required'}, room=sid)
                return

            user_id = await _get_user_id_from_sid(sid)

            # Editar no banco
            updated_message = await MessageService.edit_message(message_id, user_id, content)

            if not updated_message:
                await sio.emit('error', {'message': 'Failed to edit'}, room=sid)
                return

            # Broadcast atualização
            room_id = updated_message['room_id']
            await sio.emit('message_edited', updated_message, room=room_id)

            print(f"Message {message_id} edited")

        except Exception as e:
            print(f"Error editing message: {e}")
            await sio.emit('error', {'message': str(e)}, room=sid)

    @sio.event
    async def delete_message(sid, data):
        """Deletar mensagem"""
        try:
            message_id = data.get('message_id')

            if not message_id:
                await sio.emit('error', {'message': 'message_id required'}, room=sid)
                return

            user_id = await _get_user_id_from_sid(sid)

            # Deletar (soft delete)
            result = await MessageService.delete_message(message_id, user_id)

            if not result:
                await sio.emit('error', {'message': 'Failed to delete'}, room=sid)
                return

            # Broadcast
            room_id = result['room_id']
            await sio.emit('message_deleted', {
                'message_id': message_id,
                'room_id': room_id
            }, room=room_id)

            print(f"Message {message_id} deleted")

        except Exception as e:
            print(f"Error deleting message: {e}")

    # --- Typing Indicators
    @sio.event
    async def typing_start(sid, data):
        """Usuario começou a digitar"""
        try:
            room_id = data.get('room_id')
            if not room_id:
                return

            user_id = await _get_user_id_from_sid(sid)
            if not user_id:
                return

            # Salvar no Redis (TTLS 10s)
            await redis_client.set_typing(room_id, user_id, settings.TYPING_TIMEOUT)

            # Notificar outros na sala
            await sio.emit('user_typing', {
                'user_id': user_id,
                'room_id': room_id
            }, room=room_id, skip_sid=sid)

        except Exception as e:
            print(f"Error in typing_start: {e}")

    @sio.event
    async def typing_stop(sid, data):
        """Usuário parou de digitar"""
        try:
            room_id = data.get('room_id')
            if not room_id:
                return

            user_id = await _get_user_id_from_sid(sid)
            if not user_id:
                return

            # Remover do Redis
            await redis_client.remove_typing(room_id, user_id)

            # Notificar outros
            await sio.emit('user_stopped_typing', {
                'user_id': user_id,
                'room_id': room_id
            }, room=room_id, skip_sid=sid)

        except Exception as e:
            print(f"❌ Error in typing_stop: {e}")

    # --- Presence / Status
    @sio.event
    async def update_status(sid, data):
        """Atualizar status (online/away/busy)"""
        try:
            status = data.get('status', 'online')

            if status not in ['online', 'offline', 'away', 'busy']:
                await sio.emit('error', {'message': 'Invalid status'}, room=sid)
                return

            user_id = await _get_user_id_from_sid(sid)
            if not user_id:
                return

            # Atualizar no Redis e banco
            await PresenceService.update_status(user_id, status)

            # Broadcast
            await sio.emit('user_status_changed', {
                'user_id': user_id,
                'status': status
            }, skip_sid=sid)

            print(f"User {user_id} status: {status}")

        except Exception as e:
            print(f"Error updating status: {e}")

    # --- File Upload (metadados apos upload no Storage)
    async def file_uploaded(sid, data):
        """Cliente fez upload de arquivo no storage - salvar metadados"""
        try:
            room_id = data.get('room_id')
            file_name = data.get('file_name')
            storage_path = data.get('storage_path')
            file_size = data.get('file_size')
            file_type = data.get('file_type', 'document')

            user_id = await _get_user_id_from_sid(sid)

            # Criar mensagem com anexo
            message = await MessageService.create_message_with_attachment(
                room_id=room_id,
                sender_id=user_id,
                file_name=file_name,
                storage_path=storage_path,
                file_size=file_size,
                file_type=file_type,
                mime_type=data.get('mime_type'),
                thumbnail_path=data.get('thumbnail_path'),
                width=data.get('width'),
                height=data.get('height'),
                duration=data.get('duration')
            )

            # Broadcast
            await sio.emit('message', message, room=room_id)
            print(f"File uploaded in room {room_id}")

        except Exception as e:
            print(f"Error in file_uploaded: {e}")
            await sio.emit('error', {'message': str(e)}, room=sid)


# === Helper Functions
async def _get_user_id_from_sid(sid: str) -> str | None:
    """Busca user_id pelo socket_id"""
    for user_id, sockets in connected_user.items():
        if sid in sockets:
            return user_id

    return None

async def _check_room_membership(user_id: str, room_id: str) -> bool:
    """Verifica se user é membro da sala"""
    try:
        # Tenta buscar do cache Redis
        cached_members = await redis_client.get_cached_room_members(room_id)
        if cached_members:
            return user_id in cached_members

        # Buscar do banco
        db = supabase_client.get_admin()
        result = db.table('room_members').select('user_id').eq('room_id', room_id).eq('user_id', user_id).execute()

        is_member = len(result.data) > 0

        # Cachear membros da sala
        if is_member:
            all_members = db.table('room_members').select('user_id').eq('room_id', room_id).execute()
            member_ids = [m['user_id'] for m in all_members.data]
            await redis_client.cache_room_members(room_id, member_ids)

        return is_member

    except Exception as e:
        print(f"Error checking membership: {e}")
        return False

async def _notify_offline_members(room_id: str, sender_id: str, message: dict):
    """Envia notificações para membros offline"""
    try:
        # Buscar membros da sala
        db = supabase_client.get_admin()
        members = db.table('room_members').select('user_id').eq('room_id', room_id).neq('user_id', sender_id).execute()

        for member in members.data:
            member_id = member['user_id']

            # Verifica se está online
            is_online = await redis_client.is_user_online(member_id)

            if not is_online:
                # Enfileirar mensagem
                await redis_client.queue_message(member_id, message)

                # Criar notificações no banco
                await NotificaitonService.create_notification(
                    user_id=member_id,
                    title="Nova mensagem",
                    body=message.get('content', 'Arquivo'),
                    notification_type='new_message',
                    reference_id=message['id']
                )

    except Exception as e:
        print(f"Error notifying offline members: {e}")