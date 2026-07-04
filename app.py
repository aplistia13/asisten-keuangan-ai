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
# 2. UI STREAMLIT & LIFECYCLE MANAGEMENT
# ==========================================
st.set_page_config(page_title="AI Finance Logger v3", layout="centered")
st.title("💰 AI Finance Logger v3.0 (Anti-Break)")

# FIX LIFECYCLE: Eksekusi pembersihan state di awal putaran sebelum widget digambar
if st.session_state.get("harus_reset", False):
    st.session_state.teks_input_user = ""  # Kotak input bersih kembali
    st.session_state.data_pilihan = None   # Tabel verifikasi disembunyikan
    st.session_state.harus_reset = False   # Matikan sakelar reset

# Pengecek notifikasi sukses setelah halaman dimuat ulang (Rerun)
if "notif_sukses" in st.session_state and st.session_state.notif_sukses:
    st.success(st.session_state.notif_sukses)
    st.session_state.notif_sukses = "" 

st.link_button("📊 Buka Dasbor Looker Studio", URL_LOOKER_STUDIO)
st.markdown("---")

if "data_pilihan" not in st.session_state:
    st.session_state.data_pilihan = None

# Kotak input utama terikat dengan key teks_input_user
input_user = st.text_area("Ketik rincian pendapatan/pengeluaran secara mendetail di sini:", key="teks_input_user")

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
                1. Setiap jenis komponen pendapatan yang disebutkan (misal: Gaji Pokok, Tukin, Uang SPD, Insentif, Tambahan) HARUS dipisah menjadi baris tersendiri dengan tipe "Catatan" untuk histori pelacakan karir.
                2. Setiap nominal uang yang benar-benar dimasukkan ke dalam kas bersama/tabungan bersama HARUS dijadikan baris tersendiri dengan tipe "Pemasukan".
                3. Jangan menggabungkan nominal komponen histori ke dalam nominal pemasukan kas. Biarkan terpisah secara vertikal.
                
                CONTOH OUTPUT JSON ARRAY YANG WAJIB DIKUTIP (Kaku tanpa markdown):
                [
                  {{"tanggal": "{hari_ini}", "nominal": 3000000, "kategori": "Gaji", "keterangan": "Gaji Pokok Suami", "tipe": "Catatan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 7000000, "kategori": "Gaji", "keterangan": "Tukin Bulanan Suami", "tipe": "Catatan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 8000000, "kategori": "Gaji", "keterangan": "Setoran Kas Bersama Suami", "tipe": "Pemasukan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 2000000, "kategori": "Gaji", "keterangan": "Gaji Pokok Istri", "tipe": "Catatan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 6000000, "kategori": "Gaji", "keterangan": "Tukin Bulanan Istri", "tipe": "Catatan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 5000000, "kategori": "Gaji", "keterangan": "Uang SPD Istri", "tipe": "Catatan"}},
                  {{"tanggal": "{hari_ini}", "nominal": 8000000, "kategori": "Gaji", "keterangan": "Setoran Kas Bersama Istri", "tipe": "Pemasukan"}}
                ]
                
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
# 3. VERIFIKASI & KONFIRMASI PENGGUNA
# ==========================================
if st.session_state.data_pilihan:
    st.markdown("---")
    st.subheader("📋 Verifikasi Data Hasil AI")
    st.caption("Kamu bisa mengubah langsung data di bawah ini jika tebakan AI ada yang keliru sebelum disimpan.")
    
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
            if item.get("tanggal") and item.get("nominal") is not None:
                rows_to_append.append([
                    item.get("tanggal"),
                    int(item.get("nominal")),
                    item.get("kategori"),
                    item.get("keterangan"),
                    item.get("tipe", "Pengeluaran"),
                    item.get("link_nota", "-")
                ])
        
        if rows_to_append:
            # 1. Kirim paket data ke spreadsheet
            sheet.append_rows(rows_to_append)
            
            # 2. Amankan pesan sukses
            st.session_state.notif_sukses = f"🎉 Sukses! {len(rows_to_append)} komponen transaksi telah tercatat di Google Sheets."
            
            # 3. AKTIFKAN SAKELAR RESET: Sinyal untuk membersihkan layar pada putaran berikutnya
            st.session_state.harus_reset = True
            
            # 4. Pemicu muat ulang halaman secara aman
            st.rerun()
        else:
            st.warning("Tidak ada data transaksi valid yang bisa disimpan.")