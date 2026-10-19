# Dokumentasi Wiring

## Diagram Rangkaian

![Foto perangkat dan rangkaian LED](../images/praktikum/praktikum_test_wiring.jpeg)

Foto di atas menunjukkan susunan perangkat saat praktikum. Pemetaan koneksi
GPIO yang digunakan program dijelaskan pada diagram dan tabel di bawah.

```text
                Jetson Nano (Header 40-pin)
        ┌─────────────────────────────────────────┐
        │                                         │
        │  Pin 1 (3.3V) ──┬──┬──┐                 │
        │                 │  │  │                 │
        │               [330Ω][330Ω][330Ω]        │
        │                 │  │  │                 │
        │                LED LED LED              │
        │                Merah Kuning Hijau       │
        │                 │  │  │                 │
        │  Pin 11 ────────┘  │  │                 │
        │  Pin 13 ───────────┘  │                 │
        │  Pin 15 ──────────────┘                 │
        │                                         │
        │  Pin 6 (GND) ───── (opsional, tidak     │
        │                     dipakai di active-low)│
        └─────────────────────────────────────────┘
```

## Pemetaan Pin

| Fungsi | Pin BOARD | Warna Kabel | Warna LED |
|--------|-----------|-------------|-----------|
| STOP   | 11        | Merah       | 🔴 Merah  |
| SLOW   | 13        | Kuning      | 🟡 Kuning |
| GO     | 15        | Hijau       | 🟢 Hijau  |
| VCC    | 1         | Merah (3V3) | Anoda     |
| GND    | 6 / 9     | Hitam       | (opsional)|

## Konfigurasi Active-LOW

Program memakai **active-low** secara default:

- GPIO `LOW`  → **LED NYALA**
- GPIO `HIGH` → **LED MATI**

Karena itu wiring LED disusun sebagai:

```
3.3V (pin 1) ── Resistor 330Ω ── Anoda LED ── Katoda LED ── GPIO (11/13/15)
```

Ketika GPIO ditarik LOW, arus mengalir dari 3.3V melalui LED menuju pin GPIO.

## Jika Menggunakan Active-HIGH

Ubah wiring menjadi:

```
GPIO (11/13/15) ── Resistor 330Ω ── Anoda LED ── Katoda LED ── GND
```

Jalankan program dengan flag:

```bash
python3 src/traffic_sign_jetson.py --active-high
```

## Tabel Kebutuhan Resistor

| Warna LED | Vf (V) | If (mA) | R = (3.3 − Vf) / If | Resistor |
|-----------|--------|---------|---------------------|----------|
| Merah     | 1.8    | 5       | 300 Ω               | 330 Ω ✅ |
| Kuning    | 2.0    | 5       | 260 Ω               | 330 Ω ✅ |
| Hijau     | 2.2    | 5       | 220 Ω               | 330 Ω ✅ |

## ⚠️ Peringatan Keselamatan

1. **Jangan** menghubungkan 5V langsung ke pin GPIO.
2. **Selalu** gunakan resistor pembatas arus.
3. Pastikan GND Jetson dan GND catu LED common (jika memakai catu terpisah).
4. Jangan menarik lebih dari **16 mA** per pin GPIO.
5. Matikan Jetson sebelum mengubah wiring.

## Verifikasi Wiring

Untuk memverifikasi tanpa kamera:

```bash
python3 src/traffic_sign_jetson.py --test-led --repeat 0
```

Urutan LED yang benar: `SEMUA MATI → STOP → SLOW → GO → SEMUA MATI` (berulang).
