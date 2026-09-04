import streamlit as st
import pandas as pd
import re
import statistics
from datetime import datetime

# База знаний прямых ссылок (Deep Links)
DEEP_LINKS = {
    "ЯНДЕКС": "https://plus.yandex.ru/my",
    "СБЕР": "https://www.sberbank.ru/ru/person",
    "TELEGRAM": "https://t.me/PremiumBot",
    "NETFLIX": "https://www.netflix.com/youraccount",
    "ИВИ": "https://www.ivi.ru/profile/subscription",
}

# Известные сервисы (ключ: (Название, Категория))
_KNOWN_SERVICES = {
    'YANDEXPLUS': ('Яндекс Плюс', 'Развлечения'),
    'YMPLUS': ('Яндекс Плюс', 'Развлечения'),
    'YANDEXMUSIC': ('Яндекс Музыка', 'Развлечения'),
    'SBERPRIME': ('СберПрайм', 'Сервисы'),
    'NETFLIX': ('Netflix', 'Кино'),
    'TELEGRAMPREMIUM': ('Telegram Premium', 'Связь'),
}

# Алиасы для принудительного объединения разных написаний в одну группу
_ALIASES = {
    'YMPLUS': 'YANDEXPLUS',
    'YANDXPLUS': 'YANDEXPLUS',
    'YMUSIC': 'YANDEXMUSIC'
}

# Черный список мерчантов (Латиница + Кириллица)
_BLACKLIST_MERCHANTS = [
    'PYATEROCHKA', 'MAGNIT', 'PEREKRESTOK', 'DIKSY', 'LENTA', 'OZON', 'KVITOUCHKA',
    'ПЯТЕРОЧКА', 'МАГНИТ', 'ПЕРЕКРЕСТОК', 'ДИКСИ', 'ЛЕНТА', 'ОЗОН', 'КВИТОЧКА'
]

def normalize_description(desc: str) -> str:
    """Удаляет все символы, кроме букв, для точного матчинга."""
    if not isinstance(desc, str): return ""
    return re.sub(r'[^A-ZА-Я]', '', desc.upper())

def get_group_key(norm_desc: str) -> str:
    """Объединяет разные варианты написания (и алиасы) в один ключ."""
    # Сначала проверяем алиасы
    for alias, target_key in _ALIASES.items():
        if alias in norm_desc:
            return target_key
    # Потом проверяем основные ключи
    for key in _KNOWN_SERVICES.keys():
        if key in norm_desc:
            return key
    return norm_desc

def analyze_statement(df_raw):
    """Умный алгоритм поиска подписок."""
    df = df_raw.copy()
    df.columns = [col.lower().strip() for col in df.columns]
    
    # Ищем нужные колонки
    amount_col = next((c for c in df.columns if 'amount' in c or 'сумма' in c or 'сумма операции' in c), None)
    desc_col = next((c for c in df.columns if 'description' in c or 'title' in c or 'описание' in c or 'название' in c or 'memo' in c), None)
    date_col = next((c for c in df.columns if 'date' in c or 'дата' in c), None)

    if not amount_col or not desc_col:
        return pd.DataFrame()

    # Берем модуль суммы, чтобы отрицательные списания стали положительными
    df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce').abs()
    
    # Преобразуем даты
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.sort_values(by=date_col)

    results = []
    df['norm_desc'] = df[desc_col].apply(normalize_description)
    df['group_key'] = df['norm_desc'].apply(get_group_key)
    
    for group_key, group in df.groupby('group_key'):
        
        if any(merchant in group_key for merchant in _BLACKLIST_MERCHANTS):
            continue
            
        if len(group) < 2:
            continue
            
        real_amounts = [a for a in group[amount_col] if a > 15]
        if not real_amounts:
            continue
            
        median_amount = statistics.median(real_amounts)
        
        period_type = "Нерегулярно"
        if date_col and len(group) >= 2:
            dates = group[date_col].dropna().tolist()
            if len(dates) >= 2:
                diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
                avg_diff = sum(diffs) / len(diffs)
                
                # Расширили диапазон месячной подписки до 25-40 дней (защита от сдвигов)
                if 6 <= avg_diff <= 9: period_type = "Еженедельно"
                elif 25 <= avg_diff <= 40: period_type = "Ежемесячно"
                elif 360 <= avg_diff <= 370: period_type = "Ежегодно"
        
        pretty_name = group[desc_col].iloc[0]
        category = "Прочее"
        score = 65
        
        if group_key in _KNOWN_SERVICES:
            pretty_name, category = _KNOWN_SERVICES[group_key]
            score = 95
            
        if len(set(real_amounts)) == 1:
            score = min(100, score + 10)

        results.append({
            'service': pretty_name,
            'amount': int(median_amount),
            'count': len(group),
            'period': period_type,
            'category': category,
            'score': score
        })
        
    return pd.DataFrame(results)

def analyze_statement_with_csv(file_path: str) -> dict:
    """Обёртка для тестов: принимает путь к CSV, возвращает словарь со summary."""
    df = pd.read_csv(file_path)
    results_df = analyze_statement(df)
    
    if results_df.empty:
        return {"summary": {"total_monthly": 0, "total_yearly": 0, "count": 0}, "subscriptions": []}
        
    active_subs = results_df[results_df['period'] != 'Нерегулярно'].copy()
    total_monthly = 0
    for _, row in active_subs.iterrows():
        if 'Ежегодно' in row['period']: total_monthly += row['amount'] / 12
        elif 'Еженедельно' in row['period']: total_monthly += row['amount'] * 4.33
        else: total_monthly += row['amount']
        
    return {
        "summary": {
            "total_monthly": int(total_monthly),
            "total_yearly": int(total_monthly * 12),
            "count": len(active_subs)
        },
        "subscriptions": active_subs.to_dict(orient='records')
    }

def generate_synthetic_data():
    return pd.DataFrame([
        {"date": "2026-02-05", "amount": -1, "description": "Yandex.Plus", "category": "Развлечения"},
        {"date": "2026-03-05", "amount": -299, "description": "Yandex Plus", "category": "Развлечения"},
        {"date": "2026-04-05", "amount": -299, "description": "YM*PLUS", "category": "Развлечения"},
        {"date": "2026-05-12", "amount": -299, "description": "YM*PLUS", "category": "Развлечения"},
        {"date": "2026-06-12", "amount": -299, "description": "Yandex.Plus", "category": "Развлечения"},
        {"date": "2026-03-01", "amount": -299, "description": "SBERPRIME PODPISKA", "category": "Сервисы"},
        {"date": "2026-04-01", "amount": -299, "description": "SBERPRIME PODPISKA", "category": "Сервисы"},
        {"date": "2026-03-10", "amount": -550, "description": "Пятерочка", "category": "Супермаркеты"},
        {"date": "2026-04-07", "amount": -620, "description": "Пятерочка", "category": "Супермаркеты"},
    ])

def main():
    st.set_page_config(page_title="Сбер.Сканер Подписок", page_icon="💳", layout="wide")
    st.title("💳 Сбер.Сканер Подписок")
    st.caption("Автоматический поиск, анализ и отмена скрытых рекуррентных списаний")

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader("Загрузите CSV-выписку", type=["csv"])
    with col2:
        st.write("Или протестируйте на генераторе:")
        generate_btn = st.button("✨ Сгенерировать тестовую выписку", use_container_width=True)

    df_to_analyze = None

    if uploaded_file is not None:
        try:
            df_to_analyze = pd.read_csv(uploaded_file)
            st.success("Реальный CSV-файл успешно загружен!")
        except Exception as e:
            st.error(f"Ошибка при чтении файла: {e}")
    elif generate_btn:
        df_to_analyze = generate_synthetic_data()
        st.info("Сгенерирована жесткая тестовая выписка.")

    if df_to_analyze is not None:
        results_df = analyze_statement(df_to_analyze)
        
        if not results_df.empty:
            st.divider()
            active_subs = results_df[results_df['period'] != 'Нерегулярно'].copy()
            
            total_monthly = 0
            for _, row in active_subs.iterrows():
                if 'Ежегодно' in row['period']: total_monthly += row['amount'] / 12
                elif 'Еженедельно' in row['period']: total_monthly += row['amount'] * 4.33
                else: total_monthly += row['amount']
                
            total_yearly = int(total_monthly * 12)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Найдено подписок", f"{len(active_subs)} шт")
            m2.metric("Траты в месяц", f"{int(total_monthly):,} ₽".replace(",", " "))
            m3.metric("Потенциальная экономия в год", f"{total_yearly:,} ₽".replace(",", " "))
            
            st.subheader("📋 Найденные активные подписки")
            st.dataframe(
                active_subs[["service", "amount", "period", "category", "score"]],
                column_config={
                    "service": "Сервис",
                    "amount": st.column_config.NumberColumn("Стоимость", format="%d ₽"),
                    "period": "Периодичность",
                    "category": "Категория",
                    "score": "Score"
                },
                hide_index=True,
                use_container_width=True
            )
            
            st.subheader("⚡ Быстрый переход к отмене")
            for idx, row in active_subs.iterrows():
                srv = str(row["service"])
                link = next((v for k, v in DEEP_LINKS.items() if k.lower() in srv.lower()), f"https://yandex.ru/search/?text=как+отменить+подписку+{srv}")
                c1, c2 = st.columns([3, 1])
                c1.write(f"• **{srv}** — {int(row['amount'])} ₽ ({row['period']})")
                c2.link_button("🔗 Перейти к отмене", link)
        else:
            st.warning("В загруженном файле не обнаружено регулярных повторяющихся списаний.")
    else:
        st.divider()
        st.info("👋 Загрузите CSV-файл с банковской выпиской или нажмите «Сгенерировать тестовую выписку», чтобы начать анализ.")

if __name__ == "__main__":
    main()
