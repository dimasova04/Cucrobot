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


def _mp4(width: int = 640, height: int = 480) -> bytes:
    import os
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "clip.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c=0x808080:s={width}x{height}:d=0.3",
                "-r", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                path,
            ],
            check=True,
        )
        with open(path, "rb") as fh:
            return fh.read()


def _white_span(frame: np.ndarray) -> tuple[int, int, int, int]:
    white = np.all(frame > 210, axis=2)
    ys, xs = np.where(white)
    assert len(xs) > 20
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def test_broken_video_stays_untouched():
    from services.generation.watermark import apply_free_mark_video

    assert apply_free_mark_video(b"not a video") == b"not a video"
    assert apply_free_mark_video(b"") == b""


def _first_frame(video: bytes) -> np.ndarray:
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "clip.mp4")
        with open(path, "wb") as fh:
            fh.write(video)
        cap = cv2.VideoCapture(path)
        ok, frame = cap.read()
        cap.release()
    assert ok and frame is not None
    return frame


def test_video_mark_keeps_the_whole_word_inside_the_frame():
    from services.generation.watermark import apply_free_mark_video

    raw = _mp4(1280, 720)
    marked = apply_free_mark_video(raw)
    assert marked != raw
    frame = _first_frame(marked)
    height, width = frame.shape[:2]
    assert (width, height) == (1280, 720)
    x0, x1, y0, _y1 = _white_span(frame)
    assert x1 - x0 > 80
    assert width - 1 - x1 >= int(width * 0.06)
    assert y0 >= int(height * 0.05)
    dark = frame.mean(axis=2) < 80
    _ys, dxs = np.where(dark)
    assert len(dxs) > 50
    assert width - 1 - int(dxs.max()) >= int(width * 0.055)
    # Середина кадра не закрашена.
    assert 90 < int(frame[height // 2, width // 2].mean()) < 170
