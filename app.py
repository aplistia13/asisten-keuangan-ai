import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import datetime
import json
from PIL import Image

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
st.title("💰 AI Finance Logger v3.0")

if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = "" 

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

input_user = st.text_area("Ketik catatan tambahan / konteks (misal: 'Belanja Superindo'):", key="teks_input_user")
foto_nota = st.file_uploader("📸 Atau upload / foto langsung nota belanja kamu:", type=["jpg", "jpeg", "png"])

if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user or foto_nota:
        with st.spinner("Gemini sedang merangkum nota belanjaan..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                
                # REVISI PROMPT: Memaksa Gemini merangkum seluruh nota menjadi SATU baris agregat
                prompt = f"""
                Kamu adalah robot kasir yang bertugas merangkum nota belanjaan menjadi TEPAT SATU baris transaksi JSON Array.
                Tanggal hari ini adalah {hari_ini}.
                
                Aturan Ekstraksi Kaku:
                1. 'nominal': Isi dengan TOTAL AKHIR / GRAND TOTAL (angka bersih setelah dikurangi diskon) yang tertera di nota. Wajib berupa angka/integer murni tanpa titik/koma.
                2. 'keterangan': Susun string multi-line terstruktur. Mulai dengan teks konteks dari user: '{input_user}'. Di baris-baris berikutnya, sebutkan beberapa item barang penting yang dibeli, subtotal/jumlah awal, nilai diskon yang didapat, dan informasi relevan lainnya dari nota. Gunakan tanda '\\n' untuk memisahkan setiap baris rincian agar rapi.
                3. 'kategori': Pilih satu kategori utama yang paling mewakili seluruh pengeluaran di nota ini.
                
                Hasilkan output dalam format JSON array dengan TEPAT SATU objek kaku seperti contoh ini:
                [
                  {{
                    "tanggal": "{hari_ini}", 
                    "nominal": 972000, 
                    "kategori": "Belanja", 
                    "keterangan": "Belanja Superindo\\n- Minum: 2000\\n- Biskuit: 10000\\n- dst\\nJumlah: 1002000\\nDiskon: 30000"
                  }}
                ]
                
                Pilihan Kategori WAJIB salah satu dari: [Makanan, Transportasi, Tagihan, Belanja, Hiburan, Lainnya]
                JANGAN berikan teks pengantar, penutup, atau markdown ```json. HANYA OUTPUT JSON RAW.
                """
                
                if foto_nota:
                    gambar = Image.open(foto_nota)
                    input_gemini = [prompt, gambar]
                else:
                    input_gemini = f"{prompt}\nTeks dari user: '{input_user}'"
                
                # Memanggil AI dengan konfigurasi engine milikmu[cite: 2]
                response = client.interactions.create(
                    model="gemini-3.5-flash",
                    input=input_gemini
                )
                
                parsed_json = json.loads(response.output_text.strip())
                st.session_state.data_pilihan = parsed_json
                
            except Exception as e:
                st.error(f"Gagal memproses dokumen. Pastikan gambar jelas. Eror: {e}")
    else:
        st.warning("Silakan isi teks konteks atau lampirkan foto nota terlebih dahulu.")

# ==========================================
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    st.caption("Periksa total nominal dan rincian teks di bawah ini sebelum disimpan ke spreadsheet.")
    
    # Render tabel satu baris rangkuman
    edited_df = st.data_editor(
        st.session_state.data_pilihan, 
        num_rows="dynamic",
        column_config={
            "nominal": st.column_config.NumberColumn("Total Nominal", format="%,d"),
            "keterangan": st.column_config.TextColumn("Rincian Keterangan (Multi-line)")
        }
    )
    
    if st.button("Simpan ke Google Sheets"):
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
            
            # Reset form dan state[cite: 2]
            st.session_state.teks_input_user = ""  
            st.session_state.data_pilihan = None   
            
            st.session_state.notif_sukses = f"🎉 Sukses! Rangkuman transaksi telah tercatat di Google Sheets."
            st.rerun()
        else:
            st.warning("Tidak ada data transaksi valid yang bisa disimpan.")