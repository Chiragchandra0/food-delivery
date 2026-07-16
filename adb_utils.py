import subprocess
import time

def run_adb(command):
    try:
        result = subprocess.run(f"adb {command}", shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

def get_connected_devices():
    out = run_adb("devices")
    lines = out.split('\n')
    devices = []
    for line in lines[1:]:
        if 'device' in line and 'unauthorized' not in line:
            devices.append(line.split('\t')[0])
    return devices

def capture_and_pull(serial, save_path):
    """ Targets a specific device using its serial ID. """
    prefix = f"-s {serial}"
    
    # Wake device (just in case)
    run_adb(f"{prefix} shell input keyevent 224")
    
    # Open camera directly
    run_adb(f"{prefix} shell am start -a android.media.action.IMAGE_CAPTURE")
    time.sleep(1.5) # Wait for camera to open
    
    # Capture image
    run_adb(f"{prefix} shell input keyevent 27")
    time.sleep(2) # Wait for device to save the photo internally
    
    # Pull latest image
    out = run_adb(f"{prefix} shell ls -t /sdcard/DCIM/Camera")
    files = [f.strip() for f in out.split('\n') if f.lower().strip().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not files:
        return False
        
    latest_file = files[0]
    run_adb(f"{prefix} pull /sdcard/DCIM/Camera/{latest_file} {save_path}")
    
    # Close camera and go to home screen
    run_adb(f"{prefix} shell input keyevent 3")
    return True