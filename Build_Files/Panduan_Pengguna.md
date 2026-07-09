# Trade Manager - Panduan Pengguna Resmi

Selamat datang di **Trade Manager**, asisten *trading* canggih Anda untuk MetaTrader 5 (MT5)! Aplikasi ini dirancang khusus untuk mempermudah manajemen *layering*, eksekusi instan multi-posisi, dan kalkulasi risiko keamanan modal Anda secara *real-time*.

---

## 🚀 1. Persiapan Awal (SANGAT PENTING!)
Agar aplikasi Trade Manager dapat berkomunikasi secara kilat (*0.01 detik*) dengan aplikasi MetaTrader 5 Anda, Anda **WAJIB** memasang modul otak (EA Relay) ke dalam MT5 Anda.

### Langkah Memasang EA Relay:
1. Buka aplikasi **MetaTrader 5 (MT5)**.
2. Pada menu atas, klik **File** -> **Open Data Folder**.
3. Masuk ke dalam folder **`MQL5`** -> **`Experts`**.
4. Buka folder instalasi Trade Manager Anda (contoh: `C:\Program Files\TradeManager`), lalu temukan file bernama **`TradeManager_Relay.mq5`**.
5. **Copy** file tersebut dan **Paste** ke dalam folder `MQL5\Experts` tadi.
6. Kembali ke aplikasi MT5 Anda, cari jendela **Navigator** (sebelah kiri).
7. Di bawah *Expert Advisors*, klik kanan dan pilih **Refresh**. Anda akan melihat `TradeManager_Relay` muncul.
8. Klik kanan pada `TradeManager_Relay` lalu pilih **Modify**. (Ini akan membuka aplikasi MetaEditor).
9. Di MetaEditor, tekan tombol **Compile** (atau **F7** di keyboard). Pastikan tidak ada pesan error di bawahnya. Tutup MetaEditor.
10. Terakhir, *Drag & Drop* (tarik) `TradeManager_Relay` dari Navigator ke dalam chart mana pun di MT5 Anda. 
    > **Catatan:** Pastikan tombol "Algo Trading" berwarna Hijau di bagian atas MT5!

---

## 🖥️ 2. Fitur & Cara Penggunaan

### A. Dashboard Utama
Setelah Anda masuk (*login*) menggunakan akun MT5, Anda akan disajikan dengan *Live Monitor*. Ini menampilkan secara instan sisa Margin, Persentase Profit/Loss dalam mata uang *base* (misal USC) maupun Rupiah (IDR). 
*   **Nilai Tukar Otomatis:** Fitur ini secara *real-time* menarik kurs tukar USD ke IDR dari API global. Jika Anda ingin menguncinya secara manual, silakan ubah pada kolom *Manual Rate* di pojok atas.

### B. Selective Liquidator (Custom Close)
Punya 20 *layer* posisi dan hanya ingin memotong 5 posisi yang paling rugi?
1. Di panel **Selective Liquidator**, pilih `Close Qty` sebanyak **5**.
2. Pilih Sort berdasarkan **Most Loss** (Paling Rugi).
3. Klik **EXECUTE CLOSE**.
   > *Sistem akan membungkus 5 nomor tiket terburuk Anda dan menembakkannya ke EA Relay. Kelima layer tersebut akan lenyap dalam sekejap tanpa berkedip!*

### C. Emergency Close All
Jika pasar bergejolak dan Anda ingin keluar dari SEMUA posisi dalam satu tarikan napas:
1. Di panel **Emergency & Safety Console**, klik tombol merah besar **EMERGENCY CLOSE ALL**.
2. Seluruh ratusan *layer* Anda akan diratakan seketika tanpa harus menunggu antrean eksekusi Python.

### D. Fitur Kalkulator (Add-Layer Simulator)
Ingin tahu apakah Margin Anda kuat menahan *layer* tambahan?
1. Gunakan panel Simulator di bawah grafik *candlestick*.
2. Masukkan rencana tambahan lot (contoh: `0.10`).
3. Klik **Preview**. Panel kiri (Risk & MC Calculator) akan langsung menghitung estimasi baru dari Margin Level dan *Margin Call Price* Anda secara gaib sebelum Anda benar-benar mengeksekusi order tersebut!

---
*Dikembangkan dengan teknologi Asynchronous Python + MQL5 C++ Engine.*
*Trade Manager v1.0*
