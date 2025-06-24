import pandas as pd
import numpy as np

def group_type(type_series):
    """
    Mengelompokkan nilai pada kolom 'Type' ke dalam kategori berdasarkan keyword.

    Args:
        type_series (pd.Series): Kolom 'Type' dari DataFrame.

    Returns:
        pd.Series: Kategori tipe berdasarkan keyword.
    """
    keywords = [
        'agya', 'avanza', 'calya', 'fortuner', 'innova', 'raize', 'rush', 'sienta', 'veloz', 'yaris',
        'alphard', 'camry', 'corolla', 'etios', 'hiace', 'nav 1', 'vios', 'vellfire', 'voxy'
    ]

    def map_type(t):
        t = str(t).lower()
        for keyword in keywords:
            if keyword in t:
                return keyword.capitalize()
        return 'Others'

    return type_series.apply(map_type)

def hitung_depresiasi_tahun_ke_n(df):
    """
    Hitung depresiasi per tahun ke-n (bukan rata-rata kumulatif).

    Args:
        df (pd.DataFrame): Kolom ['Brand', 'Type', 'Year', 'OTRPrice', 'Region', 'TahunLelang', 'SalePrice']

    Returns:
        pd.DataFrame: Kolom ['Brand', 'TypeGroup', 'TahunKe', 'DepresiasiPerTahun']
    """
    # df = df.copy()
    df['TypeGroup'] = group_type(df['Type'])
    
    # Filter hanya data dengan harga valid
    # df = df.dropna(subset=['OTRPrice', 'SalePrice'])

    results = []

    # Iterasi setiap kombinasi brand + type + year produksi
    grouped = df.groupby(['Brand', 'TypeGroup', 'Year'])
    for (brand, type_group, year), group in grouped:
        # Harga OTR dianggap sebagai harga tahun ke-0
        harga_awal = group['OTRPrice'].iloc[0]
        # Ambil data harga lelang berdasarkan TahunLelang (umur tahun)
        for _, row in group.iterrows():
            tahun_ke = row['TahunLelang'] - row['Year']
            if tahun_ke <= 0:
                continue
            depresiasi = (1 - row['SalePrice'] / harga_awal) * 100
            results.append({
                'Brand': brand,
                'TypeGroup': type_group,
                'TahunKe': tahun_ke,
                'DepresiasiKumulatif': depresiasi
            })

    df_result = pd.DataFrame(results)

    # Hitung depresiasi dari tahun ke-n ke tahun ke-(n-1)
    df_result = df_result.sort_values(by=['Brand', 'TypeGroup', 'TahunKe'])
    df_result['DepresiasiPerTahun'] = df_result.groupby(['Brand', 'TypeGroup'])['DepresiasiKumulatif'].diff()

    # print(df_result[['DepresiasiKumulatif', 'DepresiasiPerTahun']].head(10))

    return df_result[['Brand', 'TypeGroup', 'TahunKe', 'DepresiasiPerTahun']]

df = pd.read_excel("./Data_Lelang_Toyota.xlsx")

df = df[['Brand', 'Type', 'Year', 'OTRPrice', 'Region', 'TahunLelang', 'SalePrice']]
df = df[df['OTRPrice'] > 0]
df = df[df['SalePrice'] <= df['OTRPrice']]

print(df)

hasil = hitung_depresiasi_tahun_ke_n(df)

# Agregasi rata-rata depresiasi per tahun per Brand dan TypeGroup
rata2_depresiasi = (
    hasil.groupby(['Brand', 'TypeGroup', 'TahunKe'])['DepresiasiPerTahun']
    .mean()
    .reset_index()
)

# Konversi dari proporsi ke persen jika masih dalam bentuk desimal
rata2_depresiasi['DepresiasiPerTahun'] *= 100

# Bulatkan ke 2 desimal biar rapi
rata2_depresiasi['DepresiasiPerTahun'] = rata2_depresiasi['DepresiasiPerTahun'].round(2)

print(rata2_depresiasi)

# Simpan hasil ke file Excel
rata2_depresiasi.to_excel("rata2_depresiasi.xlsx", index=False)