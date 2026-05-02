import os
import time
from datetime import datetime

import cv2
import numpy as np
import pandas as pd
import requests
import streamlit as st
import tensorflow as tf
from picamera2 import Picamera2
import RPi.GPIO as GPIO

st.set_page_config(page_title="DRBK GUI", layout="wide")

SENSORS = {
    "Left": {"TRIG": 23, "ECHO": 24},
    "Front": {"TRIG": 5, "ECHO": 6},
    "Right": {"TRIG": 13, "ECHO": 19},
    "Behind": {"TRIG": 16, "ECHO": 26},
}

BUZZER = 18
MOTOR = 17
EMERGENCY_BUTTON = 22

TELEGRAM_BOT_TOKEN = "8674601062:AAFGR5PCZfCvSaLgAMS578FogdL4SYB7jH4"
TELEGRAM_CHAT_ID = "1924995044"

telegram_session = requests.Session()

DEFAULTS = {
    "system_running": False,
    "gpio_ready": False,
    "realtime_mode": False,
    "voice_enabled": True,
    "buzzer_enabled": True,
    "vibration_enabled": True,
    "danger_distance": 30,
    "caution_distance": 70,
    "confidence_threshold": 0.45,
    "refresh_interval": 0.20,
    "last_object": "None",
    "last_confidence": 0.0,
    "last_distance": -1.0,
    "closest_sensor": "None",
    "camera_status": "Not started",
    "ultrasonic_status": "Not started",
    "alert_history": [],
    "last_frame_path": "latest_frame.jpg",
    "last_output_path": "latest_output.jpg",
    "last_spoken_object": None,
    "last_speak_time": 0.0,
    "speech_cooldown": 4.0,
    "last_cycle_time": 0.0,
    "sensor_distances": {
        "Left": -1.0,
        "Front": -1.0,
        "Right": -1.0,
        "Behind": -1.0,
    },
    "emergency_status": "Idle",
    "last_emergency_time": 0.0,
    "emergency_cooldown": 2.0,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


@st.cache_resource
def load_labels():
    with open("labelmap.txt", "r") as f:
        labels = [line.strip() for line in f.readlines()]
    return [x for x in labels if x]


@st.cache_resource
def load_model():
    interpreter = tf.lite.Interpreter(model_path="detect.tflite", num_threads=4)
    interpreter.allocate_tensors()
    return interpreter


@st.cache_resource
def init_camera():
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (320, 240), "format": "RGB888"},
        buffer_count=1,
        queue=False,
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.20)
    return picam2


def setup_gpio():
    try:
        GPIO.setwarnings(False)
        try:
            GPIO.cleanup()
        except Exception:
            pass

        GPIO.setmode(GPIO.BCM)

        for pins in SENSORS.values():
            GPIO.setup(pins["TRIG"], GPIO.OUT)
            GPIO.setup(pins["ECHO"], GPIO.IN)
            GPIO.output(pins["TRIG"], False)

        GPIO.setup(BUZZER, GPIO.OUT)
        GPIO.setup(MOTOR, GPIO.OUT)
        GPIO.setup(EMERGENCY_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.output(BUZZER, GPIO.LOW)
        GPIO.output(MOTOR, GPIO.LOW)

        time.sleep(0.05)

        st.session_state.gpio_ready = True
        st.session_state.ultrasonic_status = "Ready"
        st.session_state.emergency_status = "Ready"
        return True
    except Exception as e:
        st.session_state.gpio_ready = False
        st.session_state.ultrasonic_status = f"GPIO error: {e}"
        st.session_state.emergency_status = f"GPIO error: {e}"
        return False


def stop_gpio():
    try:
        GPIO.output(BUZZER, GPIO.LOW)
        GPIO.output(MOTOR, GPIO.LOW)
    except Exception:
        pass

    try:
        GPIO.cleanup()
    except Exception:
        pass

    st.session_state.gpio_ready = False
    st.session_state.ultrasonic_status = "Stopped"
    st.session_state.emergency_status = "Stopped"


def cleanup_outputs():
    try:
        GPIO.output(BUZZER, GPIO.LOW)
        GPIO.output(MOTOR, GPIO.LOW)
    except Exception:
        pass


def send_telegram_message(message_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text}

    last_error = "Unknown error"

    for _ in range(3):
        try:
            response = telegram_session.post(url, data=data, timeout=(3, 8))
            result = response.json()

            if result.get("ok"):
                st.session_state.emergency_status = "Emergency message sent"
                return True

            last_error = result.get("description", "Telegram API error")
        except Exception as e:
            last_error = str(e)

        time.sleep(0.3)

    st.session_state.emergency_status = f"Telegram send error: {last_error}"
    return False


def trigger_emergency_alert():
    now = time.time()

    if now - st.session_state.last_emergency_time < st.session_state.emergency_cooldown:
        return False

    distance_text = (
        f"{st.session_state.last_distance:.1f} cm"
        if st.session_state.last_distance >= 0
        else "No reading"
    )

    message = (
        "EMERGENCY ALERT from DRBK.\n"
        "The emergency button was pressed.\n"
        f"Closest sensor: {st.session_state.closest_sensor}\n"
        f"Closest distance: {distance_text}\n"
        f"Last object: {st.session_state.last_object}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    success = send_telegram_message(message)

    if success:
        st.session_state.last_emergency_time = now
        st.session_state.alert_history.insert(
            0,
            {
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Closest Sensor": st.session_state.closest_sensor,
                "Object": st.session_state.last_object,
                "Confidence": round(st.session_state.last_confidence, 2),
                "Distance (cm)": round(st.session_state.last_distance, 1) if st.session_state.last_distance >= 0 else "No reading",
                "Left (cm)": round(st.session_state.sensor_distances["Left"], 1) if st.session_state.sensor_distances["Left"] >= 0 else "No reading",
                "Front (cm)": round(st.session_state.sensor_distances["Front"], 1) if st.session_state.sensor_distances["Front"] >= 0 else "No reading",
                "Right (cm)": round(st.session_state.sensor_distances["Right"], 1) if st.session_state.sensor_distances["Right"] >= 0 else "No reading",
                "Behind (cm)": round(st.session_state.sensor_distances["Behind"], 1) if st.session_state.sensor_distances["Behind"] >= 0 else "No reading",
                "Alert": "EMERGENCY BUTTON PRESSED - TELEGRAM SENT",
            },
        )
        st.session_state.alert_history = st.session_state.alert_history[:50]

    return success


def check_emergency_button():
    if not st.session_state.gpio_ready:
        return

    try:
        if GPIO.input(EMERGENCY_BUTTON) == GPIO.LOW:
            time.sleep(0.03)
            if GPIO.input(EMERGENCY_BUTTON) == GPIO.LOW:
                trigger_emergency_alert()
                while GPIO.input(EMERGENCY_BUTTON) == GPIO.LOW:
                    time.sleep(0.02)
    except Exception:
        pass


def get_warning_level(distance_cm: float) -> str:
    if distance_cm < 0:
        return "unknown"
    if distance_cm <= st.session_state.danger_distance:
        return "danger"
    if distance_cm <= st.session_state.caution_distance:
        return "caution"
    return "safe"


def get_alert_text(distance_cm: float, obj: str, sensor_name: str) -> str:
    level = get_warning_level(distance_cm)

    if level == "unknown":
        if obj != "none":
            return f"OBJECT DETECTED: {obj}"
        return "NO DISTANCE READING"

    if level == "danger":
        if sensor_name == "Front":
            if obj != "none":
                return f"DANGER: {obj} detected in front at {int(distance_cm)} cm"
            return f"DANGER: Obstacle in front at {int(distance_cm)} cm"
        return f"DANGER: Obstacle on {sensor_name.lower()} side at {int(distance_cm)} cm"

    if level == "caution":
        if sensor_name == "Front":
            if obj != "none":
                return f"CAUTION: {obj} ahead at {int(distance_cm)} cm"
            return f"CAUTION: Object ahead at {int(distance_cm)} cm"
        return f"CAUTION: Object on {sensor_name.lower()} side at {int(distance_cm)} cm"

    return "PATH CLEAR"


def log_event(obj: str, conf: float, distance_cm: float, sensor_name: str, alert_text: str):
    st.session_state.alert_history.insert(
        0,
        {
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Closest Sensor": sensor_name,
            "Object": obj,
            "Confidence": round(conf, 2),
            "Distance (cm)": round(distance_cm, 1) if distance_cm >= 0 else "No reading",
            "Left (cm)": round(st.session_state.sensor_distances["Left"], 1) if st.session_state.sensor_distances["Left"] >= 0 else "No reading",
            "Front (cm)": round(st.session_state.sensor_distances["Front"], 1) if st.session_state.sensor_distances["Front"] >= 0 else "No reading",
            "Right (cm)": round(st.session_state.sensor_distances["Right"], 1) if st.session_state.sensor_distances["Right"] >= 0 else "No reading",
            "Behind (cm)": round(st.session_state.sensor_distances["Behind"], 1) if st.session_state.sensor_distances["Behind"] >= 0 else "No reading",
            "Alert": alert_text,
        },
    )
    st.session_state.alert_history = st.session_state.alert_history[:50]


def measure_distance_once(trig_pin, echo_pin):
    try:
        GPIO.output(trig_pin, False)
        time.sleep(0.0001)

        GPIO.output(trig_pin, True)
        time.sleep(0.00001)
        GPIO.output(trig_pin, False)

        pulse_start = None
        pulse_end = None

        start_time = time.time()
        while GPIO.input(echo_pin) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.015:
                return None

        start_time = time.time()
        while GPIO.input(echo_pin) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.015:
                return None

        if pulse_start is None or pulse_end is None:
            return None

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150

        if distance < 2 or distance > 400:
            return None

        return round(distance, 2)
    except Exception:
        return None


def measure_distance(trig_pin, echo_pin, samples=1):
    readings = []

    for _ in range(samples):
        d = measure_distance_once(trig_pin, echo_pin)
        if d is not None:
            readings.append(d)
        time.sleep(0.002)

    if not readings:
        return None

    return round(sum(readings) / len(readings), 2)


def measure_all_sensors():
    if not st.session_state.gpio_ready:
        return None, "None", {
            "Left": -1.0,
            "Front": -1.0,
            "Right": -1.0,
            "Behind": -1.0,
        }

    distances = {}

    for sensor_name, pins in SENSORS.items():
        distance = measure_distance(pins["TRIG"], pins["ECHO"], samples=1)
        distances[sensor_name] = distance if distance is not None else -1.0
        time.sleep(0.003)

    st.session_state.sensor_distances = distances.copy()

    valid = {k: v for k, v in distances.items() if v >= 0}
    if not valid:
        st.session_state.last_distance = -1.0
        st.session_state.closest_sensor = "None"
        st.session_state.ultrasonic_status = "No reading"
        return None, "None", distances

    closest_sensor = min(valid, key=valid.get)
    closest_distance = valid[closest_sensor]

    st.session_state.last_distance = closest_distance
    st.session_state.closest_sensor = closest_sensor
    st.session_state.ultrasonic_status = "Live"

    return closest_distance, closest_sensor, distances


def set_alert_outputs(sensor_distances):
    try:
        valid_distances = [d for d in sensor_distances.values() if d >= 0]

        if not valid_distances:
            GPIO.output(BUZZER, GPIO.LOW)
            GPIO.output(MOTOR, GPIO.LOW)
            return

        nearest_distance = min(valid_distances)

        danger_active = nearest_distance <= st.session_state.danger_distance
        caution_active = (
            nearest_distance > st.session_state.danger_distance
            and nearest_distance <= st.session_state.caution_distance
        )

        buzzer_on = False
        motor_on = False

        if danger_active:
            if st.session_state.buzzer_enabled:
                buzzer_on = True
            if st.session_state.vibration_enabled:
                motor_on = True

        GPIO.output(BUZZER, GPIO.HIGH if buzzer_on else GPIO.LOW)
        GPIO.output(MOTOR, GPIO.HIGH if motor_on else GPIO.LOW)
    except Exception:
        pass


def speak_message(message: str, label: str):
    if not st.session_state.voice_enabled:
        return

    now = time.time()

    if (
        label != st.session_state.last_spoken_object
        or (now - st.session_state.last_speak_time) > st.session_state.speech_cooldown
    ):
        os.system(f'espeak "{message}"')
        st.session_state.last_spoken_object = label
        st.session_state.last_speak_time = now


def capture_frame():
    try:
        picam2 = init_camera()
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        st.session_state.camera_status = "Live"
        return frame_bgr
    except Exception as e:
        st.session_state.camera_status = f"Camera error: {e}"
        return None


def detect_best_object(frame_bgr):
    labels = load_labels()
    interpreter = load_model()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    image = frame_bgr.copy()
    orig_h, orig_w, _ = image.shape

    input_h = input_details[0]["shape"][1]
    input_w = input_details[0]["shape"][2]

    image_resized = cv2.resize(image, (input_w, input_h))
    input_data = np.expand_dims(image_resized, axis=0)

    if input_details[0]["dtype"] == np.float32:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]["index"], input_data)
    interpreter.invoke()

    boxes = interpreter.get_tensor(output_details[0]["index"])[0]
    classes = interpreter.get_tensor(output_details[1]["index"])[0]
    scores = interpreter.get_tensor(output_details[2]["index"])[0]
    count = int(interpreter.get_tensor(output_details[3]["index"])[0])

    best_label = "No confident object"
    best_score = 0.0
    best_box = None

    for i in range(count):
        score = float(scores[i])
        if score < st.session_state.confidence_threshold:
            continue

        class_id = int(classes[i])

        if 0 <= class_id + 1 < len(labels):
            label = labels[class_id + 1]
        elif 0 <= class_id < len(labels):
            label = labels[class_id]
        else:
            label = f"id_{class_id}"

        ymin, xmin, ymax, xmax = boxes[i]

        left = max(0, int(xmin * orig_w))
        right = min(orig_w, int(xmax * orig_w))
        top = max(0, int(ymin * orig_h))
        bottom = min(orig_h, int(ymax * orig_h))

        if score > best_score:
            best_score = score
            best_label = label
            best_box = (left, top, right, bottom)

    output = image.copy()

    if best_box is not None:
        left, top, right, bottom = best_box
        cv2.rectangle(output, (left, top), (right, bottom), (0, 255, 0), 2)
        text = f"{best_label}: {best_score:.2f}"
        cv2.putText(
            output,
            text,
            (left, max(18, top - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
        )

    distance_text = (
        f"Closest: {st.session_state.closest_sensor} {st.session_state.last_distance:.1f} cm"
        if st.session_state.last_distance >= 0
        else "Closest: No reading"
    )

    cv2.putText(
        output,
        distance_text,
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 0, 0),
        1,
    )

    cv2.imwrite(st.session_state.last_output_path, output)
    return best_label, best_score, output


def build_voice_message(obj, distance, sensor_name):
    object_detected = obj != "No confident object"

    if sensor_name == "Front":
        if object_detected:
            if distance is None:
                return f"There is a {obj} in front"
            return f"There is a {obj} in front at {int(distance)} centimeters"
        if distance is not None:
            return f"Obstacle in front at {int(distance)} centimeters"
        return "Obstacle detected in front"

    if sensor_name == "Left":
        if object_detected:
            if distance is None:
                return f"There is a {obj} on the left"
            return f"There is a {obj} on the left at {int(distance)} centimeters"
        if distance is not None:
            return f"Obstacle on the left at {int(distance)} centimeters"
        return "Obstacle on the left"

    if sensor_name == "Right":
        if object_detected:
            if distance is None:
                return f"There is a {obj} on the right"
            return f"There is a {obj} on the right at {int(distance)} centimeters"
        if distance is not None:
            return f"Obstacle on the right at {int(distance)} centimeters"
        return "Obstacle on the right"

    if sensor_name == "Behind":
        if object_detected:
            if distance is None:
                return f"There is a {obj} behind you"
            return f"There is a {obj} behind you at {int(distance)} centimeters"
        if distance is not None:
            return f"Obstacle behind at {int(distance)} centimeters"
        return "Obstacle behind"

    return "Obstacle detected"


def run_system_cycle():
    if not st.session_state.system_running or not st.session_state.gpio_ready:
        return "System not running"

    check_emergency_button()

    frame = capture_frame()
    closest_distance, closest_sensor, all_distances = measure_all_sensors()

    set_alert_outputs(all_distances)

    if frame is None:
        st.session_state.last_object = "Camera error"
        st.session_state.last_confidence = 0.0
        alert_text = get_alert_text(
            st.session_state.last_distance,
            "none",
            st.session_state.closest_sensor,
        )
        log_event(
            "Camera error",
            0.0,
            st.session_state.last_distance,
            st.session_state.closest_sensor,
            alert_text,
        )
        return alert_text

    obj, conf, _ = detect_best_object(frame)

    st.session_state.last_object = obj
    st.session_state.last_confidence = conf

    obj_for_alert = obj.lower() if (
        obj != "No confident object" and closest_sensor == "Front"
    ) else "none"

    alert_text = get_alert_text(
        st.session_state.last_distance,
        obj_for_alert,
        st.session_state.closest_sensor,
    )

    log_event(
        obj,
        conf,
        st.session_state.last_distance,
        st.session_state.closest_sensor,
        alert_text,
    )

    if closest_distance is not None and closest_distance <= st.session_state.caution_distance:
        message = build_voice_message(obj, closest_distance, closest_sensor)
        speak_message(message, f"{closest_sensor}_{obj}")

    st.session_state.last_cycle_time = time.time()
    return alert_text


def test_buzzer():
    try:
        if not st.session_state.buzzer_enabled:
            return False, "Buzzer is disabled in settings"

        GPIO.output(BUZZER, GPIO.HIGH)
        time.sleep(0.15)
        GPIO.output(BUZZER, GPIO.LOW)
        return True, "Buzzer test triggered"
    except Exception as e:
        return False, f"Buzzer error: {e}"


def test_vibration():
    try:
        if not st.session_state.vibration_enabled:
            return False, "Vibration is disabled in settings"

        GPIO.output(MOTOR, GPIO.HIGH)
        time.sleep(0.15)
        GPIO.output(MOTOR, GPIO.LOW)
        return True, "Vibration test triggered"
    except Exception as e:
        return False, f"Vibration error: {e}"


def test_camera():
    frame = capture_frame()
    if frame is None:
        return False, "Camera check failed"
    cv2.imwrite(st.session_state.last_frame_path, frame)
    return True, "Camera check passed"


def test_one_sensor(sensor_name):
    pins = SENSORS[sensor_name]
    distance = measure_distance(pins["TRIG"], pins["ECHO"], samples=1)
    if distance is None:
        st.session_state.sensor_distances[sensor_name] = -1.0
        return False, f"{sensor_name} sensor: No reading"
    st.session_state.sensor_distances[sensor_name] = distance
    return True, f"{sensor_name} sensor reading: {distance:.1f} cm"


st.sidebar.title("DRBK")
st.sidebar.markdown("Control panel")

col_a, col_b = st.sidebar.columns(2)

with col_a:
    if st.button("Start System", use_container_width=True, key="start_system_btn"):
        ok = setup_gpio()
        if ok:
            st.session_state.system_running = True
            st.session_state.realtime_mode = False
            try:
                init_camera()
                st.session_state.camera_status = "Ready"
            except Exception as e:
                st.session_state.camera_status = f"Camera init error: {e}"
            st.rerun()
        else:
            st.session_state.system_running = False

with col_b:
    if st.button("Stop System", use_container_width=True, key="stop_system_btn"):
        st.session_state.system_running = False
        st.session_state.realtime_mode = False
        cleanup_outputs()
        stop_gpio()
        st.rerun()

st.sidebar.divider()

if st.sidebar.button("Send Emergency Alert", use_container_width=True):
    if st.session_state.system_running:
        if trigger_emergency_alert():
            st.sidebar.success("Emergency message sent")
        else:
            st.sidebar.warning(st.session_state.emergency_status)
    else:
        st.sidebar.warning("Start the system first.")

st.sidebar.subheader("Current Status")
st.sidebar.write(f"System: {'Running' if st.session_state.system_running else 'Stopped'}")
st.sidebar.write(f"Camera: {st.session_state.camera_status}")
st.sidebar.write(f"Ultrasonic: {st.session_state.ultrasonic_status}")
st.sidebar.write(f"Last Object: {st.session_state.last_object}")
st.sidebar.write(f"Closest Sensor: {st.session_state.closest_sensor}")
st.sidebar.write(f"Emergency: {st.session_state.emergency_status}")

if st.session_state.last_distance >= 0:
    st.sidebar.write(f"Closest Distance: {st.session_state.last_distance:.1f} cm")
else:
    st.sidebar.write("Closest Distance: No reading")

st.sidebar.divider()

st.sidebar.subheader("All Sensor Readings")
for sensor_name in ["Left", "Front", "Right", "Behind"]:
    value = st.session_state.sensor_distances[sensor_name]
    if value >= 0:
        st.sidebar.write(f"{sensor_name}: {value:.1f} cm")
    else:
        st.sidebar.write(f"{sensor_name}: No reading")

st.sidebar.divider()

st.sidebar.subheader("Real-Time Refresh")
st.session_state.refresh_interval = st.sidebar.slider(
    "Refresh interval (seconds)",
    min_value=0.10,
    max_value=1.00,
    value=float(st.session_state.refresh_interval),
    step=0.05,
)

st.title("DRBK Monitoring Dashboard")

current_alert = get_alert_text(
    st.session_state.last_distance,
    st.session_state.last_object.lower() if (
        st.session_state.last_object != "No confident object"
        and st.session_state.closest_sensor == "Front"
    ) else "none",
    st.session_state.closest_sensor,
)

current_level = get_warning_level(st.session_state.last_distance)

if current_level == "danger":
    st.error(current_alert)
elif current_level == "caution":
    st.warning(current_alert)
elif current_level == "safe":
    st.success(current_alert)
else:
    st.info(current_alert)

tab1, tab2, tab3, tab4 = st.tabs(
    ["Dashboard", "Live Detection", "Sensor Test", "Settings"]
)

with tab1:
    st.subheader("System Overview")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("System", "Running" if st.session_state.system_running else "Stopped")
    c2.metric(
        "Closest Distance",
        "No reading" if st.session_state.last_distance < 0 else f"{st.session_state.last_distance:.1f} cm",
    )
    c3.metric("Closest Sensor", st.session_state.closest_sensor)
    c4.metric("Object", st.session_state.last_object)

    st.markdown("### Sensor Distances")
    s1, s2, s3, s4 = st.columns(4)
    for col, sensor_name in zip([s1, s2, s3, s4], ["Left", "Front", "Right", "Behind"]):
        value = st.session_state.sensor_distances[sensor_name]
        col.metric(sensor_name, "No reading" if value < 0 else f"{value:.1f} cm")

    st.markdown("### Detection Status")
    d1, d2, d3 = st.columns(3)
    d1.info(f"Camera: {st.session_state.camera_status}")
    d2.info(f"Ultrasonic: {st.session_state.ultrasonic_status}")
    d3.info(
        f"Buzzer: {'Enabled' if st.session_state.buzzer_enabled else 'Disabled'} | "
        f"Vibration: {'Enabled' if st.session_state.vibration_enabled else 'Disabled'}"
    )

    st.markdown("### Emergency Status")
    st.info(st.session_state.emergency_status)

    st.markdown("### Recent Alerts")
    if st.session_state.alert_history:
        history_df = pd.DataFrame(st.session_state.alert_history[:10])
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("No alerts recorded yet.")

with tab2:
    st.subheader("Live Detection")

    top_left, top_right = st.columns([2, 1])

    with top_left:
        st.markdown("### Camera View")
        if os.path.exists(st.session_state.last_output_path):
            st.image(st.session_state.last_output_path, channels="BGR", use_container_width=True)
        elif os.path.exists(st.session_state.last_frame_path):
            st.image(st.session_state.last_frame_path, channels="BGR", use_container_width=True)
        else:
            st.info("Start the system first.")

    with top_right:
        st.markdown("### Detection Results")
        st.write(f"Detected Object: {st.session_state.last_object}")
        st.write(f"Confidence: {st.session_state.last_confidence:.2f}")
        st.write(f"Closest Sensor: {st.session_state.closest_sensor}")

        if st.session_state.last_distance >= 0:
            st.write(f"Closest Distance: {st.session_state.last_distance:.1f} cm")
        else:
            st.write("Closest Distance: No reading")

        st.write(f"Warning Level: {current_level.upper()}")

        st.markdown("### Sensor Readings")
        for sensor_name in ["Left", "Front", "Right", "Behind"]:
            value = st.session_state.sensor_distances[sensor_name]
            if value >= 0:
                st.write(f"{sensor_name}: {value:.1f} cm")
            else:
                st.write(f"{sensor_name}: No reading")

        col_run, col_pause = st.columns(2)

        with col_run:
            if st.button("Run Real Time", use_container_width=True):
                if st.session_state.system_running:
                    st.session_state.realtime_mode = True
                    st.rerun()
                else:
                    st.warning("Start the system first.")

        with col_pause:
            if st.button("Pause Real Time", use_container_width=True):
                st.session_state.realtime_mode = False
                cleanup_outputs()
                st.rerun()

        if st.button("Single Refresh", use_container_width=True):
            if st.session_state.system_running:
                run_system_cycle()
                st.rerun()
            else:
                st.warning("Start the system first.")

        st.markdown("### Voice Output")
        st.code(current_alert)

        st.markdown("### Real-Time Mode")
        st.write(f"Status: {'ON' if st.session_state.realtime_mode else 'OFF'}")
        st.write(f"Refresh interval: {st.session_state.refresh_interval:.2f} sec")

with tab3:
    st.subheader("Hardware Test")

    st.markdown("### Ultrasonic Sensor Tests")
    u1, u2, u3, u4 = st.columns(4)

    with u1:
        if st.button("Test Left Sensor", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_one_sensor("Left")
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    with u2:
        if st.button("Test Front Sensor", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_one_sensor("Front")
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    with u3:
        if st.button("Test Right Sensor", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_one_sensor("Right")
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    with u4:
        if st.button("Test Behind Sensor", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_one_sensor("Behind")
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    st.markdown("### Output Device Tests")
    s1, s2, s3 = st.columns(3)

    with s1:
        if st.button("Test Buzzer", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_buzzer()
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    with s2:
        if st.button("Test Vibration", use_container_width=True):
            if st.session_state.system_running:
                ok, msg = test_vibration()
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
            else:
                st.warning("Start the system first.")

    with s3:
        if st.button("Test Emergency Alert", use_container_width=True):
            if st.session_state.system_running:
                if trigger_emergency_alert():
                    st.success("Emergency message sent")
                else:
                    st.warning(st.session_state.emergency_status)
            else:
                st.warning("Start the system first.")

    st.markdown("### Camera Test")
    if st.button("Test Camera", use_container_width=False):
        if st.session_state.system_running:
            ok, msg = test_camera()
            if ok:
                st.success(msg)
                if os.path.exists(st.session_state.last_frame_path):
                    st.image(st.session_state.last_frame_path, channels="BGR", width=320)
            else:
                st.error(msg)
        else:
            st.warning("Start the system first.")

with tab4:
    st.subheader("System Settings")

    st.session_state.voice_enabled = st.checkbox(
        "Enable Voice Alerts",
        value=st.session_state.voice_enabled,
    )

    st.session_state.buzzer_enabled = st.checkbox(
        "Enable Buzzer",
        value=st.session_state.buzzer_enabled,
    )

    st.session_state.vibration_enabled = st.checkbox(
        "Enable Vibration",
        value=st.session_state.vibration_enabled,
    )

    st.session_state.danger_distance = st.slider(
        "Danger Distance (cm)",
        min_value=10,
        max_value=150,
        value=st.session_state.danger_distance,
        step=5,
    )

    st.session_state.caution_distance = st.slider(
        "Caution Distance (cm)",
        min_value=20,
        max_value=250,
        value=st.session_state.caution_distance,
        step=5,
    )

    st.session_state.confidence_threshold = st.slider(
        "Detection Confidence Threshold",
        min_value=0.0,
        max_value=1.0,
        value=st.session_state.confidence_threshold,
        step=0.05,
    )

    st.session_state.speech_cooldown = st.slider(
        "Speech Cooldown (seconds)",
        min_value=1.0,
        max_value=10.0,
        value=float(st.session_state.speech_cooldown),
        step=0.5,
    )



    st.markdown("### Current Settings")
    st.write(f"Voice Alerts: {'Enabled' if st.session_state.voice_enabled else 'Disabled'}")
    st.write(f"Buzzer: {'Enabled' if st.session_state.buzzer_enabled else 'Disabled'}")
    st.write(f"Vibration: {'Enabled' if st.session_state.vibration_enabled else 'Disabled'}")
    st.write(f"Danger Distance: {st.session_state.danger_distance} cm")
    st.write(f"Caution Distance: {st.session_state.caution_distance} cm")
    st.write(f"Confidence Threshold: {st.session_state.confidence_threshold:.2f}")
    st.write(f"Speech Cooldown: {st.session_state.speech_cooldown:.1f} sec")
    st.write(f"Refresh Interval: {st.session_state.refresh_interval:.2f} sec")

st.divider()

if st.session_state.system_running and st.session_state.realtime_mode:
    run_system_cycle()
    time.sleep(st.session_state.refresh_interval)
    st.rerun()
