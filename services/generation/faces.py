import threading
from pathlib import Path

import cv2
import numpy as np
from loguru import logger

_CASCADE = None
_cascade_load_attempted = False
# YuNet (OpenCV Zoo, Apache-2.0). Каскад Хаара на этих кадрах пропускает мужчину
# в профиль и рисует рамки на груди и халате, поэтому лица локации закрывает он.
_YUNET_PATH = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
_YUNET = None
_yunet_lock = threading.Lock()


def _get_cascade():
    # Lazy + guarded: some opencv-python-headless builds (e.g. 5.0.x wheels seen in
    # this environment) ship without cv2.CascadeClassifier / the haarcascades data
    # files at all, which would otherwise make this whole module unimportable.
    global _CASCADE, _cascade_load_attempted
    if not _cascade_load_attempted:
        _cascade_load_attempted = True
        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            if not cascade.empty():
                _CASCADE = cascade
        except AttributeError:
            logger.error("cv2 build has no CascadeClassifier; face detection disabled")
    return _CASCADE


def detector_available() -> bool:
    return _get_cascade() is not None


def has_face(image_bytes: bytes) -> bool:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return False
    cascade = _get_cascade()
    if cascade is None:
        # The face check is a UX helper, not the safety gate: if the detector
        # is unavailable we must fail open (allow the photo) rather than
        # rejecting every upload.
        logger.warning("face detector unavailable, skipping check")
        return True
    h, w = img.shape[:2]
    scale = 800 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    return len(faces) > 0


def _detect_faces(img):
    """Детектор один на процесс: setInputSize и detect нельзя звать параллельно."""
    global _YUNET
    height, width = img.shape[:2]
    if not _YUNET_PATH.is_file():
        return None
    with _yunet_lock:
        if _YUNET is None:
            _YUNET = cv2.FaceDetectorYN.create(
                str(_YUNET_PATH), "", (width, height),
                score_threshold=0.6, nms_threshold=0.3, top_k=20,
            )
        else:
            _YUNET.setInputSize((width, height))
        return _YUNET.detect(img)


def _blur_region(img, x0: int, y0: int, x1: int, y1: int) -> None:
    """Мягкое пятно вместо прямоугольника: модель не копирует серый блок как человека."""
    height, width = img.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    roi = img[y0:y1, x0:x1]
    if roi.size == 0 or min(roi.shape[:2]) < 3:
        return
    kernel = max(31, (min(roi.shape[:2]) // 2) | 1)
    kernel = min(kernel, min(roi.shape[:2]) | 1)
    if kernel % 2 == 0:
        kernel -= 1
    if kernel < 3:
        return
    blurred = cv2.GaussianBlur(roi, (kernel, kernel), 0)
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    cv2.ellipse(
        mask, (roi.shape[1] // 2, roi.shape[0] // 2),
        (max(1, roi.shape[1] // 2), max(1, roi.shape[0] // 2)), 0, 0, 360, 255, -1,
    )
    feather = min(31, (min(roi.shape[:2]) // 3) | 1)
    if feather % 2 == 0:
        feather -= 1
    if feather >= 3:
        mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    img[y0:y1, x0:x1] = (blurred * alpha + roi * (1.0 - alpha)).astype(np.uint8)


def _cover_bodies_under_faces(img, found) -> None:
    """Под небольшим лицом в комнате закрываем и фигуру: иначе остаётся оператор."""
    height, width = img.shape[:2]
    for face in found:
        x, y, fw, fh = (int(v) for v in face[:4])
        if min(fw, fh) < 28:
            continue
        pad_x = int(fw * 0.25)
        pad_up = int(fh * 0.45)
        pad_down = int(fh * 0.2)
        _blur_region(
            img,
            x - pad_x, y - pad_up,
            x + fw + pad_x, y + fh + pad_down,
        )
        # Крупный план — это пара в кадре локации, тело и так почти всё фото.
        # Фигуру дорисовываем только людям, которые стоят в комнате.
        if fh >= height * 0.22:
            continue
        cx = x + fw / 2
        bw = int(fw * 3.4)
        top = y + int(fh * 0.55)
        _blur_region(img, int(cx - bw / 2), top, int(cx + bw / 2), top + int(fh * 6.5))


def _cover_standing_people(img) -> None:
    """Лицо в пол смотрит вниз, детектор лиц его пропускает. Фигуру ловит HOG.

    Порог высокий: на пустой комнате детектор цепляется за свет и скульптуру.
    """
    height, width = img.shape[:2]
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    scale = 800 / max(height, width)
    view = cv2.resize(img, (int(width * scale), int(height * scale))) if scale < 1 else img
    rects, weights = hog.detectMultiScale(view, winStride=(8, 8), padding=(8, 8), scale=1.05)
    inv = 1 / scale if scale < 1 else 1.0
    for (x, y, rw, rh), weight in zip(rects, weights):
        if float(weight) < 1.5:
            continue
        _blur_region(
            img,
            int(x * inv), int(y * inv),
            int((x + rw) * inv), int((y + rh) * inv),
        )


def anonymize_faces(image_bytes: bytes) -> bytes:
    """Закрывает чужих людей на кадре локации. Комната, свет и реквизит остаются.

    Если детектора нет или на фото никого нет, байты возвращаются как есть.
    """
    img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes
    changed = False
    try:
        detected = _detect_faces(img)
        if detected is None:
            logger.warning("location face anonymizer unavailable")
        else:
            _count, found = detected
            if found is not None and len(found):
                before = img.copy()
                _cover_bodies_under_faces(img, found)
                changed = changed or not np.array_equal(before, img)
    except Exception:
        logger.exception("location face anonymizer failed")
        return image_bytes
    try:
        before = img.copy()
        _cover_standing_people(img)
        changed = changed or not np.array_equal(before, img)
    except Exception:
        logger.exception("location person anonymizer failed")
    if not changed:
        return image_bytes
    ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return image_bytes
    return encoded.tobytes()
