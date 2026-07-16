import sys, os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QMessageBox, QDialog, QFormLayout)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import cv2
import concurrent.futures

from adb_utils import get_connected_devices, capture_and_pull
from image_utils import open_opencv_cropper, get_combined_image_cv2, add_watermark_and_save
from ocr_utils import run_ocr_on_image

class CaptureWorker(QThread):
    finished = pyqtSignal(bool)
    
    def __init__(self, devices, paths):
        super().__init__()
        self.devices = devices
        self.paths = paths

    def run(self):
        # Run ADB captures concurrently for true simultaneous execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_device = {
                executor.submit(capture_and_pull, self.devices[0], self.paths[0]): "Device 1",
                executor.submit(capture_and_pull, self.devices[1], self.paths[1]): "Device 2"
            }
            results = [future.result() for future in concurrent.futures.as_completed(future_to_device)]
            
        self.finished.emit(all(results))

class OcrWorker(QThread):
    finished = pyqtSignal(str, str)
    
    def __init__(self, path1, path2):
        super().__init__()
        self.path1 = path1
        self.path2 = path2

    def run(self):
        # Run OCR concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(run_ocr_on_image, self.path1)
            future2 = executor.submit(run_ocr_on_image, self.path2)
            
            text1 = future1.result()
            text2 = future2.result()
            
        self.finished.emit(text1, text2)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phone Image Combiner (PyQt & OpenCV)")
        self.setGeometry(100, 100, 1200, 700)
        
        self.temp_dir = "temp"
        self.out_dir = "output"
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.out_dir, exist_ok=True)
        
        self.img1_path = os.path.join(self.temp_dir, "image1.jpg")
        self.img2_path = os.path.join(self.temp_dir, "image2.jpg")
        self.combined_cv2_img = None # Kept in memory, not disk
        
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # --- LEFT PANEL ---
        left_panel = QVBoxLayout()
        
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_panel.addWidget(self.lbl_status)
        
        btn_capture = QPushButton("Simultaneous Capture (Both Devices)")
        btn_capture.clicked.connect(self.start_capture)
        left_panel.addWidget(btn_capture)
        
        # Image 1 block
        self.lbl_img1 = QLabel("Image 1")
        self.lbl_img1.setAlignment(Qt.AlignCenter)
        self.lbl_img1.setFixedSize(300, 200)
        self.lbl_img1.setStyleSheet("border: 1px solid black;")
        left_panel.addWidget(self.lbl_img1)
        
        btn_crop1 = QPushButton("Crop Image 1")
        btn_crop1.clicked.connect(lambda: self.trigger_crop(self.img1_path, self.lbl_img1))
        left_panel.addWidget(btn_crop1)
        
        # Image 2 block
        self.lbl_img2 = QLabel("Image 2")
        self.lbl_img2.setAlignment(Qt.AlignCenter)
        self.lbl_img2.setFixedSize(300, 200)
        self.lbl_img2.setStyleSheet("border: 1px solid black;")
        left_panel.addWidget(self.lbl_img2)
        
        btn_crop2 = QPushButton("Crop Image 2")
        btn_crop2.clicked.connect(lambda: self.trigger_crop(self.img2_path, self.lbl_img2))
        left_panel.addWidget(btn_crop2)
        
        main_layout.addLayout(left_panel, 1)
        
        # --- RIGHT PANEL ---
        right_panel = QVBoxLayout()
        
        self.lbl_combined = QLabel("Combined Image Preview")
        self.lbl_combined.setAlignment(Qt.AlignCenter)
        self.lbl_combined.setStyleSheet("border: 1px solid black; background-color: #333;")
        right_panel.addWidget(self.lbl_combined, 1)
        
        btn_save = QPushButton("Save, Watermark & Run OCR")
        btn_save.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        btn_save.clicked.connect(self.prompt_save)
        right_panel.addWidget(btn_save)
        
        main_layout.addLayout(right_panel, 2)

    def start_capture(self):
        devices = get_connected_devices()
        if len(devices) < 2:
            QMessageBox.warning(self, "Error", f"Need 2 devices connected. Found {len(devices)}.")
            return
            
        self.lbl_status.setText("Status: Capturing simultaneously...")
        self.lbl_status.setStyleSheet("color: blue; font-weight: bold;")
        
        # Run in background thread to avoid freezing GUI
        self.worker = CaptureWorker(devices[:2], [self.img1_path, self.img2_path])
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()

    def on_capture_finished(self, success):
        if success:
            self.lbl_status.setText("Status: Capture Complete")
            self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
            self.update_preview(self.img1_path, self.lbl_img1)
            self.update_preview(self.img2_path, self.lbl_img2)
            self.update_combined_preview()
        else:
            self.lbl_status.setText("Status: Capture Failed")
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")

    def update_preview(self, path, label_widget):
        if os.path.exists(path):
            pixmap = QPixmap(path).scaled(label_widget.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label_widget.setPixmap(pixmap)

    def trigger_crop(self, path, label_widget):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "No image to crop.")
            return
            
        self.lbl_status.setText("Status: Draw box in OpenCV window and press ENTER")
        # Opens the OpenCV window
        if open_opencv_cropper(path):
            self.update_preview(path, label_widget)
            self.update_combined_preview() # Auto update combined image
            self.lbl_status.setText("Status: Cropped successfully")
        else:
            self.lbl_status.setText("Status: Crop cancelled")

    def update_combined_preview(self):
        self.combined_cv2_img = get_combined_image_cv2(self.img1_path, self.img2_path)
        
        if self.combined_cv2_img is not None:
            # Convert OpenCV BGR to QImage for PyQt preview
            h, w, ch = self.combined_cv2_img.shape
            bytes_per_line = ch * w
            rgb_image = cv2.cvtColor(self.combined_cv2_img, cv2.COLOR_BGR2RGB)
            
            q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img).scaled(self.lbl_combined.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_combined.setPixmap(pixmap)

    def prompt_save(self):
        if self.combined_cv2_img is None:
            QMessageBox.warning(self, "Error", "No combined image to save.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Save Configuration")
        layout = QFormLayout(dialog)
        
        name_input = QLineEdit()
        id_input = QLineEdit()
        
        layout.addRow("Name (Mandatory):", name_input)
        layout.addRow("ID (Mandatory):", id_input)
        
        btn_confirm = QPushButton("Confirm & Save")
        layout.addRow(btn_confirm)
        
        def on_confirm():
            name = name_input.text().strip()
            user_id = id_input.text().strip()
            
            if not name or not user_id:
                QMessageBox.warning(dialog, "Validation Error", "BOTH Name and ID are mandatory to save the image!")
                return
                
            # Requirements met, proceed to save and run OCR
            dialog.accept()
            self.execute_save_and_ocr(name, user_id)
            
        btn_confirm.clicked.connect(on_confirm)
        dialog.exec_()

    def execute_save_and_ocr(self, name, user_id):
        self.lbl_status.setText("Status: Saving image and processing OCR...")
        self.lbl_status.setStyleSheet("color: blue; font-weight: bold;")
        
        # 1. Save Image to disk for the first time
        saved_path = add_watermark_and_save(self.combined_cv2_img, name, user_id, self.out_dir)
        
        # 2. Start OCR asynchronously
        self.ocr_worker = OcrWorker(self.img1_path, self.img2_path)
        self.ocr_worker.finished.connect(lambda t1, t2: self.on_ocr_finished(t1, t2, saved_path))
        self.ocr_worker.start()

    def on_ocr_finished(self, text1, text2, saved_path):
        self.lbl_status.setText(f"Status: Saved to {os.path.basename(saved_path)}. OCR Complete.")
        self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
        
        # Show OCR results
        msg = QMessageBox(self)
        msg.setWindowTitle("Process Complete")
        msg.setText("Image Saved Successfully!")
        msg.setDetailedText(f"--- OCR Image 1 ---\n{text1}\n\n--- OCR Image 2 ---\n{text2}")
        msg.exec_()