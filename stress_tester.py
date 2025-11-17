import requests
import threading
import time
import base64

# --- KONFIGURASI ---
SERVER_URL = "http://143.198.93.53:5000/identifikasi-objek" # Ganti IP jika server di mesin lain
IMAGE_PATH = "things.jpg"  # Nama file gambar yang ada di folder backend
JUMLAH_REQUEST = 15
# -------------------

# Variabel untuk mencatat hasil
sukses_count = 0
gagal_count = 0
lock = threading.Lock() # Kunci untuk mencegah tabrakan data antar thread

# Fungsi yang akan dijalankan oleh setiap "robot" (thread)
def kirim_request(nomor_robot, data_gambar_base64):
    global sukses_count, gagal_count

    print(f"[Robot #{nomor_robot}] Siap-siap, mulai mengirim request...")
    
    try:
        # Siapkan payload JSON
        payload = {
            "image_base64": data_gambar_base64
        }
        
        # Kirim request POST
        response = requests.post(SERVER_URL, json=payload, timeout=60) # Timeout 60 detik

        # Cek status response
        if response.status_code == 200:
            with lock:
                sukses_count += 1
            print(f"✅ [Robot #{nomor_robot}] SUKSES! Jawaban: {response.json().get('object_name')}")
        else:
            with lock:
                gagal_count += 1
            print(f"❌ [Robot #{nomor_robot}] GAGAL! Status Code: {response.status_code}, Pesan: {response.text}")

    except requests.exceptions.RequestException as e:
        with lock:
            gagal_count += 1
        print(f"❌ [Robot #{nomor_robot}] GAGAL PARAH! Error koneksi: {e}")


# --- PROGRAM UTAMA ---
if __name__ == "__main__":
    print("--- Memulai Stress Test ---")
    
    # 1. Baca dan encode gambar sekali saja
    try:
        with open(IMAGE_PATH, "rb") as image_file:
            gambar_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        print(f"Gambar '{IMAGE_PATH}' berhasil dibaca dan di-encode.")
    except FileNotFoundError:
        print(f"Error: File gambar '{IMAGE_PATH}' tidak ditemukan! Pastikan file ada di folder backend.")
        exit()

    
    # 2. Siapkan "pasukan robot" (threads)
    threads = []
    for i in range(JUMLAH_REQUEST):
        robot = threading.Thread(target=kirim_request, args=(i + 1, gambar_base64))
        threads.append(robot)

    # 3. Catat waktu mulai
    waktu_mulai = time.time()
    print(f"\n--- MELEPASKAN {JUMLAH_REQUEST} ROBOT SEKALIGUS! ---")

    # 4. Lepaskan semua robot untuk bekerja
    for robot in threads:
        robot.start()

    # 5. Tunggu sampai semua robot selesai bekerja
    for robot in threads:
        robot.join()
    
    # 6. Catat waktu selesai dan hitung durasi
    waktu_selesai = time.time()
    durasi = waktu_selesai - waktu_mulai
    
    # 7. Tampilkan laporan hasil
    print("\n\n--- LAPORAN STRESS TEST SELESAI ---")
    print(f"Total Durasi\t: {durasi:.2f} detik")
    print(f"Total Request\t: {JUMLAH_REQUEST}")
    print(f"✅ Sukses\t\t: {sukses_count}")
    print(f"❌ Gagal\t\t: {gagal_count}")
    if JUMLAH_REQUEST > 0 and durasi > 0:
        rps = JUMLAH_REQUEST / durasi
        print(f"Kecepatan\t: {rps:.2f} request per detik")
    print("---------------------------------")