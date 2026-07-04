import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import datetime
import json

# ==========================================
# 1. INITIALIZATION
# ==========================================
NAMA_SPREADSHEET = "pencatat-keuangan" 
URL_LOOKER_STUDIO = "https://datastudio.google.com/s/mHCWurmgDmc"

client = genai.Client()

def init_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # KONDISI 1: Jika berjalan di Cloud Server Streamlit
    if "RAW_GA_JSON" in st.secrets:
        import json
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)
    
    # KONDISI 2: Jika berjalan di Lokal Laptop Kamu
    else:
        creds = Credentials.from_service_account_file("kunci-google.json", scopes=scopes)
        
    gc = gspread.authorize(creds)
    return gc.open(NAMA_SPREADSHEET).get_worksheet(0)

try:
    sheet = init_google_sheets()
except Exception as e:
    st.error(f"Gagal terhubung ke Google Sheets: {e}")
    st.stop()

# ==========================================
# 2. UI STREAMLIT
# ==========================================
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")
st.title("💰 AI Finance Logger v3.0 (Anti-Break)")
st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

# Inisialisasi tempat penyimpanan sementara data hasil AI
if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

input_user = st.text_area("Ketik satu atau beberapa pengeluaran sekaligus di sini:")

if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user:
        with st.spinner("Gemini sedang memproses struktur data..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                prompt = f"""
                Kamu adalah robot kasir yang bertugas mengekstrak teks menjadi JSON Array terstruktur.
                Tanggal hari ini adalah {hari_ini}.
                Analisis teks berikut dan pecah menjadi beberapa item transaksi jika pengguna menyebutkan beberapa pengeluaran: '{input_user}'
                
                Hasilkan output dalam format JSON array yang kaku seperti contoh ini:
                [
                  {{"tanggal": "{hari_ini}", "nominal": 25000, "kategori": "Makanan", "keterangan": "Lontong sayur"}},
                  {{"tanggal": "{hari_ini}", "nominal": 5000, "kategori": "Lainnya", "keterangan": "Gemblong"}}
                ]
                
                Pilihan Kategori WAJIB salah satu dari: [Makanan, Transportasi, Tagihan, Belanja, Hiburan, Lainnya]
                JANGAN berikan teks pengantar, penutup, atau markdown ```json. HANYA OUTPUT JSON RAW.
                """
                
                response = client.interactions.create(
                    model="gemini-3.5-flash",
                    input=prompt
                )
                
                # Mengubah teks balasan Gemini menjadi Objek List/Dictionary Python
                parsed_json = json.loads(response.output_text.strip())
                st.session_state.data_pilihan = parsed_json
                
            except Exception as e:
                st.error(f"Gagal memproses teks. Pastikan format input logis. Eror: {e}")
    else:
        st.warning("Input tidak boleh kosong.")

# ==========================================
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    st.caption("Kamu bisa mengubah langsung data di bawah ini jika tebakan AI ada yang keliru sebelum disimpan.")
    
    # Menampilkan data ke dalam tabel interaktif yang bisa diedit pengguna
    edited_df = st.data_editor(
    st.session_state.data_pilihan, 
    num_rows="dynamic",
    column_config={
        "nominal": st.column_config.NumberColumn(
            "Nominal",
            format="%d",  # Menampilkan angka bulat bersih di Google Sheets
        )
    }
)
    
    if st.button("Simpan ke Google Sheets", type="secondary"):
        with st.spinner("Menulis ke spreadsheet..."):
            try:
                rows_to_append = []
                for item in edited_df:
                    rows_to_append.append([
                        item.get("tanggal"),
                        item.get("nominal"),
                        item.get("kategori"),
                        item.get("keterangan"),
                        "-"  # <--- Tambahan untuk mengisi kolom ke-5 (Link_Nota)
                    ])
                
                # Masukkan semua baris sekaligus ke Google Sheets
                sheet.append_rows(rows_to_append)
                st.success("🎉 Data sukses ditambahkan ke Google Sheets!")
                st.session_state.data_pilihan = None # Reset form
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan data: {e}")