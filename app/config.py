import os
from pydantic import BaseModel



class Settings(BaseModel):
    jwt_secret_key: str = os.getenv("JWT_SECRET", "dev_secret_key_change_in_production")
    db_host: str = os.getenv("DB_HOST", "swecc-db-instance")
    db_port: int = int(os.getenv("DB_PORT", 5432))
    db_name: str = os.getenv("DB_NAME", "swecc")
    db_user: str = os.getenv("DB_USER", "swecc")
    db_password: str = os.getenv("DB_PASSWORD", "swecc")

    jwt_algorithm: str = "HS256"
    
    host: str = "0.0.0.0"
    port: int = 8004
    
    redis_host: str = "swecc-redis-instance"
    redis_port: int = 6379

    cors_origins: list[str] = [
        "http://localhost:8000",
        "http://localhost:80",
        "http://localhost:3000",
        "http://api.swecc.org",
    ]



settings = Settings()