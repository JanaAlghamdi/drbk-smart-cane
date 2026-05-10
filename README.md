# drbk-smart-cane
# DRBK Smart Cane System 🦯🧠

An AI-powered smart cane system designed to assist visually impaired individuals using real-time object detection and distance sensing.

---

## Project Overview

The DRBK Smart Cane is an embedded AI system built using a Raspberry Pi.  
It combines ultrasonic sensors and a camera module to detect obstacles and provide real-time feedback through sound and vibration.

The system helps users navigate safely by identifying nearby objects and classifying risk levels (Safe, Caution, Danger).

---

## System Architecture

<img width="352" height="813" alt="image" src="https://github.com/user-attachments/assets/be5ea8f6-6f1b-4b54-8b48-a127962a222d" />


The system follows a pipeline architecture:

Sensor Reading + Image Capture 
→ Object Detection (MobileNet) 
→ Distance Analysis 
→ Warning Classification 
→ Feedback Generation 
→ GUI Update

---

## Main Features

- Real-time object detection using MobileNet (OpenCV DNN)
- Distance measurement using ultrasonic sensors
- Audio feedback (voice alerts)
- Vibration feedback for critical warnings
- Emergency alert via Telegram Bot
- GUI dashboard using Streamlit

---

## Hardware Components

<img width="546" height="290" alt="image" src="https://github.com/user-attachments/assets/5a21cb68-c8d4-47c4-b011-83d1b2253138" />

<img width="319" height="319" alt="image" src="https://github.com/user-attachments/assets/713de24f-31d1-4553-9b4d-1f2ce2839857" />

- Raspberry Pi 4 Model B  
- Raspberry Pi Camera (OV5647)  
- Ultrasonic Sensors (HC-SR04)  
- Buzzer  
- Vibration Motor  
- Power Bank  

---

## GUI Interface

<img width="975" height="455" alt="image" src="https://github.com/user-attachments/assets/411ae6c2-421a-489b-8b9e-6a90aa36d3e8" />


The system includes a GUI built with Streamlit to display:
- Detected objects  
- Distance readings  
- System status  
- Alerts  

---

## Object Detection Example

<img width="975" height="452" alt="image" src="https://github.com/user-attachments/assets/2d548663-1fff-409a-ac33-85680d276339" />

Example of real-time object detection using the camera module.

---

## Software and Tools

- Python 3  
- OpenCV  
- TensorFlow Lite  
- Streamlit  
- Picamera2  
- Telegram API  

---

## How It Works

1. Ultrasonic sensors measure distance  
2. Camera captures frames  
3. AI model detects objects  
4. System identifies closest obstacle  
5. Risk level is classified (Safe / Caution / Danger)  
6. Feedback is generated (voice, vibration, buzzer)  
7. GUI updates in real-time  

---


## How to Run

Install dependencies:

pip install streamlit opencv-python numpy pandas tensorflow

Run the system:

python DRBK-GUI.py

---

## Emergency Feature

When the emergency button is pressed:
- A message is sent via Telegram  
- Includes distance, object, and timestamp  

---

## Future Improvements

- Improve detection in low-light conditions  
- Enhance GUI design  
- Add more object categories  
- Extend system capabilities  

---
## Authors

- Jana Alghamdi  
  [LinkedIn](https://www.linkedin.com/in/jana-alghamdi-54a787328?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

- Layan Alquraini  
  [LinkedIn](YOUR_LINK_HERE)

- Shaikha Alkhathlan  
  [LinkedIn](https://www.linkedin.com/in/shaikha-a-2ba51b325/)

### Supervisor
- Malak Abdullah Almarshad  
  Assistant Professor of Computer Science, Imam Mohammad Ibn Saud Islamic University (IMSIU)
  https://scholar.google.com/citations?user=h2wmOswAAAAJ&hl=ar

