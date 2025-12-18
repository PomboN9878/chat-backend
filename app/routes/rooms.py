"""
REST API Endpoints - Gerenciamento de Salas e Usuários
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional, List
from app.middleware.auth import verify_jwt_token
from app.database.supabase import supabase_client
from app.database.redis_client import redis_client
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Rooms & Users"])


# --- Models

class CreateDirectChatRequest(BaseModel):
    other_user_id: str


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None
    member_ids: List[str] = ()


class AddMemberRequest(BaseModel):
    user_id: str


class UpdateRoomRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# --- Auth Dependency

async def get_current_user(authorization: str = Header(None)):
    """Extrai e valida JWT do header Authorization"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization[7:]  # Remove "Bearer "
    user_data = verify_jwt_token(token)

    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --- Usuarios
@router.get("/user/search")
async def search_users(
        query: str,
        limit: int = 20,
        current_user: dict = Depends(get_current_user)
):
    """
    Busca usuários por username ou display_name

    Query params:
    - query: termo de busca (mínimo 2 caracteres)
    - limit: máximo de resultados (padrão: 20)
    """
    if (len(query) < 2):
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    try:
        db = supabase_client.get_admin()

        # Buscar por username ou display_name
        result = db.table('profiles').select(
            'id, username, display_name, avatar_url, status'
        ).or_(
            f'username.ilike.%{query}%,display_name.ilike.%{query}%'
        ).limit(limit).execute()

        return {
            "users": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
async def get_user_profile(
        user_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Busca perfil de um usuário específico"""
    try:
        db = supabase_client.get_admin()

        result = db.table('profiles').select(
            'id, username, display_name, avatar_url, bio, status, last_seen'
        ).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        user = result.data[0]

        # Verificar se está online (Redis)
        is_online = await redis_client.is_user_online(user_id)
        user['is_online'] = is_online

        return user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/me/profile")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Retorna prefil do usuario autenticado"""
    try:
        db = supabase_client.get_admin()

        result = db.table('profiles').select('*').eq('id', current_user['user_id']).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Chat Direto (1:1)

@router.post("/rooms/direct")
async def create_direct_chat(
        request: CreateDirectChatRequest,
        current_user: dict = Depends(get_current_user)
):
    """
    Cria ou retorna sala de chat direto com outro usuário

    Se já existe uma sala direct entre os 2 usuários, retorna ela.
    Caso contrário, cria uma nova.
    """
    try:
        user_id = current_user['user_id']
        other_user_id = request.other_user_id

        if user_id == other_user_id:
            raise HTTPException(status_code=400, detail="Cannot chat with yourself")

        db = supabase_client.get_admin()

        # Verificar se outro usuário existe
        other_user = db.table('profiles').select('id').eq('id', other_user_id).execute()
        if not other_user.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Buscar sala direct existente
        # Query: salas onde ambos são membros E tipo = 'direct'
        existing = db.rpc('find_direct_room', {
            'user_a': user_id,
            'user_b': other_user_id
        }).execute()

        if existing.data:
            room_id = existing.data

            # Buscar dados completos da sala
            room = db.table('rooms').select('*').eq('id', room_id).execute()
            return room.data[0] if room.data else {"id": room_id}

        # Criar nova sala direct
        new_room = db.table('rooms').insert({
            'room_type': 'direct',
            'is_private': True,
            'created_by': user_id
        }).execute()

        if not new_room.data:
            raise HTTPException(status_code=500, detail="Failed to create room")

        room_id = new_room.data[0]['id']

        # Adicionar ambos usuários como membros
        db.table('room_members').insert([
            {'room_id': room_id, 'user_id': user_id, 'role': 'owner'},
            {'room_id': room_id, 'user_id': other_user_id, 'role': 'owner'}
        ]).execute()

        return new_room.data[0]

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating direct chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Grupos
@router.post("/rooms/group")
async def create_group(
        request: CreateGroupRequest,
        current_user: dict = Depends(get_current_user)
):
    """
    Cria um grupo/canal

    Body:
    - name: nome do grupo
    - description: descrição (opcional)
    - member_ids: lista de user_ids para adicionar (opcional)
    """
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Criar sala
        new_room = db.table('rooms').insert({
            'name': request.name,
            'description': request.description,
            'room_type': 'group',
            'is_private': True,
            'created_by': user_id
        }).execute()

        if not new_room.data:
            raise HTTPException(status_code=500, detail="Failed to create group")

        room_id = new_room.data[0]['id']

        # Adicionar criador como owner
        members_to_add = [
            {'room_id': room_id, 'user_id': user_id, 'role': 'owner'}
        ]

        # Adicionar outros membros
        for member_id in request.member_ids:
            if member_id != user_id:
                members_to_add.append({
                    'room_id': room_id,
                    'user_id': member_id,
                    'role': 'member'
                })

        db.table('room_members').insert(members_to_add).execute()

        return new_room.data[0]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms")
async def list_my_rooms(
        current_user: dict = Depends(get_current_user)
):
    """
    Lista todas as salas que o usuário é membro

    Retorna com última mensagem e contagem de não lidas
    """
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Buscar salas do usuário
        rooms_result = db.table('room_members').select(
            '''
            room_id,
            last_read_at,
            rooms!inner(
                id,
                name,
                description,
                room_type,
                avatar_url,
                created_at,
                last_message_at
            )
            '''
        ).eq('user_id', user_id).order('rooms.last_message_at', desc=True).execute()

        rooms = []

        for item in rooms_result.data:
            room = item['rooms']
            room_id = room['id']
            last_read = item['last_read_at']

            # Buscar última mensagem
            last_msg = db.table('messages').select(
                'id, content, message_type, created_at, sender_id, profiles!inner(username, display_name, avatar_url)'
            ).eq('room_id', room_id).eq('is_deleted', False).order('created_at', desc=True).limit(1).execute()

            if last_msg.data:
                room['last_message'] = last_msg.data[0]
            else:
                room['last_message'] = None

            # Contar não lidas
            unread = db.table('messages').select('id', count='exact').eq('room_id', room_id).gt('created_at',
                                                                                                last_read).neq(
                'sender_id', user_id).eq('is_deleted', False).execute()

            room['unread_count'] = unread.count if unread.count else 0

            # Para direct, buscar nome do outro usuário
            if room['room_type'] == 'direct':
                other_member = db.table('room_members').select(
                    'profiles!inner(id, username, display_name, avatar_url, status)'
                ).eq('room_id', room_id).neq('user_id', user_id).execute()

                if other_member.data:
                    other_user = other_member.data[0]['profiles']
                    room['other_user'] = other_user

                    # Usar dados do outro usuário como "nome" da sala
                    if not room['name']:
                        room['name'] = other_user['display_name']
                    if not room['avatar_url']:
                        room['avatar_url'] = other_user['avatar_url']

            rooms.append(room)

        return {"rooms": rooms, "count": len(rooms)}

    except Exception as e:
        print(f"Error listing rooms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms/{room_id}")
async def get_room_details(
        room_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Busca detalhes de uma sala específica"""
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Verificar se é membro
        membership = db.table('room_members').select('role').eq('room_id', room_id).eq('user_id', user_id).execute()

        if not membership.data:
            raise HTTPException(status_code=403, detail="Not a member of this room")

        # Buscar sala
        room = db.table('rooms').select('*').eq('id', room_id).execute()

        if not room.data:
            raise HTTPException(status_code=404, detail="Room not found")

        room_data = room.data[0]

        # Buscar membros
        members = db.table('room_members').select(
            'user_id, role, joined_at, profiles!inner(id, username, display_name, avatar_url, status)'
        ).eq('room_id', room_id).execute()

        room_data['members'] = members.data
        room_data['member_count'] = len(members.data)
        room_data['my_role'] = membership.data[0]['role']

        return room_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms/{room_id}/messages")
async def get_room_messages(
        room_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        current_user: dict = Depends(get_current_user)
):
    """
    Busca mensagens de uma sala (paginado)

    Query params:
    - limit: máximo de mensagens (padrão: 50)
    - before: timestamp ISO para paginação (busca mensagens antes deste timestamp)
    """
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Verificar se é membro
        membership = db.table('room_members').select('user_id').eq('room_id', room_id).eq('user_id', user_id).execute()

        if not membership.data:
            raise HTTPException(status_code=403, detail="Not a member of this room")

        # Buscar mensagens
        query = db.table('messages').select(
            '''
            id, content, message_type, reply_to, is_edited, created_at, updated_at,
            sender_id,
            profiles!inner(username, display_name, avatar_url),
            message_attachments(id, file_name, file_type, storage_path, mime_type, thumbnail_path, width, height, duration)
            '''
        ).eq('room_id', room_id).eq('is_deleted', False).order('created_at', desc=True).limit(limit)

        if before:
            query = query.lt('created_at', before)

        result = query.execute()

        # Reverter ordem (mais antigas primeiro)
        messages = list(reversed(result.data))

        return {
            "messages": messages,
            "count": len(messages),
            "has_more": len(result.data) == limit
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rooms/{room_id}")
async def update_room(
        room_id: str,
        request: UpdateRoomRequest,
        current_user: dict = Depends(get_current_user)
):
    """Atualiza nome/descrição da sala (apenas owner/admin)"""
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Verificar permissão (owner ou admin)
        membership = db.table('room_members').select('role').eq('room_id', room_id).eq('user_id', user_id).execute()

        if not membership.data or membership.data[0]['role'] not in ['owner', 'admin']:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Atualizar
        updates = {}
        if request.name is not None:
            updates['name'] = request.name
        if request.description is not None:
            updates['description'] = request.description

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = db.table('rooms').update(updates).eq('id', room_id).execute()

        return result.data[0] if result.data else {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rooms/{room_id}/members")
async def add_member(
        room_id: str,
        request: AddMemberRequest,
        current_user: dict = Depends(get_current_user)
):
    """Adiciona membro ao grupo (apenas owner/admin)"""
    try:
        user_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Verificar permissão
        membership = db.table('room_members').select('role').eq('room_id', room_id).eq('user_id', user_id).execute()

        if not membership.data or membership.data[0]['role'] not in ['owner', 'admin']:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Verificar se já é membro
        existing = db.table('room_members').select('user_id').eq('room_id', room_id).eq('user_id',
                                                                                        request.user_id).execute()

        if existing.data:
            raise HTTPException(status_code=400, detail="User is already a member")

        # Adicionar
        result = db.table('room_members').insert({
            'room_id': room_id,
            'user_id': request.user_id,
            'role': 'member'
        }).execute()

        return result.data[0] if result.data else {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rooms/{room_id}/members/{user_id}")
async def remove_member(
        room_id: str,
        user_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Remove membro do grupo (apenas owner/admin ou o próprio usuário pode sair)"""
    try:
        requester_id = current_user['user_id']
        db = supabase_client.get_admin()

        # Se está removendo a si mesmo, pode
        if requester_id == user_id:
            db.table('room_members').delete().eq('room_id', room_id).eq('user_id', user_id).execute()
            return {"success": True, "message": "Left room"}

        # Caso contrário, verificar permissão
        membership = db.table('room_members').select('role').eq('room_id', room_id).eq('user_id',
                                                                                       requester_id).execute()

        if not membership.data or membership.data[0]['role'] not in ['owner', 'admin']:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Remover
        db.table('room_members').delete().eq('room_id', room_id).eq('user_id', user_id).execute()

        return {"success": True, "message": "Member removed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
