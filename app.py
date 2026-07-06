import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types  
import datetime
import json
import io
from PIL import Image

# ==========================================
# 1. KAMUS KATEGORI RESMI (FASE OBSERVASI)
# ==========================================
KATEGORI_RESMI = [
    "Kebutuhan Pokok",
    "Makanan & Minuman",
    "Tagihan & Cicilan",
    "Transportasi",
    "Anak & Keluarga",
    "Hobi & Gaya Lifestyle",
    "Tabungan & Investasi",
    "Lainnya"
]

NAMA_SPREADSHEET = "pencatat-keuangan"
URL_LOOKER_STUDIO = "https://datastudio.google.com/reporting/d77baf56-8245-462a-b6c7-e63dd0410dab"

client = genai.Client()

def init_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "RAW_GA_JSON" in st.secrets:
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("kunci-google.json", scopes=scopes)
        
    sheet = gspread.authorize(creds).open(NAMA_SPREADSHEET).get_worksheet(0)
    return sheet

try:
    sheet = init_google_sheets()
except Exception as e:
    st.error(f"Gagal terhubung ke layanan Google Sheets: {e}")
    st.stop()

# ==========================================
# 2. KALKULASI ARUS KAS & PROPORSI DATA
# ==========================================
total_penerimaan = 0
total_pengeluaran = 0
distribusi_pengeluaran = {k: 0 for k in KATEGORI_RESMI}

try:
    all_rows = sheet.get_all_values()
    if len(all_rows) > 1:
        for row in all_rows[1:]:
            if len(row) >= 5:  
                nom_mentah = row[1].strip()
                kat_tercatat = row[2].strip()
                tipe_tercatat = row[4].strip()
                
                # Pembersihan format uang ribuan Indonesia
                nom_clean = nom_mentah.split(',')[0].replace('.', '').replace(' ', '')
                
                if nom_clean.isdigit():
                    nominal_int = int(nom_clean)
                    
                    if tipe_tercatat == "Penerimaan":
                        total_penerimaan += nominal_int
                    elif tipe_tercatat == "Pengeluaran":
                        total_pengeluaran += nominal_int
                        if kat_tercatat in distribusi_pengeluaran:
                            distribusi_pengeluaran[kat_tercatat] += nominal_int
                        else:
                            distribusi_pengeluaran["Lainnya"] += nominal_int
except Exception as e:
    st.sidebar.warning(f"Gagal memproses data visualisasi: {e}")

# ==========================================
# 3. UI STREAMLIT: DASBOR DISTRIBUSI BULANAN
# ==========================================
st.set_page_config(page_title="Catatan Keuangan Mima Baba", layout="centered")
st.title("💰 Catatan Keuangan Mima Baba")
st.caption("🔬 Mode Observasi: Pengumpulan Data Baseline Keuangan")

st.markdown("### 📊 Ringkasan Arus Kas Bulan Ini")
col1, col2 = st.columns(2)
with col1:
    st.metric(label="Total Pemasukan (Penerimaan)", value=f"Rp {total_penerimaan:,.0f}".replace(",", "."))
with col2:
    st.metric(label="Total Pengeluaran", value=f"Rp {total_pengeluaran:,.0f}".replace(",", "."))

st.markdown("#### 🥧 Distribusi Alokasi Uang Keluar")
if total_pengeluaran > 0:
    for kategori, nominal in distribusi_pengeluaran.items():
        persen = (nominal / total_pengeluaran) * 100
        progress_val = nominal / total_pengeluaran
        
        str_nominal = f"Rp {nominal:,.0f}".replace(",", ".")
        st.text(f"📁 {kategori} | {persen:.1f}% ({str_nominal})")
        st.progress(progress_val)
else:
    st.info("Belum ada data pengeluaran yang terekam bulan ini. Silakan masukkan nota pertama kamu.")

st.markdown("---")

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = ""

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None


# ==========================================
# 4 & 5. LOGIKA INTERAKSI KONDISIONAL (ANTI FORM GANDA)
# ==========================================

if st.session_state.data_pilihan:
    # --------------------------------------
    # KONDISI A: TAHAP VERIFIKASI DATA (FORM INPUT DISEMBUNYIKAN)
    # --------------------------------------
    st.subheader("📋 Verifikasi Data Hasil AI")
    st.warning("⚠️ DATA DI BAWAH INI BELUM TEREKAM! Periksa kembali rincian, lalu tekan tombol 'Rekam!' di bawah untuk menyimpan.")
    
    edited_df = st.data_editor(
        st.session_state.data_pilihan,
        num_rows="dynamic",
        column_config={
            "tanggal": st.column_config.TextColumn("Tanggal", help="Format: YYYY-MM-DD"),
            "nominal": st.column_config.NumberColumn("Total Nominal", format="%,d"),
            "tipe": st.column_config.SelectboxColumn("Tipe Transaksi", options=["Pengeluaran", "Penerimaan", "catatan"], required=True),
            "kategori": st.column_config.SelectboxColumn("Kategori", options=KATEGORI_RESMI, required=True),
            "keterangan": st.column_config.TextColumn("Rincian Keterangan")
        }
    )
    
    btn_col1, btn_col2 = st.columns([1, 4])
    
    with btn_col1:
        if st.button("Rekam!", type="primary"):
            with st.spinner("Sedang menyimpan data transaksi resmi..."):
                try:
                    rows_to_append = []
                    for item in edited_df:
                        if item.get("tanggal") and item.get("nominal") is not None:
                            rows_to_append.append([
                                item.get("tanggal"),
                                int(item.get("nominal")),
                                item.get("kategori"),   
                                item.get("keterangan"), 
                                item.get("tipe"),       
                                "-"                     
                            ])
                    
                    if rows_to_append:
                        sheet.append_rows(rows_to_append)
                        st.session_state.reset_counter += 1
                        st.session_state.data_pilihan = None
                        st.session_state.notif_sukses = f"🎉 Sukses! {len(rows_to_append)} transaksi terekam ke database."
                        st.rerun()
                except Exception as e:
                    st.error(f"Eror saat proses simpan ke Sheets: {e}")
                    
    with btn_col2:
        if st.button("Batal / Reset Input"):
            st.session_state.data_pilihan = None
            st.rerun()

else:
    # --------------------------------------
    # KONDISI B: FASE INPUT NORMAL
    # --------------------------------------
    st.subheader("📥 Tambah Catatan Transaksi Baru")
    input_user = st.text_area(
        "Ketik konteks transaksi (Bisa masukkan banyak transaksi sekaligus dalam baris baru):", 
        key=f"teks_input_user_{st.session_state.reset_counter}",
        placeholder="Contoh:\n1 juli 2026 bayar kartu kredit 570000\n1 juli 2026 terima transferan bonus 2000000"
    )
    berkas_nota = st.file_uploader("📸 Atau upload Nota / berkas PDF belanja kamu:", type=["jpg", "jpeg", "png", "pdf"])

    if st.button("Ekstrak Data dengan AI"):
        if input_user or berkas_nota:
            with st.spinner("Gemini sedang memecah dan mengekstrak data transaksi..."):
                try:
                    hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                    daftar_kategori_valid = ", ".join(KATEGORI_RESMI)
                    
                    # Pembaruan Prompt: Mengizinkan pembuatan banyak objek dalam array JSON
                    prompt = f"""
                    Kamu adalah robot akuntan cerdas dan teliti. Tugas utamamu adalah mengekstrak teks konteks keuangan menjadi baris-baris transaksi terpisah di dalam struktur JSON Array.
                    
                    PANDUAN EKSTRAKSI UTAMA:
                    - JIKA teks berisi lebih dari satu aktivitas transaksi keuangan, kamu WAJIB memisahnya menjadi objek JSON yang berbeda secara individual di dalam array. Jangan digabung, jangan ditotal!
                    - Deteksi secara peka mana yang merupakan uang masuk ('Penerimaan') dan mana uang keluar ('Pengeluaran').
                    
                    Aturan Atribut Objek:
                    1. 'tanggal': Cari petunjuk tanggal di dalam teks (misal: '1 juli 2026' menjadi '2026-07-01'). Jika tidak ada petunjuk tanggal sama sekali, gunakan tanggal default hari ini: '{hari_ini}'.
                    2. 'nominal': Isi dengan nilai uang angka bersih tanpa titik/koma/simbol mata uang. (misal: 1,450000 atau 2juta diubah menjadi integer murni: 1450000 atau 2000000).
                    3. 'tipe': Pilih secara akurat dari tiga opsi ini: [Pengeluaran, Penerimaan, catatan].
                    4. 'kategori': Pilih satu yang paling cocok dari daftar resmi ini saja: [{daftar_kategori_valid}]
                    5. 'keterangan': Tulis rincian deskripsi pendek khusus untuk transaksi terkait tersebut saja. Jangan mencampur deskripsi antar transaksi berbeda.
                    
                    Hasilkan HANYA output JSON array kaku seperti contoh struktur multi-objek ini:
                    [
                      {{
                        "tanggal": "2026-07-01", 
                        "nominal": 570000,
                        "tipe": "Pengeluaran",
                        "kategori": "Tagihan & Cicilan", 
                        "keterangan": "Bayar kartu kredit"
                      }},
                      {{
                        "tanggal": "2026-07-01", 
                        "nominal": 2000000,
                        "tipe": "Penerimaan",
                        "kategori": "Lainnya", 
                        "keterangan": "Terima transferan bonus"
                      }}
                    ]
                    """
                    
                    if berkas_nota:
                        file_bytes = berkas_nota.read()
                        if berkas_nota.type == "application/pdf":
                            dokumen_pdf = types.Part.from_bytes(data=file_bytes, mime_type="application/pdf")
                            input_gemini = [prompt, dokumen_pdf]
                        else:
                            gambar = Image.open(io.BytesIO(file_bytes))
                            input_gemini = [prompt, gambar]
                    else:
                        input_gemini = [f"{prompt}\nTeks dari user:\n{input_user}"]
                    
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=input_gemini,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    
                    parsed_json = json.loads(response.text.strip())
                    st.session_state.data_pilihan = parsed_json
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Gagal memproses dokumen keuangan. Eror: {e}")
        else:
            st.warning("Silakan isi konteks teks atau lampirkan berkas terlebih dahulu.")
