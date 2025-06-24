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
    juta = value / 1_000_000
    return f"Rp {juta:,.1f} juta".replace(",", ".")

# ====== Mapping Region ======
def map_region_from_text(text):
    text = (text or "").lower()
    region_mapping = {
        "jabodetabek": [
            "jakarta", "bogor", "depok", "tangerang", "bekasi", "jabodetabek", "serang", "banten", "dki jakarta"
        ],
        "jawa": [
            "jawa", "jawa barat", "jawa tengah", "jawa timur", "bandung", "semarang", "surabaya", "yogyakarta",
            "solo", "tegal", "cirebon", "malang"
        ],
        "sumatera": [
            "sumatera", "aceh", "nanggroe aceh darussalam", "nad", "medan", "lampung", "palembang",
            "pekanbaru", "padang"
        ],
        "others": [
            "kalimantan", "sulawesi", "papua", "makassar", "manado", "bali", "denpasar", "ntt", "nusa tenggara timur"
        ]
    }
    for region, keys in region_mapping.items():
        if any(k in text for k in keys):
            return region
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
    region_raw = match.group("region") or ""

    # standardisasi brand
    brand = next(
        (b for b in df['brand'].dropna().unique()
         if b.lower() == brand_raw.lower()),
        None
    )
    if not brand:
        return None, None, None, None

    # mapping region
    region = map_region_from_text(region_raw)

    # gabungkan 'model' + 'type' jadi kolom Type
    df['Type'] = df['model'].str.strip() + " " + df['type'].str.strip()

    # filter df
    df_f = df[
        (df['brand'].str.lower() == brand.lower()) &
        (df['tahun_kendaraan'] == tahun)
    ]
    if region:
        df_f = df_f[
            df_f['provinsi']
              .str.lower()
              .apply(map_region_from_text)
              .eq(region)
        ]

    # cari tipe yang relevan
    tipe_list = [
        t for t in df_f['Type'].dropna().unique()
        if tipe_input.lower() in t.lower()
    ]

    return brand, tipe_list, tahun, region

# ====== Estimasi Nilai Sisa ======
def hitung_estimasi_nilaisisa(harga_awal):
    pers = {1: 0.85, 2: 0.70, 3: 0.58, 4: 0.48, 5: 0.40}
    rows = []
    for k, v in pers.items():
        rows.append({
            "Tahun ke-": f"Tahun {k}",
            "Sisa Depresiasi": f"{int(v * 100)}%",  # tambahkan persentase
            "Perkiraan Nilai Sisa (Depresiasi)": format_rupiah(harga_awal * v)
        })
    return pd.DataFrame(rows)

# ====== Load Excel & Bersihkan Kolom ======
FILE_PATH = "./Harga OTR_MobilBaru.xlsx"

@st.cache_data
def load_data():
    df = pd.read_excel(FILE_PATH)
    # standar nama kolom: strip spasi + lowercase
    df.columns = df.columns.str.strip().str.lower()
    return df

# ====== STREAMLIT APP ======
st.set_page_config(page_title="Tanya Harga Mobil", layout="centered")
st.title("🚗 Harga Mobil Baru & Estimasi Depresiasinya")

if not os.path.exists(FILE_PATH):
    st.error(f"❌ File Excel tidak ditemukan di: {FILE_PATH}")
else:
    df = load_data()
    # DEBUG: lihat kolom
    # st.write("Kolom:", df.columns.tolist())

    query = st.text_input(
        "Tanyakan harga mobil (contoh: Berapa harga BMW 5 Series 520i M Sport tahun 2024 di Bali?)"
    )
    if st.button("Cari Jawaban") and query:
        brand, tipe_list, tahun, region = extract_from_text(query, df)

        if not brand or not tahun:
            st.warning("❗ Gagal ekstrak parameter—perjelas pertanyaannya.")
        elif not tipe_list:
            st.warning("❗ Tipe mobil tidak ditemukan pada data.")
        else:
            # st.success(
            #     f"✅ Ditemukan: {brand} {tahun} "
            #     f"di wilayah {region or 'tidak diketahui'}"
            # )
            st.markdown("**Tipe yang cocok:**")
            for t in tipe_list:
                st.markdown(f"- {t}")

            # filter harga
            df_price = df[df['type'].notna()]  # pastikan ada kolom type
            df_price = df_price[
                (df_price['brand'].str.lower() == brand.lower()) &
                (df_price['tahun_kendaraan'] == tahun) &
                (df_price['Type'].str.lower().isin([x.lower() for x in tipe_list]))
            ]
            if region:
                df_price = df_price[
                    df_price['provinsi']
                      .str.lower()
                      .apply(map_region_from_text)
                      .eq(region)
                ]

            if df_price.empty:
                st.warning("❗ Data harga tidak tersedia untuk kombinasi ini.")
            else:
                harga_rata2 = df_price['otr_price'].mean()
                st.markdown(f"### 💰 Estimasi Harga Saat Ini di Region {region}: {format_rupiah(harga_rata2)}")

                st.markdown("### 📉 Estimasi Nilai Sisa 5 Tahun Ke Depan")
                st.table(hitung_estimasi_nilaisisa(harga_rata2))

if st.button("Kembali ke Halaman Utama"):
    st.session_state.page = "main"
    st.rerun()