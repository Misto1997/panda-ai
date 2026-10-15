from app.core.enums import ValueFormat


def format_value(value, kind: ValueFormat | str = ValueFormat.NUMBER) -> str:
    if value is None:
        return "n/a"
    kind = ValueFormat(kind) if not isinstance(kind, ValueFormat) else kind
    if kind == ValueFormat.PERCENT:
        return f"{value * 100:.2f}%"
    magnitude = abs(value)
    if magnitude >= 1e9:
        short = f"{magnitude / 1e9:.2f}B"
    elif magnitude >= 1e6:
        short = f"{magnitude / 1e6:.2f}M"
    elif magnitude >= 1e4 or kind == ValueFormat.NUMBER:
        short = f"{magnitude / 1e3:.1f}K" if magnitude >= 1e4 else f"{magnitude:,.0f}"
    else:
        short = f"{magnitude:,.2f}"
    sign = "-" if value < 0 else ""
    return f"{sign}${short}" if kind == ValueFormat.CURRENCY else f"{sign}{short}"
