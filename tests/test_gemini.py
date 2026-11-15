"""Gemini hívás: újrapróbálás és modellváltás túlterhelésnél (hálózat nélkül, ál-szerverrel)."""
import asyncio
import json

import httpx
import pytest

from app.services import gemini

OK_BODY = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
SETTINGS = {"gemini_api_key": "AIzaTEST", "gemini_model": "gemini-flash-latest"}


def run(responses: dict[str, list[int]]):
    """responses: modellnév -> egymás utáni HTTP státuszkódok."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = request.url.path.split("/models/")[1].split(":")[0]
        calls.append(model)
        codes = responses.get(model, [404])
        code = codes.pop(0) if len(codes) > 1 else codes[0]
        return httpx.Response(code, json=OK_BODY if code == 200 else {"error": {"message": "x"}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await gemini.generate(SETTINGS, [{"text": "hi"}], schema={"type": "OBJECT"}, client=client)

    return asyncio.run(go()), calls


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(gemini, "RETRY_DELAY_S", 0)


def test_retry_once_on_503_then_success():
    result, calls = run({"gemini-flash-latest": [503, 200]})
    assert result == {"ok": True}
    assert calls == ["gemini-flash-latest", "gemini-flash-latest"]


def test_falls_back_to_next_model_when_overloaded():
    result, calls = run({"gemini-flash-latest": [503], "gemini-2.5-flash": [200]})
    assert result == {"ok": True}
    assert calls == ["gemini-flash-latest", "gemini-flash-latest", "gemini-2.5-flash"]


def test_falls_back_on_quota_429():
    result, calls = run({"gemini-flash-latest": [429], "gemini-2.5-flash": [429], "gemini-2.5-flash-lite": [200]})
    assert result == {"ok": True}
    assert calls[-1] == "gemini-2.5-flash-lite"


def test_all_overloaded_gives_friendly_message():
    with pytest.raises(gemini.GeminiError, match="túlterhelt"):
        run({"gemini-flash-latest": [503], "gemini-2.5-flash": [503], "gemini-2.5-flash-lite": [503]})


def test_bad_key_does_not_try_other_models():
    with pytest.raises(gemini.GeminiError, match="kulcs"):
        _, calls = run({"gemini-flash-latest": [403]})
