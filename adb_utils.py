"""
adb_utils.py
------------
All ADB (Android Debug Bridge) interactions live here: checking device
connection, opening the camera app, triggering a capture, and pulling the
resulting file to the computer.

Every function raises ADBError on failure so the GUI layer can catch a
single exception type and show a friendly message box.
"""

import os
import subprocess
import time

ADB_PATH = "adb"  # change this to a full path if adb is not on your PATH

# On Windows, hide the console window that subprocess would otherwise flash.
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class ADBError(Exception):
    """Raised for any recoverable ADB/device problem."""
    pass


def _run_adb(args, timeout=10):
    """Run an adb command and return the CompletedProcess, wrapping errors."""
    try:
        return subprocess.run(
            [ADB_PATH] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATIONFLAGS,
        )
    except FileNotFoundError:
        raise ADBError(
            "adb executable not found. Install Android platform-tools and "
            "make sure 'adb' is on your system PATH."
        )
    except subprocess.TimeoutExpired:
        raise ADBError("ADB command timed out. Check the USB/Wi-Fi connection.")


def check_device():
    """
    Return True if exactly one authorized device is attached, False if
    none is attached. Raises ADBError only on a hard failure (adb missing,
    adb server error) - a simple "no device" is NOT an error, it's False.
    """
    result = _run_adb(["devices"])
    if result.returncode != 0:
        raise ADBError(f"'adb devices' failed: {result.stderr.strip()}")

    lines = [l.strip() for l in result.stdout.strip().splitlines()[1:] if l.strip()]
    if not lines:
        return False

    unauthorized = [l for l in lines if "unauthorized" in l]
    if unauthorized:
        raise ADBError("Device detected but unauthorized. Accept the USB debugging prompt on the phone.")

    ready = [l for l in lines if l.endswith("device")]
    return len(ready) > 0


def open_camera():
    """Launch the phone's default camera app in still-capture mode."""
    result = _run_adb(["shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE"])
    if result.returncode != 0:
        raise ADBError(f"Failed to open camera app: {result.stderr.strip()}")
    time.sleep(2)  # give the camera app time to fully load


def capture_image():
    """Send the camera/shutter keyevent to take a photo."""
    result = _run_adb(["shell", "input", "keyevent", "27"])
    if result.returncode != 0:
        raise ADBError(f"Failed to trigger shutter: {result.stderr.strip()}")
    time.sleep(2)  # give the phone time to write the file to disk


def get_latest_filename(remote_dir="/sdcard/DCIM/Camera"):
    """Return the newest filename inside remote_dir on the device."""
    result = _run_adb(["shell", "ls", "-t", remote_dir])
    if result.returncode != 0:
        raise ADBError(f"Could not list '{remote_dir}' on device: {result.stderr.strip()}")

    files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    if not files:
        raise ADBError(f"No files found in '{remote_dir}' on the device.")
    return files[0]


def pull_latest_image(save_path, remote_dir="/sdcard/DCIM/Camera"):
    """Pull the most recently modified file from remote_dir to save_path."""
    filename = get_latest_filename(remote_dir)
    remote_path = f"{remote_dir}/{filename}"

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    result = _run_adb(["pull", remote_path, save_path], timeout=20)
    if result.returncode != 0:
        raise ADBError(f"Failed to pull '{remote_path}': {result.stderr.strip()}")
    if not os.path.exists(save_path):
        raise ADBError(f"Pull reported success but '{save_path}' was not created.")
    return save_path


def close_camera():
    """Best-effort: send Back to close the camera app. Never raises."""
    try:
        _run_adb(["shell", "input", "keyevent", "4"])
    except ADBError:
        pass  # closing the camera is a nicety, not critical
