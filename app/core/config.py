from functools import lru_cache
from urllib.parse import urlparse

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_HOSTS = {"your-api-domain.com"}


def _validate_public_http_url(
    value: str,
    field_name: str,
    *,
    reject_placeholders: bool,
) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL.")

    host = (parsed.hostname or "").lower()
    if reject_placeholders and host in PLACEHOLDER_HOSTS:
        raise ValueError(
            f"{field_name} points to placeholder host '{host}'. Set a real public URL."
        )


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

    # Google OAuth
    google_client_id: str | None = Field(None, env="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(None, env="GOOGLE_CLIENT_SECRET")

    # AI / Embedding (Layer 2 & 3)
    openai_api_key: str | None = Field(None, env="OPENAI_API_KEY")
    encryption_key: str | None = Field(None, env="ENCRYPTION_KEY")
    embedding_model: str = "text-embedding-3-small"
    agent_model: str = "gpt-4o-mini"

    # MCP / ChatGPT Apps integration
    mcp_shared_secret: str | None = Field(None, env="MCP_SHARED_SECRET")
    mcp_public_base_url: str | None = Field(None, env="MCP_PUBLIC_BASE_URL")
    chatgpt_widget_base_url: str | None = Field(None, env="CHATGPT_WIDGET_BASE_URL")
    chatgpt_widget_js_url: str | None = Field(None, env="CHATGPT_WIDGET_JS_URL")
    chatgpt_widget_css_url: str | None = Field(None, env="CHATGPT_WIDGET_CSS_URL")

    @model_validator(mode="after")
    def validate_settings(self):
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

        if bool(self.chatgpt_widget_js_url) != bool(self.chatgpt_widget_css_url):
            raise ValueError(
                "CHATGPT_WIDGET_JS_URL and CHATGPT_WIDGET_CSS_URL must be set together."
            )

        base_urls = {
            "MCP_PUBLIC_BASE_URL": self.mcp_public_base_url,
            "CHATGPT_WIDGET_BASE_URL": self.chatgpt_widget_base_url,
        }
        for field_name, value in base_urls.items():
            if value:
                _validate_public_http_url(
                    value, field_name, reject_placeholders=False
                )

        explicit_asset_urls = {
            "CHATGPT_WIDGET_JS_URL": self.chatgpt_widget_js_url,
            "CHATGPT_WIDGET_CSS_URL": self.chatgpt_widget_css_url,
        }
        for field_name, value in explicit_asset_urls.items():
            if value:
                _validate_public_http_url(
                    value, field_name, reject_placeholders=True
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
