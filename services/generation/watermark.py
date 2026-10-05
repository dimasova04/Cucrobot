"""Водяной знак для кадров без подписки. Подписчикам фото уходит как есть."""
import cv2
import numpy as np
from loguru import logger

MARK = "cucro_bot"


def apply_free_mark(image_bytes: bytes) -> bytes:
    """Тёмная плашка с именем бота в правом нижнем углу. Битый файл возвращаем как есть."""
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes
        _draw_mark(img)
        ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    except Exception:
        logger.exception("free mark failed")
        return image_bytes
    if not ok:
        return image_bytes
    return encoded.tobytes()


def _draw_mark(img: np.ndarray) -> None:
    height, width = img.shape[:2]
    short = min(height, width)
    font = cv2.FONT_HERSHEY_SIMPLEX
    target = max(14, int(short * 0.034))
    (_, base_h), _ = cv2.getTextSize(MARK, font, 1.0, 1)
    scale = target / max(base_h, 1)
    thickness = max(1, int(round(scale * 1.6)))
    (text_w, text_h), baseline = cv2.getTextSize(MARK, font, scale, thickness)
    pad_x = max(8, int(text_h * 0.85))
    pad_y = max(5, int(text_h * 0.5))
    box_w = text_w + pad_x * 2
    box_h = text_h + baseline + pad_y * 2
    margin = max(8, int(short * 0.028))
    x = max(0, width - margin - box_w)
    y = max(0, height - margin - box_h)
    box_w = min(box_w, width - x)
    box_h = min(box_h, height - y)
    if box_w < 8 or box_h < 8:
        return
    roi = img[y : y + box_h, x : x + box_w]
    mask = np.zeros((box_h, box_w), np.uint8)
    radius = max(1, box_h // 2)
    cv2.rectangle(mask, (radius, 0), (max(radius, box_w - radius), box_h), 255, -1)
    cv2.circle(mask, (radius, box_h // 2), radius, 255, -1)
    if box_w - radius > 0:
        cv2.circle(mask, (box_w - radius, box_h // 2), radius, 255, -1)
    dark = np.full_like(roi, (16, 16, 16))
    blended = cv2.addWeighted(dark, 0.72, roi, 0.28, 0)
    roi[mask.astype(bool)] = blended[mask.astype(bool)]
    origin = (x + pad_x, y + pad_y + text_h)
    cv2.putText(img, MARK, origin, font, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, MARK, origin, font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
