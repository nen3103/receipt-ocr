import io
from typing import Any

import pandas as pd


def _to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
    base = {
        "店舗名": data.get("vendor_name", ""),
        "日付": data.get("date", ""),
        "通貨": data.get("currency", ""),
    }
    rows = []
    for item in data.get("items") or []:
        rows.append({
            **base,
            "品目": item.get("description", ""),
            "数量": item.get("quantity", ""),
            "単価": item.get("unit_price", ""),
            "金額": item.get("amount", ""),
        })

    def _summary_row(label: str, amount: Any) -> dict:
        return {**base, "品目": label, "数量": "", "単価": "", "金額": amount}

    if data.get("subtotal") is not None:
        rows.append(_summary_row("【小計】", data["subtotal"]))
    if data.get("tax_amount") is not None:
        rate = data.get("tax_rate")
        label = f"【消費税 {rate}%】" if rate else "【消費税】"
        rows.append(_summary_row(label, data["tax_amount"]))
    if data.get("total") is not None:
        rows.append(_summary_row("【合計】", data["total"]))

    return pd.DataFrame(rows)


def to_csv(data: dict[str, Any]) -> bytes:
    return _to_dataframe(data).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def to_excel(data: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _to_dataframe(data).to_excel(writer, index=False, sheet_name="領収書データ")
    return buf.getvalue()
