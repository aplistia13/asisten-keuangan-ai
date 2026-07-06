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
    "Hobi & Gaya Hidup",
    "Tabungan & Investasi",
    "Lainnya"
]

NAMA_SPREADSHEET = "pencatat-keuangan"
URL_LOOKER_STUDIO = "https://datastudio.google.com/s/mHCWurmgDmc"

client = genai.Client()

def init_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "RAW_GA_JSON" in st.secrets:
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("kunci-ggle.json", scopes=scopes)
        
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
                nom_bersih = nom_mentah.split(',')[0].replace('.', '').replace(' ', '')
                
                if nom_bersih.isdigit():
                    nominal_int = int(nom_bersih)
                    
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
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")
st.title("💰 AI Finance Logger v3.0")
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

input_user = st.text_area(
    "Ketik konteks transaksi (misal: 'Beli bensin shell' atau 'Gaji masuk bulanan'):", 
    key=f"teks_input_user_{st.session_state.reset_counter}"
)
berkas_nota = st.file_uploader("📸 Atau upload Nota / berkas PDF belanja kamu:", type=["jpg", "jpeg", "png", "pdf"])

if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user or berkas_nota:
        with st.spinner("Gemini sedang mengekstrak data..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                daftar_kategori_valid = ", ".join(KATEGORI_RESMI)
                
                prompt = f"""
                Kamu adalah robot akuntan cerdas. Tugasmu merangkum data keuangan menjadi TEPAT SATU baris transaksi JSON Array.
                Tanggal hari ini adalah {hari_ini}.
                
                Aturan Ekstraksi Kaku:
                1. 'nominal': Isi dengan nilai uang bersih tanpa titik/koma.
                2. 'tipe': Wajib pilih salah satu dari: [Pengeluaran, Penerimaan, catatan]. Jika ada berkas nota belanja fisik, otomatis 'Pengeluaran'. Jika user menceritakan uang masuk/transferan dapat, jadikan 'Penerimaan'.
                3. 'keterangan': Mulai dengan konteks user: '{input_user}'. Jika ada nota belanja, tuliskan rincian item barang dan harganya secara lengkap tanpa dipotong.
                4. 'kategori': Pilih satu yang paling cocok dari daftar kaku ini: [{daftar_kategori_valid}]
                
                Hasilkan HANYA output JSON array kaku seperti contoh ini:
                [
                  {{
                    "tanggal": "{hari_ini}", 
                    "nominal": 481544,
                    "tipe": "Pengeluaran",
                    "kategori": "Kebutuhan Pokok", 
                    "keterangan": "Belanja mingguan di Superindo\\n- Item A: 20000"
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
                    input_gemini = [f"{prompt}\nTeks dari user: '{input_user}'"]
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=input_gemini,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                
                parsed_json = json.loads(response.text.strip())
                st.session_state.data_pilihan = parsed_json
                
            except Exception as e:
                st.error(f"Gagal memproses dokumen keuangan. Eror: {e}")
    else:
        st.warning("Silakan isi konteks teks atau lampirkan berkas terlebih dahulu.")

# ==========================================
# 4. VERIFIKASI & PENGIRIMAN DATA KAKU (A-F)
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    
    edited_df = st.data_editor(
        st.session_state.data_pilihan,
        num_rows="dynamic",
        column_config={
            "nominal": st.column_config.NumberColumn("Total Nominal", format="%,d"),
            "tipe": st.column_config.SelectboxColumn("Tipe Transaksi", options=["Pengeluaran", "Penerimaan", "catatan"], required=True),
            "kategori": st.column_config.SelectboxColumn("Kategori", options=KATEGORI_RESMI, required=True),
            "keterangan": st.column_config.TextColumn("Rincian Keterangan")
        }
    )
    
    if st.button("Simpan ke Google Sheets"):
        with st.spinner("Sedang mengirim data transaksi..."):
            try:
                rows_to_append = []
                for item in edited_df:
                    if item.get("tanggal") and item.get("nominal") is not None:
                        rows_to_append.append([
                            item.get("tanggal"),
                            int(item.get("nominal")),
                            item.get("kategori"),   # Kolom C
                            item.get("keterangan"), # Kolom D
                            item.get("tipe"),       # Kolom E
                            "-"                     # Kolom F
                        ])
                
                if rows_to_append:
                    sheet.append_rows(rows_to_append)
                    st.session_state.reset_counter += 1
                    st.session_state.data_pilihan = None
                    st.session_state.notif_sukses = f"🎉 Sukses! Transaksi terekam ke database baseline."
                    st.rerun()
            except Exception as e:
                st.error(f"Eror saat proses simpan ke Sheets: {e}")