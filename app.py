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
NAMA_SPREADSHEET = "pencatat-keuangan"[cite: 2]
URL_LOOKER_STUDIO = "https://datastudio.google.com/s/mHCWurmgDmc"[cite: 2]

# Tempatkan ID Folder Google Drive milikmu di sini
ID_FOLDER_DRIVE = "PASTE_ID_FOLDER_GOOGLE_DRIVE_SHARED_KAMU_DISINI"

client = genai.Client()[cite: 2]

def init_google_services():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets", 
        "https://www.googleapis.com/auth/drive"
    ]
    
    if "RAW_GA_JSON" in st.secrets:[cite: 2]
        info_kunci = json.loads(st.secrets["RAW_GA_JSON"])[cite: 2]
        creds = Credentials.from_service_account_info(info_kunci, scopes=scopes)[cite: 2]
    else:
        creds = Credentials.from_service_account_file("kunci-google.json", scopes=scopes)[cite: 2]
        
    sheet = gspread.authorize(creds).open(NAMA_SPREADSHEET).get_worksheet(0)[cite: 2]
    drive_service = build('drive', 'v3', credentials=creds)
    
    return sheet, drive_service

try:
    sheet, drive_service = init_google_services()
except Exception as e:
    st.error(f"Gagal terhubung ke layanan Google: {e}")[cite: 2]
    st.stop()[cite: 2]

# ==========================================
# 2. UI STREAMLIT
# ==========================================
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")[cite: 2]
st.title("💰 AI Finance Logger v3.0")[cite: 2]

if "notif_sukses" in st.session_state and st.session_state.notif_sukses:[cite: 2]
    st.success(st.session_state.notif_sukses)[cite: 2]
    st.session_state.notif_sukses = ""[cite: 2]

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)[cite: 2]
st.markdown("---")[cite: 2]

if "data_pilihan" not in st.session_state:[cite: 2]
    st.session_state.data_pilihan = None[cite: 2]
if "berkas_mentah" not in st.session_state:
    st.session_state.berkas_mentah = None

input_user = st.text_area("Ketik catatan tambahan / konteks (misal: 'Belanja Superindo'):", key="teks_input_user")
berkas_nota = st.file_uploader("📸 Atau upload Nota / berkas PDF belanja kamu:", type=["jpg", "jpeg", "png", "pdf"])

if st.button("Ekstrak Data dengan AI", type="primary"):[cite: 2]
    if input_user or berkas_nota:
        with st.spinner("Gemini sedang menganalisis dokumen keuangan..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")[cite: 2]
                
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
                
                response = client.interactions.create([cite: 2]
                    model="gemini-3.5-flash",[cite: 2]
                    input=input_gemini[cite: 2]
                )
                
                parsed_json = json.loads(response.output_text.strip())[cite: 2]
                st.session_state.data_pilihan = parsed_json[cite: 2]
                
            except Exception as e:
                st.error(f"Gagal memproses dokumen. Eror: {e}")
    else:
        st.warning("Silakan isi konteks teks atau lampirkan berkas terlebih dahulu.")

# ==========================================
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:[cite: 2]
    st.markdown("---")[cite: 2]
    st.subheader("📋 Verifikasi Data Hasil AI")[cite: 2]
    
    edited_df = st.data_editor([cite: 2]
        st.session_state.data_pilihan,[cite: 2]
        num_rows="dynamic",[cite: 2]
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
                    
                    # LOGIKA PERCABANGAN KOMPRESI (CRUCIAL):
                    if bm["type"].startswith("image/") or bm["type"] in ["image/jpeg", "image/png", "image/jpg"]:
                        # 1. Buka berkas biner foto asli
                        img = Image.open(io.BytesIO(bm["bytes"]))
                        
                        # 2. Normalisasi mode warna jika formatnya PNG transparan (RGBA) agar bisa diubah ke JPG
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        # 3. Kompresi gambar ke format JPEG dengan kualitas 60% (Sangat Ringan, Teks Tetap Tajam)
                        img_buffer = io.BytesIO()
                        img.save(img_buffer, format="JPEG", quality=60, optimize=True)
                        data_unggah = img_buffer.getvalue()
                        
                        # 4. Sesuaikan ekstensi nama file baru di Drive
                        nama_bersih = bm["name"].rsplit(".", 1)[0]
                        nama_file_drive = f"{nama_bersih}_compressed.jpg"
                        mime_drive = "image/jpeg"
                    else:
                        # JALUR PDF: Biarkan berkas murni apa adanya tanpa kompresi
                        data_unggah = bm["bytes"]
                        nama_file_drive = bm["name"]
                        mime_drive = bm["type"]
                    
                    # Proses unggah ke folder Google Drive
                    media = MediaIoBaseUpload(io.BytesIO(data_unggah), mimetype=mime_drive, resumable=True)
                    file_metadata = {'name': nama_file_drive, 'parents': [ID_FOLDER_DRIVE]}
                    
                    file_drive = drive_service.files().create(
                        body=file_metadata, 
                        media_body=media, 
                        fields='webViewLink'
                    ).execute()
                    
                    link_drive = file_drive.get('webViewLink', '-')
                
                # Input baris data ke Sheets
                rows_to_append = []
                for item in edited_df:[cite: 2]
                    if item.get("tanggal") and item.get("nominal") is not None:[cite: 2]
                        rows_to_append.append([
                            item.get("tanggal"),[cite: 2]
                            int(item.get("nominal")),[cite: 2]
                            item.get("kategori"),[cite: 2]
                            item.get("keterangan"),[cite: 2]
                            link_drive[cite: 2]
                        ])
                
                if rows_to_append:
                    sheet.append_rows(rows_to_append)[cite: 2]
                    
                    st.session_state.teks_input_user = ""[cite: 2]
                    st.session_state.data_pilihan = None[cite: 2]
                    st.session_state.berkas_mentah = None
                    
                    st.session_state.notif_sukses = f"🎉 Sukses! Data masuk Sheets dan bukti file aman di Drive."[cite: 2]
                    st.rerun()[cite: 2]
                else:
                    st.warning("Tidak ada data transaksi valid.")
            except Exception as e:
                st.error(f"Eror saat proses simpan/upload: {e}")