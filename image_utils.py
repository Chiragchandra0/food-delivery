"""
image_utils.py
---------------
Cropping, side-by-side combining, and watermarking with Pillow.

CROP CONFIGURATION
-------------------
There was no exact crop region specified, so cropping is controlled by the
two constants below. Adjust them for your phone's photo resolution / the
part of the frame you actually want to keep.

- CROP_BOX: exact pixel box (left, top, right, bottom). Set this if you
  know precisely what you want cropped. Leave as None to use the
  percentage-based margin instead.
- CROP_MARGIN_PERCENT: trims this fraction off each edge (0.05 = 5% off
  every side). Used only when CROP_BOX is None. Set to 0 to disable
  cropping entirely.
"""

from PIL import Image, ImageDraw, ImageFont

CROP_BOX = None                 # e.g. (100, 300, 2800, 3800)
CROP_MARGIN_PERCENT = 0.05      # trims 5% off each side by default


def crop_image(image_path, output_path=None, box=None):
    """Crop image_path in place (or to output_path) using CROP_BOX / CROP_MARGIN_PERCENT."""
    output_path = output_path or image_path
    box = box if box is not None else CROP_BOX

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size

        if box:
            cropped = img.crop(box)
        elif CROP_MARGIN_PERCENT > 0:
            dx = int(w * CROP_MARGIN_PERCENT)
            dy = int(h * CROP_MARGIN_PERCENT)
            cropped = img.crop((dx, dy, w - dx, h - dy))
        else:
            cropped = img

        cropped.save(output_path, quality=95)
    return output_path


def combine_side_by_side(image1_path, image2_path, output_path):
    """Combine two images left/right into a single image, matched to equal height."""
    with Image.open(image1_path) as i1, Image.open(image2_path) as i2:
        img1 = i1.convert("RGB")
        img2 = i2.convert("RGB")

        target_h = min(img1.height, img2.height)

        def resize_to_height(img, h):
            ratio = h / img.height
            new_w = max(1, int(img.width * ratio))
            return img.resize((new_w, h))

        img1 = resize_to_height(img1, target_h)
        img2 = resize_to_height(img2, target_h)

        combined = Image.new("RGB", (img1.width + img2.width, target_h), "white")
        combined.paste(img1, (0, 0))
        combined.paste(img2, (img1.width, 0))
        combined.save(output_path, quality=95)

    return output_path


def _load_font(size):
    """Try a couple of common font files before falling back to Pillow's default."""
    for candidate in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def add_watermark(image_path, text, output_path=None, font_size=None, margin=12):
    """Stamp `text` as a small watermark in the bottom-right corner of the image."""
    output_path = output_path or image_path

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        if font_size is None:
            font_size = max(14, int(h * 0.022))
        font = _load_font(font_size)

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

        x = w - text_w - margin
        y = h - text_h - margin
        pad = 6

        # semi-opaque background block so the text stays legible on any photo
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle(
            [x - pad, y - pad, x + text_w + pad, y + text_h + pad],
            fill=(0, 0, 0, 160),
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(img)
        draw.text((x, y - bbox[1]), text, font=font, fill=(255, 255, 255))

        img.save(output_path, quality=95)

    return output_path
