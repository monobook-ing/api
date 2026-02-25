from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
import app.main as main_app
import app.mcp.server as mcp_server


def _settings_kwargs() -> dict[str, str]:
    return {
        "supabase_url": "https://demo.supabase.co",
        "supabase_service_key": "service-key",
        "jwt_secret": "jwt-secret",
    }


def _run(coro):
    return asyncio.run(coro)


def test_settings_accepts_explicit_widget_asset_urls():
    settings = Settings(
        **_settings_kwargs(),
        chatgpt_widget_js_url="https://static.example.com/widgets/chatgpt-widget.js",
        chatgpt_widget_css_url="https://static.example.com/widgets/chatgpt-widget.css",
    )

    assert settings.chatgpt_widget_js_url is not None
    assert settings.chatgpt_widget_css_url is not None


def test_settings_rejects_single_explicit_widget_asset_url():
    with pytest.raises(ValidationError, match="must be set together"):
        Settings(
            **_settings_kwargs(),
            chatgpt_widget_js_url="https://static.example.com/widgets/chatgpt-widget.js",
        )


def test_settings_rejects_placeholder_widget_url():
    with pytest.raises(ValidationError, match="placeholder host"):
        Settings(
            **_settings_kwargs(),
            chatgpt_widget_js_url="https://your-api-domain.com/widgets/chatgpt-widget.js",
            chatgpt_widget_css_url="https://static.example.com/widgets/chatgpt-widget.css",
        )


def test_widget_assets_prefer_explicit_urls(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url="https://static.example.com/widgets/widget.js",
            chatgpt_widget_css_url="https://static.example.com/widgets/widget.css",
            chatgpt_widget_base_url="https://legacy.example.com",
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    css_url, js_url = mcp_server.get_widget_asset_urls()
    assert css_url == "https://static.example.com/widgets/widget.css"
    assert js_url == "https://static.example.com/widgets/widget.js"


def test_widget_assets_fall_back_to_legacy_base_url(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url=None,
            chatgpt_widget_css_url=None,
            chatgpt_widget_base_url="https://legacy.example.com/base",
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    css_url, js_url = mcp_server.get_widget_asset_urls()
    assert css_url == "https://legacy.example.com/base/apps/chatgpt-widget.css"
    assert js_url == "https://legacy.example.com/base/apps/chatgpt-widget.js"


def test_widget_assets_reject_partial_explicit_urls(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url="https://static.example.com/widgets/widget.js",
            chatgpt_widget_css_url=None,
            chatgpt_widget_base_url="https://legacy.example.com",
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    with pytest.raises(ValueError, match="must be set together"):
        mcp_server.get_widget_asset_urls()


def test_resource_meta_includes_asset_origins(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url="https://static.example.com/widgets/widget.js",
            chatgpt_widget_css_url="https://static.example.com/widgets/widget.css",
            chatgpt_widget_base_url=None,
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    meta = mcp_server._resource_meta("desc")
    domains = meta["openai/widgetCSP"]["resource_domains"]
    assert "https://api.example.com" in domains
    assert "https://static.example.com" in domains
    assert meta["openai/widgetDomain"] == "https://api.example.com"


def test_render_widget_html_uses_external_asset_tags(monkeypatch):
    css_url = "https://static.example.com/widgets/widget.css"
    js_url = "https://static.example.com/widgets/widget.js"
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url=js_url,
            chatgpt_widget_css_url=css_url,
            chatgpt_widget_base_url=None,
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    html = mcp_server._render_widget_html("search_hotels")

    assert f"<link rel='stylesheet' href='{css_url}' />" in html
    assert f"<script type='module' src='{js_url}'></script>" in html
    assert "<style>" not in html
    assert '<script id=\'monobook-widget-bootstrap\' type=\'application/json\'>{"widget": "search_hotels"}</script>' in html


def test_widget_resources_embed_distinct_widget_bootstrap_values(monkeypatch):
    css_url = "https://static.example.com/widgets/widget.css"
    js_url = "https://static.example.com/widgets/widget.js"
    monkeypatch.setattr(
        mcp_server,
        "settings",
        SimpleNamespace(
            chatgpt_widget_js_url=js_url,
            chatgpt_widget_css_url=css_url,
            chatgpt_widget_base_url=None,
            mcp_public_base_url="https://api.example.com",
            mcp_shared_secret=None,
            openai_api_key=None,
        ),
    )

    hotels_html = mcp_server.mcp_search_hotels_widget()
    rooms_html = mcp_server.mcp_search_rooms_widget()

    assert '{"widget": "search_hotels"}' in hotels_html
    assert '{"widget": "search_rooms"}' in rooms_html
    assert f"<script type='module' src='{js_url}'></script>" in hotels_html
    assert f"<script type='module' src='{js_url}'></script>" in rooms_html


def _build_async_client(status_by_method_and_url: dict[tuple[str, str], int]):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return None

        async def head(self, url: str, follow_redirects: bool = True):
            del follow_redirects
            return SimpleNamespace(status_code=status_by_method_and_url.get(("HEAD", url), 500))

        async def get(self, url: str, follow_redirects: bool = True):
            del follow_redirects
            return SimpleNamespace(status_code=status_by_method_and_url.get(("GET", url), 500))

    return FakeAsyncClient


def test_validate_widget_runtime_assets_passes_on_head_success(monkeypatch):
    css_url = "https://static.example.com/widgets/widget.css"
    js_url = "https://static.example.com/widgets/widget.js"
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_css_url", css_url)
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_js_url", js_url)
    monkeypatch.setattr(main_app, "get_widget_asset_urls", lambda: (css_url, js_url))
    monkeypatch.setattr(
        main_app.httpx,
        "AsyncClient",
        _build_async_client(
            {
                ("HEAD", css_url): 200,
                ("HEAD", js_url): 204,
            }
        ),
    )

    _run(main_app.validate_widget_runtime_assets())


def test_validate_widget_runtime_assets_uses_get_fallback(monkeypatch):
    css_url = "https://static.example.com/widgets/widget.css"
    js_url = "https://static.example.com/widgets/widget.js"
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_css_url", css_url)
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_js_url", js_url)
    monkeypatch.setattr(main_app, "get_widget_asset_urls", lambda: (css_url, js_url))
    monkeypatch.setattr(
        main_app.httpx,
        "AsyncClient",
        _build_async_client(
            {
                ("HEAD", css_url): 405,
                ("GET", css_url): 200,
                ("HEAD", js_url): 200,
            }
        ),
    )

    _run(main_app.validate_widget_runtime_assets())


def test_validate_widget_runtime_assets_fails_when_unreachable(monkeypatch):
    css_url = "https://static.example.com/widgets/widget.css"
    js_url = "https://static.example.com/widgets/widget.js"
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_css_url", css_url)
    monkeypatch.setattr(main_app.settings, "chatgpt_widget_js_url", js_url)
    monkeypatch.setattr(main_app, "get_widget_asset_urls", lambda: (css_url, js_url))
    monkeypatch.setattr(
        main_app.httpx,
        "AsyncClient",
        _build_async_client(
            {
                ("HEAD", css_url): 503,
                ("GET", css_url): 404,
                ("HEAD", js_url): 200,
            }
        ),
    )

    with pytest.raises(RuntimeError, match="Widget runtime asset validation failed"):
        _run(main_app.validate_widget_runtime_assets())
