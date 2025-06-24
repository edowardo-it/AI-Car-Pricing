import streamlit as st
import pandas as pd
import re
import os

# Path file Excel
FILE_PATH = "./Data_Lelang_Toyota.xlsx"

@st.cache_data
def load_data():
    return pd.read_excel(FILE_PATH)

# Format angka ke Rupiah
def format_rupiah(value):
    return f"Rp{int(value):,}".replace(",", ".")

# Fungsi pencarian berdasarkan parameter
def cari_harga_mobil(df, brand, tipe_list, tahun, region=None, match_partial_type=True):
    df = df[['Brand', 'Type', 'Year', 'OTRPrice', 'SalePrice', 'Region', 'TahunLelang']]
    query = (
        (df['Brand'].str.lower() == brand.lower()) &
        (df['Year'] == tahun)
    )

    if tipe_list:
        type_query = pd.Series([False] * len(df))
        for t in tipe_list:
            if match_partial_type:
                type_query |= df['Type'].str.lower().str.contains(t.lower())
            else:
                type_query |= df['Type'].str.lower() == t.lower()
        query &= type_query
    else:
        query &= False  # Tidak ada tipe cocok

    if region:
        query &= df['Region'].str.lower().str.contains(region.lower())

    hasil = df[query]

    if hasil.empty:
        return f"Maaf, tidak ada data untuk mobil {brand} {tipe_list} tahun {tahun}.", None, None
    else:
        max_otr = hasil['OTRPrice'].max()
        min_otr = hasil['OTRPrice'].min()
        avg_otr = hasil['OTRPrice'].mean()
        min_lelang = hasil['SalePrice'].min()
        max_lelang = hasil['SalePrice'].max()

        region_info = region if region else "SEMUA REGION"
        tipe_info = ", ".join([t.upper() for t in tipe_list])

        hasil_string = (
            f"📌 **Informasi untuk {brand.upper()} {tipe_info} tahun {tahun} (Region: {region_info})**\n\n"
            f"- 🔼 Harga OTR Tertinggi: {format_rupiah(max_otr)}\n"
            f"- 🔽 Harga OTR Terendah: {format_rupiah(min_otr)}\n"
            f"- 📊 Rata-rata Harga OTR: {format_rupiah(avg_otr)}\n"
            f"- 💰 Harga Lelang: {format_rupiah(min_lelang)} s.d. {format_rupiah(max_lelang)}"
        )

        hasil_riwayat = hasil[hasil['TahunLelang'] >= tahun]
        lelang_summary = hasil_riwayat.groupby("TahunLelang").agg(
            **{
                "Min Lelang": ("SalePrice", "min"),
                "Max Lelang": ("SalePrice", "max")
            }
        ).reset_index().sort_values("TahunLelang")

        lelang_summary["Min Lelang"] = lelang_summary["Min Lelang"].apply(format_rupiah)
        lelang_summary["Max Lelang"] = lelang_summary["Max Lelang"].apply(format_rupiah)

        return hasil_string, hasil, lelang_summary

# Mapping sinonim region
def map_region_from_text(text):
    text = text.lower()
    region_mapping = {
        "jabodetabek": ["jakarta", "bogor", "depok", "tangerang", "bekasi", "jabodetabek", "serang"],
        "jawa": ["jawa", "jawa tengah", "jawa barat", "jawa timur", "pulau jawa", "bandung", "banyumas", "bojonegoro", "cakranegara", "cirebon", "garut", "jember", "jogja", "kabupaten banyumas", "banyumas", "kediri", "bandung", "madiun", "malang", "mojokerto", "pati", "purwokerto", "semarang", "solo", "surabaya", "tegal", "yogyakarta"],
        "sumatera": ["sumatera", "sumatera utara", "sumatera selatan", "medan", "lampung", "aceh", "bangka belitung", "batam", "kota batam", "bengkulu", "jambi", "kota bengkulu", "kota medan", "kota padang", "kota palembang", "kota pekanbaru", "lampung", "medan", "padang", "palembang", "pekanbaru"],
        "others": ["luar jawa", "lainnya", "kalimantan", "sulawesi", "papua", "balikpapan", "banjarmasin", "denpasar", "gorontalo", "kendari", "kota balikpapan", "kota banjarmasin", "kota denpasar", "kota palangkaraya", "makassar", "manado", "palangkaraya", "palu", "pontianak", "samarinda"]
    }

    for canonical, synonyms in region_mapping.items():
        if any(keyword in text for keyword in synonyms):
            return canonical.capitalize()

    return None

import re

def extract_from_text(text, df):
    # Regex untuk format eksak
    match = re.search(r"berapa harga (.+?) (.+?) tahun (20[1-2][0-9]) di (.+?)\?", text.lower())
    
    if not match:
        return None, None, None, None

    brand_raw = match.group(1).strip()
    type_raw = match.group(2).strip()
    year_raw = int(match.group(3).strip())
    region_raw = match.group(4).strip()

    type_raw_lower = type_raw.lower()
    brand_raw_lower = brand_raw.lower()

    brands = df['Brand'].dropna().unique().tolist()
    types = df['Type'].dropna().unique().tolist()

    brand = next((b for b in brands if b.lower() == brand_raw_lower), None)

    # Case 1: exact match
    exact_match = next((t for t in types if t.lower() == type_raw_lower), None)
    if exact_match:
        tipe = [exact_match]  # bungkus dalam list agar konsisten
    else:
        # Case 2: partial match
        tipe = [t for t in types if type_raw_lower in t.lower()]
        if not tipe:
            tipe = None

    year = int(year_raw)
    region = map_region_from_text(region_raw)

    return brand, tipe, year, region

# ---------------- STREAMLIT APP ---------------- #
st.set_page_config(page_title="Tanya Harga Mobil", layout="centered")
st.title("🚗 Informasi Harga OTR & Lelang Mobil")

if not os.path.exists(FILE_PATH):
    st.error(f"❌ File Excel tidak ditemukan di path: {FILE_PATH}")
else:
    df = load_data()

    input_text = st.text_input("Tanyakan harga mobil (contoh: Berapa harga Toyota Agya tahun 2022 di Jakarta?)")

    if st.button("Cari Jawaban"):
        brand, tipe_list, tahun, region = extract_from_text(input_text, df)

        if brand and tipe_list and tahun:
            hasil_text, hasil_data, lelang_summary = cari_harga_mobil(df, brand, tipe_list, tahun, region, match_partial_type=True)

            st.markdown("---")
            st.markdown("### 📊 Hasil Analisis")
            st.markdown(hasil_text)

            if lelang_summary is not None and not lelang_summary.empty:
                st.markdown("### 📈 Riwayat Harga Lelang")
                st.dataframe(lelang_summary.set_index("TahunLelang"))
        else:
            st.warning("⚠️ Mohon pastikan teks kamu menyebutkan **Merk**, **Tipe**, dan **Tahun Mobil**.")