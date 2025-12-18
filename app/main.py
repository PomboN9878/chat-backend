"""
FastAPI + Socket.IO - Backend de Chat em Tempo Real
Entry point da aplicação
"""
import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database.supabase import supabase_client
from app.database.redis_client import redis_client
from app.sockets.events import register_socket_events
from app.routes.rooms import router as rooms_router


# Socket.IO Server (AsyncServer para ASGI)
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.CORS_ORIGINS.split(',') if settings.CORS_ORIGINS != "*" else "*",
    logger=settings.DEBUG,
    engineio_logger=settings.DEBUG,
    ping_timeout=settings.SOCKETIO_PING_TIMEOUT,
    ping_interval=settings.SOCKETIO_PING_INTERVAL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia startup e shutdown da aplicação"""
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # Testar conexão Redis
    try:
        await redis_client.ping()
        print("Redis connected")
    except Exception as e:
        print(f"Redis connection failed: {e}")

    # Registrar eventos Socket.IO
    register_socket_events(sio)
    print("Socket.IO events registered")

    yield

    # Shutdown
    print("Shutting down...")
    await redis_client.close()
    print("Goodbye!")

# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(',') if settings.CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO
socket_app = socketio.ASGIApp(
    sio,
    other_asgi_app=app,
    socketio_path='/socket.io'
)

# Registrar rotas REST
app.include_router(rooms_router)


# Health Check
@app.get("/health")
async def health_check():
    """Endpoint de health check para Render"""
    redis_status = "connected"
    try:
        await redis_client.ping()
    except:
        redis_status = "disconnected"

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "redis": redis_status
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "socket": "/socket.io"
    }


# Exportar para uvicorn
app_instance = socket_app