import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ローカル用 .env を読み込む（クラウドでは無視される）
from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# ────────────────────────────────────────────
# Streamlit Secrets → 環境変数へ橋渡し（クラウド対応）
# ────────────────────────────────────────────
def _load_secrets():
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        try:
            val = st.secrets.get(key)
            if val:
                os.environ[key] = val
        except Exception:
            pass

    # Google Cloud Vision: secrets に [gcp_service_account] がある場合
    try:
        if "gcp_service_account" in st.secrets:
            import json, tempfile
            sa = dict(st.secrets["gcp_service_account"])
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w")
            json.dump(sa, tmp)
            tmp.close()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
    except Exception:
        pass

_load_secrets()

# ────────────────────────────────────────────
# パスワード保護
# ────────────────────────────────────────────
def _check_password() -> bool:
    try:
        correct = st.secrets.get("APP_PASSWORD") or os.environ.get("APP_PASSWORD", "")
    except Exception:
        correct = os.environ.get("APP_PASSWORD", "")

    if not correct:
        return True  # パスワード未設定なら認証スキップ（ローカル開発用）

    if st.session_state.get("authenticated"):
        return True

    st.title("🧾 多言語領収書 OCR")
    pw = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pw == correct:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()
    return False

_check_password()

# ────────────────────────────────────────────
# 以下、認証後のアプリ本体
# ────────────────────────────────────────────
from services.ocr import OCREngine, extract_text
from services.analyzer import AIModel, analyze_receipt
from utils.export import to_csv, to_excel
from utils.image_utils import preprocess_for_ocr

st.set_page_config(
    page_title="多言語領収書 OCR",
    page_icon="🧾",
    layout="wide",
)

# ────────────────────────────────────────────
# サイドバー：設定
# ────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

    ocr_engine = st.selectbox(
        "OCR エンジン",
        options=[OCREngine.CLOUD_VISION, OCREngine.TESSERACT],
        format_func=lambda x: (
            "Google Cloud Vision（高精度・推奨）"
            if x == OCREngine.CLOUD_VISION
            else "Tesseract（ローカル・無料）"
        ),
    )

    ocr_lang = "auto"
    if ocr_engine == OCREngine.TESSERACT:
        ocr_lang = st.selectbox(
            "言語パック",
            options=["auto", "arabic", "persian", "hebrew", "english"],
            format_func=lambda x: {
                "auto": "自動（アラビア語＋ペルシャ語＋ヘブライ語＋英語）",
                "arabic": "アラビア語 (ara)",
                "persian": "ペルシャ語 (fas)",
                "hebrew": "ヘブライ語 (heb)",
                "english": "英語 (eng)",
            }[x],
        )
        st.caption("※ Tesseract に各言語パックのインストールが必要です")

    ai_model = st.selectbox(
        "AI モデル",
        options=[AIModel.OPENAI_GPT4O, AIModel.ANTHROPIC_CLAUDE],
        format_func=lambda x: (
            "GPT-4o（OpenAI）"
            if x == AIModel.OPENAI_GPT4O
            else "Claude Sonnet（Anthropic）"
        ),
    )

    use_preprocess = st.checkbox("OCR 前処理（コントラスト強調）", value=True)

    st.divider()
    if st.button("ログアウト", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

# ────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────
st.title("🧾 多言語領収書 OCR・会計データ抽出")
st.caption("アラビア語・ペルシャ語・ヘブライ語等の領収書に対応")

uploaded_file = st.file_uploader(
    "領収書をアップロード（PNG / JPG / PDF）",
    type=["png", "jpg", "jpeg", "pdf"],
)

if uploaded_file is None:
    st.info("ファイルをアップロードすると処理が開始されます。")
    st.stop()

file_bytes = uploaded_file.read()

with st.spinner("OCR 処理中..."):
    try:
        raw_text, images = extract_text(file_bytes, uploaded_file.name, ocr_engine, ocr_lang)
    except Exception as e:
        st.error(f"OCR エラー: {e}")
        st.stop()

if use_preprocess and ocr_engine == OCREngine.TESSERACT:
    with st.spinner("前処理後に再 OCR 中..."):
        try:
            import io as _io
            page_texts = []
            for img in images:
                buf = _io.BytesIO()
                preprocess_for_ocr(img).save(buf, format="PNG")
                t, _ = extract_text(buf.getvalue(), "tmp.png", ocr_engine, ocr_lang)
                page_texts.append(t)
            raw_text = "\n\n--- ページ区切り ---\n\n".join(page_texts)
        except Exception:
            pass

with st.spinner("AI 解析中..."):
    try:
        extracted = analyze_receipt(raw_text, ai_model)
    except Exception as e:
        st.error(f"AI 解析エラー: {e}")
        st.stop()

# ────────────────────────────────────────────
# 表示：画像 ｜ 抽出結果
# ────────────────────────────────────────────
col_img, col_form = st.columns([1, 1], gap="large")

with col_img:
    st.subheader("元画像")
    for i, img in enumerate(images):
        if len(images) > 1:
            st.caption(f"ページ {i + 1}")
        st.image(img, use_container_width=True)

    with st.expander("OCR 生テキスト（確認用）"):
        st.text(raw_text or "（テキストなし）")

with col_form:
    st.subheader("AI 抽出結果（編集可能）")

    if extracted.get("verification_status") == "error":
        for msg in extracted.get("verification_messages", []):
            st.warning(f"⚠️ {msg}")
    else:
        st.success("✅ 金額整合性チェック: 問題なし")

    with st.form("edit_form"):
        vendor   = st.text_input("店舗・会社名",          value=extracted.get("vendor_name") or "")
        date_val = st.text_input("日付（YYYY-MM-DD）",    value=extracted.get("date") or "")
        currency = st.text_input("通貨コード（ISO 4217）", value=extracted.get("currency") or "")

        st.markdown("---")
        st.markdown("**内訳**")

        items = extracted.get("items") or []
        edited_items: list[dict] = []

        for i, item in enumerate(items):
            c1, c2, c3, c4 = st.columns([3, 1, 2, 2])
            vis = "collapsed" if i > 0 else "visible"
            desc = c1.text_input("品目名", value=item.get("description") or "", key=f"desc_{i}", label_visibility=vis)
            qty  = c2.text_input("数量",   value=str(item.get("quantity") or ""),   key=f"qty_{i}",  label_visibility=vis)
            unit = c3.text_input("単価",   value=str(item.get("unit_price") or ""), key=f"unit_{i}", label_visibility=vis)
            amt  = c4.text_input("金額",   value=str(item.get("amount") or ""),     key=f"amt_{i}",  label_visibility=vis)
            edited_items.append({"description": desc, "quantity": qty, "unit_price": unit, "amount": amt})

        if not items:
            st.caption("内訳が抽出されませんでした")

        st.markdown("---")
        c_sub, c_tax, c_total = st.columns(3)
        subtotal_val = c_sub.text_input("小計",  value=str(extracted.get("subtotal") or ""))
        tax_val      = c_tax.text_input("税額",  value=str(extracted.get("tax_amount") or ""))
        total_val    = c_total.text_input("合計", value=str(extracted.get("total") or ""))
        notes_val    = st.text_area("備考",      value=extracted.get("notes") or "")

        submitted = st.form_submit_button("✅ 確定", type="primary", use_container_width=True)

    if submitted:
        st.session_state["confirmed_data"] = {
            "vendor_name": vendor,
            "date": date_val,
            "currency": currency,
            "items": edited_items,
            "subtotal": subtotal_val,
            "tax_amount": tax_val,
            "total": total_val,
            "notes": notes_val,
        }
        st.success("データを確定しました。下部からダウンロードできます。")

# ────────────────────────────────────────────
# ダウンロード
# ────────────────────────────────────────────
export_data = st.session_state.get("confirmed_data", extracted)
basename = os.path.splitext(uploaded_file.name)[0]

st.divider()
st.subheader("💾 ダウンロード")
dl1, dl2 = st.columns(2)

with dl1:
    try:
        st.download_button(
            "📄 CSV ダウンロード",
            data=to_csv(export_data),
            file_name=f"{basename}_receipt.csv",
            mime="text/csv",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"CSV 生成エラー: {e}")

with dl2:
    try:
        st.download_button(
            "📊 Excel ダウンロード",
            data=to_excel(export_data),
            file_name=f"{basename}_receipt.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"Excel 生成エラー: {e}")
