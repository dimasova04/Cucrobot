import cv2
import numpy as np

from services.generation.watermark import MARK, apply_free_mark


def _jpeg(width: int, height: int, color: tuple[int, int, int] = (70, 140, 210)) -> bytes:
    image = np.full((height, width, 3), color, np.uint8)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert ok
    return encoded.tobytes()


def test_broken_bytes_stay_untouched():
    assert apply_free_mark(b"not a photo") == b"not a photo"
    assert apply_free_mark(b"") == b""


def test_mark_sits_in_the_top_right_corner():
    color = (180, 90, 40)
    raw = _jpeg(1248, 832, color)
    marked = apply_free_mark(raw)
    assert marked != raw
    out = cv2.imdecode(np.frombuffer(marked, np.uint8), cv2.IMREAD_COLOR)
    assert out.shape == (832, 1248, 3)
    corner = out[12:80, -220:-12]
    center = out[400:440, 600:640]
    expected = sum(color) / 3
    assert int(corner.min()) < 40
    assert int(corner.max()) > 230
    assert abs(float(center.mean()) - expected) < 15
    # Низ кадра и левый верхний угол не трогаем.
    assert abs(float(out[-50:-20, -80:-20].mean()) - expected) < 15
    assert abs(float(out[20:50, 20:50].mean()) - expected) < 15


def test_mark_fits_a_portrait_frame():
    out = cv2.imdecode(np.frombuffer(apply_free_mark(_jpeg(832, 1248)), np.uint8), cv2.IMREAD_COLOR)
    assert out.shape == (1248, 832, 3)
    corner = out[10:90, -240:-10]
    assert int(corner.max()) > 230
    assert int(out[-80:-10, -240:-10].max()) < 230
    assert MARK == "cucro_bot"
