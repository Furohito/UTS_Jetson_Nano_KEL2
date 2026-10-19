#!/usr/bin/env python3
# Jetson Nano CSI IMX219 + TensorRT YOLOv8 + GPIO LEDs
# Python 3.6 compatible.
#
# LED ACTIVE-LOW:
# GPIO.LOW  = LED NYALA
# GPIO.HIGH = LED MATI
#
# Physical pins (GPIO.BOARD):
# STOP = pin 11
# SLOW = pin 13
# GO   = pin 15

import os
import time
import ctypes
import signal
import sys
import argparse
import importlib
import platform
import math

# ============================================================
# CONFIGURATION
# ============================================================

ENGINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "best.engine"
)

CAMERA_ID = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30
CAMERA_FLIP_METHOD = 2

IMG_SIZE = 320
CONF_THRESHOLD = 0.55
IOU_THRESHOLD = 0.45
STABLE_FRAMES = 3

CLASS_NAMES = ["go", "slow", "stop"]

# Physical header pin numbers: GPIO.BOARD.
STOP_PIN = 11
SLOW_PIN = 13
GO_PIN = 15

# Sama seperti kode LED pertama.
LED_ACTIVE_LOW = True

HOST_TO_DEVICE = 1
DEVICE_TO_HOST = 2

# ============================================================
# GPIO
# ============================================================

GPIO = None

gpio_ready = False
gpio_active_low = LED_ACTIVE_LOW

gpio_on_level = None
gpio_off_level = None

gpio_initialized_pins = []
gpio_lock = None


def led_pin_mapping():
    return {
        "stop": STOP_PIN,
        "slow": SLOW_PIN,
        "go": GO_PIN
    }


def print_startup_diagnostics(active_low):
    print("Engine: {}".format(ENGINE_PATH))
    print("Engine tersedia: {}".format(os.path.isfile(ENGINE_PATH)))
    print("Kelas model: {}".format(CLASS_NAMES))

    print(
        "Pin fisik BOARD: STOP={}, SLOW={}, GO={}".format(
            STOP_PIN, SLOW_PIN, GO_PIN
        )
    )

    print(
        "LED_ACTIVE_LOW={} | {}".format(
            active_low,
            "LOW=NYALA, HIGH=MATI"
            if active_low
            else "HIGH=NYALA, LOW=MATI"
        )
    )

    print(
        "Pastikan wiring, pinout, dan polaritas LED sesuai "
        "dengan konfigurasi hardware."
    )


def initialize_gpio():
    global GPIO
    global gpio_ready
    global gpio_on_level
    global gpio_off_level
    global gpio_lock

    if gpio_ready:
        return True

    try:
        import Jetson.GPIO as GPIO
        import fcntl

        gpio_lock = open(
            "/tmp/traffic-sign-gpio-{}.lock".format(os.getuid()),
            "a"
        )

        fcntl.flock(
            gpio_lock.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )

        pins = [STOP_PIN, SLOW_PIN, GO_PIN]

        if len(set(pins)) != len(pins):
            raise ValueError(
                "STOP_PIN, SLOW_PIN, dan GO_PIN harus berbeda."
            )

        # ACTIVE-LOW:
        # LOW  = LED ON
        # HIGH = LED OFF
        gpio_on_level = (
            GPIO.LOW if gpio_active_low else GPIO.HIGH
        )

        gpio_off_level = (
            GPIO.HIGH if gpio_active_low else GPIO.LOW
        )

        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

        for pin in pins:
            GPIO.setup(
                pin,
                GPIO.OUT,
                initial=gpio_off_level
            )

            gpio_initialized_pins.append(pin)

        gpio_ready = True

        if not all_led_off():
            raise RuntimeError(
                "Gagal mengatur kondisi awal LED mati."
            )

        print("GPIO berhasil diinisialisasi.")
        print("Pin fisik 11, 13, 15: SEMUA LED MATI.")

        return True

    except Exception as exc:
        print(
            "PERINGATAN: GPIO tidak aktif: {}: {}".format(
                type(exc).__name__, exc
            )
        )

        print("LED tidak dapat dikendalikan.")

        cleanup_gpio()
        return False


def all_led_off():
    global gpio_ready

    if GPIO is None or not gpio_initialized_pins:
        return True

    try:
        # Semua LED menggunakan level OFF.
        GPIO.output(
            gpio_initialized_pins,
            gpio_off_level
        )

        return True

    except Exception as exc:
        gpio_ready = False

        print(
            "PERINGATAN: gagal mematikan LED: {}".format(exc)
        )

        return False


def set_led(label):
    global gpio_ready

    if not gpio_ready:
        return False

    pin = led_pin_mapping().get(label)

    # Label None atau tidak dikenal berarti semua LED mati.
    if pin is None:
        return all_led_off()

    try:
        # Matikan semua LED terlebih dahulu.
        if not all_led_off():
            return False

        # Nyalakan LED yang sesuai.
        GPIO.output(pin, gpio_on_level)

        return True

    except Exception as exc:
        gpio_ready = False

        print(
            "PERINGATAN: kontrol LED gagal: {}".format(exc)
        )

        return False


def cleanup_gpio():
    global gpio_ready
    global gpio_lock

    # Kirim perintah untuk mematikan semua LED.
    success = all_led_off()

    # Sengaja tidak memanggil GPIO.cleanup().
    # Tujuannya mengikuti kode pertama, yaitu mempertahankan
    # pin sebagai output dengan level OFF setelah program berhenti.
    gpio_ready = False

    if gpio_lock is not None:
        try:
            gpio_lock.close()

        except Exception as exc:
            success = False

            print(
                "PERINGATAN: pelepasan lock GPIO gagal: {}".format(
                    exc
                )
            )

        gpio_lock = None

    if success:
        print("Perintah LED MATI telah dikirim.")

    else:
        print(
            "PERINGATAN: kondisi mati LED tidak dapat dipastikan."
        )

    return success


def show_wiring(active_low):
    print("Nomor pin menggunakan GPIO.BOARD.")
    print("STOP = pin 11")
    print("SLOW = pin 13")
    print("GO   = pin 15")

    if active_low:
        print("Konfigurasi ACTIVE-LOW:")
        print("LOW = LED NYALA")
        print("HIGH = LED MATI")
        print(
            "Untuk LED biasa: pin 1 (3.3 V) -> resistor -> "
            "anoda LED; katoda -> pin kontrol."
        )

    else:
        print("Konfigurasi ACTIVE-HIGH:")
        print("HIGH = LED NYALA")
        print("LOW = LED MATI")
        print(
            "Untuk LED biasa: pin kontrol -> resistor -> "
            "anoda LED; katoda -> GND."
        )

    print("Gunakan resistor pembatas arus untuk setiap LED.")
    print("Jangan menghubungkan 5 V langsung ke pin GPIO.")


# ============================================================
# ENVIRONMENT CHECK
# ============================================================

def check_environment(active_low):
    print(
        "Python: {} | CPU: {}".format(
            sys.version.split()[0],
            platform.machine()
        )
    )

    failed = False

    modules = {}

    apt_names = {
        "numpy": "python3-numpy",
        "cv2": "python3-opencv",
        "gi": (
            "python3-gi gir1.2-gstreamer-1.0 "
            "gir1.2-gst-plugins-base-1.0"
        ),
        "Jetson.GPIO": "python3-jetson-gpio",
        "tensorrt": "python3-libnvinfer"
    }

    for name in [
        "numpy",
        "cv2",
        "gi",
        "Jetson.GPIO",
        "tensorrt"
    ]:
        try:
            module = importlib.import_module(name)
            modules[name] = module

            print(
                "[OK] {}: {}".format(
                    name,
                    getattr(
                        module,
                        "__version__",
                        getattr(module, "VERSION", "terpasang")
                    )
                )
            )

        except Exception as exc:
            failed = True

            print(
                "[ERR] {}: {}. Paket terkait: {}".format(
                    name, exc, apt_names[name]
                )
            )

    gpio = modules.get("Jetson.GPIO")

    if gpio is not None:
        print("Info Jetson.GPIO: {}".format(gpio.JETSON_INFO))

        writable = os.access(
            "/sys/class/gpio/export",
            os.W_OK
        )

        print("Izin export GPIO: {}".format(writable))

        if not writable:
            print(
                "[PERINGATAN] Periksa izin GPIO dan konfigurasi "
                "sistem Jetson."
            )

    show_wiring(active_low)

    if failed:
        return 1

    try:
        initialize_detection_runtime()

        for name in [
            "nvarguscamerasrc",
            "nvvidconv",
            "videoconvert",
            "appsink"
        ]:
            if Gst.ElementFactory.find(name) is None:
                raise RuntimeError(
                    "Plugin GStreamer tidak tersedia: " + name
                )

        pipeline = Gst.parse_launch(
            make_camera_pipeline(CAMERA_ID)
        )

        pipeline.set_state(Gst.State.NULL)

        model_runtime = trt.Runtime(logger)

        with open(ENGINE_PATH, "rb") as stream:
            model = model_runtime.deserialize_cuda_engine(
                stream.read()
            )

        if model is None:
            raise RuntimeError(
                "Engine TensorRT gagal dimuat."
            )

        print("[OK] Pipeline kamera dan engine TensorRT tersedia.")

        return 0

    except Exception as exc:
        print(
            "[ERR] {}: {}".format(type(exc).__name__, exc)
        )

        return 1


# ============================================================
# LED TEST
# ============================================================

def test_led(args, active_low):
    global gpio_active_low

    gpio_active_low = active_low

    previous_handlers = {}

    def request_stop(signum, frame):
        raise KeyboardInterrupt()

    try:
        for signum in [signal.SIGINT, signal.SIGTERM]:
            previous_handlers[signum] = signal.signal(
                signum,
                request_stop
            )

        if not initialize_gpio():
            return 1

        print(
            "Uji LED: {}".format(
                "ACTIVE-LOW" if active_low else "ACTIVE-HIGH"
            ),
            flush=True
        )

        selected = next(
            (
                label
                for label, pin in led_pin_mapping().items()
                if pin == args.pin
            ),
            None
        )

        if args.off_only:
            sequence = [None]

        elif args.pin is not None:
            sequence = [None, selected, None]

        else:
            sequence = [
                None,
                "stop",
                "slow",
                "go",
                None
            ]

        cycle = 0

        while args.repeat == 0 or cycle < args.repeat:

            for label in sequence:

                if not set_led(label):
                    raise RuntimeError(
                        "GPIO tidak siap atau output gagal."
                    )

                levels = {
                    pin: GPIO.input(pin)
                    for pin in gpio_initialized_pins
                }

                pin_on = led_pin_mapping().get(label)

                expected = {
                    pin: (
                        gpio_on_level
                        if pin == pin_on
                        else gpio_off_level
                    )
                    for pin in gpio_initialized_pins
                }

                print(
                    "{} | GPIO {}".format(
                        label.upper() if label else "SEMUA MATI",
                        levels
                    ),
                    flush=True
                )

                if levels != expected:
                    raise RuntimeError(
                        "Level GPIO tidak sesuai: {} != {}".format(
                            levels, expected
                        )
                    )

                time.sleep(args.hold)

            cycle += 1

            if args.off_only:
                break

        print("Uji level GPIO selesai.")

        return 0

    except KeyboardInterrupt:
        print("\nUji dihentikan.")
        return 130

    except Exception as exc:
        print("[ERR] Uji LED: {}".format(exc))
        return 1

    finally:
        try:
            cleanup_gpio()

        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


# ============================================================
# GSTREAMER CAMERA
# ============================================================

def make_camera_pipeline(sensor_id):
    return (
        "nvarguscamerasrc sensor-id={} ! "
        "video/x-raw(memory:NVMM),width={},height={},"
        "framerate={}/1,format=NV12 ! "
        "nvvidconv flip-method={} ! "
        "video/x-raw,format=BGRx,width={},height={} ! "
        "videoconvert ! "
        "video/x-raw,format=BGR ! "
        "appsink name=python_sink max-buffers=1 "
        "drop=true sync=false"
    ).format(
        sensor_id,
        CAMERA_WIDTH,
        CAMERA_HEIGHT,
        CAMERA_FPS,
        CAMERA_FLIP_METHOD,
        CAMERA_WIDTH,
        CAMERA_HEIGHT
    )


def open_camera(sensor_id):
    pipeline_text = make_camera_pipeline(sensor_id)

    print("Pipeline kamera: {}".format(pipeline_text))

    pipeline = Gst.parse_launch(pipeline_text)

    sink = pipeline.get_by_name("python_sink")

    if sink is None:
        pipeline.set_state(Gst.State.NULL)

        raise RuntimeError(
            "Appsink GStreamer tidak ditemukan."
        )

    sink.set_property("emit-signals", False)

    result = pipeline.set_state(Gst.State.PLAYING)

    if result == Gst.StateChangeReturn.FAILURE:
        pipeline.set_state(Gst.State.NULL)

        raise RuntimeError(
            "GStreamer gagal menjalankan kamera."
        )

    bus = pipeline.get_bus()
    deadline = time.time() + 10.0

    while time.time() < deadline:

        msg = bus.timed_pop_filtered(
            100 * Gst.MSECOND,
            Gst.MessageType.ERROR | Gst.MessageType.WARNING
        )

        if msg is not None and msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()

            pipeline.set_state(Gst.State.NULL)

            raise RuntimeError(
                "Error kamera GStreamer: {} ({})".format(
                    err, debug
                )
            )

        sample = sink.emit(
            "try-pull-sample",
            100 * Gst.MSECOND
        )

        if sample is not None:
            return pipeline, sink, sample

    pipeline.set_state(Gst.State.NULL)
    pipeline.get_state(2 * Gst.SECOND)

    raise RuntimeError(
        "Tidak ada frame kamera dalam 10 detik. "
        "Periksa kamera CSI dan sensor-id={}.".format(sensor_id)
    )


def sample_to_bgr(sample):
    caps = sample.get_caps()
    structure = caps.get_structure(0)

    width = structure.get_value("width")
    height = structure.get_value("height")
    fmt = structure.get_value("format")

    if fmt != "BGR":
        raise RuntimeError(
            "Format frame tidak sesuai BGR: {}".format(fmt)
        )

    buffer = sample.get_buffer()

    success, mapping = buffer.map(Gst.MapFlags.READ)

    if not success:
        raise RuntimeError(
            "Gagal memetakan buffer kamera."
        )

    try:
        frame = np.frombuffer(
            mapping.data,
            dtype=np.uint8
        )

        expected = width * height * 3

        if frame.size < expected:
            raise RuntimeError(
                "Ukuran frame terlalu kecil: {} < {}".format(
                    frame.size, expected
                )
            )

        frame = frame[:expected].reshape(
            (height, width, 3)
        ).copy()

    finally:
        buffer.unmap(mapping)

    return frame


def read_frame(sink, first_sample=None):
    sample = first_sample

    if sample is None:
        sample = sink.emit(
            "try-pull-sample",
            5 * Gst.SECOND
        )

    if sample is None:
        return None

    return sample_to_bgr(sample)


# ============================================================
# CUDA RUNTIME
# ============================================================

cv2 = None
np = None
trt = None
Gst = None
cuda = None

logger = None
runtime = None
engine = None
context = None

gpu_allocations = []


def initialize_detection_runtime():
    global cv2, np, trt, Gst, cuda, logger

    cv2 = importlib.import_module("cv2")
    np = importlib.import_module("numpy")
    trt = importlib.import_module("tensorrt")

    import gi

    gi.require_version("Gst", "1.0")

    from gi.repository import Gst as gst

    Gst = gst
    Gst.init(None)

    cuda = ctypes.CDLL("libcudart.so")

    cuda.cudaMalloc.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_size_t
    ]

    cuda.cudaMalloc.restype = ctypes.c_int

    cuda.cudaFree.argtypes = [ctypes.c_void_p]
    cuda.cudaFree.restype = ctypes.c_int

    cuda.cudaMemcpy.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int
    ]

    cuda.cudaMemcpy.restype = ctypes.c_int

    logger = trt.Logger(trt.Logger.WARNING)


def check_cuda(code, operation):
    if code != 0:
        raise RuntimeError(
            "{} gagal, kode CUDA {}".format(operation, code)
        )


# ============================================================
# TENSORRT ENGINE
# ============================================================

def load_engine():
    global runtime, engine, context

    if not os.path.isfile(ENGINE_PATH):
        raise FileNotFoundError(
            "Engine tidak ditemukan: " + ENGINE_PATH
        )

    runtime = trt.Runtime(logger)

    with open(ENGINE_PATH, "rb") as model_file:
        engine = runtime.deserialize_cuda_engine(
            model_file.read()
        )

    if engine is None:
        raise RuntimeError(
            "TensorRT gagal memuat engine."
        )

    context = engine.create_execution_context()

    if context is None:
        raise RuntimeError(
            "TensorRT gagal membuat execution context."
        )

    input_index = None
    output_indices = []

    for i in range(engine.num_bindings):
        name = engine.get_binding_name(i)
        shape = tuple(engine.get_binding_shape(i))

        print(
            "Binding {}: {} {}".format(i, name, shape)
        )

        if engine.binding_is_input(i):
            input_index = i
        else:
            output_indices.append(i)

    if input_index is None or len(output_indices) != 1:
        raise RuntimeError(
            "Engine harus memiliki satu input dan satu output."
        )

    input_shape = tuple(
        context.get_binding_shape(input_index)
    )

    if input_shape != (1, 3, IMG_SIZE, IMG_SIZE):
        raise RuntimeError(
            "Bentuk input engine tidak sesuai: {}".format(
                input_shape
            )
        )

    output_index = output_indices[0]

    output_shape = tuple(
        context.get_binding_shape(output_index)
    )

    if (
        len(output_shape) != 3
        or output_shape[1] != 4 + len(CLASS_NAMES)
    ):
        raise RuntimeError(
            "Bentuk output engine tidak sesuai: {}".format(
                output_shape
            )
        )

    input_dtype = trt.nptype(
        engine.get_binding_dtype(input_index)
    )

    output_dtype = trt.nptype(
        engine.get_binding_dtype(output_index)
    )

    input_host = np.empty(
        input_shape,
        dtype=input_dtype
    )

    output_host = np.empty(
        output_shape,
        dtype=output_dtype
    )

    def allocate(nbytes):
        ptr = ctypes.c_void_p()

        check_cuda(
            cuda.cudaMalloc(
                ctypes.byref(ptr),
                nbytes
            ),
            "cudaMalloc"
        )

        gpu_allocations.append(ptr)

        return ptr

    input_gpu = allocate(input_host.nbytes)
    output_gpu = allocate(output_host.nbytes)

    bindings = [0] * engine.num_bindings

    bindings[input_index] = input_gpu.value
    bindings[output_index] = output_gpu.value

    print(
        "TensorRT siap: {} -> {}".format(
            input_shape, output_shape
        )
    )

    return (
        bindings,
        input_host,
        output_host,
        input_gpu,
        output_gpu,
        input_index,
        output_index
    )


# ============================================================
# PREPROCESS
# ============================================================

def preprocess(frame):
    h, w = frame.shape[:2]

    scale = min(
        float(IMG_SIZE) / w,
        float(IMG_SIZE) / h
    )

    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    resized = cv2.resize(
        frame,
        (new_w, new_h)
    )

    pad_x = (IMG_SIZE - new_w) / 2.0
    pad_y = (IMG_SIZE - new_h) / 2.0

    left = int(round(pad_x - 0.1))
    right = int(round(pad_x + 0.1))

    top = int(round(pad_y - 0.1))
    bottom = int(round(pad_y + 0.1))

    image = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114)
    )

    image = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB
    )

    image = image.astype(np.float32) / 255.0

    image = np.transpose(
        image,
        (2, 0, 1)
    )

    image = np.ascontiguousarray(
        image[None, ...]
    )

    return image, scale, pad_x, pad_y


# ============================================================
# YOLOV8 DETECTION AND NMS
# ============================================================

def detect(output, frame_shape, scale, pad_x, pad_y):
    h, w = frame_shape[:2]

    pred = output[0].T

    boxes_xywh = pred[:, :4]
    class_scores = pred[:, 4:]

    class_ids = np.argmax(
        class_scores,
        axis=1
    )

    scores = class_scores[
        np.arange(len(class_scores)),
        class_ids
    ]

    valid = (
        np.isfinite(scores)
        & (scores >= CONF_THRESHOLD)
        & np.all(
            np.isfinite(boxes_xywh),
            axis=1
        )
    )

    boxes_xywh = boxes_xywh[valid]
    scores = scores[valid]
    class_ids = class_ids[valid]

    if len(scores) == 0:
        return []

    detections = []

    for class_id in np.unique(class_ids):

        indices = np.where(
            class_ids == class_id
        )[0]

        boxes = []
        kept_scores = []
        kept_indices = []

        for idx in indices:

            cx, cy, bw, bh = boxes_xywh[idx]

            x1 = int(max(
                0,
                min(
                    w - 1,
                    (cx - bw / 2 - pad_x) / scale
                )
            ))

            y1 = int(max(
                0,
                min(
                    h - 1,
                    (cy - bh / 2 - pad_y) / scale
                )
            ))

            x2 = int(max(
                0,
                min(
                    w - 1,
                    (cx + bw / 2 - pad_x) / scale
                )
            ))

            y2 = int(max(
                0,
                min(
                    h - 1,
                    (cy + bh / 2 - pad_y) / scale
                )
            ))

            if x2 > x1 and y2 > y1:
                boxes.append([
                    x1,
                    y1,
                    x2 - x1,
                    y2 - y1
                ])

                kept_scores.append(
                    float(scores[idx])
                )

                kept_indices.append(idx)

        if not boxes:
            continue

        order = np.argsort(
            np.asarray(kept_scores)
        )[::-1]

        selected = []

        while order.size > 0:

            current = int(order[0])
            selected.append(current)

            if order.size == 1:
                break

            box_current = boxes[current]

            x1a = box_current[0]
            y1a = box_current[1]

            x2a = box_current[0] + box_current[2]
            y2a = box_current[1] + box_current[3]

            rest = order[1:]

            xx1 = np.maximum(
                np.asarray([
                    boxes[j][0] for j in rest
                ]),
                x1a
            )

            yy1 = np.maximum(
                np.asarray([
                    boxes[j][1] for j in rest
                ]),
                y1a
            )

            xx2 = np.minimum(
                np.asarray([
                    boxes[j][0] + boxes[j][2]
                    for j in rest
                ]),
                x2a
            )

            yy2 = np.minimum(
                np.asarray([
                    boxes[j][1] + boxes[j][3]
                    for j in rest
                ]),
                y2a
            )

            inter_w = np.maximum(
                0,
                xx2 - xx1
            )

            inter_h = np.maximum(
                0,
                yy2 - yy1
            )

            intersection = inter_w * inter_h

            area_current = (
                boxes[current][2]
                * boxes[current][3]
            )

            areas_rest = np.asarray([
                boxes[j][2] * boxes[j][3]
                for j in rest
            ])

            union = (
                area_current
                + areas_rest
                - intersection
            )

            iou = intersection / np.maximum(
                union,
                1e-9
            )

            order = rest[
                iou <= IOU_THRESHOLD
            ]

        for local_idx in selected:

            original_idx = kept_indices[local_idx]

            x, y, bw, bh = boxes[local_idx]

            detections.append((
                int(class_id),
                float(scores[original_idx]),
                (
                    x,
                    y,
                    x + bw,
                    y + bh
                )
            ))

    return detections


# ============================================================
# MAIN
# ============================================================

def main(argv=None):
    global gpio_active_low
    global runtime, engine, context

    parser = argparse.ArgumentParser(
        description="Deteksi rambu YOLOv8 dan LED Jetson Nano"
    )

    modes = parser.add_mutually_exclusive_group()

    modes.add_argument(
        "--check",
        action="store_true",
        help="Periksa library, kamera, dan model"
    )

    modes.add_argument(
        "--test-led",
        action="store_true",
        help="Uji LED tanpa kamera dan TensorRT"
    )

    modes.add_argument(
        "--wiring",
        action="store_true",
        help="Tampilkan panduan wiring LED"
    )

    polarity = parser.add_mutually_exclusive_group()

    polarity.add_argument(
        "--active-low",
        dest="active_low",
        action="store_true",
        help="LOW menyalakan LED"
    )

    polarity.add_argument(
        "--active-high",
        dest="active_low",
        action="store_false",
        help="HIGH menyalakan LED"
    )

    parser.set_defaults(
        active_low=LED_ACTIVE_LOW
    )

    parser.add_argument(
        "--pin",
        type=int,
        choices=[STOP_PIN, SLOW_PIN, GO_PIN],
        help="Pin fisik yang diuji dengan --test-led"
    )

    parser.add_argument(
        "--hold",
        type=float,
        default=2.0,
        help="Durasi setiap langkah pengujian LED"
    )

    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Jumlah siklus uji LED; 0 berarti terus berulang"
    )

    parser.add_argument(
        "--off-only",
        action="store_true",
        help="Uji dengan semua LED mati saja"
    )

    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Jalankan tanpa jendela video"
    )

    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Berhenti setelah jumlah frame tertentu"
    )

    args = parser.parse_args(argv)

    if (
        args.max_frames is not None
        and args.max_frames <= 0
    ):
        parser.error(
            "--max-frames harus lebih besar dari nol"
        )

    if (
        not math.isfinite(args.hold)
        or args.hold <= 0
        or args.repeat < 0
    ):
        parser.error(
            "--hold harus positif dan --repeat tidak boleh negatif"
        )

    if (
        (args.pin is not None or args.off_only)
        and not args.test_led
    ):
        parser.error(
            "--pin dan --off-only digunakan bersama --test-led"
        )

    print_startup_diagnostics(
        args.active_low
    )

    if args.wiring:
        show_wiring(args.active_low)
        return 0

    if args.check:
        return check_environment(
            args.active_low
        )

    if args.test_led:
        return test_led(
            args,
            args.active_low
        )

    gpio_active_low = args.active_low

    preview = (
        not args.no_preview
        and bool(os.environ.get("DISPLAY"))
    )

    frames_processed = 0

    gst_pipeline = None
    sink = None
    first_sample = None

    state = None
    candidate = None
    candidate_count = 0

    last_print = 0.0
    running = True

    def request_stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(
        signal.SIGINT,
        request_stop
    )

    signal.signal(
        signal.SIGTERM,
        request_stop
    )

    try:
        initialize_gpio()

        initialize_detection_runtime()

        (
            bindings,
            input_host,
            output_host,
            input_gpu,
            output_gpu,
            input_index,
            output_index
        ) = load_engine()

        gst_pipeline, sink, first_sample = open_camera(
            CAMERA_ID
        )

        if preview:
            cv2.namedWindow(
                "Traffic Sign Detection",
                cv2.WINDOW_NORMAL
            )

            cv2.resizeWindow(
                "Traffic Sign Detection",
                960,
                540
            )

            print(
                "Kamera aktif. Tekan q pada video atau Ctrl+C."
            )

        else:
            print(
                "Kamera aktif tanpa preview. Tekan Ctrl+C untuk berhenti."
            )

        while running:

            frame = read_frame(
                sink,
                first_sample
            )

            first_sample = None

            if frame is None:
                all_led_off()

                raise RuntimeError(
                    "Frame kamera gagal dibaca."
                )

            tensor, scale, pad_x, pad_y = preprocess(
                frame
            )

            np.copyto(
                input_host,
                tensor
            )

            check_cuda(
                cuda.cudaMemcpy(
                    input_gpu,
                    input_host.ctypes.data_as(
                        ctypes.c_void_p
                    ),
                    input_host.nbytes,
                    HOST_TO_DEVICE
                ),
                "Salin input ke GPU"
            )

            if not context.execute_v2(bindings):
                raise RuntimeError(
                    "Inferensi TensorRT gagal."
                )

            check_cuda(
                cuda.cudaMemcpy(
                    output_host.ctypes.data_as(
                        ctypes.c_void_p
                    ),
                    output_gpu,
                    output_host.nbytes,
                    DEVICE_TO_HOST
                ),
                "Salin output ke RAM"
            )

            detections = detect(
                output_host,
                frame.shape,
                scale,
                pad_x,
                pad_y
            )

            # Gambar kotak pada objek yang terdeteksi.
            for det_class_id, det_score, det_box in detections:

                x1, y1, x2, y2 = det_box

                det_name = (
                    CLASS_NAMES[det_class_id].upper()
                    if 0 <= det_class_id < len(CLASS_NAMES)
                    else "UNKNOWN"
                )

                color = {
                    "STOP": (0, 0, 255),
                    "SLOW": (0, 255, 255),
                    "GO": (0, 255, 0)
                }.get(
                    det_name,
                    (255, 255, 255)
                )

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    color,
                    2
                )

                caption = "{} {:.0f}%".format(
                    det_name,
                    det_score * 100
                )

                cv2.putText(
                    frame,
                    caption,
                    (x1, max(24, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    color,
                    2,
                    cv2.LINE_AA
                )

            # Pilih deteksi dengan confidence tertinggi.
            best = (
                max(detections, key=lambda d: d[1])
                if detections
                else None
            )

            label = None
            score = 0.0

            if best is not None:

                class_id, score, box = best

                if (
                    0 <= class_id < len(CLASS_NAMES)
                    and np.isfinite(score)
                    and score >= CONF_THRESHOLD
                ):
                    label = CLASS_NAMES[class_id]

                    if label not in (
                        "go",
                        "slow",
                        "stop"
                    ):
                        label = None

            # Menunggu deteksi stabil.
            if label is not None and label == candidate:
                candidate_count += 1

            else:
                candidate = label
                candidate_count = (
                    1 if label is not None else 0
                )

            if label is None:

                state = None
                candidate = None
                candidate_count = 0

                # Tidak ada rambu: semua LED mati.
                all_led_off()

            elif candidate_count >= STABLE_FRAMES:

                if state != candidate:

                    if set_led(candidate):
                        state = candidate

                    else:
                        state = None
                        all_led_off()

            else:

                # Matikan LED selama deteksi belum stabil.
                state = None
                all_led_off()

            # Cetak status.
            now = time.time()

            if now - last_print >= 0.25:

                led_status = (
                    "TIDAK AKTIF"
                    if not gpio_ready
                    else state.upper()
                    if state
                    else "MATI"
                )

                if label is None:

                    message = (
                        "STATUS: TIDAK TERDETEKSI | LED: {}".format(
                            led_status
                        )
                    )

                else:

                    message = (
                        "STATUS: {} ({:.0f}%) | STABIL: {}/{} "
                        "| LED: {}".format(
                            label.upper(),
                            score * 100,
                            min(
                                candidate_count,
                                STABLE_FRAMES
                            ),
                            STABLE_FRAMES,
                            led_status
                        )
                    )

                print(
                    "\r" + message + " " * 12,
                    end="",
                    flush=True
                )

                last_print = now

            overlay = (
                "TIDAK TERDETEKSI"
                if label is None
                else "{} {:.0f}%".format(
                    label.upper(),
                    score * 100
                )
            )

            cv2.putText(
                frame,
                overlay,
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            if preview:

                cv2.imshow(
                    "Traffic Sign Detection",
                    frame
                )

                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    running = False

            frames_processed += 1

            if (
                args.max_frames is not None
                and frames_processed >= args.max_frames
            ):
                running = False

    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna.")

    except Exception as exc:

        print(
            "\n[ERR] {}: {}".format(
                type(exc).__name__,
                exc
            )
        )

        return 1

    finally:

        print("\nMenghentikan program dan mematikan LED...")

        # Perintahkan semua LED mati sebelum menghentikan kamera.
        all_led_off()

        if gst_pipeline is not None:

            try:
                gst_pipeline.set_state(
                    Gst.State.NULL
                )

                gst_pipeline.get_state(
                    2 * Gst.SECOND
                )

            except Exception as exc:

                print(
                    "[ERR] Penghentian kamera: {}".format(
                        exc
                    )
                )

        if preview and cv2 is not None:

            try:
                cv2.destroyAllWindows()

            except Exception:
                pass

        if cuda is not None:

            for ptr in gpu_allocations:

                try:
                    check_cuda(
                        cuda.cudaFree(ptr),
                        "cudaFree"
                    )

                except Exception as exc:

                    print(
                        "[ERR] Pelepasan memori GPU: {}".format(
                            exc
                        )
                    )

        gpu_allocations[:] = []

        context = None
        engine = None
        runtime = None

        gpio_cleanup_ok = cleanup_gpio()

        print(
            "\nProgram berhenti. {} frame diproses. "
            "Perintah LED mati: {}.".format(
                frames_processed,
                "berhasil" if gpio_cleanup_ok else "perlu diperiksa"
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
