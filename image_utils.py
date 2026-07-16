import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime

def open_opencv_cropper(image_path):
    """ Opens an OpenCV window to draw a bounding box. """
    img = cv2.imread(image_path)
    if img is None:
        return False
        
    window_name = f"Crop {os.path.basename(image_path)} - Draw square and press ENTER"
    
    # cv2.selectROI pauses execution until the user presses Enter or Space
    roi = cv2.selectROI(window_name, img, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(window_name)
    
    x, y, w, h = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
    
    # If the user actually drew a box
    if w > 0 and h > 0:
        cropped = img[y:y+h, x:x+w]
        cv2.imwrite(image_path, cropped) # Overwrite temp image with cropped version
        return True
    return False

def get_combined_image_cv2(img1_path, img2_path):
    """ Combines images side-by-side in memory. Returns numpy array. """
    if not os.path.exists(img1_path) or not os.path.exists(img2_path):
        return None

    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    
    if img1 is None or img2 is None:
        return None
        
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    
    # Pad the shorter image with black pixels so they concatenate perfectly
    max_h = max(h1, h2)
    if h1 < max_h:
        img1 = cv2.copyMakeBorder(img1, 0, max_h - h1, 0, 0, cv2.BORDER_CONSTANT, value=[0,0,0])
    if h2 < max_h:
        img2 = cv2.copyMakeBorder(img2, 0, max_h - h2, 0, 0, cv2.BORDER_CONSTANT, value=[0,0,0])
        
    return cv2.hconcat([img1, img2])

def add_watermark_and_save(combined_cv2_img, name, user_id, output_dir):
    """ Converts OpenCV image to Pillow for watermarking and saves to disk. """
    combined_rgb = cv2.cvtColor(combined_cv2_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(combined_rgb)
    
    draw = ImageDraw.Draw(pil_img)
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except IOError:
        font = ImageFont.load_default()
        
    text = f"{name} - {user_id}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    width, height = pil_img.size
    x = width - text_width - 60
    y = height - text_height - 60
    
    draw.text((x, y), text, font=font, fill="white", stroke_width=4, stroke_fill="black")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    save_path = os.path.join(output_dir, filename)
    
    pil_img.save(save_path, format="PNG")
    return save_path