"""
gui.py
------
Tkinter GUI for the Phone Image Combiner.

Layout:
    PHONE IMAGE COMBINER
    Device: Connected / Disconnected   (auto-refreshes every 5 seconds)
    [ Capture Image 1 ]  -> preview
    [ Capture Image 2 ]  -> preview
    [ Combine Images ]   -> preview  (asks for Name + ID before saving)
    [ Open Output Folder ]  [ Exit ]
    Status bar

Threading model:
    ADB calls and OCR can take a second or two, so every long operation
    (capture, combine) runs on a background daemon thread. That thread
    never touches Tkinter widgets directly - it always hands results back
    to the main thread via root.after(0, ...), which is the safe way to
    update a Tkinter GUI from another thread. The device-status poll works
    the same way, and runs continuously every 5 seconds for the lifetime
    of the app.
"""

import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk

import adb_utils
import image_utils
import ocr_utils

TEMP_DIR = "temp"
OUTPUT_DIR = "output"
PREVIEW_MAX_SIZE = (320, 320)
POLL_INTERVAL_SECONDS = 5


class NameIDDialog(tk.Toplevel):
    """
    Modal popup that collects Name + ID. The combined image is only ever
    saved if the user fills both fields in and presses Save; Cancel (or
    closing the window) aborts the save and self.result stays None.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Enter Name & ID")
        self.resizable(False, False)
        self.result = None

        self.transient(parent)
        self.grab_set()  # modal

        container = ttk.Frame(self, padding=15)
        container.grid(row=0, column=0, sticky="nsew")

        ttk.Label(container, text="Enter details before saving:", font=("Segoe UI", 10, "bold")) \
            .grid(row=0, column=0, columnspan=2, pady=(0, 10))

        ttk.Label(container, text="Name:").grid(row=1, column=0, sticky="e", padx=5, pady=6)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(container, textvariable=self.name_var, width=28)
        self.name_entry.grid(row=1, column=1, pady=6)

        ttk.Label(container, text="ID:").grid(row=2, column=0, sticky="e", padx=5, pady=6)
        self.id_var = tk.StringVar()
        self.id_entry = ttk.Entry(container, textvariable=self.id_var, width=28)
        self.id_entry.grid(row=2, column=1, pady=6)

        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Return>", lambda e: self._on_save())
        self.name_entry.focus_set()

        # centre roughly over the parent window
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        self.geometry(f"+{px + 80}+{py + 120}")

        self.wait_window(self)  # block until closed

    def _on_save(self):
        name = self.name_var.get().strip()
        id_ = self.id_var.get().strip()
        if not name or not id_:
            messagebox.showwarning("Missing Info", "Both Name and ID are required to save.", parent=self)
            return
        # keep the watermark/filename safe from characters that break paths
        safe = lambda s: "".join(c for c in s if c.isalnum() or c in (" ", "-", "_")).strip()
        name, id_ = safe(name), safe(id_)
        if not name or not id_:
            messagebox.showwarning("Invalid Info", "Name/ID must contain at least one letter or number.", parent=self)
            return
        self.result = (name, id_)
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


class PhoneCaptureApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Phone Image Combiner")
        self.root.geometry("640x780")
        self.root.resizable(False, False)

        os.makedirs(TEMP_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        self.image1_path = None
        self.image2_path = None

        self._busy = False
        self._device_connected = False
        self._stop_polling = False

        self._build_ui()
        self._start_device_polling()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        ttk.Label(self.root, text="PHONE IMAGE COMBINER", font=("Segoe UI", 16, "bold")).pack(pady=(15, 5))

        status_frame = ttk.Frame(self.root)
        status_frame.pack(pady=(0, 10))
        ttk.Label(status_frame, text="Device:", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.device_label = ttk.Label(status_frame, text="Checking...", foreground="#b5851a")
        self.device_label.pack(side="left", padx=6)

        frame1 = ttk.LabelFrame(self.root, text="Image 1")
        frame1.pack(padx=15, pady=8, fill="x")
        self.btn_capture1 = ttk.Button(frame1, text="Capture Image 1", command=lambda: self._capture(1))
        self.btn_capture1.pack(pady=6)
        self.preview1_label = ttk.Label(frame1, text="No image yet", relief="groove",
                                         width=44, anchor="center", background="#f2f2f2")
        self.preview1_label.pack(pady=6, ipady=40)

        frame2 = ttk.LabelFrame(self.root, text="Image 2")
        frame2.pack(padx=15, pady=8, fill="x")
        self.btn_capture2 = ttk.Button(frame2, text="Capture Image 2", command=lambda: self._capture(2))
        self.btn_capture2.pack(pady=6)
        self.preview2_label = ttk.Label(frame2, text="No image yet", relief="groove",
                                         width=44, anchor="center", background="#f2f2f2")
        self.preview2_label.pack(pady=6, ipady=40)

        frame3 = ttk.LabelFrame(self.root, text="Combined Image")
        frame3.pack(padx=15, pady=8, fill="x")
        self.btn_combine = ttk.Button(frame3, text="Combine Images", command=self._combine)
        self.btn_combine.pack(pady=6)
        self.preview_combined_label = ttk.Label(frame3, text="No image yet", relief="groove",
                                                  width=44, anchor="center", background="#f2f2f2")
        self.preview_combined_label.pack(pady=6, ipady=40)

        action_frame = ttk.Frame(self.root)
        action_frame.pack(pady=12)
        ttk.Button(action_frame, text="Open Output Folder", command=self._open_output_folder).pack(side="left", padx=5)
        ttk.Button(action_frame, text="Exit", command=self._on_exit).pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(side="bottom", fill="x")

    def _set_status(self, msg):
        self.status_var.set(msg)

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_capture1.config(state=state)
        self.btn_capture2.config(state=state)
        self.btn_combine.config(state=state)

    # ---------------------------------------------------- device polling

    def _start_device_polling(self):
        """Background thread that checks the device every 5s, for the app's lifetime."""

        def poll_loop():
            while not self._stop_polling:
                try:
                    connected = adb_utils.check_device()
                    error = None
                except adb_utils.ADBError as e:
                    connected = False
                    error = str(e)
                if not self._stop_polling:
                    self.root.after(0, self._update_device_label, connected, error)
                for _ in range(POLL_INTERVAL_SECONDS * 10):
                    if self._stop_polling:
                        break
                    time.sleep(0.1)

        threading.Thread(target=poll_loop, daemon=True).start()

    def _update_device_label(self, connected, error):
        self._device_connected = connected
        if connected:
            self.device_label.config(text="Connected", foreground="#1a7a1a")
        else:
            text = "Disconnected" if not error else "Disconnected (adb error - see status bar)"
            self.device_label.config(text=text, foreground="#b02020")
            if error:
                self._set_status(error)

    # ---------------------------------------------------------- capture

    def _capture(self, index):
        if self._busy:
            return
        if not self._device_connected:
            messagebox.showerror("Device Error", "No device connected. Enable USB debugging and plug in the phone.")
            return

        self._set_busy(True)
        self._set_status(f"Capturing image {index}... keep the phone still.")

        def worker():
            try:
                adb_utils.open_camera()
                adb_utils.capture_image()
                save_path = os.path.join(TEMP_DIR, f"image{index}.jpg")
                adb_utils.pull_latest_image(save_path)
                image_utils.crop_image(save_path)
                adb_utils.close_camera()
                self.root.after(0, self._on_capture_success, index, save_path)
            except adb_utils.ADBError as e:
                self.root.after(0, self._on_capture_error, str(e))
            except Exception as e:
                self.root.after(0, self._on_capture_error, f"Unexpected error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_capture_success(self, index, path):
        if index == 1:
            self.image1_path = path
            self._show_preview(path, self.preview1_label)
        else:
            self.image2_path = path
            self._show_preview(path, self.preview2_label)
        self._set_status(f"Image {index} captured and cropped successfully.")
        self._set_busy(False)

    def _on_capture_error(self, msg):
        self._set_status("Error during capture.")
        messagebox.showerror("Capture Error", msg)
        self._set_busy(False)

    # ---------------------------------------------------------- combine

    def _combine(self):
        if self._busy:
            return
        if not self.image1_path or not self.image2_path:
            messagebox.showwarning("Missing Images", "Please capture both Image 1 and Image 2 first.")
            return

        self._set_busy(True)
        self._set_status("Combining images and scanning for a 9-digit code...")

        def worker():
            try:
                combined_tmp = os.path.join(TEMP_DIR, "combined_preview.jpg")
                image_utils.combine_side_by_side(self.image1_path, self.image2_path, combined_tmp)

                code = None
                for p in (self.image1_path, self.image2_path):
                    try:
                        found = ocr_utils.find_nine_digit_code(p)
                    except ocr_utils.OCRError:
                        found = None  # OCR problems shouldn't block the workflow
                    if found:
                        code = found
                        break

                self.root.after(0, self._on_combine_ready, combined_tmp, code)
            except Exception as e:
                self.root.after(0, self._on_capture_error, f"Combine failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_combine_ready(self, combined_tmp, code):
        self._set_busy(False)
        self._show_preview(combined_tmp, self.preview_combined_label)

        if code:
            self._set_status(f"9-digit code detected: {code}. Enter Name and ID to save.")
        else:
            self._set_status("No 9-digit code detected. Enter Name and ID to save.")

        dialog = NameIDDialog(self.root)
        if dialog.result is None:
            self._set_status("Save cancelled - combined image was not saved.")
            return

        name, id_ = dialog.result
        self._finalize_save(combined_tmp, name, id_, code)

    def _finalize_save(self, combined_tmp, name, id_, code):
        try:
            watermark_text = f"{name} | {id_}"
            filename_base = code if code else f"{id_}_{int(time.time())}"
            output_path = os.path.join(OUTPUT_DIR, f"{filename_base}.jpg")

            counter = 1
            base_output_path = output_path
            while os.path.exists(output_path):
                output_path = base_output_path[:-4] + f"_{counter}.jpg"
                counter += 1

            image_utils.add_watermark(combined_tmp, watermark_text, output_path)

            self._show_preview(output_path, self.preview_combined_label)
            note = f" Code used in filename: {code}." if code else " No code found - used ID + timestamp instead."
            self._set_status(f"Saved: {output_path}.{note}")
            messagebox.showinfo("Saved", f"Combined image saved as:\n{output_path}\n{note}")
        except Exception as e:
            self._set_status("Save failed.")
            messagebox.showerror("Save Error", f"Failed to save combined image: {e}")

    # ---------------------------------------------------------- helpers

    def _show_preview(self, path, label_widget):
        try:
            with Image.open(path) as img:
                img = img.copy()
            img.thumbnail(PREVIEW_MAX_SIZE)
            photo = ImageTk.PhotoImage(img)
            label_widget.config(image=photo, text="")
            label_widget.image = photo  # keep a reference so it isn't garbage collected
        except Exception as e:
            label_widget.config(text=f"Preview error: {e}", image="")

    def _open_output_folder(self):
        path = os.path.abspath(OUTPUT_DIR)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            messagebox.showerror("Error", f"Could not open output folder: {e}")

    def _on_exit(self):
        self._stop_polling = True
        self.root.destroy()
