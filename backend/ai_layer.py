"""
Scaner — AI-слой распознавания транзакций.
Автор: Никита (AI / Prompt Engineer).

Каскад: preclean -> справочник -> нечёткое сопоставление -> LLM (опционально).
Внешний контракт — одна функция classify_batch(transactions) -> list[dict].
Формат ответа описан в schemas/response.json и в docs/AI_LAYER.md.

LLM-вызов вынесен за интерфейс: если ключа нет или сеть недоступна,
слой продолжает работать на справочнике и нечётком сопоставлении.
"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

BASE = Path(__file__).resolve().parent
REGISTRY: list[dict[str, Any]] = json.loads((BASE / "merchants.json").read_text(encoding="utf-8"))
for _m in REGISTRY:
    _m["_re"] = [re.compile(p, re.I) for p in _m["patterns"]]

CATEGORIES = ["Streaming", "Music", "Cloud", "Gaming", "Education", "Fitness", "Delivery",
              "Telecom", "Software", "Marketplace", "Finance", "Ecosystem", "Other"]

NOISE = re.compile(
    r"\b(RUS|RU|MOSCOW|MOSKVA|SPB|EKB|IRKUTSK|KAZAN|NLD|USA|IE|GBR|OOO|IP|ZAO|PAO|AO|LLC|INC|LTD|"
    r"COM|WWW|PAYMENT|PODPISKA|OPLATA|PAY|SUBSCR|SUBSCRIPTION|MONTHLY)\b", re.I)


def preclean(s: str) -> str:
    """Детерминированная предочистка: убираем мусор эквайринга, коды, города."""
    x = str(s).upper().replace('"', " ").replace("'", " ")
    x = re.sub(r"[*#/\\.,;:]+", " ", x)
    # токены с цифрами (терминалы, хеши, объёмы) выкидываем целиком
    x = re.sub(r"\b[A-ZА-Я0-9]*\d[A-ZА-Я0-9]*\b", " ", x)
    x = NOISE.sub(" ", x)
    return re.sub(r"\s+", " ", x).strip()


def match_registry(raw: str) -> dict[str, Any] | None:
    up = str(raw).upper()
    for m in REGISTRY:
        if any(rx.search(up) for rx in m["_re"]):
            return m
    return None


def fuzzy_key(clean: str) -> str:
    """Ключ группировки для неизвестных мерчантов. Токены сортируются,
    поэтому 'CLOUD MAIL' и 'MAIL CLOUD' дают один ключ."""
    words = [w for w in clean.split() if len(w) > 2]
    # берём два самых длинных токена (они несут бренд), затем сортируем —
    # так порядок слов в описании не влияет на ключ
    toks = sorted(sorted(words, key=len, reverse=True)[:2])
    key = "_".join(toks).lower()
    return re.sub(r"[^a-zа-я0-9_]", "", key) or "unknown"


def similarity(a: str, b: str) -> float:
    """Замена косинусной близости эмбеддингов для офлайн-режима.
    В проде здесь SentenceTransformers('paraphrase-multilingual-MiniLM-L12-v2')."""
    return SequenceMatcher(None, a, b).ratio()


NON_SUBSCRIPTION = re.compile(
    r"PEREVOD|PERECHISLENIE|SBP|NALICHN|ATM|CASH|ZARPLATA|PYATEROCHKA|MAGNIT|VKUSVILL|"
    r"AZS|LUKOIL|TAXI|APTEKA|CAFE|COFFEE|RESTORAN|OPLATA USLUG|PAYMENT|PURCHASE|STORE|BILET", re.I)


@lru_cache(maxsize=4096)
def classify_one(description: str, mcc: str = "") -> tuple:
    """Кэшируемое ядро: по описанию возвращает (service, key, category, vendor_type, conf, evidence, source)."""
    clean = preclean(description)
    reg = match_registry(description)
    if reg:
        ev = [f"точное вхождение бренда «{reg['service']}»"]
        if mcc in ("4899", "5817", "5818"):
            ev.append(f"MCC {mcc} — цифровые сервисы")
        return (reg["service"], reg["key"], reg["category"], "subscription", 0.96, tuple(ev), "registry")

    if NON_SUBSCRIPTION.search(description):
        kind = "cash" if re.search(r"NALICHN|ATM|CASH", description, re.I) else (
            "transfer" if re.search(r"PEREVOD|SBP|ZARPLATA", description, re.I) else "one_time")
        return ("UNKNOWN", "unknown", "Other", kind, 0.08,
                ("описание не содержит бренда сервиса подписки",), "registry")

    # мягкое сопоставление с брендами справочника
    best, best_score = None, 0.0
    for m in REGISTRY:
        sc = similarity(clean, m["service"].upper())
        if sc > best_score:
            best, best_score = m, sc
    if best and best_score >= 0.82:
        return (best["service"], best["key"], best["category"], "subscription", round(best_score, 2),
                (f"название близко к «{best['service']}» ({best_score:.2f})",), "embedding")

    if not clean:
        return ("UNKNOWN", "unknown", "Other", "unknown", 0.05, ("описание пустое после очистки",), "embedding")

    title = " ".join(w.capitalize() for w in clean.split()[:3])
    return (title, fuzzy_key(clean), "Other", "unknown", 0.55,
            ("бренд не найден в справочнике, ключ собран из очищенного названия",), "embedding")


def classify_batch(transactions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Основная точка входа для backend. Порядок и id сохраняются, длина совпадает."""
    out: list[dict[str, Any]] = []
    for t in transactions:
        service, key, cat, vtype, conf, ev, src = classify_one(str(t.get("description", "")), str(t.get("mcc", "")))
        out.append({
            "id": t.get("id"),
            "service": service,
            "normalized_key": key,
            "category": cat,
            "vendor_type": vtype,
            "confidence": conf,
            "evidence": list(ev)[:3],
            "source": src,
        })
    return out


# --------------------------------------------------------------------------
# Опциональный LLM-фолбэк. Включается переменной окружения SCANER_LLM=1.
# Промпты лежат в ai/prompts/ и не дублируются в коде.
# --------------------------------------------------------------------------
def llm_resolve(descriptions: list[str]) -> list[dict[str, Any]] | None:
    if os.environ.get("SCANER_LLM") != "1":
        return None
    try:
        from openai import OpenAI  # noqa: F401  (зависимость ставится только для прод-режима)
    except Exception:
        return None
    system = (BASE / "prompts" / "system.txt").read_text(encoding="utf-8")
    user = (BASE / "prompts" / "p1_service.txt").read_text(encoding="utf-8").replace(
        "{{TRANSACTIONS_JSON}}", json.dumps(descriptions, ensure_ascii=False))
    schema = json.loads((BASE / "schemas" / "response.json").read_text(encoding="utf-8"))
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("SCANER_MODEL", "gpt-4o-mini"),
            temperature=0, seed=42,
            response_format={"type": "json_schema", "json_schema": {"name": "scaner", "schema": schema}},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content)["results"]
    except Exception:
        return None  # слой никогда не роняет продукт: возвращаемся к справочнику


if __name__ == "__main__":
    demo = [{"id": "t_001", "description": "NETFLIX.COM*12345", "mcc": "4899"},
            {"id": "t_002", "description": "GOOGLE*YOUTUBEPREMIUM"},
            {"id": "t_003", "description": "PEREVOD SBP IVANOV I."}]
    print(json.dumps(classify_batch(demo), ensure_ascii=False, indent=2))
