"""Reading bank statements into the common transaction format."""

from pathlib import Path

import pandas as pd


_COLUMN_ALIASES = {
    "date": {"date", "дата", "дата и время", "operation_date"},
    "description": {"description", "описание", "merchant", "recipient"},
    "amount": {"amount", "сумма", "сумма (rub)", "sum"},
}


def _normalize_column_name(column) -> str:
    """Make a source header comparable with known column aliases."""
    return str(column).strip().lower().lstrip("\ufeff")


def _find_column(columns, aliases):
    """Return the first source column whose normalized name matches an alias."""
    normalized_columns = {
        _normalize_column_name(column): column for column in columns
    }
    normalized_aliases = {_normalize_column_name(alias) for alias in aliases}
    for alias in normalized_aliases:
        if alias in normalized_columns:
            return normalized_columns[alias]
    return None


def _parse_amount(value):
    """Convert common statement amounts, including Russian decimal commas."""
    if isinstance(value, str):
        value = value.strip().replace("\u00a0", "").replace(" ", "")
        value = value.replace(",", ".")
    return pd.to_numeric(value, errors="coerce")


def parse_statement(file_path: str) -> pd.DataFrame:
    """Read a CSV or XLSX statement and return date, description and amount columns.

    Rows where any required value cannot be converted are skipped.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Файл не найден: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            source = pd.read_csv(path, sep=None, engine="python")
        except UnicodeDecodeError:
            source = pd.read_csv(path, sep=None, engine="python", encoding="cp1251")
    elif suffix == ".xlsx":
        source = pd.read_excel(path)
    else:
        raise ValueError("Поддерживаются только файлы CSV и XLSX.")

    if source.empty:
        raise ValueError("Выписка пуста.")

    source_columns = {}
    for standard_name, aliases in _COLUMN_ALIASES.items():
        column = _find_column(source.columns, aliases)
        if column is None:
            raise ValueError(
                f"Не удалось определить колонку '{standard_name}'. "
                "Проверьте названия колонок выписки."
            )
        source_columns[standard_name] = column

    result = source.loc[:, [source_columns["date"], source_columns["description"], source_columns["amount"]]].copy()
    result.columns = ["date", "description", "amount"]
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result["description"] = result["description"].astype("string").str.strip()
    # Bank statements often mark expenses as negative; analysis uses their magnitude.
    result["amount"] = result["amount"].map(_parse_amount).abs()
    result = result.dropna(subset=["date", "description", "amount"])
    result = result[result["description"] != ""]

    if result.empty:
        raise ValueError("В выписке нет строк, пригодных для обработки.")

    return result.reset_index(drop=True)
