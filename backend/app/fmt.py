def fmt(v, kind: str) -> str:
    if v is None:
        return "n/a"
    if kind == "percent":
        return f"{v * 100:.2f}%"
    if kind == "currency":
        a = abs(v)
        s = f"{a / 1e9:.2f}B" if a >= 1e9 else f"{a / 1e6:.2f}M" if a >= 1e6 else f"{a / 1e3:.1f}K" if a >= 1e4 else f"{a:,.2f}"
        return f"{'-' if v < 0 else ''}${s}"
    a = abs(v)
    return f"{v / 1e9:.2f}B" if a >= 1e9 else f"{v / 1e6:.2f}M" if a >= 1e6 else f"{v:,.0f}"
