"""Generation of safe, ready-to-send subscription cancellation letters."""


UNSUBSCRIBE_PROMPT = """Напиши краткое и профессиональное письмо в поддержку сервиса
{service_name} на русском языке. Используй только переданное название сервиса.
Не придумывай факты, обстоятельства или персональные данные пользователя (имя,
email, номер карты, договора и т. п.). Вежливо попроси отменить подписку,
прекратить дальнейшие списания и подтвердить отмену. Упомяни возможность
рассмотреть возврат последнего платежа только если это допускают правила
сервиса."""


def _validate_service_name(service_name: str) -> str:
    """Return a cleaned service name or raise a clear validation error."""
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("Название сервиса должно быть непустой строкой.")
    return service_name.strip()


def generate_fallback_letter(service_name: str) -> str:
    """Create a Russian cancellation request without APIs or personal data."""
    name = _validate_service_name(service_name)
    return (
        "Здравствуйте!\n\n"
        f"Прошу отменить мою подписку на сервис «{name}» и прекратить дальнейшие списания. "
        "Пожалуйста, подтвердите отмену подписки. "
        "Если это допускают правила сервиса, прошу также рассмотреть возможность "
        "возврата последнего платежа.\n\n"
        "Спасибо!"
    )


def generate_unsubscribe_letter(service_name: str, use_ai: bool = False) -> str:
    """Return a ready-to-send cancellation letter.

    ``use_ai`` is reserved for a future LLM integration. Until an API client is
    configured, both paths safely use the local fallback template.
    """
    _validate_service_name(service_name)

    if use_ai:
        # Future LLM API call should be implemented here using UNSUBSCRIBE_PROMPT.
        # Fallback remains mandatory when the API is unavailable or fails.
        return generate_fallback_letter(service_name)

    return generate_fallback_letter(service_name)
