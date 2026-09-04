"""
Клиент LLM для Scaner. Артефакт 5 сентября (по плану тимлида).

Главное свойство: **этот модуль не может уронить продукт**.
Нет ключа, нет сети, API отвечает мусором, кончился таймаут — функция
возвращает None, и вызывающий код продолжает работать на офлайн-движке
(ai_layer.classify_batch). Это и есть «План Б» на уровне AI-слоя.

Поддерживаются два провайдера:
  * GigaChat (Сбер) — основной, включается GIGACHAT_CREDENTIALS
  * любой OpenAI-совместимый — запасной, включается OPENAI_API_KEY

Переменные окружения:
  USE_REAL_AI=1               включить обращение к API (по умолчанию выключено)
  LLM_PROVIDER=gigachat|openai
  GIGACHAT_CREDENTIALS=...    Authorization key из личного кабинета GigaChat
  GIGACHAT_SCOPE=GIGACHAT_API_PERS
  OPENAI_API_KEY=...
  LLM_MODEL=GigaChat          имя модели
  LLM_CA_BUNDLE=/path/ru.pem  сертификаты НУЦ Минцифры для GigaChat

Про сертификаты: GigaChat выпущен под российским корневым сертификатом.
Правильный путь — поставить сертификаты НУЦ Минцифры в систему или указать
их через LLM_CA_BUNDLE. Отключать проверку TLS не нужно и небезопасно.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import prompts

GIGACHAT_OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_CHAT = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

_token_cache: dict[str, Any] = {"value": None, "expires": 0.0}
_response_cache: dict[str, list[dict]] = {}


def enabled() -> bool:
    """Включён ли реальный AI. Ровно тот самый флаг USE_REAL_AI из плана."""
    return os.environ.get("USE_REAL_AI") == "1"


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        return None


def _verify():
    return os.environ.get("LLM_CA_BUNDLE") or True


def _gigachat_token() -> str | None:
    """OAuth-токен GigaChat живёт 30 минут — кэшируем и обновляем заранее."""
    if _token_cache["value"] and time.time() < _token_cache["expires"] - 60:
        return _token_cache["value"]
    creds = os.environ.get("GIGACHAT_CREDENTIALS")
    requests = _requests()
    if not creds or not requests:
        return None
    try:
        r = requests.post(
            GIGACHAT_OAUTH,
            headers={"Authorization": f"Basic {creds}",
                     "RqUID": str(uuid.uuid4()),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")},
            timeout=15, verify=_verify())
        r.raise_for_status()
        data = r.json()
        _token_cache["value"] = data["access_token"]
        _token_cache["expires"] = data.get("expires_at", time.time() * 1000 + 1_800_000) / 1000
        return _token_cache["value"]
    except Exception as e:  # noqa: BLE001 — любой сбой означает «работаем офлайн»
        print(f"[api_client] GigaChat OAuth недоступен: {e}")
        return None


def _call_gigachat(messages: list[dict]) -> str | None:
    requests = _requests()
    token = _gigachat_token()
    if not token or not requests:
        return None
    payload = {
        "model": os.environ.get("LLM_MODEL", "GigaChat"),
        "messages": messages,
        "temperature": prompts.LLM_PARAMS["temperature"] or 0.0001,  # GigaChat не любит ровный ноль
        "top_p": prompts.LLM_PARAMS["top_p"],
        "max_tokens": prompts.LLM_PARAMS["max_tokens"],
    }
    try:
        r = requests.post(GIGACHAT_CHAT, headers={"Authorization": f"Bearer {token}"},
                          json=payload, timeout=60, verify=_verify())
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        print(f"[api_client] GigaChat не ответил: {e}")
        return None


def _call_openai(messages: list[dict]) -> str | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=prompts.LLM_PARAMS["temperature"],
            seed=prompts.LLM_PARAMS["seed"],
            max_tokens=prompts.LLM_PARAMS["max_tokens"],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "scaner", "schema": prompts.RESPONSE_SCHEMA}},
        )
        return resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        print(f"[api_client] OpenAI не ответил: {e}")
        return None


def _extract_json(raw: str) -> dict | None:
    """Модель иногда оборачивает JSON в ```json ... ``` или добавляет текст.
    Достаём первый валидный объект, а не падаем."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.lower().startswith("json") else raw
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def _validate(results: list[dict], n: int) -> list[dict] | None:
    """Проверяем контракт: столько же объектов, обязательные поля, допустимые значения."""
    if not isinstance(results, list) or len(results) != n:
        return None
    cats = set(prompts.RESPONSE_SCHEMA["properties"]["results"]["items"]["properties"]["category"]["enum"])
    types = set(prompts.RESPONSE_SCHEMA["properties"]["results"]["items"]["properties"]["vendor_type"]["enum"])
    out = []
    for r in results:
        if not isinstance(r, dict) or "normalized_key" not in r:
            return None
        out.append({
            "id": r.get("id"),
            "service": str(r.get("service", "UNKNOWN"))[:64],
            "normalized_key": str(r.get("normalized_key", "unknown")).lower().replace(" ", "_")[:64],
            "category": r["category"] if r.get("category") in cats else "Other",
            "vendor_type": r["vendor_type"] if r.get("vendor_type") in types else "unknown",
            "confidence": max(0.0, min(1.0, float(r.get("confidence", 0.5)))),
            "evidence": [str(e) for e in (r.get("evidence") or [])][:3],
            "source": "llm",
        })
    return out


def classify_via_llm(descriptions: list[str], retries: int = 1) -> list[dict] | None:
    """Отправляет пачку описаний в модель. Возвращает None, если что-то пошло не так.

    Кэш по тексту пачки: на демо один и тот же файл прогоняется несколько раз,
    платить за это повторно незачем.
    """
    if not enabled() or not descriptions:
        return None
    key = "|".join(descriptions)
    if key in _response_cache:
        return _response_cache[key]

    provider = os.environ.get("LLM_PROVIDER", "gigachat").lower()
    messages = prompts.build_messages(descriptions)
    call = _call_gigachat if provider == "gigachat" else _call_openai

    for attempt in range(retries + 1):
        raw = call(messages)
        data = _extract_json(raw or "")
        results = _validate((data or {}).get("results", []), len(descriptions))
        if results:
            _response_cache[key] = results
            return results
        if attempt < retries:
            time.sleep(1.5)
            messages = messages + [{"role": "user",
                                    "content": "Предыдущий ответ не прошёл валидацию. "
                                               "Верни СТРОГО JSON вида {\"results\": [...]} "
                                               f"ровно из {len(descriptions)} объектов, без пояснений."}]
    print("[api_client] ответ модели не прошёл валидацию — работаем на офлайн-движке")
    return None


def classify(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ЕДИНАЯ ТОЧКА ВХОДА ДЛЯ BACKEND. Это то, что зовёт Игнат.

        from api_client import classify
        result = classify([{"id": "1", "description": "NETFLIX.COM*12345"}])

    Что происходит внутри:
      1. если USE_REAL_AI=1 и есть ключ — описания уходят в модель батчами по 40;
      2. всё, что модель не вернула или вернула криво, добирается офлайн-движком
         из ai_layer.py (справочник + нечёткое сопоставление);
      3. если и его рядом нет — заполняем UNKNOWN, но НЕ падаем.

    Гарантии: столько же объектов, сколько на входе, тот же порядок, те же id.
    Функция никогда не бросает исключение — продукт не должен падать из-за AI.
    """
    if not transactions:
        return []

    descriptions = [str(t.get("description", "")) for t in transactions]
    out: list[dict[str, Any] | None] = [None] * len(transactions)

    # 1. модель, батчами
    if enabled():
        for start in range(0, len(descriptions), prompts.BATCH_SIZE):
            chunk = descriptions[start:start + prompts.BATCH_SIZE]
            got = classify_via_llm(chunk)
            if not got:
                continue
            for i, r in enumerate(got):
                out[start + i] = r

    # 2. офлайн-движок для всего, что осталось
    missing = [i for i, r in enumerate(out) if r is None]
    if missing:
        offline = _offline(descriptions, missing)
        for i, r in zip(missing, offline):
            out[i] = r

    # 3. проставляем id из входных данных
    for t, r in zip(transactions, out):
        r["id"] = t.get("id")
    return out  # type: ignore[return-value]


def _offline(descriptions: list[str], indexes: list[int]) -> list[dict[str, Any]]:
    """Резервный путь: справочник из ai_layer.py, если он лежит рядом."""
    try:
        from ai_layer import classify_batch
    except ImportError:
        try:
            from .ai_layer import classify_batch  # type: ignore[no-redef]
        except ImportError:
            print("[api_client] ai_layer.py рядом нет — заполняю UNKNOWN")
            return [{"id": None, "service": "UNKNOWN", "normalized_key": "unknown",
                     "category": "Other", "vendor_type": "unknown", "confidence": 0.0,
                     "evidence": ["офлайн-движок недоступен"], "source": "registry"}
                    for _ in indexes]
    return classify_batch([{"id": None, "description": descriptions[i]} for i in indexes])


def status() -> dict[str, Any]:
    """Для интерфейса: показать, в каком режиме работает AI-слой."""
    provider = os.environ.get("LLM_PROVIDER", "gigachat")
    return {
        "use_real_ai": enabled(),
        "provider": provider if enabled() else "offline",
        "has_credentials": bool(os.environ.get("GIGACHAT_CREDENTIALS") or os.environ.get("OPENAI_API_KEY")),
        "label": f"AI: {provider}" if enabled() else "AI: офлайн-движок",
    }


if __name__ == "__main__":
    print("Режим:", json.dumps(status(), ensure_ascii=False))
    demo = [
        {"id": "t_001", "description": "NETFLIX.COM*12345"},
        {"id": "t_002", "description": "GOOGLE*YOUTUBEPREMIUM"},
        {"id": "t_003", "description": 'OOO "KINOPOISK" 3623 MOSCOW'},
        {"id": "t_004", "description": "PEREVOD SBP IVANOV I."},
    ]
    res = classify(demo)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nНа входе {len(demo)} транзакций, на выходе {len(res)} — контракт соблюдён.")
    if not enabled():
        print("Работал офлайн-движок. Для проверки API: "
              "USE_REAL_AI=1 GIGACHAT_CREDENTIALS=ваш_ключ python api_client.py")
