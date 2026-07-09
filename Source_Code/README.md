# Trade Manager 🚀

**Trade Manager** adalah aplikasi *desktop* level profesional yang dirancang khusus untuk memonitor, mengelola, dan mengeksekusi transaksi trading di MetaTrader 5 (MT5) dengan kecepatan tinggi. Dibangun menggunakan Python dan *CustomTkinter*, aplikasi ini menawarkan antarmuka *Dark Mode* modern yang elegan dan responsif, menjadikannya senjata utama bagi para *trader* agresif (terutama pengguna strategi *layering*, *martingale*, atau *grid*).

Aplikasi ini bersifat **Universal**—dirancang untuk menangani berbagai jenis akun mulai dari **USC (Cent), USD (Standard), hingga IDR (Rupiah)** dengan konversi nilai tukar secara *real-time*.

---

## 🌟 Fitur Utama (Core Features)

### 1. Ultra-Fast Execution Engine (Selective Liquidator)
Dirancang untuk menghadapi volatilitas ekstrem, mesin eksekusi aplikasi ini mampu menutup (melikuidasi) posisi secara massal dalam sekejap mata.
* **Kecepatan Brutal:** Mampu melikuidasi hingga **300+ layer (posisi) dalam waktu kurang dari 2 detik!**
* **Filter Selektif:** Menutup posisi berdasarkan kuantitas tertentu, arah (*Buy/Sell*), atau urutan (*Sort*).

### 2. Multi-Currency Live Monitor
Tidak perlu lagi menerka-nerka keuntungan dalam rupiah. Trade Manager menyediakan monitoring *real-time* yang komprehensif:
* Menampilkan *Floating* Net PnL secara akurat dalam mata uang dasar akun (USC/USD) dan ekuivalennya dalam **Rupiah (IDR)**.
* Konversi kurs USD/IDR berjalan otomatis di latar belakang (*live rate fetching*).
* Persentase *profit/drawdown* langsung dikalkulasi terhadap total modal.

### 3. Performance Analytics & Visual Charts (Smart Matplotlib)
Lacak performa *trading* historis Anda dengan fitur analitik kelas kakap. 
* **Filter Waktu Dinamis:** Harian, Mingguan, Bulanan, hingga *All-Time*.
* **Smart Charting:** Grafik Matplotlib *built-in* dengan teknologi *Smart Trimming* & *Dynamic Grouping*. Grafik "All-Time" tidak akan memiliki area kosong bertahun-tahun, melainkan otomatis dikelompokkan secara rapi per bulan sejak trade pertama Anda.
* **Statistik Detil:** Menampilkan *Gross Profit*, *Gross Loss*, *Net Profit*, *Total Trades*, dan persentase *Win Rate* harian/bulanan.

### 4. Smart Trailing Stop & Breakeven (BE)
Amankan profit Anda tanpa harus mengawasi *chart* 24 jam.
* **Smart BE:** Memindahkan *Stop Loss* ke titik impas (*entry*) ditambah *offset* (pips) secara otomatis untuk ratusan layer sekaligus.
* **Start Trailing:** Sistem *Trailing Stop* otomatis yang mengunci profit seiring pergerakan harga.

### 5. Emergency & Safety Console
Fitur keselamatan absolut untuk kondisi darurat (*market crash* atau anomali):
* **Emergency Close All:** Satu tombol panik (berwarna merah) untuk menebas seluruh posisi terbuka seketika.
* **Hedge Lock:** Satu tombol untuk segera mengunci (*lock*) *floating loss* saat ini dengan membuka posisi berlawanan sebesar total lot yang sedang berjalan.
* **Equity Guard:** Proteksi otomatis (Auto Cut-Off) jika *drawdown* akun menyentuh persentase batas maksimal yang ditentukan.

### 6. Live Position Chart & Hotkeys
* **Mini Chart Integrasi:** Terdapat grafik pergerakan harga (*candlestick*) mini langsung di *dashboard* yang membantu memvisualisasikan posisi Anda terhadap harga *market* saat ini.
* **Global Hotkeys:** Eksekusi perintah krusial melalui *shortcut keyboard* tanpa harus memindahkan kursor *mouse*, memastikan nol-keterlambatan saat *scalping* atau *layering*.

---

## ⚙️ Spesifikasi Teknis (Technical Specifications)

* **Architecture:** Asynchronous multithreading (mencegah UI *freeze* saat eksekusi data ribuan *layer*).
* **Backend / API:** MetaTrader 5 Python Integration (`MetaTrader5` library).
* **GUI Framework:** `customtkinter` (Modern hardware-accelerated UI).
* **Charting Engine:** `matplotlib` dengan integrasi `FigureCanvasTkAgg` untuk performa *rendering* ringan.
* **Timezone Safety:** Manajemen zona waktu yang kuat untuk menangani *Clock Desync* antara jam lokal komputer pengguna dan jam server *broker* (menjamin akurasi kalkulasi PnL harian 100%).
* **Data Formatting:** Universal IDR & USD Formatting, mendeteksi secara otomatis apakah akun merupakan *Cent* (USC) atau *Standard* (USD) dan memformat desimal/ribuan secara cerdas.

---
*Trade Manager - Kecepatan, Presisi, dan Kontrol Penuh di Tangan Anda.*
