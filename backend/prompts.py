"""
Промпты AI-слоя Scaner — единственный источник правды.
Артефакт 4 сентября (по плану тимлида).

Ни один промпт не дублируется в другом файле: api_client.py и ai_layer.py
импортируют их отсюда. Копия в prompts.json — для тех, кто работает
не на Python (например, при тесте промпта в веб-версии нейросети).

Использование:
    from prompts import build_messages, RESPONSE_SCHEMA
    messages = build_messages(["NETFLIX.COM*12345", "GOOGLE*YOUTUBEPREMIUM"])
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# SYSTEM — правила, которые действуют всегда
# --------------------------------------------------------------------------
SYSTEM = """Ты — модуль нормализации банковских транзакций сервиса Scaner.
Твоя задача: по строке описания платежа определить, какому сервису он принадлежит.

ПРАВИЛА:
1. Отвечай ТОЛЬКО валидным JSON по заданной схеме. Никакого текста до или после.
2. Никогда не выдумывай сервис. Если бренд не узнаётся однозначно — service = "UNKNOWN", confidence <= 0.4.
3. Технический мусор в описании игнорируй: номера терминалов, коды городов,
   RUS/MOSCOW/SPB/IRKUTSK, номера карт, префиксы вида "OOO", "IP", "ZAO",
   символы * / # и последовательности цифр длиннее 3.
4. normalized_key — латиница в нижнем регистре, слова через "_":
   "Яндекс Плюс" -> "yandex_plus", "YouTube Premium" -> "youtube_premium".
5. Один бренд = один normalized_key всегда, независимо от написания в выписке.
6. Переводы физлицам, снятие наличных, оплата в магазинах и на АЗС —
   vendor_type = "transfer" / "cash" / "one_time", service = "UNKNOWN".
7. confidence отражает уверенность в БРЕНДЕ, а не в том, что это подписка.
8. evidence — максимум 3 коротких факта на русском, почему принято такое решение."""

# --------------------------------------------------------------------------
# Промпт №1 + №2 — сервис и категория одним вызовом
# (раздельные вызовы стоят вдвое дороже и дают рассинхрон категории с брендом)
# --------------------------------------------------------------------------
CATEGORIES_BLOCK = """Категории и их определения:
- Streaming   — видео по подписке (Netflix, Кинопоиск, Иви, Okko, START, КИОН)
- Music       — музыка и подкасты (Spotify, Apple Music, VK Музыка, Звук)
- Cloud       — хранилища и инфраструктура (iCloud, Google One, Облако Mail.ru, AWS)
- Gaming      — игры и игровые сервисы (PS Plus, Xbox Game Pass, Steam, VK Play)
- Education   — курсы и обучение (Skyeng, Coursera, Duolingo, Литрес)
- Fitness     — спорт и здоровье (клубы, приложения тренировок, медитации)
- Delivery    — доставка и подписки на доставку (Самокат, Купер, Яндекс Еда)
- Telecom     — связь и интернет (МТС, Билайн, Мегафон, Ростелеком)
- Software    — рабочие инструменты (Adobe, Notion, Figma, JetBrains, ChatGPT)
- Marketplace — маркетплейсы (Ozon Premium, WB Клуб)
- Finance     — финансовые сервисы и страхование
- Ecosystem   — пакетные подписки экосистем (СберПрайм, Яндекс Плюс, МТС Premium,
                Ozon Premium, VK Combo) — приоритет над узкой категорией
- Other       — не подходит ни под одну категорию

ВАЖНО: если сервис входит в экосистемный пакет — категория Ecosystem, даже если
внутри пакета есть видео и музыка. Это нужно для поиска дублей: пользователь
с Яндекс Плюс и отдельным Кинопоиском переплачивает."""

FEWSHOT = """Примеры (вход -> service / normalized_key / confidence):
NETFLIX.COM*12345          -> Netflix / netflix / 0.98
Netflix Amsterdam NLD      -> Netflix / netflix / 0.95
YANDEX 4 PLUS RU MOSCOW    -> Яндекс Плюс / yandex_plus / 0.94
SBERPRIME PODPISKA         -> СберПрайм / sberprime / 0.97
OOO "KINOPOISK" 3623       -> Кинопоиск / kinopoisk / 0.92
SPOTIFY P1A2B3C4D          -> Spotify / spotify / 0.96
PEREVOD SBP IVANOV I.      -> UNKNOWN / unknown / 0.05  (vendor_type: transfer)
PYATEROCHKA 4512 EKB       -> UNKNOWN / unknown / 0.10  (vendor_type: one_time)
WB RU 8712                 -> Wildberries / wildberries / 0.71 (vendor_type: one_time)"""

SERVICE_TEMPLATE = """Определи сервис и категорию для каждой транзакции.

Известные бренды (используй точное написание из списка, если узнаёшь):
{brands}

{categories}

{fewshot}

Транзакции:
{transactions}

Верни JSON вида {{"results": [...]}} по схеме."""

# --------------------------------------------------------------------------
# Промпт №3 — разрешение спорных кластеров
# --------------------------------------------------------------------------
CLUSTER_TEMPLATE = """Ниже — группа описаний из банковской выписки. Определи, относятся ли они
к ОДНОМУ сервису. Если да — верни каноническое имя и normalized_key.
Если это разные сервисы — раздели на группы.

Внимание: общий префикс платёжного агрегатора (GOOGLE*, APPLE.COM/BILL, PAYPAL*)
НЕ означает один сервис. Смотри на то, что идёт после префикса.

Описания:
{descriptions}

Ответ строго JSON:
{{"groups": [{{"normalized_key": "...", "service": "...", "members": [1,2], "confidence": 0.0}}]}}"""

# Схема ответа. Файл может лежать в schemas/, рядом или отсутствовать вовсе —
# тогда берётся встроенная копия. Так prompts.py работает в одиночку,
# без остальных файлов модуля.
_SCHEMA_FALLBACK = {
    "type": "object", "additionalProperties": False, "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "service", "normalized_key", "category",
                     "vendor_type", "confidence", "evidence", "source"],
        "properties": {
            "id": {"type": "string"},
            "service": {"type": "string"},
            "normalized_key": {"type": "string", "pattern": "^[a-z0-9_]+$"},
            "category": {"type": "string", "enum": [
                "Streaming", "Music", "Cloud", "Gaming", "Education", "Fitness",
                "Delivery", "Telecom", "Software", "Marketplace", "Finance",
                "Ecosystem", "Other"]},
            "vendor_type": {"type": "string", "enum": [
                "subscription", "one_time", "transfer", "cash", "unknown"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "source": {"type": "string", "enum": ["registry", "embedding", "llm"]},
        }}}},
}


def _load_schema() -> dict:
    for path in (BASE / "schemas" / "response.json", BASE / "response.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_FALLBACK


RESPONSE_SCHEMA = _load_schema()

# Список брендов для промпта. Обычно берётся из merchants.json; если справочника
# рядом нет — используется этот минимальный набор.
BRANDS_FALLBACK = (
    "Netflix, Яндекс Плюс, Кинопоиск, СберПрайм, YouTube Premium, Google One, "
    "VK Музыка, Spotify, iCloud+, ChatGPT Plus, Adobe Creative Cloud, Ozon Premium, "
    "Самокат Про, World Class, Skyeng, МТС Premium, Иви, Okko, Литрес, Duolingo, "
    "Notion, Яндекс Музыка, Ростелеком, Облако Mail.ru, WB Клуб")

# Параметры вызова — вынесены сюда, чтобы не разъезжались между модулями
LLM_PARAMS = {"temperature": 0, "top_p": 1, "seed": 42, "max_tokens": 2000}
BATCH_SIZE = 40


def known_brands() -> str:
    """Список брендов из справочника — подставляется в промпт.
    Если merchants.json рядом нет, берётся встроенный список."""
    path = BASE / "merchants.json"
    if not path.exists():
        return BRANDS_FALLBACK
    return ", ".join(m["service"] for m in json.loads(path.read_text(encoding="utf-8")))


def build_messages(descriptions: list[str]) -> list[dict]:
    """Готовые messages для chat/completions: system + user."""
    txs = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    user = SERVICE_TEMPLATE.format(
        brands=known_brands(), categories=CATEGORIES_BLOCK, fewshot=FEWSHOT, transactions=txs)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def build_cluster_messages(descriptions: list[str]) -> list[dict]:
    txs = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": CLUSTER_TEMPLATE.format(descriptions=txs)}]


def export_json(path: str | Path = None) -> Path:
    """Синхронизирует prompts.json с этим файлом. Запускать после правки промптов."""
    path = Path(path or BASE / "prompts.json")
    data = {
        "system": SYSTEM,
        "service_template": SERVICE_TEMPLATE,
        "categories_block": CATEGORIES_BLOCK,
        "fewshot": FEWSHOT,
        "cluster_template": CLUSTER_TEMPLATE,
        "llm_params": LLM_PARAMS,
        "batch_size": BATCH_SIZE,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(export_json(), "обновлён")
    msgs = build_messages(["NETFLIX.COM*12345", "GOOGLE*YOUTUBEPREMIUM"])
    print("\n--- system ---\n" + msgs[0]["content"][:200] + "…")
    print("\n--- user ---\n" + msgs[1]["content"][-400:])
