"""Frame sampling and the motion trigger.

Frames stay in memory. Nothing in this module writes an image to disk.
"""

from __future__ import annotations

from typing import Iterator

import cv2
import numpy as np


def sample_frames(video_path: str, every_sec: float) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (seconds_into_clip, BGR frame) every `every_sec` seconds.

    For a live camera, pass the device index as a string, e.g. "0".
    """
    source = int(video_path) if video_path.isdigit() else video_path
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps * every_sec)))
    idx = 0
    try:
        while total == 0 or idx < total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            yield idx / fps, frame
            idx += step
    finally:
        cap.release()


def to_jpeg(frame: np.ndarray, max_side: int = 896, quality: int = 85) -> bytes:
    """Downscale and JPEG-encode in memory."""
    h, w = frame.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


class MotionTrigger:
    """Stage one of the two-stage design: only wake the VLM when the scene changes.

    Prototype version: frame differencing on a small grayscale image.
    On the UGen300 this is replaced by a lightweight person detector.
    """

    def __init__(self, threshold: float = 0.01, min_interval_sec: float = 0.0, heartbeat_sec: float = 0.0):
        self.threshold = threshold          # fraction of pixels that changed
        self.min_interval_sec = min_interval_sec
        self.heartbeat_sec = heartbeat_sec  # describe at least this often while a scene is active (0 = off)
        self._prev: np.ndarray | None = None
        self._last_fire: float | None = None

    def reset(self) -> None:
        """Call at the start of every new clip or camera session."""
        self._prev = None
        self._last_fire = None

    def check(self, frame: np.ndarray, t: float) -> tuple[bool, float]:
        small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        small = cv2.GaussianBlur(small, (5, 5), 0)
        if self._prev is None:
            changed = 1.0  # first frame of a scene always counts as activity
        else:
            diff = cv2.absdiff(small, self._prev)
            changed = float((diff > 25).mean())
        self._prev = small
        fire = changed >= self.threshold
        if (not fire and self.heartbeat_sec > 0 and self._last_fire is not None
                and t - self._last_fire >= self.heartbeat_sec):
            fire = True  # someone sitting still is still worth one line now and then
        if (fire and self.min_interval_sec > 0 and self._last_fire is not None
                and t - self._last_fire < self.min_interval_sec):
            fire = False
        if fire:
            self._last_fire = t
        return fire, changed
