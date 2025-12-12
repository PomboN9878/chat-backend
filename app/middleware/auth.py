"""
Middleware de Autenticação - Validação de JWT do Supabase
"""
from jose import jwt, JWTError
from typing import Optional
from app.config import settings

def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Valida token JWT do Supabase

    Args:
        token: JWT token (access_token do Supabase Auth)

    Returns:
        dict com user_id e email se válido, None se inválido
    """
    try:
        # Decodifica e valida o token
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False
            }
        )

        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")

        if not user_id:
            return None

        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "payload": payload
        }

    except JWTError as e:
        print(f" JWT Validation error: {e}")
        return None
    except Exception as e:
        print(f" Unexpected error validating JWT: {e}")
        return None

def extract_token_from_handshake(auth_data: dict) -> Optional[str]:
    """
        Extrai token do handshake do Socket.IO

        Aceita token em:
        - auth.token
        - query params: ?token=xxx
        - headers: Authorization: Bearer xxx
        """
    # 1. Tentar pegar do auth object
    if "token" in auth_data:
        return auth_data["token"]

    # 2. Tentar pegar de Authorization header
    if "Authorization" in auth_data:
        auth_header = auth_data["Authorization"]
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

    return None