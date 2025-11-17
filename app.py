import os
import io
import base64
import tempfile
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
from gtts import gTTS
from io import BytesIO

# --- GANTI BAGIAN IMPORT ---
import vertexai 
from vertexai.generative_models import GenerativeModel, Part, FinishReason
from vertexai.language_models import TextGenerationModel # buat text-only kalau perlu

# Muat variabel dari file .env
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__)

# --- BAGIAN BARU: KONFIGURASI VERTEX AI ---
try:
    # GANTI "gemini-new-api-id-kamu" dengan ID project kamu
    # GANTI "us-central1" dengan region kamu (us-central1 biasanya default)
    PROJECT_ID = "gemininewapi" # <-- GANTI INI
    LOCATION = "global" # <-- GANTI INI
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    
    # Kita akan buat modelnya nanti pas dipakai, jadi 'client' bisa dikosongin
    client = True # Anggap aja 'True' sebagai tanda siap
    print(f"Koneksi ke VERTEX AI (Project: {PROJECT_ID}) berhasil dikonfigurasi.")
except Exception as e:
    client = False
    print(f"Error konfigurasi Vertex AI: {e}")
# -----------------------------------------------------------

def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )
    return conn
# Ini adalah "endpoint" atau "alamat" pertama kita
# Cuma buat ngetes server jalan atau nggak
@app.route('/')
def index():
    return "Halo, Dapur backend siap dan terhubung ke Gemini!"

@app.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    print("Menerima request di /text-to-speech...")
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"status": "gagal", "pesan": "Data tidak lengkap, butuh 'text'"}), 400

    text_to_speak = data['text']
    
    try:
        # Buat objek gTTS
        # lang='en' untuk Bahasa Inggris, slow=False biar kecepatannya normal
        tts = gTTS(text=text_to_speak, lang='en', slow=False)
        
        # Simpan audio ke 'file' di dalam memori, bukan di hard drive server
        mp3_fp = BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0) # Penting! Balikin pointer ke awal 'file'
        
        print(f"Berhasil membuat audio untuk teks: '{text_to_speak}'")
        
        # Kirim 'file' dari memori ini sebagai response
        return send_file(
            mp3_fp,
            mimetype="audio/mpeg",
            as_attachment=False, # Biar bisa langsung di-stream
            download_name="speech.mp3"
        )

    except Exception as e:
        print(f"Terjadi Error saat membuat TTS: {e}")
        return jsonify({"status": "gagal", "pesan": str(e)}), 500

# --- BAGIAN BARU 2: ENDPOINT IDENTIFIKASI OBJEK ---
@app.route('/identifikasi-objek', methods=['POST'])
def identifikasi_objek():
    print("Menerima request di /identifikasi-objek...")

    image = None # Siapkan variabel kosong untuk gambar
    uploaded_file_ref = None  # referensi file yang diupload ke Gemini

    # Cek apakah request berisi file upload (untuk testing Postman)
    if 'file' in request.files:
        print("Mendeteksi adanya file upload...")
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "gagal", "pesan": "Tidak ada file yang dipilih"}), 400
        
        # Baca file dan buka sebagai gambar
        image = Image.open(file.stream)

    # Cek apakah request berisi JSON (untuk aplikasi Unity nanti)
    elif request.is_json:
        print("Mendeteksi adanya data JSON...")
        data = request.get_json()
        if 'image_base64' not in data:
            return jsonify({"status": "gagal", "pesan": "JSON tidak berisi image_base64"}), 400
        
        # Ubah string base64 kembali menjadi gambar
        image_base64 = data['image_base64']
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))

    # Jika tidak ada file atau JSON, kirim error
    if image is None:
        return jsonify({"status": "gagal", "pesan": "Request harus berisi file atau JSON image_base64"}), 400
    
    try:
        if client is False:
            return jsonify({"status": "gagal", "pesan": "Client Vertex AI belum terinisialisasi"}), 500
        # 3. Siapkan prompt (tetap sama seperti sebelumnya)
        prompt = """
        Kamu adalah API backend untuk sebuah aplikasi edukasi AR Bahasa Inggris.
        Tugasmu adalah mengidentifikasi benda-benda yang biasa ditemukan di dalam **kamar tidur atau ruang tamu (things in the bedroom and living room)**.
        Lihat gambar ini, fokus HANYA pada objek / benda utama yang diletakkan DI ATAS marker yang bercorak dan berisi simbol simbol di setiap sisinya, jika di gambar terdapat tulisan "taruh benda di sini" dengan jelas maka jawab dengan "unknown" yang artinya benda tidak terdeteksi jika ada sesuatu yang menghalangi tulisannya identifikasi nama benda itu.
        Abaikan objek lain di latar belakang. Jika ada lebih dari satu objek, pilih SATU saja yang paling menonjol.

        PENTING: Jangan identifikasi sebagai hewan, makanan, atau benda-benda yang tidak relevan dengan konteks kamar tidur/ruang tamu.

        Balas HANYA dengan nama objeknya saja dalam Bahasa Inggris, dalam bentuk tunggal (singular).

        Contoh balasan: 'book', 'lamp', 'tissue', 'mouse', 'pillow'.
        """

        # 4. Upload gambar ke Gemini Files, lalu minta model memproses (API genai terbaru)
        print("Mempersiapkan gambar untuk Vertex AI...")

        # Ubah gambar PIL kamu jadi 'bytes' mentah
        img_byte_arr = io.BytesIO()
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(img_byte_arr, format='JPEG')
        image_bytes = img_byte_arr.getvalue()

        # Buat "Part" gambar
        image_part = Part.from_data(
            data=image_bytes,
            mime_type="image/jpeg"
        )
        
        # 5. Inisialisasi model & kirim request
        print("Mengirim request ke Vertex AI (gemini-2.5-flash)...")
        # Kita pakai model 'pro' atau 'flash' yang support vision
        model = GenerativeModel("gemini-2.5-flash") 
        
        # Kirim GABUNGAN [gambar, teks_prompt]
        response = model.generate_content(
            [image_part, prompt], # Kirim sebagai list
            generation_config={
                "max_output_tokens": 32, # Jawabanmu pendek, 32 cukup
                "temperature": 0.1,
            }
        )
        print("Menerima response dari Vertex AI.")
        
        # 6. Ambil nama objek (cara ngambilnya sama kayak di atas)
        object_name = ""
        if response.candidates and response.candidates[0].content.parts:
            object_name = response.candidates[0].content.parts[0].text
        
        object_name = object_name.strip().lower()
        if object_name and object_name != "unknown":
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                # Perintah ini akan memasukkan object_name baru.
                # ON CONFLICT DO NOTHING artinya kalau namanya sudah ada, yaudah diemin aja, jangan error.
                cur.execute(
                    "INSERT INTO objects (object_name) VALUES (%s) ON CONFLICT (object_name) DO NOTHING",
                    (object_name,)
                )
                conn.commit()
                cur.close()
                conn.close()
                print(f"Mencatat '{object_name}' ke database (jika belum ada).")
            except Exception as db_error:
                print(f"Error saat mencatat objek ke database: {db_error}")
        # 6. Kirim balasan sukses ke Unity
        return jsonify({"status": "sukses", "object_name": object_name})

    except Exception as e:
        # Kalau ada error, kirim pesan error ke Unity
        print(f"Terjadi Error: {e}")
        return jsonify({"status": "gagal", "pesan": str(e)}), 500
# ----------------------------------------------------

# --- BAGIAN BARU 3: ENDPOINT TANYA JAWAB (Q&A) ---
@app.route('/tanya-ai', methods=['POST'])
def tanya_ai():
    print("Menerima request di /tanya-ai...")
    data = request.get_json()
    if not data or 'object_name' not in data or 'question_key' not in data:
        return jsonify({"status": "gagal", "pesan": "Data tidak lengkap"}), 400

    object_name = data['object_name']
    question_key = data['question_key'] # misal: "fungsi", "ejaan", "definisi", "kalimat"

    # --- LOGIKA BARU DIMULAI DARI SINI ---

    # 1. Cek dulu ke Database (buku contekan)
    try:
        conn = get_db_connection()
        # RealDictCursor bikin hasil query jadi kayak dictionary, lebih gampang dibaca
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Ambil semua data untuk objek ini
        cur.execute("SELECT * FROM objects WHERE object_name = %s", (object_name,))
        db_result = cur.fetchone()
        
        # Cek apakah jawaban untuk pertanyaan SPESIFIK ini sudah ada
        if db_result and db_result[question_key] is not None:
            jawaban_cache = db_result[question_key]
            print(f"Jawaban untuk '{object_name}' - '{question_key}' DITEMUKAN di cache!")
            cur.close()
            conn.close()
            return jsonify({"status": "sukses", "jawaban": jawaban_cache})
            
        print(f"Jawaban untuk '{object_name}' - '{question_key}' TIDAK ADA di cache. Tanya Gemini...")
        # Jika tidak ada, lanjut ke proses tanya Gemini di bawah
        # Kita biarkan koneksi database terbuka untuk proses UPDATE nanti

    except Exception as db_error:
        print(f"Error saat cek cache database: {db_error}")
        # Kalau database error, kita langsung fallback tanya ke Gemini
        # (Koneksi akan ditutup di blok finally nanti jika masih terbuka)
        pass # Lanjut saja ke proses Gemini


    # 2. Kamus untuk menerjemahkan 'key' menjadi pertanyaan (ini masih sama)
    question_map = {
        "definisi": f"What is a {object_name}?",
        "fungsi": f"What is a {object_name} for?",
        "ejaan": f"How do you spell '{object_name}'?",
        "kalimat": f"Can you make a simple sentence with the word '{object_name}'?"
    }

    if question_key not in question_map:
        return jsonify({"status": "gagal", "pesan": "Kunci pertanyaan tidak valid"}), 400
    question_text = question_map[question_key]

    # 3. Proses Tanya ke Gemini (ini juga masih sama)
    try:
        if client is None:
            return jsonify({"status": "gagal", "pesan": "Client Gemini belum terinisialisasi"}), 500

        if question_key == "ejaan":
            prompt = f"""
            Kamu adalah API backend untuk aplikasi edukasi.
            JANGAN BERTINGKAH SEPERTI CHATBOT. JANGAN MENYAPA.
            Objeknya adalah '{object_name}'.
            Tugasmu adalah mengeja kata tersebut huruf per huruf, dengan tanda hubung (-) sebagai pemisah.
            Balas HANYA dengan ejaannya saja.

            Contoh jika objek='chair':
            'C-H-A-I-R'

            Contoh jika objek='book':
            'B-O-O-K'
            """
        else:
            prompt = f"""
            Kamu adalah API backend untuk aplikasi edukasi.
            JANGAN BERTINGKAH SEPERTI CHATBOT. JANGAN MENYAPA.
            Objeknya adalah '{object_name}'.
            Pertanyaannya adalah: '{question_text}'.
            Berikan jawaban yang SANGAT SINGKAT dan JELAS dalam Bahasa Inggris, cocok untuk anak 10 tahun.
            Balas HANYA dengan jawaban langsungnya. Maksimal 2 kalimat pendek.

            Contoh jika objek='book' dan pertanyaan='What is a book for?':
            'We read a book to learn things or enjoy a story.'

            Contoh jika objek='unknown' dan pertanyaan='What is a unknown?':
            'Unknown means something we do not know.'
            """

        print(f"Mengirim pertanyaan tentang '{object_name}' ke Vertex AI...")
        
        # 1. Inisialisasi model
        # Model 'gemini-2.5-flash' itu gak ada di Vertex,
        # kita pakai 'gemini-1.5-flash-001' yang lebih baru
        model = GenerativeModel("gemini-2.5-flash") 
        
        # 2. Kirim request
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 256,
                "temperature": 0.8, # Biar jawabannya konsisten
            },
        )
        print("Menerima jawaban dari Vertex AI.")
        # 3. Ambil teksnya (cara ngambilnya sedikit beda)
        jawaban_ai = ""
        if response.candidates and response.candidates[0].content.parts:
            jawaban_ai = response.candidates[0].content.parts[0].text
        
        jawaban_ai = jawaban_ai.strip()

        # --- BAGIAN BARU: SIMPAN JAWABAN BARU KE DATABASE ---
        try:
            # Kita pakai koneksi yang tadi (jika masih ada) atau buat baru
            if 'conn' not in locals() or conn.closed:
                conn = get_db_connection()
            cur = conn.cursor()
            
            # Perintah UPDATE yang dinamis sesuai question_key
            # f-string di sini aman karena question_key kita validasi dari question_map
            sql_update_query = f"UPDATE objects SET {question_key} = %s WHERE object_name = %s"
            cur.execute(sql_update_query, (jawaban_ai, object_name))
            conn.commit()
            print(f"Jawaban baru untuk '{object_name}' - '{question_key}' telah disimpan ke database.")
        
        except Exception as db_error:
            print(f"Gagal menyimpan jawaban ke database: {db_error}")
        finally:
            if 'cur' in locals() and not cur.closed:
                cur.close()
            if 'conn' in locals() and not conn.closed:
                conn.close()
        # ----------------------------------------------------

        return jsonify({"status": "sukses", "jawaban": jawaban_ai})

    except Exception as e:
        print(f"Terjadi Error saat menghubungi Gemini: {e}")
        return jsonify({"status": "gagal", "pesan": str(e)}), 500
    
@app.route('/tanya-gambar-manual', methods=['POST'])
def tanya_gambar_manual():
    print("Menerima request di /tanya-gambar-manual...")

    # 1. Cek apakah ada file gambar dan teks pertanyaan
    if 'image_file' not in request.files:
        return jsonify({"status": "gagal", "pesan": "Request tidak berisi file gambar"}), 400
    
    if 'question_text' not in request.form:
        return jsonify({"status": "gagal", "pesan": "Request tidak berisi teks pertanyaan"}), 400

    image_file = request.files['image_file']
    question_text = request.form['question_text']
    print(f"Menerima pertanyaan: '{question_text}' untuk sebuah gambar.")

    # Siapkan variabel untuk file yang diupload ke Gemini
    uploaded_file_ref = None

    try:
        # 2. Buka gambar dan upload ke Gemini (mirip proses identifikasi)
        image = Image.open(image_file.stream)
        
        print("Mengupload gambar konteks ke Gemini Files...")
        tmp_path = None
        try:
            if image.mode in ("RGBA", "P"): image = image.convert("RGB")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                image.save(tmp, format="JPEG")
                tmp_path = tmp.name
            uploaded_file_ref = client.files.upload(file=tmp_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass
        
        # 3. Buat prompt yang menggabungkan gambar dan pertanyaan siswa
        prompt = f"""
        Kamu adalah AI guru yang ramah untuk aplikasi edukasi anak-anak.
        Lihat gambar yang diberikan. Lalu, jawab pertanyaan dari siswa tentang objek di gambar itu.
        Pertanyaan siswa: "{question_text}"

        PENTING:
        - Jawab dengan Bahasa Inggris yang SANGAT SINGKAT dan sederhana.
        - Cocokkan jawabanmu untuk anak usia 10 tahun.
        - JANGAN menyapa atau menggunakan kalimat pembuka. Langsung berikan jawabannya.
        
        Contoh jika pertanyaannya "can it fly?":
        Jawaban yang baik: "No, a book cannot fly."
        Jawaban yang buruk: "Hello! Regarding your question, no, the object in the image, which is a book, does not have the ability to fly."
        """

        # 4. Kirim prompt ke Gemini untuk dapat jawaban TEKS
        print("Mengirim pertanyaan dan gambar ke Gemini...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_file_ref, prompt],
        )
        jawaban_ai_text = (response.text or "").strip()
        print(f"Gemini menjawab: '{jawaban_ai_text}'")

        # 5. UBAH JAWABAN TEKS MENJADI SUARA (TTS)
        if not jawaban_ai_text: # Jika Gemini tidak menjawab apa-apa
            jawaban_ai_text = "Sorry, I don't know how to answer that."

        tts = gTTS(text=jawaban_ai_text, lang='en', slow=False)
        mp3_fp = BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        print("Berhasil membuat audio dari jawaban Gemini. Mengirim audio ke Unity...")
        
        # 6. Kirim file audio MP3 sebagai jawaban akhir
        return send_file(
            mp3_fp,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="manual_answer.mp3"
        )

    except Exception as e:
        print(f"Terjadi Error di /tanya-gambar-manual: {e}")
        return jsonify({"status": "gagal", "pesan": str(e)}), 500

# -----------------------------------------------------------
if __name__ == '__main__':
    # PASTIKAN ADA host='0.0.0.0'
    app.run(host='0.0.0.0', port=5000, debug=True)