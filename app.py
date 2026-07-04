import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types  
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import datetime
import json
import io
from PIL import Image

# ==========================================
# 1. CONFIGURATION & INITIALIZATION
# ==========================================
NAMA_SPREADSHEET = "pencatat-keuangan"
URL_LOOKER_STUDIO = "https://datastudio.google.com/s/mHCWurmgDmc"

# ID Folder Google Drive milikmu yang sudah steril
ID_FOLDER_DRIVE = "1Vb-_NLggBSOQ8d3Hk5tSmKMEoT4ijQmz"

client = genai.Client()

def init_google_services():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets", 
        "https://www.googleapis.com/auth/drive"
    ]
    
    if "RAW_GA_JSON" in st.secrets:
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("kunci-google.json", scopes=scopes)
        
    sheet = gspread.authorize(creds).open(NAMA_SPREADSHEET).get_worksheet(0)
    drive_service = build('drive', 'v3', credentials=creds)
    
    return sheet, drive_service

try:
    sheet, drive_service = init_google_services()
except Exception as e:
    st.error(f"Gagal terhubung ke layanan Google: {e}")
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
if "berkas_mentah" not in st.session_state:
    st.session_state.berkas_mentah = None

input_user = st.text_area("Ketik catatan tambahan / konteks (misal: 'Belanja Superindo'):", key="teks_input_user")
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
                1. 'nominal': Isi dengan TOTAL AKHIR / GRAND TOTAL (angka bersih setelah dikurangi diskon) yang tertera di nota. Wajib berupa angka/integer murni tanpa titik/koma.
                2. 'keterangan': Susun string multi-line terstruktur. Mulai dengan teks konteks dari user: '{input_user}'. Di baris-baris berikutnya, sebutkan beberapa item barang penting yang dibeli, subtotal/jumlah awal, nilai diskon yang didapat, dan informasi relevan lainnya dari nota. Gunakan tanda '\\n' untuk memisahkan setiap baris rincian agar rapi.
                3. 'kategori': Pilih satu kategori utama yang paling mewakili seluruh pengeluaran di nota ini.
                
                Hasilkan output dalam format JSON array dengan TEPAT SATU objek kaku seperti contoh ini:
                [
                  {{
                    "tanggal": "{hari_ini}", 
                    "nominal": 972000, 
                    "kategori": "Belanja", 
                    "keterangan": "Belanja Superindo\\n- Minum: 2000\\n- Biskuit: 10000\\nJumlah: 1002000\\nDiskon: 30000"
                  }}
                ]
                
                Pilihan Kategori WAJIB salah satu dari: [Makanan, Transportasi, Tagihan, Belanja, Hiburan, Lainnya]
                JANGAN berikan teks pengantar, penutup, atau markdown ```json. HANYA OUTPUT JSON RAW.
                """
                
                if berkas_nota:
                    file_bytes = berkas_nota.read()
                    st.session_state.berkas_mentah = {
                        "bytes": file_bytes,
                        "name": berkas_nota.name,
                        "type": berkas_nota.type
                    }
                    
                    if berkas_nota.type == "application/pdf":
                        dokumen_pdf = types.Part.from_bytes(data=file_bytes, mime_type="application/pdf")
                        input_gemini = [prompt, dokumen_pdf]
                    else:
                        gambar = Image.open(io.BytesIO(file_bytes))
                        input_gemini = [prompt, gambar]
                else:
                    input_gemini = f"{prompt}\nTeks dari user: '{input_user}'"
                    st.session_state.berkas_mentah = None
                
                response = client.interactions.create(
                    model="gemini-3.5-flash",
                    input=input_gemini
                )
                
                parsed_json = json.loads(response.output_text.strip())
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
    
    if st.button("Simpan ke Google Sheets & Drive"):
        with st.spinner("Sedang mengamankan data dan memproses berkas..."):
            try:
                link_drive = "-"
                
                if st.session_state.berkas_mentah:
                    bm = st.session_state.berkas_mentah
                    
                    if bm["type"].startswith("image/") or bm["type"] in ["image/jpeg", "image/png", "image/jpg"]:
                        img = Image.open(io.BytesIO(bm["bytes"]))
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        img_buffer = io.BytesIO()
                        img.save(img_buffer, format="JPEG", quality=60, optimize=True)
                        data_unggah = img_buffer.getvalue()
                        
                        nama_bersih = bm["name"].rsplit(".", 1)[0]
                        nama_file_drive = f"{nama_bersih}_compressed.jpg"
                        mime_drive = "image/jpeg"
                    else:
                        data_unggah = bm["bytes"]
                        nama_file_drive = bm["name"]
                        mime_drive = bm["type"]
                    
                    media = MediaIoBaseUpload(io.BytesIO(data_unggah), mimetype=mime_drive, resumable=True)
                    file_metadata = {'name': nama_file_drive, 'parents': [ID_FOLDER_DRIVE]}
                    
                    file_drive = drive_service.files().create(
                        body=file_metadata, 
                        media_body=media, 
                        fields='webViewLink'
                    ).execute()
                    
                    link_drive = file_drive.get('webViewLink', '-')
                
                rows_to_append = []
                for item in edited_df:
                    if item.get("tanggal") and item.get("nominal") is not None:
                        rows_to_append.append([
                            item.get("tanggal"),
                            int(item.get("nominal")),
                            item.get("kategori"),
                            item.get("keterangan"),
                            link_drive
                        ])
                
                if rows_to_append:
                    sheet.append_rows(rows_to_append)
                    
                    st.session_state.teks_input_user = ""
                    st.session_state.data_pilihan = None
                    st.session_state.berkas_mentah = None
                    
                    st.session_state.notif_sukses = f"🎉 Sukses! Data masuk Sheets dan bukti file aman di Drive."
                    st.rerun()
                else:
                    st.warning("Tidak ada data transaksi valid.")
            except Exception as e:
                st.error(f"Eror saat proses simpan/upload: {e}")