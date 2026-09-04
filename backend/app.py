[04.09.2026 21:08] Игнат Владимирович: import streamlit as st
import pandas as pd

# Настройка страницы
st.set_page_config(page_title="Сбер.Сканер Подписок", page_icon="💳", layout="wide")

st.title("💳 Сбер.Сканер Подписок")
st.caption("Автоматический поиск, анализ и отмена скрытых рекуррентных списаний")

# База знаний прямых ссылок (Deep Links)
DEEP_LINKS = {
    "Яндекс": "https://plus.yandex.ru/my",
    "Telegram": "https://t.me/PremiumBot",
    "Netflix": "https://www.netflix.com/youraccount",
    "Иви": "https://www.ivi.ru/profile/subscription",
    "Fitness": "https://example.com/fitness"
}

# Функция поиска регулярных подписок по выписке
def scan_subscriptions(df_raw):
    """
    Простой алгоритм: ищет повторяющиеся списания по названию или похожим суммам.
    """
    # Приводим колонки к нижнему регистру для удобства
    df_raw.columns = [col.lower().strip() for col in df_raw.columns]
    
    # Определяем нужные колонки
    amount_col = next((c for c in df_raw.columns if 'amount' in c or 'сумма' in c), None)
    desc_col = next((c for c in df_raw.columns if 'description' in c or 'title' in c or 'описание' in c or 'название' in c), None)
    cat_col = next((c for c in df_raw.columns if 'category' in c or 'категория' in c), None)

    if not amount_col or not desc_col:
        st.error("В CSV-файле не найдены необходимые колонки (нужны колонки с суммой и описанием/названием).")
        return pd.DataFrame()

    # Группируем по описанию и считаем частоту списаний
    summary = df_raw.groupby(desc_col).agg(
        amount=(amount_col, 'mean'),
        count=(amount_col, 'count')
    ).reset_index()

    # Фильтруем: подпиской считаем то, что списывалось 2 и более раз
    subs = summary[summary['count'] >= 2].copy()
    subs.columns = ['service', 'amount', 'count']
    subs['period'] = 'Ежемесячно'
    subs['category'] = 'Развлечения / Сервисы'
    
    return subs

# Функция генерации синтетических данных (только по кнопке)
def generate_synthetic_data():
    return pd.DataFrame([
        {"date": "2026-03-05", "amount": 399, "description": "YNDX_PLUS", "category": "Развлечения"},
        {"date": "2026-04-05", "amount": 399, "description": "YNDX.MUSIC", "category": "Развлечения"},
        {"date": "2026-03-12", "amount": 799, "description": "NETFLIX.COM", "category": "Кино"},
        {"date": "2026-04-12", "amount": 799, "description": "NETFLIX.COM", "category": "Кино"},
        {"date": "2026-03-20", "amount": 299, "description": "TELEGRAM PREMIUM", "category": "Связь"},
        {"date": "2026-04-20", "amount": 299, "description": "TELEGRAM PREMIUM", "category": "Связь"},
    ])

# Панель загрузки
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader("Загрузите CSV-выписку", type=["csv"])
with col2:
    st.write("Или протестируйте на генераторе:")
    generate_btn = st.button("✨ Сгенерировать тестовую выписку", use_container_width=True)

df_to_analyze = None

# Сценарий 1: Пользователь загрузил свой реальный CSV
if uploaded_file is not None:
    try:
        df_to_analyze = pd.read_csv(uploaded_file)
        st.success("Реальный CSV-файл успешно загружен!")
    except Exception as e:
        st.error(f"Ошибка при чтении файла: {e}")

# Сценарий 2: Пользователь нажал кнопку генерации
elif generate_btn:
    df_to_analyze = generate_synthetic_data()
    st.info("Сгенерирована тестовая выписка на 6 транзакций.")

# Отображение результатов
if df_to_analyze is not None:
    # Запускаем обработку
    results_df = scan_subscriptions(df_to_analyze)
    
    if not results_df.empty:
        st.divider()
        
        total_monthly = int(results_df["amount"].sum())
        total_yearly = total_monthly * 12
        
        # Метрики
        m1, m2, m3 = st.columns(3)
        m1.metric("Найдено подписок", f"{len(results_df)} шт")
        m2.metric("Траты в месяц", f"{total_monthly:,} ₽".replace(",", " "))
[04.09.2026 21:08] Игнат Владимирович: m3.metric("Потенциальная экономия в год", f"{total_yearly:,} ₽".replace(",", " "))
        
        st.subheader("📋 Найденные активные подписки")
        
        # Таблица результатов
        st.dataframe(
            results_df[["service", "amount", "period", "category"]],
            column_config={
                "service": "Сервис / Мерчант",
                "amount": st.column_config.NumberColumn("Стоимость", format="%d ₽"),
                "period": "Периодичность",
                "category": "Категория",
            },
            hide_index=True,
            use_container_width=True
        }
        
        # Ссылки на отмену
        st.subheader("⚡ Быстрый переход к отмене")
        for idx, row in results_df.iterrows():
            srv = str(row["service"])
            # Ищем совпадение названия с ключами в DEEP_LINKS
            link = next((v for k, v in DEEP_LINKS.items() if k.lower() in srv.lower()), f"https://yandex.ru/search/?text=как+отменить+подписку+{srv}")
            
            c1, c2 = st.columns([3, 1])
            c1.write(f"• {srv} — {int(row['amount'])} ₽/мес")
            c2.link_button("🔗 Перейти к отмене", link)
    else:
        st.warning("В загруженном файле не обнаружено регулярных повторяющихся списаний.")

else:
    # Empty State — чистый экран до загрузки
    st.divider()
    st.info("👋 Загрузите CSV-файл с банковской выпиской или нажмите «Сгенерировать тестовую выписку», чтобы начать анализ.")
