import json
import os
from enum import Enum
from typing import Any


class AIModel(Enum):
    OPENAI_GPT4O = "openai_gpt4o"
    ANTHROPIC_CLAUDE = "anthropic_claude"


_SYSTEM_PROMPT = """\
あなたは多言語領収書の会計データ抽出専門家です。

【厳守ルール】
1. 数字の推論・推測は絶対に禁止。領収書に記載された数値のみを使用すること
2. 読み取れない項目は null を返すこと（推測で埋めない）
3. 金額はすべて数値型（文字列不可）で返すこと
4. 日付は ISO 8601 形式（YYYY-MM-DD）。不明な場合は null
5. 通貨コードは ISO 4217 に従うこと（ILS, IRR, AED, USD 等）
6. 品目名は原文を保持しつつ日本語訳を括弧内に付記すること

必ず以下の JSON 形式のみを返すこと。JSON 以外の文字は一切含めないこと:
{
  "vendor_name": "店舗・会社名",
  "date": "YYYY-MM-DD or null",
  "currency": "ISO 4217コード",
  "items": [
    {
      "description": "品目名（日本語訳）",
      "quantity": 数値 or null,
      "unit_price": 数値 or null,
      "amount": 数値 or null
    }
  ],
  "subtotal": 数値 or null,
  "tax_amount": 数値 or null,
  "tax_rate": 数値 or null,
  "total": 数値 or null,
  "notes": "特記事項（なければ空文字）"
}"""

_USER_PROMPT = """\
以下の OCR テキストは領収書から抽出されたものです。
上記ルールに従い、会計データを JSON として抽出してください。

--- OCR テキスト ---
{ocr_text}
---"""


def _parse_json(text: str) -> dict[str, Any]:
    # Anthropic が Markdown コードブロックを返す場合に対応
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON が見つかりませんでした")
    return json.loads(text[start:end])


def _call_openai(ocr_text: str) -> dict[str, Any]:
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(ocr_text=ocr_text)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def _call_anthropic(ocr_text: str) -> dict[str, Any]:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _USER_PROMPT.format(ocr_text=ocr_text)}],
        temperature=0,
    )
    return _parse_json(resp.content[0].text)


def _verify_amounts(data: dict[str, Any]) -> dict[str, Any]:
    """LLMに依存せず Python 側で金額整合性を検証する。"""
    items = data.get("items") or []
    total = data.get("total")
    subtotal = data.get("subtotal")
    tax_amount = data.get("tax_amount") or 0

    messages: list[str] = []

    try:
        item_sum = sum(float(item["amount"]) for item in items if item.get("amount") is not None)

        if subtotal is not None:
            if abs(item_sum - float(subtotal)) > 0.02:
                messages.append(
                    f"内訳合計 {item_sum:.2f} と小計 {float(subtotal):.2f} が一致しません"
                )

        if total is not None:
            base = float(subtotal) if subtotal is not None else item_sum
            expected = base + float(tax_amount)
            if abs(expected - float(total)) > 0.02:
                messages.append(
                    f"小計＋税 {expected:.2f} と合計 {float(total):.2f} が一致しません"
                )
    except (TypeError, ValueError):
        # 数値変換できない項目がある場合はスキップ
        pass

    data["verification_status"] = "error" if messages else "ok"
    data["verification_messages"] = messages
    return data


def analyze_receipt(ocr_text: str, model: AIModel = AIModel.OPENAI_GPT4O) -> dict[str, Any]:
    if model == AIModel.OPENAI_GPT4O:
        data = _call_openai(ocr_text)
    else:
        data = _call_anthropic(ocr_text)
    return _verify_amounts(data)
