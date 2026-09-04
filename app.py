import streamlit as st
import pandas as pd

st.set_page_config(page_title="Subscription Scanner", page_icon="💳", layout="centered")

st.title("💳 Subscription Scanner")
st.caption("Автоматический поиск и отмена скрытых подписок по банковской выписке")

# Зона загрузки / генерации
uploaded_file = st.file_uploader("Загрузите выписку (CSV)", type=["csv"])
generate_btn = st.button("✨ Сгенерировать тестовую выписку")

# Демо-данные для заглушки
demo_data = pd.DataFrame([
    {"Сервис": "Яндекс Плюс", "Сумма": "299 ₽", "Период": "Ежемесячно", "Категория": "Развлечения", "Ссылка": "https://plus.yandex.ru"},
    {"Сервис": "Telegram Premium", "Сумма": "299 ₽", "Период": "Ежемесячно", "Категория": "Мессенджеры", "Ссылка": "https://t.me/premium"},
    {"Сервис": "Фитнес-клуб", "Сумма": "2 890 ₽", "Период": "Ежемесячно", "Категория": "Спорт", "Ссылка": "https://example.com"},
])

# Отображение результатов (когда есть действие)
if uploaded_file or generate_btn:
    st.success("Выписка успешно обработана!")
    
    col1, col2 = st.columns(2)
    col1.metric(label="Найдено подписок", value="3 шт")
    col2.metric(label="Итоговые траты", value="3 488 ₽/мес")

    st.subheader("Найденные регулярные списания")
    st.dataframe(demo_data, use_container_width=True)
else:
    st.info("👋 Загрузите файл выписки или нажмите кнопку генерации, чтобы начать сканирование.")