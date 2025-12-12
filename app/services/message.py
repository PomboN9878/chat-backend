"""
Message Service - Lógica de negócio para mensagens
"""
from typing import Optional
from datetime import datetime
from app.database.supabase import supabase_client

class MessageService:
    """Service para operações de mensagens"""

    @staticmethod
    async def create_message(
            room_id: str,
            sender_id: str,
            content: Optional[str],
            message_type: str = "text",
            reply_to: Optional[str] = None
    ) -> Optional[dict]:
        """Cria nova mensgaem no banco"""
        try:
            db = supabase_client.get_admin()

            # Inserir Mensagem
            result = db.table('messages').insert({
                'room_id': room_id,
                'sender_id': sender_id,
                'content': content,
                'message_type': message_type,
                'reply_to': reply_to
            }).execute()

            if not result.data:
                return None

            message = result.data[0]

            # Buscar dados do sender
            sender = db.table('profile').select('username, display_name, avatar url').eq('id', sender_id).execute()

            if sender.data:
                message['sender_username'] = sender.data[0].get('username')
                message['sender_display_name'] = sender.data[0].get('display_name')
                message['sender_avatar'] = sender.data[0].get('avatar_url')

            return message

        except Exception as e:
            print(f"Error creating message: {e}")
            return None

    @staticmethod
    async def create_message_with_attachment(
            room_id: str,
            sender_id: str,
            file_name: str,
            storage_path: str,
            file_size: int,
            file_type: str,
            mime_type: Optional[str] = None,
            thumbnail_path: Optional[str] = None,
            width: Optional[int] = None,
            height: Optional[int] = None,
            duration: Optional[int] = None
    ) -> Optional[dict]:
        """Cria mensagem com anexo"""
        try:
            db = supabase_client.get_admin()

            # 1. Criar mensagem
            message_result = db.table('messages').insert({
                'room_id': room_id,
                'sender_id': sender_id,
                'content': None,
                'message_type': file_type
            }).execute()

            if not message_result.data:
                return None

            message = message_result.data[0]
            message_id = message['id']

            # 2. Criar attachment
            attachment = db.table('message_attachments').insert({
                'message_id': message_id,
                'file_name': file_name,
                'file_type': file_type,
                'file_size': file_size,
                'storage_path': storage_path,
                'mime_type': mime_type,
                'thumbnail_path': thumbnail_path,
                'width': width,
                'height': height,
                'duration': duration
            }).execute()

            # 3. Buscar sender data
            sender = db.table('profiles').select('username, display_name, avatar_url').eq('id', sender_id).execute()

            if sender.data:
                message['sender_username'] = sender.data[0].get('username')
                message['sender_display_name'] = sender.data[0].get('display_name')
                message['sender_avatar'] = sender.data[0].get('avatar_url')

            # Adicionar attachment data
            if attachment.data:
                message['attachment'] = attachment.data[0]

            return message

        except Exception as e:
            print(f"Error creating message with attachment: {e}")
            return None

    @staticmethod
    async def edit_message(message_id: str, user_id: str, new_content: str) -> Optional[dict]:
        """Edita mensagem (apenas o dono pode editar)"""
        try:
            db = supabase_client.get_admin()

            # Verificar se mensagem existe e pertence ao user
            check = db.table('messages').select('*').eq('id', message_id).eq('sender_id', user_id).execute()

            if not check.data:
                return None

            # Atualizar
            result = db.table('messages').update({
                'content': new_content,
                'is_edited': True,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', message_id).execute()

            if result.data:
                return result.data[0]

            return None

        except Exception as e:
            print(f"Error editing message: {e}")
            return None

    @staticmethod
    async def delete_message(message_id: str, user_id: str) -> Optional[dict]:
        """Deleta mensagem (soft delete)"""
        try:
            db = supabase_client.get_admin()

            # Verificar ownership
            check = db.table('messages').select('room_id').eq('id', message_id).eq('sender_id', user_id).execute()

            if not check.data:
                return None

            # Soft delete
            result = db.table('messages').update({
                'is_deleted': True,
                'content': None,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', message_id).execute()

            if result.data:
                return {'message_id': message_id, 'room_id': check.data[0]['room_id']}

            return None

        except Exception as e:
            print(f"Error deleting message: {e}")
            return None