from functools import lru_cache

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "fastapi-starter-kit"
    
    # Supabase configuration (required)
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_service_key: str = Field(..., env="SUPABASE_SERVICE_KEY")
    supabase_anon_key: str | None = Field(None, env="SUPABASE_ANON_KEY")
    
    # JWT configuration
    jwt_secret: str = Field(..., env="JWT_SECRET")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Email configuration
    resend_api_key: str | None = None
    resend_from_email: EmailStr | None = None
    magic_link_base_url: str | None = None
    skip_emails: bool = Field(False, env="SKIP_EMAILS")

    @model_validator(mode="after")
    def validate_supabase(self):
        if not self.supabase_url or not self.supabase_service_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are required. "
                "Get these from your Supabase project settings."
            )
        
        if not self.supabase_url.endswith(".supabase.co"):
            raise ValueError(
                "SUPABASE_URL must be a valid Supabase project URL "
                "(e.g., https://<project>.supabase.co)"
            )
        
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
