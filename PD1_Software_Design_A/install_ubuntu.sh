#!/usr/bin/env bash
# Dependency installation for the Component Twin exercise station.
# Target: Ubuntu 22.04 / 24.04 Mini PC with a USB (UVC) 720p camera.
set -euo pipefail
cd "$(dirname "$0")"

THREE_VERSION="0.170.0"
POSE_MODEL_URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
CDN="https://cdn.jsdelivr.net/npm/three@${THREE_VERSION}"

echo "==> System packages (Python, camera tools, OpenGL/EGL runtime for MediaPipe)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl v4l-utils \
  libegl1 libgles2 libgl1 libglib2.0-0
sudo usermod -aG video "$USER" || true

echo "==> Python virtual environment"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> MediaPipe BlazePose Full model"
mkdir -p models data avatar
curl -fL --retry 3 -o models/pose_landmarker_full.task "$POSE_MODEL_URL"

echo "==> Three.js ${THREE_VERSION} (served locally so the station works offline)"
mkdir -p web/vendor/three/build web/vendor/three/examples/jsm/{loaders,controls,utils}
curl -fL --retry 3 -o web/vendor/three/build/three.module.js "$CDN/build/three.module.js"
curl -fL --retry 3 -o web/vendor/three/examples/jsm/loaders/GLTFLoader.js "$CDN/examples/jsm/loaders/GLTFLoader.js"
curl -fL --retry 3 -o web/vendor/three/examples/jsm/controls/OrbitControls.js "$CDN/examples/jsm/controls/OrbitControls.js"
curl -fL --retry 3 -o web/vendor/three/examples/jsm/utils/BufferGeometryUtils.js "$CDN/examples/jsm/utils/BufferGeometryUtils.js"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created station/.env - edit BACKEND_URL and the station staff password."
fi

echo "==> Verifying installation"
python - <<'PY'
import cv2, mediapipe
from mediapipe.tasks.python import vision, BaseOptions
opts = vision.PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="models/pose_landmarker_full.task"),
    running_mode=vision.RunningMode.VIDEO)
vision.PoseLandmarker.create_from_options(opts).close()
print("OpenCV", cv2.__version__, "| MediaPipe", mediapipe.__version__, "| BlazePose Full OK")
PY
v4l2-ctl --list-devices || echo "No camera detected yet."
echo "Done. Log out and back in once so the camera (video group) permission applies."
