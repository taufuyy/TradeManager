"""
currency_utils.py
Centralized currency conversion utilities for Trade Manager.

Supports account currencies: USC (Cent), USD (Standard), IDR (Rupiah).
All conversion logic flows through these functions so there is
no hardcoded "/ 100.0" conversion scattered across the codebase.
"""


def get_currency_label(cfg) -> str:
    """Return the account currency label string (e.g. 'USC', 'USD', 'IDR')."""
    return cfg.get("account_currency", "USC")


def to_usd(value, cfg) -> float:
    """Convert a value in the account's native currency to USD."""
    cur = cfg.get("account_currency", "USC")
    if cur == "USC":
        return value / 100.0
    elif cur == "USD":
        return value
    elif cur == "IDR":
        rate = cfg.get("usd_idr_rate", 16250.0)
        return value / rate if rate > 0 else 0.0
    return value


def to_idr(value, cfg) -> float:
    """Convert a value in the account's native currency to IDR."""
    cur = cfg.get("account_currency", "USC")
    rate = cfg.get("usd_idr_rate", 16250.0)
    if cur == "USC":
        return (value / 100.0) * rate
    elif cur == "USD":
        return value * rate
    elif cur == "IDR":
        return value
    return value


def from_idr_to_account(idr_value, cfg) -> float:
    """Convert an IDR value back to account currency."""
    cur = cfg.get("account_currency", "USC")
    rate = cfg.get("usd_idr_rate", 16250.0)
    if cur == "USC":
        return (idr_value / rate) * 100.0 if rate > 0 else 0.0
    elif cur == "USD":
        return idr_value / rate if rate > 0 else 0.0
    elif cur == "IDR":
        return idr_value
    return idr_value


def format_amount(value, cfg) -> str:
    """
    Format a value in account currency into a human-readable string.

    Examples:
        USC: "+1,234.56 USC  (Rp 2,234,000)"
        USD: "+12.35 USD  (Rp 2,234,000)"
        IDR: "Rp 1,234,000"
    """
    cur = cfg.get("account_currency", "USC")
    sign = "+" if value >= 0 else ""

    if cur == "IDR":
        return f"{sign}Rp {value:,.0f}"
    else:
        idr = to_idr(value, cfg)
        return f"{sign}{value:,.2f} {cur}  (Rp {idr:,.0f})"


def format_amount_short(value, cfg) -> str:
    """
    Shorter format: just the value + currency label.
    E.g. "1,234.56 USC" / "12.35 USD" / "Rp 1,234,000"
    """
    cur = cfg.get("account_currency", "USC")
    if cur == "IDR":
        return f"Rp {value:,.0f}"
    else:
        return f"{value:,.2f} {cur}"


def format_with_idr(value, cfg) -> str:
    """
    Format like "1,234.56 USC (Rp 2,234,000)" without sign prefix.
    Used for balance/equity/margin display.
    """
    cur = cfg.get("account_currency", "USC")
    if cur == "IDR":
        return f"Rp {value:,.0f}"
    else:
        idr = to_idr(value, cfg)
        return f"{value:,.2f} {cur} (Rp {idr:,.0f})"


def format_perf_card_primary(value, cfg) -> str:
    """Primary value for performance cards: IDR string."""
    idr = to_idr(value, cfg)
    idr_str = f"{idr:,.0f}".replace(",", ".")
    return f"Rp {idr_str}"


def format_perf_card_secondary(value, cfg) -> str:
    """Secondary value for performance cards: account currency."""
    cur = cfg.get("account_currency", "USC")
    if cur == "IDR":
        return ""
    return f"({value:,.2f} {cur})"
