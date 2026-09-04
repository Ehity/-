"""A safe static cancellation-letter template."""


UNSUBSCRIBE_PROMPT = """Составь короткое вежливое письмо на русском языке для отмены
подписки на сервис {service_name}. Попроси отменить подписку, прекратить дальнейшие
списания, подтвердить отмену и, если это разрешают правила сервиса, рассмотреть
возврат последнего платежа. Не выдумывай личные данные пользователя."""


def generate_unsubscribe_letter(service_name: str) -> str:
    """Create a ready-to-send Russian cancellation request without personal data."""
    name = service_name.strip() if isinstance(service_name, str) else ""
    if not name:
        raise ValueError("Укажите название сервиса.")

    return (
        f"Здравствуйте!\n\n"
        f"Прошу отменить мою подписку на сервис «{name}» и прекратить дальнейшие списания. "
        "Пожалуйста, подтвердите отмену подписки. Если это допускают правила сервиса, "
        "прошу также рассмотреть возможность возврата последнего платежа.\n\n"
        "Спасибо!"
    )
