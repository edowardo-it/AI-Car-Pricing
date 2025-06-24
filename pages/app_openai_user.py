import streamlit as st
import pandas as pd
import re
import os
from openai import AzureOpenAI

# ====== KONFIGURASI AZURE OPENAI ======
client = AzureOpenAI(
    api_key="7orN6V8Ld4yCHcUzgNebd0mUrmMYVK2mxddoKh3cWtlOT6SiCF3oJQQJ99BDACfhMk5XJ3w3AAABACOGqJHO", # API Key Azure OpenAI
    api_version="2023-07-01-preview",
    azure_endpoint="https://carpriceopenai.openai.azure.com" # endpoint resource
)
AZURE_MODEL = "gpt-4o-mini" # deployment name model di Azure

# ====== GPT hanya berperan sebagai "NLP Assistant" (extractor), bukan Answer Generator======
def ekstrak_parameter_dengan_gpt(input_text):
    try:
        response = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tugasmu adalah mengekstrak informasi dan intent dari pertanyaan tentang harga mobil. "
                        "Jika user bertanya harga mobil, intent='tanya_harga'. "
                        "Jika user bertanya apakah harga tertentu overprice/underprice, intent='cek_over_under'. "
                        "Berikan hasil dalam format JSON seperti: "
                        "{'intent': 'tanya_harga', 'brand': 'Toyota', 'tipe': 'Avanza', 'tahun': 2018, 'region': 'Jakarta'} "
                        "atau {'intent': 'cek_over_under', 'brand': 'Toyota', 'tipe': 'Avanza', 'tahun': 2018, 'region': 'Jakarta', 'harga': 150000000} "
                        "atau null jika tidak bisa diekstrak. Jangan menebak jika tidak yakin."
                    )
                },
                {"role": "user", "content": input_text}
            ],
            temperature=0,
            max_tokens=200
        )
        hasil = response.choices[0].message.content
        return eval(hasil)
    except Exception as e:
        return None

# ====== Format Harga ======
def format_rupiah(value):
    juta = round(value / 1_000_000)  # dibulatkan ke juta terdekat
    return f"Rp {juta:,} juta".replace(",", ".")
    # return f"Rp{int(value):,}".replace(",", ".") # format: "Rp1.234.567"

# ====== Mapping Region ======
def map_region_from_text(text):
    text = text.lower()
    region_mapping = {
        "jabodetabek": ["jakarta", "bogor", "depok", "tangerang", "bekasi", "jabodetabek", "serang"],
        "jawa": ["jawa", "bandung", "semarang", "surabaya", "yogyakarta", "solo", "tegal", "cirebon", "malang"],
        "sumatera": ["sumatera", "medan", "lampung", "palembang", "pekanbaru", "padang"],
        "others": ["kalimantan", "sulawesi", "papua", "makassar", "manado", "bali", "denpasar"]
    }
    for canonical, keywords in region_mapping.items():
        if any(k in text for k in keywords):
            return canonical.capitalize()
    return None

# ====== Extract Natural Text ======
def extract_from_text(text, df):
    match = re.search(
        r"harga\s+(?P<brand>\w+)\s+(?P<tipe>[\w\s\-]+?)\s+tahun\s+(?P<tahun>20\d{2})(?:\s+di\s+(?P<region>[\w\s]+))?",
        text.lower()
    )
    if not match:
        return None, None, None, None

    brand_raw = match.group("brand").strip()
    tipe_input = match.group("tipe").strip()
    tahun = int(match.group("tahun").strip())
    region_raw = match.group("region") if match.group("region") else ""

    # standardisasi
    brand = next((b for b in df['Brand'].dropna().unique() if b.lower() == brand_raw.lower()), None)
    region = map_region_from_text(region_raw)

    if not brand:
        return None, None, None, None

    # filter data berdasarkan brand, tahun, dan region
    filtered_df = df[
        (df['Brand'].str.lower() == brand.lower()) &
        (df['Year'] == tahun)
    ]
    if region:
        filtered_df = filtered_df[filtered_df['Region'].str.lower().str.contains(region.lower())]

    # ambil semua tipe dari hasil filter, tapi juga cocokkan input tipe (untuk relevansi)
    tipe_list = filtered_df['Type'].dropna().unique().tolist()
    tipe_list = [t for t in tipe_list if tipe_input.lower() in t.lower()]  # filter yang relevan

    return brand, tipe_list, tahun, region

# ====== Pencarian Lokal Berdasarkan Data Excel ======
def cari_harga_mobil(df, brand, tipe_list, tahun, region=None, match_partial_type=True, price=None):
    """
    brand: string (optional, bisa kosong)
    tipe_list: list of string (WAJIB, minimal 1)
    tahun: int (WAJIB)
    region: string (optional)
    price: int (optional, untuk keperluan analisis over/under price di luar fungsi ini)
    """
    df = df[['Brand', 'Type', 'Year', 'OTRPrice', 'SalePrice', 'Region', 'TahunLelang']]
    query = (df['Year'] == tahun)

    # brand optional, jika ada tetap dipakai
    if brand:
        query &= (df['Brand'].str.lower() == brand.lower())

    # tipe wajib
    if tipe_list:
        type_query = pd.Series([False] * len(df))
        for t in tipe_list:
            if match_partial_type:
                type_query |= df['Type'].str.lower().str.contains(t.lower())
            else:
                type_query |= df['Type'].str.lower() == t.lower()
        query &= type_query
    else:
        # tipe wajib, jika tidak ada return kosong
        return "❌ Tipe mobil wajib diisi.", None, None

    # region optional
    if region:
        query &= df['Region'].str.lower().str.contains(region.lower())

    hasil = df[query]
    if hasil.empty:
        return "❌ Tidak ditemukan data yang cocok.", None, None

    # Hitung rata-rata OTR per tipe
    avg_otr_per_tipe = (
        hasil.groupby("Type")["OTRPrice"]
        .mean()
        .reset_index()
        .rename(columns={"OTRPrice": "Avg_OTR"})
    )
    avg_otr_per_tipe["Avg_OTR"] = avg_otr_per_tipe["Avg_OTR"].apply(format_rupiah)

    avg_otr = hasil['OTRPrice'].mean()
    min_lelang = hasil['SalePrice'].min()
    max_lelang = hasil['SalePrice'].max()

    tipe_terverifikasi = hasil['Type'].unique().tolist()
    tipe_info = ", ".join([t.upper() for t in tipe_terverifikasi])

    region_info = region if region else "SEMUA REGION"

    hasil_text = (
        f"📌 **{brand.upper() if brand else ''} {tipe_info} Tahun {tahun} (Region: {region_info})**\n\n"
        f"- 📋 Rata-rata OTR: {format_rupiah(avg_otr)}\n"
    )

    # riwayat lelang
    ringkasan_lelang = hasil[hasil['TahunLelang'] >= tahun].groupby("TahunLelang").agg(
        Min_Lelang=("SalePrice", "min"),
        Max_Lelang=("SalePrice", "max"),
        Mean_Lelang=("SalePrice", "mean")
    ).reset_index()
    ringkasan_lelang["Min_Lelang"] = ringkasan_lelang["Min_Lelang"].apply(format_rupiah)
    ringkasan_lelang["Max_Lelang"] = ringkasan_lelang["Max_Lelang"].apply(format_rupiah)
    ringkasan_lelang["Mean_Lelang"] = ringkasan_lelang["Mean_Lelang"].apply(format_rupiah)

    # Tambahkan rentang harga lelang setelah judul riwayat harga lelang
    hasil_text_riwayat = (
        "### 📈 Riwayat Harga Lelang\n"
        f"- 💰 Rentang Harga Lelang: {format_rupiah(min_lelang)} - {format_rupiah(max_lelang)}\n"
    )

    return hasil_text, hasil, ringkasan_lelang, hasil_text_riwayat

# ====== Cek Over/Under Price ======
def cek_over_under_price(df, tipe, tahun, harga_input, threshold=0.1):
    df_filtered = df[
        (df['Type'].str.lower().str.contains(tipe.lower())) &
        (df['Year'] == tahun)
    ]
    if df_filtered.empty:
        return "Data tidak ditemukan untuk tipe dan tahun tersebut."
    avg_otr = df_filtered['OTRPrice'].mean()
    if avg_otr == 0 or pd.isna(avg_otr):
        return "Data harga lelang tidak tersedia."
    batas_atas = avg_otr * (1 + threshold)
    batas_bawah = avg_otr * (1 - threshold)
    if harga_input > batas_atas:
        return f"Harga {format_rupiah(harga_input)} termasuk **overprice** (di atas rata-rata OTR {format_rupiah(avg_otr)})."
    elif harga_input < batas_bawah:
        return f"Harga {format_rupiah(harga_input)} termasuk **underprice** (di bawah rata-rata OTR {format_rupiah(avg_otr)})."
    else:
        return f"Harga {format_rupiah(harga_input)} masih wajar (10% +- rata-rata OTR {format_rupiah(avg_otr)})."

# ====== Load Excel ======
FILE_PATH = "./Data_Lelang_Toyota.xlsx"

@st.cache_data
def load_data():
    return pd.read_excel(FILE_PATH)

# ====== STREAMLIT APP ======
st.set_page_config(page_title="Tanya Harga Mobil", layout="centered")
st.title("🚗 Harga Mobil OTR & Lelang")

if not os.path.exists(FILE_PATH):
    st.error(f"❌ File Excel tidak ditemukan di path: {FILE_PATH}")
else:
    df = load_data()
    input_text = st.text_input("Tanyakan harga mobil (contoh: Berapa harga Toyota Avanza tahun 2022 di Jakarta?)")

    if st.button("Cari Jawaban"):
        if input_text:
            extracted = ekstrak_parameter_dengan_gpt(input_text)
            if extracted and "intent" in extracted:
                if extracted["intent"] == "tanya_harga" and all(k in extracted for k in ["brand", "tipe", "tahun"]):
                    brand = extracted["brand"]
                    tipe_list = [extracted["tipe"]]
                    tahun = int(extracted["tahun"])
                    region_raw = extracted.get("region", "")
                    region = map_region_from_text(region_raw) if region_raw else None

                    hasil_text, hasil_data, lelang_summary, hasil_text_riwayat = cari_harga_mobil(
                        df, brand, tipe_list, tahun, region, match_partial_type=True
                    )
                    st.markdown("---")
                    st.markdown("### 📊 Hasil Analisis")
                    st.markdown(hasil_text)
                    # Tampilkan tabel OTR per tipe dengan min/max/mean
                    if hasil_data is not None and not hasil_data.empty:
                        otr_summary = (
                            hasil_data.groupby("Type")["OTRPrice"]
                            .agg(
                                Mean_OTR="mean",
                                Min_OTR="min",
                                Max_OTR="max"
                            )
                            .reset_index()
                        )
                        otr_summary["Min_OTR"] = otr_summary["Min_OTR"].apply(format_rupiah)
                        otr_summary["Max_OTR"] = otr_summary["Max_OTR"].apply(format_rupiah)
                        otr_summary["Mean_OTR"] = otr_summary["Mean_OTR"].apply(format_rupiah)
                        otr_summary.columns = ["Type", "Min OTR", "Max OTR", "Mean OTR",]

                        st.markdown("#### Rata-rata OTR per Tipe")
                        st.dataframe(otr_summary, hide_index=True)

                    if lelang_summary is not None and not lelang_summary.empty:
                        st.markdown(hasil_text_riwayat)
                        st.dataframe(lelang_summary.set_index("TahunLelang"))

                elif extracted["intent"] == "cek_over_under" and all(k in extracted for k in ["tipe", "tahun", "harga"]):
                    tipe = extracted["tipe"]
                    tahun = int(extracted["tahun"])
                    harga = int(extracted["harga"])
                    region_raw = extracted.get("region", "")
                    region = map_region_from_text(region_raw) if region_raw else None

                    if region:
                        df_filtered = df[df['Region'].str.lower().str.contains(region.lower())]
                    else:
                        df_filtered = df

                    hasil_cek = cek_over_under_price(df_filtered, tipe, tahun, harga)
                    st.markdown("---")
                    st.markdown("### 📊 Analisis Over/Under Price")
                    st.info(hasil_cek)
                else:
                    st.warning("❌ GPT tidak dapat mengenali informasi yang cukup dari pertanyaan.")
            else:
                st.warning("❌ GPT tidak dapat mengenali informasi yang cukup dari pertanyaan.")
        else:
            st.warning("Masukkan pertanyaan terlebih dahulu.")

if st.button("Kembali ke Halaman Utama"):
    st.session_state.page = "main"
    st.run()