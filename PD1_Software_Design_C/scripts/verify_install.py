import cv2, mediapipe
from mediapipe.tasks.python import vision, BaseOptions

opts = vision.PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="models/pose_landmarker_full.task"),
    running_mode=vision.RunningMode.VIDEO,
)
vision.PoseLandmarker.create_from_options(opts).close()
print("OpenCV", cv2.__version__, "| MediaPipe", mediapipe.__version__, "| BlazePose Full OK")
