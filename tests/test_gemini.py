"""Gemini hívás: újrapróbálás, modellváltás és elérhető modellek felderítése (ál-szerverrel)."""
import asyncio
import json

import httpx
import pytest

from app.services import gemini

OK_BODY = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
AVAILABLE = [
    "models/gemini-3.6-flash", "models/gemini-3.5-flash-lite", "models/gemini-embedding-001",
    "models/gemini-3.8-pro-preview", "models/gemini-3.6-flash-image",
]


def run(responses: dict[str, list[int]], model: str = "gemini-flash-latest"):
    """responses: modellnév -> egymás utáni HTTP státuszkódok (ismeretlen modell: 404)."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":  # modellek listája
            calls.append("LIST")
            return httpx.Response(200, json={"models": [
                {"name": n, "supportedGenerationMethods": ["embedContent"] if "embedding" in n else ["generateContent"]}
                for n in AVAILABLE]})
        name = request.url.path.split("/models/")[1].split(":")[0]
        calls.append(name)
        codes = responses.get(name, [404])
        code = codes.pop(0) if len(codes) > 1 else codes[0]
        return httpx.Response(code, json=OK_BODY if code == 200 else {"error": {"message": "x"}})

    async def go():
        settings = {"gemini_api_key": "AIzaTEST", "gemini_model": model}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await gemini.generate(settings, [{"text": "hi"}], schema={"type": "OBJECT"}, client=client)

    return asyncio.run(go()), calls


@pytest.fixture(autouse=True)
def setup(fresh_db, monkeypatch):
    monkeypatch.setattr(gemini, "RETRY_DELAY_S", 0)


def test_rank_models_prefers_stable_flash_and_skips_non_text():
    ranked = gemini.rank_models([n.removeprefix("models/") for n in AVAILABLE])
    assert ranked[0] == "gemini-3.6-flash"
    assert "gemini-embedding-001" not in ranked and "gemini-3.6-flash-image" not in ranked
    assert ranked.index("gemini-3.5-flash-lite") < ranked.index("gemini-3.8-pro-preview")


def test_retry_once_on_503_then_success():
    result, calls = run({"gemini-flash-latest": [503, 200]})
    assert result == {"ok": True}
    assert calls == ["gemini-flash-latest", "gemini-flash-latest"]


def test_falls_back_to_next_model_when_overloaded():
    result, calls = run({"gemini-flash-latest": [503], "gemini-flash-lite-latest": [200]})
    assert result == {"ok": True}
    assert calls[-1] == "gemini-flash-lite-latest"
    assert gemini.LAST_MODEL == "gemini-flash-lite-latest"


def test_discovers_available_models_when_names_are_retired():
    from app import db

    # a beállított és a tartalék nevek már nem léteznek (404) -> lekéri a listát, és azzal megy
    result, calls = run({"gemini-3.6-flash": [200]}, model="gemini-2.5-flash")
    assert result == {"ok": True}
    assert "LIST" in calls and calls[-1] == "gemini-3.6-flash"
    # a működő modellt elmenti, hogy legközelebb azzal induljon
    assert db.get_setting("gemini_model") == "gemini-3.6-flash"


def test_all_overloaded_gives_friendly_message():
    with pytest.raises(gemini.GeminiError, match="túlterhelt"):
        run({name: [503] for name in ["gemini-flash-latest", "gemini-flash-lite-latest",
                                       "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.8-pro-preview"]})


def test_bad_key_does_not_try_other_models():
    with pytest.raises(gemini.GeminiError, match="kulcs"):
        run({"gemini-flash-latest": [403]})
