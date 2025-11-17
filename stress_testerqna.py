import requests
import threading
import time
import json

# --- KONFIGURASI ---
SERVER_URL = "http://143.198.93.53:5000/tanya-ai" # URL endpoint Q&A
JUMLAH_REQUEST = 50  # Jumlah "robot" yang akan menyerang
OBJECT_NAME = "scissors"   # Objek yang mau ditanyakan
QUESTION_KEY = "kalimat"  # Jenis pertanyaan (definisi, fungsi, ejaan, kalimat)
# -------------------

# Variabel untuk mencatat hasil
sukses_count = 0
gagal_count = 0
lock = threading.Lock() # Kunci untuk mencegah tabrakan data antar thread

# Fungsi yang akan dijalankan oleh setiap "robot" (thread)
def kirim_request_qna(nomor_robot):
    global sukses_count, gagal_count

    print(f"[Robot Q&A #{nomor_robot}] Siap-siap, mulai bertanya tentang '{OBJECT_NAME}'...")
    
    try:
        # Siapkan payload JSON untuk Q&A
        payload = {
            "object_name": OBJECT_NAME,
            "question_key": QUESTION_KEY
        }
        
        # Kirim request POST
        response = requests.post(SERVER_URL, json=payload, timeout=30) # Timeout 30 detik

        # Cek status response
        if response.status_code == 200 and response.json().get('status') == 'sukses':
            with lock:
                sukses_count += 1
            # Kita print jawabannya sekali aja biar ga menuhin layar
            if nomor_robot == 1:
                print(f"✅ [Robot Q&A #{nomor_robot}] SUKSES! Jawaban: {response.json().get('jawaban')}")
            else:
                print(f"✅ [Robot Q&A #{nomor_robot}] SUKSES!")

        else:
            with lock:
                gagal_count += 1
            print(f"❌ [Robot Q&A #{nomor_robot}] GAGAL! Status Code: {response.status_code}, Pesan: {response.text}")

    except requests.exceptions.RequestException as e:
        with lock:
            gagal_count += 1
        print(f"❌ [Robot Q&A #{nomor_robot}] GAGAL PARAH! Error koneksi: {e}")


# --- PROGRAM UTAMA ---
if __name__ == "__main__":
    print(f"--- Memulai Stress Test untuk Q&A: {JUMLAH_REQUEST}x pertanyaan '{QUESTION_KEY}' untuk '{OBJECT_NAME}' ---")
    
    # 1. Siapkan "pasukan robot" (threads)
    threads = []
    for i in range(JUMLAH_REQUEST):
        robot = threading.Thread(target=kirim_request_qna, args=(i + 1,))
        threads.append(robot)

    # 2. Catat waktu mulai
    waktu_mulai = time.time()
    print(f"\n--- MELEPASKAN {JUMLAH_REQUEST} ROBOT PENANYA SEKALIGUS! ---")

    # 3. Lepaskan semua robot untuk bekerja
    for robot in threads:
        robot.start()

    # 4. Tunggu sampai semua robot selesai bekerja
    for robot in threads:
        robot.join()
    
    # 5. Catat waktu selesai dan hitung durasi
    waktu_selesai = time.time()
    durasi = waktu_selesai - waktu_mulai
    
    # 6. Tampilkan laporan hasil
    print("\n\n--- LAPORAN STRESS TEST Q&A SELESAI ---")
    print(f"Total Durasi\t: {durasi:.2f} detik")
    print(f"Total Request\t: {JUMLAH_REQUEST}")
    print(f"✅ Sukses\t\t: {sukses_count}")
    print(f"❌ Gagal\t\t: {gagal_count}")
    if JUMLAH_REQUEST > 0 and durasi > 0.001: # Hindari pembagian dengan nol
        rps = JUMLAH_REQUEST / durasi
        print(f"Kecepatan\t: {rps:.2f} request per detik")
    print("---------------------------------------")