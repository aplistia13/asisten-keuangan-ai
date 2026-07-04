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
    
    if "RAW_GA_JSON" in st.secrets:
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)
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

# Menampilkan notifikasi jika ada pesan sukses yang tersimpan di session state
if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = "" 

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

# FIX: Hanya gunakan SATU text area dengan key yang terikat langsung ke sistem reset
input_user = st.text_area("Ketik satu atau beberapa pengeluaran sekaligus di sini:", key="teks_input_user")

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
                
                # Menggunakan syntax milikmu yang sudah terbukti bekerja di environment-mu
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
    
    # Menampilkan data ke dalam tabel interaktif lengkap dengan format pemisah ribuan
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
            # Menyaring baris kosong (None) agar tidak mengotori database spreadsheet
            if item.get("tanggal") and item.get("nominal") is not None:
                rows_to_append.append([
                    item.get("tanggal"),
                    int(item.get("nominal")),
                    item.get("kategori"),
                    item.get("keterangan"),
                    "-"
                ])
        
        if rows_to_append:
            # 1. Kirim data bersih ke Google Sheets
            sheet.append_rows(rows_to_append)
            
            # 2. SINKRONISASI: Mengosongkan text area utama dan menghilangkan tabel verifikasi
            st.session_state.teks_input_user = ""  
            st.session_state.data_pilihan = None   
            
            # 3. Set notifikasi untuk dimunculkan pasca rerun
            st.session_state.notif_sukses = f"🎉 Sukses! {len(rows_to_append)} transaksi telah tercatat di Google Sheets."
            
            # 4. Paksa halaman memuat ulang dengan kondisi form kosong
            st.rerun()
        else:
            st.warning("Tidak ada data transaksi valid yang bisa disimpan.")