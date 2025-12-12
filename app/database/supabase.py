"""
Cliente Supabase - Conexão com Postgres + Auth + Storage
"""
from supabase import create_client, Client
from app.config import settings

class SupabaseClient:
    """Wrapper para cliente SUpabse com service role"""

    def __init__(self):
        # Cliente com service_role (bypass RLS para operações admin)
        self.admin: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )

        # Cliente normal (respeita RLS)
        self.client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )

    def get_admin(self) -> Client:
        """Retorna cliente admin (service_role)"""
        return self.admin

    def get_client(self) -> Client:
        return self.client

# Singleton
supabase_client = SupabaseClient()