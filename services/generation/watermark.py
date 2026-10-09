"""Водяной знак для кадров без подписки. Подписчикам фото и видео уходят как есть."""
import os
import subprocess
import tempfile

import cv2
import numpy as np
from loguru import logger

MARK = "cucro_bot"


def apply_free_mark(image_bytes: bytes) -> bytes:
    """Тёмная плашка с именем бота в правом верхнем углу. Битый файл возвращаем как есть."""
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


def apply_free_mark_video(video_bytes: bytes) -> bytes:
    """Тот же знак на готовом ролике, с отступом от края. Битый ролик возвращаем как есть.

    Знак рисуется уже на кадре, который уйдёт в чат. Если нарисовать его на фото до
    оживления, модель обрезает край и слово не влезает.
    """
    if not video_bytes:
        return video_bytes
    try:
        marked = _mark_video(video_bytes)
    except Exception:
        logger.exception("free video mark failed")
        return video_bytes
    return marked or video_bytes


def _mark_video(video_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.mp4")
        dst = os.path.join(tmp, "out.mp4")
        err_path = os.path.join(tmp, "ffmpeg.txt")
        with open(src, "wb") as fh:
            fh.write(video_bytes)
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            return video_bytes
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if fps < 1 or fps > 120:
            fps = 24
        # yuv420p требует чётные стороны.
        width -= width % 2
        height -= height % 2
        if width < 16 or height < 16:
            cap.release()
            return video_bytes
        margin_x = max(24, int(round(width * 0.06)))
        margin_y = max(18, int(round(height * 0.05)))
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", f"{fps:.3f}",
            "-i", "pipe:0",
            "-i", src,
            "-map", "0:v:0", "-map", "1:a?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart",
            dst,
        ]
        with open(err_path, "wb") as err_fh:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_fh)
            frames = 0
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frame = frame[:height, :width]
                    _draw_mark(frame, margin_x=margin_x, margin_y=margin_y)
                    proc.stdin.write(frame.tobytes())
                    frames += 1
                proc.stdin.close()
                code = proc.wait(timeout=90)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
                raise
            finally:
                cap.release()
        if code != 0 or frames == 0 or not os.path.exists(dst) or os.path.getsize(dst) < 32:
            with open(err_path, "rb") as err_fh:
                logger.warning("video mark encode failed: {}", err_fh.read()[:300])
            return video_bytes
        with open(dst, "rb") as fh:
            return fh.read()


def _draw_mark(img: np.ndarray, *, margin_x: int | None = None, margin_y: int | None = None) -> None:
    height, width = img.shape[:2]
    short = min(height, width)
    font = cv2.FONT_HERSHEY_SIMPLEX
    target = max(14, int(short * 0.034))
    (_, base_h), _ = cv2.getTextSize(MARK, font, 1.0, 1)
    scale = target / max(base_h, 1)
    thickness = max(1, int(round(scale * 1.6)))
    (text_w, text_h), baseline = cv2.getTextSize(MARK, font, scale, thickness)
    pad_y = max(5, int(text_h * 0.5))
    box_h = text_h + baseline + pad_y * 2
    # Текст должен лежать на прямой части плашки, а не в скруглении: иначе последняя буква режется.
    radius = max(1, box_h // 2)
    pad_x = max(8, int(text_h * 0.85), radius + thickness + 2)
    box_w = text_w + pad_x * 2
    margin = max(8, int(short * 0.028))
    if margin_x is None:
        margin_x = margin
    if margin_y is None:
        margin_y = margin
    x = max(0, width - margin_x - box_w)
    y = max(0, margin_y)
    box_w = min(box_w, width - x)
    box_h = min(box_h, height - y)
    if box_w < 8 or box_h < 8:
        return
    roi = img[y : y + box_h, x : x + box_w]
    mask = np.zeros((box_h, box_w), np.uint8)
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
