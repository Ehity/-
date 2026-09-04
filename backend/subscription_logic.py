"""
subscription_logic.py
=====================
Модуль Серёги (Math) — вычисление Subscription Score.

Функция calculate_subscription_score(transactions) принимает список транзакций
по одному предполагаемому продавцу и возвращает скор от 0 до 100 — насколько
уверенно эти транзакции являются подпиской.

Логика скора:
  1. Регулярность интервалов (≈30 дней → высокий балл)
  2. Стабильность сумм (одинаковые суммы → высокий балл)
  3. Количество транзакций (чем больше — тем увереннее)
  4. Похожесть имён продавца (NETFLIX.COM / NETFLIX*123 — один продавец)

Использование:
    from subscription_logic import calculate_subscription_score

    transactions = [
        {"date": "2024-01-15", "amount": 799.0, "merchant": "NETFLIX.COM"},
        {"date": "2024-02-14", "amount": 799.0, "merchant": "NETFLIX.COM Amsterdam"},
        {"date": "2024-03-15", "amount": 799.0, "merchant": "NETFLIX*123"},
    ]
    result = calculate_subscription_score(transactions)
    print(result["score"])        # 0–100
    print(result["verdict"])      # "Подписка", "Вероятно подписка", "Не подписка"
    print(result["breakdown"])    # детали по каждому компоненту
"""

from __future__ import annotations

import re
import statistics
from datetime import date, datetime
from typing import Union


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _parse_date(value: Union[str, date, datetime]) -> date:
    """Приводит дату из строки / datetime / date к типу date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Не удалось распознать дату: {value!r}")


def _normalize_merchant(name: str) -> str:
    """
    Приводит название продавца к «ядру» для сравнения.
    «NETFLIX.COM*123», «Netflix Amsterdam», «NETFLIX.COM» → «netflix»
    """
    name = name.lower()
    # убираем суффиксы типа *123, *abc
    name = re.sub(r"\*\w+", "", name)
    # убираем .com / .ru и прочие домены
    name = re.sub(r"\.\w{2,4}\b", "", name)
    # убираем города и распространённые слова-паразиты
    noise = r"\b(amsterdam|moscow|ru|com|ltd|llc|inc|gmbh|bv|oy|sa|corp)\b"
    name = re.sub(noise, "", name)
    # оставляем только буквы и цифры
    name = re.sub(r"[^a-z0-9]", "", name)
    return name.strip()


def _merchant_similarity_score(merchants: list[str]) -> float:
    """
    Возвращает 0–1: насколько все названия продавцов похожи друг на друга.
    Если нормализованное «ядро» одинаковое у всех — 1.0.
    """
    if not merchants:
        return 0.0
    cores = [_normalize_merchant(m) for m in merchants]
    most_common = max(set(cores), key=cores.count)
    match_ratio = cores.count(most_common) / len(cores)
    return match_ratio


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

def calculate_subscription_score(
    transactions: list[dict],
) -> dict:
    """
    Вычисляет Subscription Score для набора транзакций одного продавца.

    Параметры
    ----------
    transactions : list[dict]
        Каждый элемент — словарь с ключами:
          • "date"     (str | date | datetime) — дата транзакции  [обязательно]
          • "amount"   (float | int)            — сумма            [обязательно]
          • "merchant" (str)                    — имя продавца     [опционально]

    Возвращает
    ----------
    dict с полями:
      • "score"     (float)  — итоговый скор 0–100
      • "verdict"   (str)    — текстовый вердикт
      • "breakdown" (dict)   — детали по каждому компоненту (0–100 каждый)
      • "details"   (dict)   — расчётные цифры (интервалы, суммы и т. д.)
    """

    # ── Базовые проверки ──────────────────────────────────────────────────
    if not transactions:
        return {
            "score": 0.0,
            "verdict": "Нет данных",
            "breakdown": {},
            "details": {},
        }

    if len(transactions) < 2:
        return {
            "score": 5.0,
            "verdict": "Недостаточно данных (1 транзакция)",
            "breakdown": {"count_score": 5.0},
            "details": {"n": 1},
        }

    # ── Парсим и сортируем ────────────────────────────────────────────────
    parsed = []
    for tx in transactions:
        parsed.append(
            {
                "date": _parse_date(tx["date"]),
                "amount": float(tx["amount"]),
                "merchant": str(tx.get("merchant", "")),
            }
        )
    parsed.sort(key=lambda x: x["date"])

    dates = [p["date"] for p in parsed]
    amounts = [p["amount"] for p in parsed]
    merchants = [p["merchant"] for p in parsed]
    n = len(parsed)

    # ── 1. Регулярность интервалов ─────────────────────────────────────────
    # Считаем разницу в днях между соседними транзакциями.
    # Идеальная подписка: ≈30 дней. Допустимо ±5 дней (25–35).
    intervals = [(dates[i + 1] - dates[i]).days for i in range(n - 1)]
    mean_interval = statistics.mean(intervals)

    # Насколько среднее близко к 30 дням
    TARGET = 30          # дней
    TOLERANCE = 5        # ±5 дней — «идеально»
    WINDOW = 20          # ±20 дней — «ещё засчитываем»

    deviation_from_30 = abs(mean_interval - TARGET)
    if deviation_from_30 <= TOLERANCE:
        interval_center_score = 100.0
    elif deviation_from_30 <= WINDOW:
        # Линейный штраф от 100 до 40
        interval_center_score = 100.0 - (deviation_from_30 - TOLERANCE) / (WINDOW - TOLERANCE) * 60
    else:
        interval_center_score = max(0.0, 40.0 - (deviation_from_30 - WINDOW) * 2)

    # Насколько сами интервалы стабильны (низкий CV → высокий балл)
    if len(intervals) >= 2:
        std_interval = statistics.stdev(intervals)
        cv_interval = std_interval / mean_interval if mean_interval > 0 else 1.0
        # CV < 0.05 → 100, CV > 0.5 → 0
        interval_stability_score = max(0.0, min(100.0, 100 - cv_interval / 0.5 * 100))
    else:
        interval_stability_score = 70.0  # только 1 интервал — неопределённость

    regularity_score = 0.5 * interval_center_score + 0.5 * interval_stability_score

    # ── 2. Стабильность сумм ──────────────────────────────────────────────
    mean_amount = statistics.mean(amounts)
    if len(amounts) >= 2:
        std_amount = statistics.stdev(amounts)
        cv_amount = std_amount / mean_amount if mean_amount > 0 else 1.0
        # CV < 0.02 → 100 (идеально одинаково), CV > 0.3 → 0
        amount_score = max(0.0, min(100.0, 100 - cv_amount / 0.3 * 100))
    else:
        amount_score = 70.0

    # ── 3. Количество транзакций ──────────────────────────────────────────
    # 1 → 5, 2 → 40, 3 → 60, 4 → 75, 5 → 85, 6+ → 95–100
    count_thresholds = {1: 5, 2: 40, 3: 60, 4: 75, 5: 85}
    if n >= 6:
        count_score = min(100.0, 85.0 + (n - 5) * 3)
    else:
        count_score = float(count_thresholds.get(n, 5))

    # ── 4. Похожесть имён продавца ────────────────────────────────────────
    merchant_score = _merchant_similarity_score(merchants) * 100.0

    # ── Итоговый взвешенный скор ──────────────────────────────────────────
    #   Регулярность     — самый важный признак подписки  (35 %)
    #   Стабильность сумм                                 (30 %)
    #   Количество транзакций                             (20 %)
    #   Похожесть имён продавца                           (15 %)
    WEIGHTS = {
        "regularity": 0.35,
        "amount":     0.30,
        "count":      0.20,
        "merchant":   0.15,
    }

    score = (
        WEIGHTS["regularity"] * regularity_score
        + WEIGHTS["amount"]   * amount_score
        + WEIGHTS["count"]    * count_score
        + WEIGHTS["merchant"] * merchant_score
    )
    score = round(min(100.0, max(0.0, score)), 1)

    # ── Вердикт ───────────────────────────────────────────────────────────
    if score >= 75:
        verdict = "Подписка"
    elif score >= 50:
        verdict = "Вероятно подписка"
    elif score >= 30:
        verdict = "Сомнительно"
    else:
        verdict = "Не подписка"

    # ── Сборка результата ─────────────────────────────────────────────────
    breakdown = {
        "regularity_score": round(regularity_score, 1),
        "amount_score":     round(amount_score, 1),
        "count_score":      round(count_score, 1),
        "merchant_score":   round(merchant_score, 1),
    }

    details = {
        "n":                  n,
        "mean_interval_days": round(mean_interval, 1),
        "intervals_days":     intervals,
        "mean_amount":        round(mean_amount, 2),
        "amounts":            amounts,
        "interval_cv":        round(std_interval / mean_interval, 3) if len(intervals) >= 2 and mean_interval > 0 else None,
        "amount_cv":          round(std_amount / mean_amount, 3) if len(amounts) >= 2 and mean_amount > 0 else None,
        "merchant_cores":     [_normalize_merchant(m) for m in merchants],
    }

    return {
        "score":     score,
        "verdict":   verdict,
        "breakdown": breakdown,
        "details":   details,
    }


# ---------------------------------------------------------------------------
# Вспомогательная функция для группировки нескольких продавцов сразу
# ---------------------------------------------------------------------------

def score_all_groups(groups: dict[str, list[dict]]) -> list[dict]:
    """
    Принимает словарь {название_группы: [транзакции]},
    возвращает список результатов, отсортированных по убыванию скора.

    Удобно передавать сюда вывод AI-парсера Никиты, который кластеризует
    транзакции по продавцам.

    Пример:
        groups = {
            "Netflix": [...],
            "Spotify": [...],
        }
        results = score_all_groups(groups)
    """
    results = []
    for name, txs in groups.items():
        res = calculate_subscription_score(txs)
        results.append({"merchant_group": name, **res})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Pandas-обвязка — для Игната (Streamlit) и работы с CSV
# ---------------------------------------------------------------------------

def process_dataframe(df) -> "pd.DataFrame":
    """
    Принимает pandas DataFrame с транзакциями и возвращает
    его же, но с двумя новыми колонками: "score" и "verdict".

    Ожидаемые колонки в df:
      • "date"     — дата транзакции
      • "amount"   — сумма
      • "merchant" — название продавца (опционально)

    Пример использования в app.py Игната:
        import pandas as pd
        from subscription_logic import process_dataframe

        df = pd.read_csv("transactions.csv")
        result_df = process_dataframe(df)
        st.dataframe(result_df[["date", "merchant", "amount", "score", "verdict"]])
    """
    import pandas as pd

    # Если колонки называются по-другому — пробуем стандартные варианты
    col_map = {}
    for col in df.columns:
        low = col.lower().strip()
        if low in ("date", "дата", "transaction_date"):
            col_map["date"] = col
        elif low in ("amount", "сумма", "sum", "price", "value"):
            col_map["amount"] = col
        elif low in ("merchant", "продавец", "name", "description", "desc", "title"):
            col_map["merchant"] = col

    if "date" not in col_map or "amount" not in col_map:
        raise ValueError(
            "В таблице не найдены обязательные колонки 'date' и 'amount'. "
            f"Найденные колонки: {list(df.columns)}"
        )

    merchant_col = col_map.get("merchant")

    # Группируем транзакции по нормализованному имени продавца
    def get_merchant(row):
        if merchant_col:
            return _normalize_merchant(str(row[col_map["merchant"]]))
        return "unknown"

    df = df.copy()
    df["_merchant_key"] = df.apply(get_merchant, axis=1)

    # Считаем скор для каждой группы продавцов
    scores_map = {}   # merchant_key → score
    verdict_map = {}  # merchant_key → verdict

    for key, group in df.groupby("_merchant_key"):
        txs = [
            {
                "date":     row[col_map["date"]],
                "amount":   row[col_map["amount"]],
                "merchant": str(row[col_map["merchant"]]) if merchant_col else "",
            }
            for _, row in group.iterrows()
        ]
        result = calculate_subscription_score(txs)
        scores_map[key] = result["score"]
        verdict_map[key] = result["verdict"]

    # Проставляем колонки каждой строке
    df["score"]   = df["_merchant_key"].map(scores_map)
    df["verdict"] = df["_merchant_key"].map(verdict_map)
    df.drop(columns=["_merchant_key"], inplace=True)

    return df


# ---------------------------------------------------------------------------
# Быстрый тест при прямом запуске
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТ 1 — Идеальная подписка (Netflix, 3 месяца)")
    print("=" * 60)
    ideal = [
        {"date": "2024-01-15", "amount": 799.0, "merchant": "NETFLIX.COM"},
        {"date": "2024-02-14", "amount": 799.0, "merchant": "NETFLIX.COM Amsterdam"},
        {"date": "2024-03-15", "amount": 799.0, "merchant": "NETFLIX*123"},
    ]
    r = calculate_subscription_score(ideal)
    print(f"  Скор:    {r['score']} / 100")
    print(f"  Вердикт: {r['verdict']}")
    print(f"  Детали:  {r['breakdown']}")

    print()
    print("=" * 60)
    print("ТЕСТ 2 — Нерегулярные покупки (не подписка)")
    print("=" * 60)
    irregular = [
        {"date": "2024-01-03", "amount": 350.0, "merchant": "MAGNIT"},
        {"date": "2024-01-20", "amount": 1200.0, "merchant": "MAGNIT"},
        {"date": "2024-03-05", "amount": 80.0,  "merchant": "MAGNIT"},
    ]
    r2 = calculate_subscription_score(irregular)
    print(f"  Скор:    {r2['score']} / 100")
    print(f"  Вердикт: {r2['verdict']}")
    print(f"  Детали:  {r2['breakdown']}")

    print()
    print("=" * 60)
    print("ТЕСТ 3 — Группировка нескольких продавцов")
    print("=" * 60)
    groups = {
        "Netflix": ideal,
        "Spotify": [
            {"date": "2024-01-10", "amount": 299.0, "merchant": "Spotify AB"},
            {"date": "2024-02-10", "amount": 299.0, "merchant": "SPOTIFY"},
            {"date": "2024-03-10", "amount": 299.0, "merchant": "Spotify"},
            {"date": "2024-04-10", "amount": 299.0, "merchant": "Spotify"},
        ],
        "Magnit": irregular,
    }
    for row in score_all_groups(groups):
        print(f"  {row['merchant_group']:12s} → {row['score']:5.1f}  ({row['verdict']})")

    print()
    print("=" * 60)
    print("ТЕСТ 4 — process_dataframe (как будет приходить от Игната)")
    print("=" * 60)
    import pandas as pd
    raw = pd.DataFrame([
        {"date": "2024-01-15", "amount": 799.0,  "merchant": "NETFLIX.COM"},
        {"date": "2024-02-14", "amount": 799.0,  "merchant": "NETFLIX*123"},
        {"date": "2024-03-15", "amount": 799.0,  "merchant": "NETFLIX.COM Amsterdam"},
        {"date": "2024-01-10", "amount": 299.0,  "merchant": "Spotify AB"},
        {"date": "2024-02-10", "amount": 299.0,  "merchant": "SPOTIFY"},
        {"date": "2024-03-10", "amount": 299.0,  "merchant": "Spotify"},
        {"date": "2024-01-03", "amount": 350.0,  "merchant": "MAGNIT"},
        {"date": "2024-01-20", "amount": 1200.0, "merchant": "MAGNIT"},
        {"date": "2024-03-05", "amount": 80.0,   "merchant": "MAGNIT"},
    ])
    result_df = process_dataframe(raw)
    print(result_df[["date", "merchant", "amount", "score", "verdict"]].to_string(index=False))
