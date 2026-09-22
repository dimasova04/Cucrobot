import cv2
import numpy as np
from loguru import logger

_CASCADE = None
_cascade_load_attempted = False


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
