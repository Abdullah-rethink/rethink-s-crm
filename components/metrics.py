import pandas as pd

def format_currency(val, symbol="£"):
    """Formats numeric values into clean currency strings rounded to 2 decimal places."""
    if pd.isna(val) or val is None:
        return f"{symbol}0.00"
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return f"{symbol}0.00"

    if f_val >= 1_000_000:
        return f"{symbol}{f_val / 1_000_000:,.2f}M"
    elif f_val >= 100_000:
        return f"{symbol}{f_val / 1_000:,.2f}K"
    else:
        return f"{symbol}{f_val:,.2f}"

def format_number(val):
    """Formats integers/floats into clean numeric strings rounded to 2 decimal places for non-integers."""
    if pd.isna(val) or val is None:
        return "0"
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return "0"

    if f_val.is_integer():
        if f_val >= 1_000_000:
            return f"{f_val / 1_000_000:,.2f}M"
        elif f_val >= 100_000:
            return f"{f_val / 1_000:,.1f}K"
        else:
            return f"{int(f_val):,}"
    else:
        return f"{f_val:,.2f}"
