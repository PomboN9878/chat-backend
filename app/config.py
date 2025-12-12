"""
Configurações do Backend - Chat em Tempo Real
Carrega variáveis de ambiente e valida configurações
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do .env"""

    # App
    APP_NAME: str = "Chat Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "*"  # Em produção, especifique domínios: "https://app.com,https://admin.app.com"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str  # anon/public key
    SUPABASE_SERVICE_KEY: str  # service_role key (para operações admin)
    SUPABASE_JWT_SECRET: str  # JWT secret para validar tokens

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_PASSWORD: str | None = None

    # Rate Limiting
    MAX_MESSAGES_PER_MINUTE: int = 30
    MAX_CONNECTIONS_PER_IP: int = 5

    # Message Queue
    MESSAGE_QUEUE_RETENTION: int = 86400  # 24h em segundos

    # Socket.IO
    SOCKETIO_PING_TIMEOUT: int = 60
    SOCKETIO_PING_INTERVAL: int = 25

    # Typing Indicator
    TYPING_TIMEOUT: int = 10  # segundos até limpar typing indicator

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Singleton para settings (cache)"""
    return Settings()


settings = get_settings()