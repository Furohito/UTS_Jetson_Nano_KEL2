# Models

Folder ini menyimpan file model TensorRT (`best.engine`) yang dipakai oleh
`src/traffic_sign_jetson.py`.

---

## File Utama

| File          | Keterangan                                       |
|---------------|--------------------------------------------------|
| `best.engine` | Engine TensorRT YOLOv8 — **siap pakai**, langsung dijalankan |

> ⚠️ File `best.engine` **tidak di-commit** ke Git (lihat `.gitignore`) karena
> ukurannya besar dan spesifik untuk device tertentu. Letakkan file ini secara
> manual di folder `models/` setelah clone.

---

## Spesifikasi Engine

| Parameter     | Nilai                        |
|---------------|------------------------------|
| Framework     | YOLOv8                       |
| Format        | TensorRT engine              |
| Input         | `(1, 3, 320, 320)` float32   |
| Output        | `(1, 7, N)` float32          |
| Kelas         | `go`, `slow`, `stop`         |
| Presisi       | FP16                         |
| Workspace     | 1024 MB                      |
| Batch size    | 1                            |

**Struktur output `(1, 7, N)`:**

- 4 nilai pertama: bounding box `(cx, cy, w, h)`
- 3 nilai berikutnya: skor kelas `[go, slow, stop]`
- `N`: jumlah anchor/grid (biasanya 2100 untuk imgsz=320)

---

## Cara Mendapatkan `best.engine`

### Opsi 1 — Dari tim (paling cepat)

File `best.engine` sudah disiapkan oleh tim. Hubungi anggota tim atau minta
via Google Drive / OneDrive. Letakkan di:

```text
models/best.engine
```

### Opsi 2 — Konversi dari ONNX (jika punya `best.onnx`)

Kalau kamu punya file `best.onnx` (hasil training), konversi ke TensorRT
engine **di Jetson Nano** dengan `trtexec`:

```bash
/usr/src/tensorrt/bin/trtexec \
    --onnx=models/best.onnx \
    --saveEngine=models/best.engine \
    --fp16 \
    --workspace=1024
```

Jalankan perintah di atas dari root repositori.

**Penjelasan opsi:**

| Opsi               | Fungsi                                     |
|--------------------|--------------------------------------------|
| `--onnx`           | File ONNX input                            |
| `--saveEngine`     | File TensorRT output                       |
| `--fp16`           | Presisi FP16 (cepat, akurasi hampir sama)  |
| `--workspace=1024` | Alokasi workspace 1 GB untuk optimasi      |

Tambahkan `--verbose` kalau ingin melihat log lengkap proses konversi.

> ⚠️ Konversi **harus dilakukan di Jetson Nano**, bukan di PC.
> Engine TensorRT **tidak portable** antar device.

---

## Cara Memakai Engine

### 1. Letakkan di folder yang benar

Default path di `src/traffic_sign_jetson.py`:

```python
ENGINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "best.engine"
)
```

Path ini menunjuk ke `models/best.engine` di root repositori secara otomatis,
tanpa bergantung pada nama folder repositori atau direktori kerja terminal.

### 2. Verifikasi engine

Jalankan:

```bash
python3 src/traffic_sign_jetson.py --check
```

Output yang diharapkan:

```text
Engine: /home/jetson/UTS_Jetson_Nano_KEL2/models/best.engine
Engine tersedia: True
Binding 0: images (1, 3, 320, 320)
Binding 1: output0 (1, 7, 2100)
TensorRT siap: (1, 3, 320, 320) -> (1, 7, 2100)
[OK] Pipeline kamera dan engine TensorRT tersedia.
```

Kalau ada `[ERR]` atau `Engine tersedia: False` — cek:

- Path `ENGINE_PATH` sudah benar?
- File `best.engine` benar-benar ada di folder itu?
- Versi TensorRT di Jetson cocok dengan yang dipakai saat konversi?

### 3. Jalankan deteksi

```bash
python3 src/traffic_sign_jetson.py
```

---

## Info Kelas Model

Model dilatih untuk mendeteksi **3 kelas rambu**:

| Class ID | Nama   | Warna LED | Pin GPIO |
|----------|--------|-----------|----------|
| 0        | go     | Hijau     | 15       |
| 1        | slow   | Kuning    | 13       |
| 2        | stop   | Merah     | 11       |

Urutan ini **harus sama** dengan variabel `CLASS_NAMES` di
`src/traffic_sign_jetson.py`:

```python
CLASS_NAMES = ["go", "slow", "stop"]
```

Kalau urutan berbeda, LED akan menyala untuk rambu yang salah.

---

## Catatan Penting

1. **Engine tidak portable** — harus dikonversi ulang di setiap Jetson.
2. **Setelah upgrade JetPack**, engine harus dikonversi ulang karena versi
   TensorRT berubah.
3. **`imgsz` harus konsisten** — nilai `IMG_SIZE = 320` di
   `traffic_sign_jetson.py` harus sama dengan `imgsz` saat export/conversion.
4. **Ukuran file** — `best.engine` biasanya 10–30 MB (FP16). Kalau >100 MB,
   pertimbangkan pakai Git LFS.

---

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `Engine tidak ditemukan` | Cek path `ENGINE_PATH` dan keberadaan file |
| `deserialize_cuda_engine` gagal | Versi TensorRT tidak cocok — konversi ulang di Jetson |
| `Bentuk input engine tidak sesuai` | Pastikan `imgsz=320` saat konversi |
| `Bentuk output engine tidak sesuai` | Cek jumlah kelas (harus 3) saat training/export |
| Deteksi selalu kosong | Turunkan `CONF_THRESHOLD` di source code |

---

## Referensi

- [TensorRT Developer Guide](https://docs.nvidia.com/deeplearning/tensorrt/developer-guide/)
- [trtexec Documentation](https://docs.nvidia.com/deeplearning/tensorrt/developer-guide/index.html#trtexec)
- [Ultralytics YOLOv8 Export](https://docs.ultralytics.com/modes/export/)
