# app.py — Google Places Lead Toplayıcı (No-Website Focus)
# Özellikler:
# - Sektör(ler) (virgüllü) + çoklu ilçe (virgüllü)
# - Sadece GERÇEK web sitesi OLMAYANları listeler (Facebook/IG/Linktree/WhatsApp = sosyal)
# - Place Details (telefon/website/rating/reviews/types), filtre/sıralama, CSV/PDF
# - Limit ilçe başına sektörler arasında ADİL dağıtılır (round-robin)
# NOT: .env içine GOOGLE_MAPS_API_KEY koy; repo'ya koyma.

import os, time, re, math
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
from urllib.parse import urlparse

load_dotenv()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL     = "https://maps.googleapis.com/maps/api/place/details/json"

st.set_page_config(page_title="Places Lead - No Website", page_icon="🗺️", layout="wide")
st.title("🗺️ Google Places Lead — Web Sitesi OLMAYANLAR")

# ---- Buton boyutlandırma (isteğe bağlı)
st.markdown("""
<style>
div.stButton > button {
    height: 56px; font-size: 20px; border-radius: 12px; padding: 0.25rem 1rem;
}
</style>
""", unsafe_allow_html=True)

if not API_KEY:
    st.error("GOOGLE_MAPS_API_KEY bulunamadı. `.env` dosyasını kontrol et.")
    st.stop()

with st.expander("ℹ️ İpucu", expanded=False):
    st.markdown("""
- Bu sürüm **gerçek web sitesi olanları eler**. Facebook/Instagram/Linktree/WhatsApp linkleri **sosyal** sayılır ve **listeye dahil edilir**.
- Billing aktif değilse Place Details `REQUEST_DENIED` döner.
- PDF için klasörde **DejaVuSans.ttf** bulundur (Türkçe için), yoksa ASCII fallback devreye girer.
""")

# ---------------- UI ----------------
c1, c2, c3, c4 = st.columns([3,3,3,2])
with c1:
    sectors_raw = st.text_input("Sektör(ler) — virgüllü", value="berber, manav")
    sectors = [s.strip() for s in sectors_raw.split(",") if s.strip()]
with c2:
    city = st.text_input("Şehir", value="Samsun")
with c3:
    districts_raw = st.text_input("İlçe(ler) — virgüllü", value="Atakum, İlkadım, Canik")
    districts = [d.strip() for d in districts_raw.split(",") if d.strip()]
with c4:
    limit_per_district = st.number_input("Kayıt limiti / ilçe", min_value=10, max_value=200, value=60, step=10)

with st.expander("🎯 Filtre/Sıralama"):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        min_rating = st.slider("Min puan", 0.0, 5.0, 0.0, 0.1)
    with fc2:
        min_reviews = st.number_input("Min yorum", min_value=0, value=0, step=5)
    with fc3:
        name_contains = st.text_input("İsim içerir (ops.)", value="")
    with fc4:
        sort_by = st.selectbox("Sırala", ["İsim (A→Z)", "Puan (yüksek→düşük)", "Yorum (çok→az)"], index=0)

b1, b2, b3 = st.columns([1, 2, 1])
with b2:
    start_btn = st.button("🔍 Ara", type="primary", use_container_width=True)

# ---------------- Yardımcılar ----------------
SOCIAL_DOMAINS = {
    "facebook.com","m.facebook.com","l.facebook.com",
    "instagram.com","l.instagram.com",
    "linktr.ee","x.com","twitter.com","tiktok.com",
    "wa.me","whatsapp.com"
}

def is_social_url(u: str) -> bool:
    if not u:
        return False
    try:
        host = urlparse(u).netloc.lower()
        return any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)
    except Exception:
        return False

def _safe_get(url, params, tries=5, timeout=30):
    for i in range(tries):
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code in (429,) or r.status_code >= 500:
            time.sleep(2 + i); continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

@st.cache_data(ttl=3600, show_spinner=False)
def text_search(full_query, page_token=None, api_key=""):
    params = {"query": full_query, "key": api_key, "language":"tr", "region":"TR"}
    if page_token:
        params["pagetoken"] = page_token
    return _safe_get(TEXT_SEARCH_URL, params).json()

@st.cache_data(ttl=3600, show_spinner=False)
def place_details(place_id, api_key=""):
    fields = ",".join([
        "place_id","name","formatted_address","types",
        "international_phone_number","website","rating","user_ratings_total","url"
    ])
    params = {"place_id": place_id, "fields": fields, "key": api_key, "language":"tr", "region":"TR"}
    return _safe_get(DETAILS_URL, params).json()

def normalize_phone_tr(s: str) -> str:
    if not s: return ""
    digits = re.sub(r"\D+", "", s)
    if digits.startswith("90") and len(digits) == 12: return digits
    if len(digits) == 11 and digits.startswith("0"): return "90" + digits[1:]
    if len(digits) == 10: return "90" + digits
    return digits

def df_to_csv_bom(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")

def _ascii_fallback(s: str) -> str:
    table = str.maketrans({
        "—": "-", "–": "-",
        "ı":"i","İ":"I","ş":"s","Ş":"S","ğ":"g","Ğ":"G","ç":"c","Ç":"C","ö":"o","Ö":"O","ü":"u","Ü":"U",
    })
    return (s or "").translate(table)

def df_to_pdf_bytes(df: pd.DataFrame) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    font_path = "DejaVuSans.ttf"
    use_unicode = os.path.exists(font_path)
    if use_unicode:
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=9)
    else:
        pdf.set_font("Helvetica", size=9)

    col_width_map = {
        "name": 60, "district": 35, "address": 90, "phone": 35, "website": 60,
        "site_type": 18, "rating": 15, "reviews": 18, "google_maps_url": 70,
        "place_id": 60, "kw": 28, "types": 55, "whatsapp": 55
    }
    cols = list(df.columns)
    widths = [col_width_map.get(c, 45) for c in cols]

    def _t(v):
        s = "" if pd.isna(v) else str(v)
        return s if use_unicode else _ascii_fallback(s)

    def row_writer(cells):
        for w, txt in zip(widths, cells):
            pdf.cell(w, 6, txt=_t(txt)[:200], border=1)
        pdf.ln(6)

    pdf.add_page()
    pdf.cell(0, 8, _t("Google Places Leads - No Website"), ln=1)
    row_writer(cols)
    for _, r in df.iterrows():
        row_writer([r.get(c, "") for c in cols])

    return pdf.output(dest="S").encode("latin-1", "ignore")

# ----------- ADİL TOPLAMA: limit ilçe içinde sektörler arası paylaştırılır -----------
def run_pipeline_for_district(city, district, keywords, per_limit):
    # Her sektör için ayrı kova; sonra round-robin ile birleştireceğiz
    meta_by_pid = {}
    buckets = {kw: [] for kw in keywords}
    per_kw_limit = max(1, math.ceil(per_limit / max(1, len(keywords))))

    for kw in keywords:
        fetched_kw = 0
        next_token = None
        while True:
            if next_token: time.sleep(2)
            q = " ".join([kw, district, city, "Türkiye"]).strip()
            data = text_search(q, page_token=next_token, api_key=API_KEY)
            if data.get("status") == "REQUEST_DENIED":
                raise RuntimeError(f"Text Search reddedildi: {data.get('error_message')}")
            for item in data.get("results", []):
                if fetched_kw >= per_kw_limit:
                    break
                pid = item.get("place_id")
                if not pid or pid in meta_by_pid:
                    continue
                meta_by_pid[pid] = {
                    "kw": kw,
                    "name_hint": item.get("name",""),
                    "addr_hint": item.get("formatted_address","")
                }
                buckets[kw].append(pid)
                fetched_kw += 1
            if fetched_kw >= per_kw_limit:
                break
            next_token = data.get("next_page_token")
            if not next_token:
                break

    # Round-robin ile adil seçimi yap: toplam per_limit kadar
    selected_pids = []
    i = 0
    while len(selected_pids) < per_limit and any(i < len(buckets[k]) for k in keywords):
        for kw in keywords:
            if i < len(buckets[kw]):
                selected_pids.append(buckets[kw][i])
                if len(selected_pids) >= per_limit:
                    break
        i += 1

    # Detaylar
    rows, first_err = [], None
    for pid in selected_pids:
        meta = meta_by_pid[pid]
        try:
            dres = place_details(pid, api_key=API_KEY)
            res = dres.get("result", {}) if dres.get("status") == "OK" else {}
            website = res.get("website", "")
            phone = res.get("international_phone_number", "")
            site_type = "social" if is_social_url(website) else ("website" if website else "none")
            if site_type == "website":
                continue
            wa = normalize_phone_tr(phone)
            rows.append({
                "name": res.get("name") or meta["name_hint"],
                "district": district or "",
                "address": res.get("formatted_address") or meta["addr_hint"],
                "phone": phone,
                "website": website or "",
                "site_type": site_type,
                "rating": res.get("rating", ""),
                "reviews": res.get("user_ratings_total", ""),
                "google_maps_url": res.get("url",""),
                "place_id": pid,
                "kw": meta["kw"],
                "types": ", ".join(res.get("types", [])),
                "whatsapp": f"https://wa.me/{wa}" if wa else ""
            })
        except Exception as e:
            if not first_err: first_err = str(e)
            continue

    return rows, first_err

# ---------------- Çalıştırma ----------------
if start_btn:
    if not sectors:
        st.error("En az bir sektör gir."); st.stop()
    if not city:
        st.error("Şehir boş olamaz."); st.stop()

    all_rows, per_dist = [], {}
    try:
        targets = districts if districts else [""]
        pb = st.progress(0, text="İlçeler taranıyor…")
        for i, d in enumerate(targets, start=1):
            rows, first_err = run_pipeline_for_district(city, d, sectors, int(limit_per_district))
            all_rows.extend(rows)
            per_dist[d or "—"] = len(rows)
            pb.progress(i/len(targets), text=f"{d or '—'} tamam ({len(rows)} kayıt)")
            if first_err:
                st.warning(f"{d or '—'} → uyarı: {first_err}")
        pb.empty()
    except Exception as e:
        st.error(f"Hata: {e}"); st.stop()

    if not all_rows:
        st.info("Kayıt bulunamadı. Sektörleri/ilçeleri genişletip tekrar deneyin.")
    else:
        df = pd.DataFrame(all_rows)

        # ---- Filtreler
        if min_rating > 0.0:
            df = df[pd.to_numeric(df["rating"], errors="coerce").fillna(0) >= float(min_rating)]
        if min_reviews > 0:
            df = df[pd.to_numeric(df["reviews"], errors="coerce").fillna(0) >= int(min_reviews)]
        if name_contains.strip():
            key = name_contains.strip().lower()
            df = df[df["name"].str.lower().str.contains(key, na=False)]

        # ---- Sıralama
        if sort_by == "İsim (A→Z)":
            df["_key"] = df["name"].str.lower()
            df = df.sort_values("_key", kind="mergesort").drop(columns=["_key"])
        elif sort_by == "Puan (yüksek→düşük)":
            df["rating_num"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0)
            df = df.sort_values("rating_num", ascending=False, kind="mergesort").drop(columns=["rating_num"])
        elif sort_by == "Yorum (çok→az)":
            df["reviews_num"] = pd.to_numeric(df["reviews"], errors="coerce").fillna(0)
            df = df.sort_values("reviews_num", ascending=False, kind="mergesort").drop(columns=["reviews_num"])

        # ---- Tekilleştirme
        if "place_id" in df.columns:
            df.drop_duplicates(subset=["place_id"], inplace=True)

        st.success(f"Toplam {len(df)} kayıt (yalnızca gerçek web sitesi OLMAYANlar). İlçe dağılımı: {per_dist}")

        st.data_editor(
            df,
            use_container_width=True, hide_index=True, height=520,
            column_config={
                "website": st.column_config.LinkColumn("website"),
                "google_maps_url": st.column_config.LinkColumn("google_maps_url"),
                "whatsapp": st.column_config.LinkColumn("whatsapp", help="WhatsApp'a direkt mesaj"),
                "rating": st.column_config.NumberColumn(format="%.1f"),
                "reviews": st.column_config.NumberColumn(format="%d"),
                "site_type": st.column_config.TextColumn("site_type", help="social / none"),
            }
        )

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ CSV indir (UTF-8-BOM)",
                data=df_to_csv_bom(df),
                file_name=f"leads_no_website_{city}.csv".replace(" ", "_"),
                mime="text/csv", use_container_width=True
            )
        with c2:
            try:
                st.download_button(
                    "⬇️ PDF indir",
                    data=df_to_pdf_bytes(df),
                    file_name=f"leads_no_website_{city}.pdf".replace(" ", "_"),
                    mime="application/pdf", use_container_width=True
                )
            except Exception as e:
                st.error(f"PDF oluşturulamadı: {e}")
else:
    st.caption("Sektör(ler), şehir ve ilçe(ler) → **Ara**")
