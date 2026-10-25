"""Station settings (.env) and exercise configuration (config/exercises.json)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

STATION_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = STATION_DIR / "config"
DATA_DIR = STATION_DIR / "data"
MODELS_DIR = STATION_DIR / "models"
WEB_DIR = STATION_DIR / "web"
AVATAR_DIR = STATION_DIR / "avatar"


class StationSettings(BaseSettings):
    backend_url: str = "http://localhost:8000"
    station_staff_email: str = "station@example.com"
    station_staff_password: str = ""
    camera_source: str = "0"
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: int = 30
    station_host: str = "127.0.0.1"
    station_port: int = 8080
    sync_interval_seconds: int = 30
    pose_model_path: str = str(MODELS_DIR / "pose_landmarker_full.task")
    database_path: str = str(DATA_DIR / "station.db")
    stream_fps: int = 15

    model_config = SettingsConfigDict(
        env_file=str(STATION_DIR / ".env"),
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def camera(self) -> int | str:
        return int(self.camera_source) if self.camera_source.isdigit() else self.camera_source


@lru_cache
def get_settings() -> StationSettings:
    return StationSettings()


@lru_cache
def load_exercise_config() -> dict[str, Any]:
    with open(CONFIG_DIR / "exercises.json", encoding="utf-8") as handle:
        return json.load(handle)


def match_exercise_key(backend_exercise_name: str) -> str | None:
    """Map a backend Exercise.name to a station exercise key."""
    name = backend_exercise_name.strip().lower()
    for key, exercise in load_exercise_config()["exercises"].items():
        names = [exercise["display_name"].lower(), *exercise.get("backend_names", [])]
        if name in names:
            return key
    return None
