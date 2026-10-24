"""MediaPipe BlazePose Full (Pose Landmarker task) wrapper."""

from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

# BlazePose landmark indices used by the lower-extremity Component Twin
LANDMARKS = {
    "left": {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27, "heel": 29, "foot": 31},
    "right": {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28, "heel": 30, "foot": 32},
}


@dataclass
class Point:
    x: float  # pixels
    y: float  # pixels
    z: float = 0.0
    visibility: float = 0.0


class PoseEstimator:
    def __init__(self, model_path: str):
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(
                model_asset_path=model_path,
                delegate=BaseOptions.Delegate.CPU,
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> dict[str, Point] | None:
        """Return the 33 landmarks as pixel Points keyed by index (str), or None."""
        timestamp_ms = max(timestamp_ms, self._last_ts + 1)
        self._last_ts = timestamp_ms

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        if not result.pose_landmarks:
            return None

        height, width = frame_bgr.shape[:2]
        return {
            str(index): Point(lm.x * width, lm.y * height, float(lm.z or 0.0), float(lm.visibility or 0.0))
            for index, lm in enumerate(result.pose_landmarks[0])
        }

    def close(self) -> None:
        self._landmarker.close()
