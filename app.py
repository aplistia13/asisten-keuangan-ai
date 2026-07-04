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
# 1. CONFIGURATION & INITIALIZATION
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
        
    sheet = gspread.authorize(creds).open(NAMA_SPREADSHEET).get_worksheet(0)
    return sheet

try:
    sheet = init_google_sheets()
except Exception as e:
    st.error(f"Gagal terhubung ke layanan Google Sheets: {e}")
    st.stop()

# ==========================================
# 2. UI STREAMLIT
# ==========================================
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")
st.title("💰 AI Finance Logger v3.0")

# Inisialisasi counter reset form agar widget bisa dikosongkan tanpa eror
if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = ""

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

# FIX UTAMA: Menyuntikkan reset_counter ke dalam key agar widget bisa di-refresh secara legal
input_user = st.text_area(
    "Ketik catatan tambahan / konteks (misal: 'Belanja Superindo'):", 
    key=f"teks_input_user_{st.session_state.reset_counter}"
)
berkas_nota = st.file_uploader("📸 Atau upload Nota / berkas PDF belanja kamu:", type=["jpg", "jpeg", "png", "pdf"])

if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user or berkas_nota:
        with st.spinner("Gemini sedang menganalisis dokumen keuangan..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                
                prompt = f"""
                Kamu adalah robot kasir yang bertugas merangkum nota belanjaan menjadi TEPAT SATU baris transaksi JSON Array.
                Tanggal hari ini adalah {hari_ini}.
                
                Aturan Ekstraksi Kaku:
                1. 'nominal': Isi dengan TOTAL AKHIR / GRAND TOTAL / Net Pembayaran setelah dikurangi diskon yang tertera di nota (Wajib berupa angka/integer murni tanpa titik atau koma).
                2. 'keterangan': Susun string multi-line terstruktur. Mulai dengan teks konteks dari user: '{input_user}'. Di baris-baris berikutnya, kamu WAJIB MENULISKAN SEMUA ITEM BARANG YANG ADA DI NOTA SATU PER SATU TANPA KECUALI BESERTA HARGANYA. JANGAN PERNAH MERANGKUM LIST BARANG, JANGAN PERNAH MEMOTONG DAFTAR, DAN JANGAN PERNAH MENGGUNAKAN KATA 'dst', 'dan lain-lain', ATAU SINGKATAN SEJENISNYA. Semua angka belanjaan wajib masuk. Tuliskan juga nilai Sub Total awal dan Hemat Total/Diskon di bagian bawah rincian teks. Gunakan tanda '\\n' untuk memisahkan setiap baris rincian agar rapi.
                3. 'kategori': Pilih satu kategori utama yang paling mewakili seluruh pengeluaran di nota ini.
                
                Hasilkan output dalam format JSON array dengan TEPAT SATU objek kaku seperti contoh struktur ini:
                [
                  {{
                    "tanggal": "{hari_ini}", 
                    "nominal": 481544, 
                    "kategori": "Belanja", 
                    "keterangan": "Belanja Superindo\\n- Barang A: 10000\\n- Barang B: 20000\\nSub Total: 30000\\nHemat: 0"
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
                st.error(f"Gagal memproses dokumen. Eror: {e}")
    else:
        st.warning("Silakan isi konteks teks atau lampirkan berkas terlebih dahulu.")

# ==========================================
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    
    edited_df = st.data_editor(
        st.session_state.data_pilihan,
        num_rows="dynamic",
        column_config={
            "nominal": st.column_config.NumberColumn("Total Nominal", format="%,d"),
            "keterangan": st.column_config.TextColumn("Rincian Keterangan")
        }
    )
    
    if st.button("Simpan ke Google Sheets"):
        with st.spinner("Sedang mengamankan data ke Spreadsheet..."):
            try:
                rows_to_append = []
                for item in edited_df:
                    if item.get("tanggal") and item.get("nominal") is not None:
                        rows_to_append.append([
                            item.get("tanggal"),
                            int(item.get("nominal")),
                            item.get("kategori"),
                            item.get("keterangan"),
                            "-"
                        ])
                
                if rows_to_append:
                    sheet.append_rows(rows_to_append)
                    
                    # FIX UTAMA: Naikkan counter untuk memaksa Streamlit mereset text_area secara legal
                    st.session_state.reset_counter += 1
                    st.session_state.data_pilihan = None
                    
                    st.session_state.notif_sukses = f"🎉 Sukses! Rangkuman belanja 100% tercatat di Google Sheets."
                    st.rerun()
                else:
                    st.warning("Tidak ada data transaksi valid.")
            except Exception as e:
                st.error(f"Eror saat proses simpan ke Sheets: {e}")