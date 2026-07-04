import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from PIL import Image
import datetime
import json
import io

# ==========================================
# 1. INITIALIZATION & CONFIGURATION
# ==========================================
NAMA_SPREADSHEET = "pencatat-keuangan" 
URL_LOOKER_STUDIO = "https://datastudio.google.com/s/mHCWurmgDmc"

# WAJIB GANTI: Masukkan ID Folder Google Drive yang sudah di-share ke Service Account
FOLDER_ID_DRIVE = "1Vb-_NLggBSOQ8d3Hk5tSmKMEoT4ijQmz"

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
        
    # Koneksi Google Sheets
    gc = gspread.authorize(creds)
    sheet = gc.open(NAMA_SPREADSHEET).get_worksheet(0)
    
    # Koneksi Google Drive API
    drive_service = build("drive", "v3", credentials=creds)
    
    return sheet, drive_service

try:
    sheet, drive_service = init_google_services()
except Exception as e:
    st.error(f"Gagal terhubung ke layanan Google: {e}")
    st.stop()

# ==========================================
# 2. UI STREAMLIT & LIFECYCLE MANAGEMENT
# ==========================================
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")
st.title("💰 AI Finance Logger v3.0 (Anti-Break)")

# PEMBERSIHAN STATE OTOMATIS
if st.session_state.get("harus_reset", False):
    st.session_state.teks_input_user = ""
    st.session_state.data_pilihan = None
    st.session_state.link_nota_terunggah = None
    st.session_state.harus_reset = False

if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = "" 

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None
if "link_nota_terunggah" not in st.session_state:
    st.session_state.link_nota_terunggah = None

# INPUT 1: Teks Narasi Transaksi
input_user = st.text_area("Ketik rincian pendapatan/pengeluaran secara mendetail di sini:", key="teks_input_user")

# INPUT 2: Kamera Penangkap Nota Fisik
foto_nota = st.camera_input("📷 Ambil Foto Nota (Opsional)")

# LOGIKA UTAMA: Unggah & Kompres Foto Nota Langsung Saat Kamera Aktif
if foto_nota and st.session_state.link_nota_terunggah is None:
    with st.spinner("Mengompres gambar & mengunggah ke Google Drive..."):
        try:
            # Kompresi instan menggunakan Pillow
            gambar_mentah = Image.open(foto_nota)
            if gambar_mentah.mode in ("RGBA", "P"):
                gambar_mentah = gambar_mentah.convert("RGB")
            
            aliran_bytes = io.BytesIO()
            # Menyusutkan kualitas ke 60% untuk menghemat penyimpanan hingga 90%
            gambar_mentah.save(aliran_bytes, format="JPEG", quality=60)
            aliran_bytes.seek(0)
            
            nama_berkas = f"nota_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            
            metadata_file = {
                "name": nama_berkas,
                "parents": [FOLDER_ID_DRIVE]
            }
            media = MediaIoBaseUpload(aliran_bytes, mimetype="image/jpeg", resumable=True)
            berkas_drive = drive_service.files().create(body=metadata_file, media_body=media, fields="id, webViewLink").execute()
            
            # Mengubah akses berkas menjadi publik agar tautannya bisa dibaca Looker Studio
            drive_service.permissions().create(
                fileId=berkas_drive.get("id"),
                body={"type": "anyone", "role": "reader"}
            ).execute()
            
            st.session_state.link_nota_terunggah = berkas_drive.get("webViewLink")
            st.toast("📷 Berkas nota sukses dikompres dan disimpan ke Drive!", icon="✅")
        except Exception as e:
            st.error(f"Sistem gagal mengamankan berkas foto: {e}")

# TOMBOL 3: Proses Struktur Data dengan AI
if st.button("Ekstrak Data dengan AI", type="primary"):
    if input_user:
        with st.spinner("Gemini sedang memproses struktur data..."):
            try:
                hari_ini = datetime.date.today().strftime("%Y-%m-%d")
                prompt = f"""
                Kamu adalah robot kasir yang bertugas mengekstrak teks menjadi JSON Array terstruktur secara vertikal (baris demi baris).
                Tanggal hari ini adalah {hari_ini}.
                Analisis teks pendapatan atau pengeluaran berikut secara mendetail: '{input_user}'
                
                ATURAN MUTLAK PEMECAHAN DATA:
                1. Setiap jenis komponen pendapatan yang disebutkan HARUS dipisah menjadi baris tersendiri dengan tipe "Catatan" untuk histori pelacakan karir.
                2. Setiap nominal uang yang benar-benar dimasukkan ke dalam kas bersama HARUS dijadikan baris tersendiri dengan tipe "Pemasukan".
                3. Jangan menggabungkan nominal komponen histori ke dalam nominal pemasukan kas. Biarkan terpisah secara vertikal.
                
                Pilihan Kategori WAJIB salah satu dari: [Makanan, Transportasi, Tagihan, Belanja, Hiburan, Gaji, Lainnya]
                Pilihan Tipe WAJIB salah satu dari: [Pengeluaran, Pemasukan, Catatan]
                JANGAN berikan teks pengantar, penutup, atau markdown ```json. HANYA OUTPUT JSON RAW.
                """
                
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
# 3. VERIFIKASI & SIMPAN DATA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    
    # Tampilkan info jika nota fisik berhasil dilampirkan
    if st.session_state.link_nota_terunggah:
        st.info(f"🔗 Nota fisik terdeteksi dan akan ditautkan otomatis ke seluruh baris di bawah ini.")
        
    edited_df = st.data_editor(
        st.session_state.data_pilihan, 
        num_rows="dynamic",
        column_config={
            "nominal": st.column_config.NumberColumn("Nominal", format="%,d")
        }
    )
    
    if st.button("Simpan ke Google Sheets"):
        rows_to_append = []
        # Ambil tautan nota yang tersimpan di session state (jika tidak ada, beri tanda kaku "-")
        tautan_nota = st.session_state.get("link_nota_terunggah", "-")
        
        for item in edited_df:
            if item.get("tanggal") and item.get("nominal") is not None:
                rows_to_append.append([
                    item.get("tanggal"),
                    int(item.get("nominal")),
                    item.get("kategori"),
                    item.get("keterangan"),
                    item.get("tipe", "Pengeluaran"),
                    tautan_nota  # URL masuk secara vertikal ke Kolom F
                ])
        
        if rows_to_append:
            sheet.append_rows(rows_to_append)
            st.session_state.notif_sukses = f"🎉 Sukses! {len(rows_to_append)} komponen transaksi beserta nota digital telah aman di spreadsheet."
            st.session_state.harus_reset = True
            st.rerun()
        else:
            st.warning("Tidak ada data transaksi valid yang bisa disimpan.")