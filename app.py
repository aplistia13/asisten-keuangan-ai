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

# Pengecek notifikasi sukses setelah halaman dimuat ulang (Rerun)
if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = "" 

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

# HANYA GUNAKAN SATU TEXT AREA (Key terikat dengan sistem pembersihan otomatis)
input_user = st.text_area("Ketik satu atau beberapa transaksi sekaligus di sini (bisa pengeluaran maupun pemasukan):", key="teks_input_user")

if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user:
        with st.spinner("Gemini sedang memproses struktur data..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                prompt = f"""
                Kamu adalah robot kasir yang bertugas mengekstrak teks menjadi JSON Array terstruktur.
                Tanggal hari ini adalah {hari_ini}.
                Analisis teks berikut dan pecah menjadi beberapa item transaksi, baik berupa pengeluaran maupun pemasukan: '{input_user}'
                
                Hasilkan output dalam format JSON array yang kaku seperti contoh ini:
                [
                  {{"tanggal": "{hari_ini}", "nominal": 25000, "kategori": "Makanan", "keterangan": "Lontong sayur", "tipe": "Pengeluaran"}},
                  {{"tanggal": "{hari_ini}", "nominal": 7500000, "kategori": "Gaji", "keterangan": "Transfer gaji bulanan", "tipe": "Pemasukan"}}
                ]
                
                Pilihan Kategori WAJIB salah satu dari: [Makanan, Transportasi, Tagihan, Belanja, Hiburan, Gaji, Lainnya]
                Pilihan Tipe WAJIB salah satu dari: [Pengeluaran, Pemasukan]
                JANGAN berikan teks pengantar, penutup, atau markdown ```json. HANYA OUTPUT JSON RAW.
                """
                
                # Menggunakan model pilihan dan sintaks yang sudah terbukti bekerja di environment-mu
                response = client.interactions.create(
                    model="gemini-3.5-flash",
                    input=prompt
                )
                
                parsed_json = json.loads(response.output_text.strip())
                st.session_state.data_pilihan = parsed_json
                
            except Exception as e:
                st.error(f"Gagal memproses teks. Eror: {e}")
    else:
        st.warning("Input tidak boleh kosong.")

# ==========================================
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    st.caption("Kamu bisa mengubah langsung data di bawah ini jika tebakan AI ada yang keliru sebelum disimpan.")
    
    # Tabel interaktif dengan konfigurasi pemisah ribuan pada kolom nominal
    edited_df = st.data_editor(
        st.session_state.data_pilihan, 
        num_rows="dynamic",
        column_config={
            "nominal": st.column_config.NumberColumn(
                "Nominal",
                format="%,d",  
            )
        }
    )
    
    if st.button("Simpan ke Google Sheets"):
        rows_to_append = []
        for item in edited_df:
            # Saringan ketat: Abaikan baris kosong (None) agar database tidak kotor
            if item.get("tanggal") and item.get("nominal") is not None:
                rows_to_append.append([
                    item.get("tanggal"),
                    int(item.get("nominal")),
                    item.get("kategori"),
                    item.get("keterangan"),
                    item.get("tipe", "Pengeluaran"),
                    item.get("link_nota", "-")  # Mengisi Kolom F (Link Nota) secara aman dengan default "-"
                ])
        
        if rows_to_append:
            # 1. Kirim paket 6 kolom data sekaligus ke spreadsheet
            sheet.append_rows(rows_to_append)
            
            # 2. Reset semua state (Text area kosong & Tabel verifikasi hilang)
            st.session_state.teks_input_user = ""  
            st.session_state.data_pilihan = None   
            
            # 3. Siapkan pesan sukses untuk dimuat setelah halaman direfresh
            st.session_state.notif_sukses = f"🎉 Sukses! {len(rows_to_append)} transaksi telah tercatat di Google Sheets."
            
            # 4. Paksa Streamlit memuat ulang halaman secara bersih
            st.rerun()
        else:
            st.warning("Tidak ada data transaksi valid yang bisa disimpan.")