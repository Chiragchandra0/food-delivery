import pytesseract
import cv2

def run_ocr_on_image(img_path):
    """ Extracts text from the given image path. """
    img = cv2.imread(img_path)
    if img is None:
        return "Image not found."
    
    # Convert to grayscale to improve OCR accuracy
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply thresholding for better contrast
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    
    text = pytesseract.image_to_string(thresh)
    return text.strip()