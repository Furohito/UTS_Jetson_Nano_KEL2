# Arsitektur Sistem

## Diagram Blok

![Arsitektur Sistem](Arsitektur%20Sistem%20dan%20Dokumentasi%20Perangkat%20keras.png)

Foto perangkat memperlihatkan modul kamera stereo. Implementasi program mengambil
satu stream CSI (`CAMERA_ID = 0`), tanpa pemrosesan kedalaman stereo.

```text
┌─────────────────────────────────────────────────────────────────┐
│                        NVIDIA Jetson Nano                       │
│                                                                 │
│  ┌───────────┐   NVMM   ┌─────────────┐   BGR   ┌────────────┐  │
│  │  IMX219   │ ───────▶ │  GStreamer  │ ──────▶ │ Preprocess │  │
│  │  (CSI)    │          │  Pipeline   │         │ 320×320    │  │
│  └───────────┘          └─────────────┘         └─────┬──────┘  │
│                                                        │         │
│                                                        ▼         │
│  ┌───────────┐          ┌─────────────┐         ┌────────────┐  │
│  │  GPIO     │ ◀─────── │  Stability  │ ◀────── │  TensorRT  │  │
│  │  11/13/15 │  label   │  Filter     │  dets   │  YOLOv8    │  │
│  └─────┬─────┘          └─────────────┘         └────────────┘  │
│        │                                    (CUDA + cuDNN)      │
└────────┼────────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────┐
  │ LED Merah    │ STOP
  │ LED Kuning   │ SLOW
  │ LED Hijau    │ GO
  └──────────────┘
```

## Alur Data (per frame)

| Tahap | Fungsi | Detail |
|-------|--------|--------|
| 1. Capture     | `read_frame()`        | `try-pull-sample` dari `appsink` |
| 2. Preprocess  | `preprocess()`        | Letterbox 320×320, RGB, CHW, /255 |
| 3. H2D Copy    | `cudaMemcpy`          | Host → GPU (input tensor) |
| 4. Inference   | `context.execute_v2`  | TensorRT YOLOv8, FP16/FP32 |
| 5. D2H Copy    | `cudaMemcpy`          | GPU → Host (output tensor) |
| 6. Postprocess | `detect()`            | Decode bbox, threshold, NMS |
| 7. Stability   | main loop             | Butuh `STABLE_FRAMES` frame berturut |
| 8. Actuation   | `set_led()`           | GPIO output ke pin 11/13/15 |
| 9. Preview     | `cv2.imshow`          | (opsional) |

## Modul Source Code

`src/traffic_sign_jetson.py` terbagi menjadi bagian:

| Bagian | Isi |
|--------|-----|
| **CONFIGURATION**     | Path engine, resolusi kamera, threshold, pin |
| **GPIO**              | `initialize_gpio()`, `set_led()`, `all_led_off()` |
| **ENVIRONMENT CHECK** | `check_environment()` — cek library & pipeline |
| **LED TEST**          | `test_led()` — uji LED tanpa kamera |
| **GSTREAMER CAMERA**  | `make_camera_pipeline()`, `open_camera()`, `read_frame()` |
| **CUDA RUNTIME**      | `initialize_detection_runtime()`, `check_cuda()` |
| **TENSORRT ENGINE**   | `load_engine()` — deserialize + alokasi buffer |
| **PREPROCESS**        | `preprocess()` — letterbox + normalisasi |
| **DETECTION & NMS**   | `detect()` — decode + NMS per kelas |
| **MAIN**              | Parsing argumen, main loop, cleanup |
