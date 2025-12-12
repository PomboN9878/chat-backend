"""
Pydantic Models - Validação de dados
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

# MENSAGENS

class MessageCreate(BaseModel):
    """Dados para criar mensagem"""
    room_id: str
    content: Optional[str] = None
    message_type: str = "text"
    reply_to: Optional[str] = None


class MessageUpdate(BaseModel):
    """Dados para editar mensagem"""
    message_id: str
    content: str


class MessageDelete(BaseModel):
    """Dados para deletar mensagem"""
    message_id: str


class MessageResponse(BaseModel):
    """Resposta de mensagem"""
    id: str
    room_id: str
    sender_id: str
    content: Optional[str]
    message_type: str
    reply_to: Optional[str]
    is_edited: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    # Dados do sender (join)
    sender_username: Optional[str] = None
    sender_display_name: Optional[str] = None
    sender_avatar: Optional[str] = None


# ROOMS

class RoomJoin(BaseModel):
    """Dados para entrar em sala"""
    room_id: str


class RoomLeave(BaseModel):
    """Dados para sair de sala"""
    room_id: str


class RoomCreate(BaseModel):
    """Dados para criar sala/grupo"""
    name: Optional[str] = None
    description: Optional[str] = None
    room_type: str = "group"  # direct, group, channel
    member_ids: List[str] = []


# TYPING INDICATORS

class TypingStart(BaseModel):
    """Usuário começou a digitar"""
    room_id: str


class TypingStop(BaseModel):
    """Usuário parou de digitar"""
    room_id: str


# PRESENCE

class PresenceUpdate(BaseModel):
    """Atualização de status"""
    status: str = Field(..., pattern="^(online|offline|away|busy)$")


# NOTIFICAÇÕES

class NotificationCreate(BaseModel):
    """Criar notificação"""
    user_id: str
    title: str
    body: Optional[str] = None
    notification_type: str
    reference_id: Optional[str] = None


# FILE UPLOAD

class FileUploadComplete(BaseModel):
    """Metadados de arquivo após upload"""
    room_id: str
    file_name: str
    file_type: str
    file_size: int
    storage_path: str
    mime_type: Optional[str] = None
    thumbnail_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None