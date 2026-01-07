from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise Calendar"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "supersecretkey_change_this_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    # Defaulting to a local postgres instance for development
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/calendar_db"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    # File Uploads
    UPLOAD_DIR: str = "static/uploads"

    class Config:
        env_file = ".env"

settings = Settings()
