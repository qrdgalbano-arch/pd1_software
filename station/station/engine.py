"""Camera -> BlazePose Full -> Component Twin -> evaluation loop (runs in its own thread)."""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

import cv2

from station.component_twin import ComponentTwinModel
from station.config import StationSettings, load_exercise_config
from station.exercises import ExerciseEvaluator, classify_arom
from station.pose import LANDMARKS, PoseEstimator
from station.storage import LocalStore

log = logging.getLogger("station.engine")

COLORS = {"ok": (80, 200, 80), "deviation": (40, 40, 230), "lost": (150, 150, 150), "bone": (255, 220, 120)}


class ExerciseEngine(threading.Thread):
    def __init__(self, settings: StationSettings, store: LocalStore, on_session_saved=None):
        super().__init__(daemon=True, name="exercise-engine")
        self.settings = settings
        self.store = store
        self.on_session_saved = on_session_saved
        self.cfg = load_exercise_config()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self.side = "left"
        self.exercise_key = "straight_leg_raising"
        self.twin = self._new_twin(self.side)
        self.session: dict | None = None
        self.evaluator: ExerciseEvaluator | None = None
        self.last_summary: dict | None = None

        self.jpeg: bytes | None = None
        self.jpeg_seq = 0
        self.state: dict = {"phase": "starting"}
        self.camera_error: str | None = None

        self.fps = 0.0
        self.frames = 0
        self.frame_errors = 0
        self.pose_ms = 0.0

    # ------------------------------------------------------------------ setup
    def _new_twin(self, side: str) -> ComponentTwinModel:
        return ComponentTwinModel(side, self.cfg["min_landmark_visibility"], self.cfg["filter"])

    def _open_camera(self) -> cv2.VideoCapture:
        source = self.settings.camera
        if isinstance(source, int):
            cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
            cap.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera source {source!r}")
        return cap

    # -------------------------------------------------------- session control
    def set_preview(self, exercise_key: str, side: str) -> None:
        if exercise_key not in self.cfg["exercises"] or side not in ("left", "right"):
            raise ValueError("Unknown exercise or side")
        with self._lock:
            if self.session is not None:
                raise RuntimeError("A session is running")
            self.exercise_key, self.side = exercise_key, side
            self.twin = self._new_twin(side)

    def start_session(self, patient: dict, prescription: dict, side: str) -> dict:
        key = prescription["exercise_key"]
        exercise_cfg = self.cfg["exercises"][key]
        with self._lock:
            if self.session is not None:
                raise RuntimeError("A session is already running")
            self.exercise_key, self.side = key, side
            self.twin = self._new_twin(side)
            self.twin.start_calibration()
            self.evaluator = ExerciseEvaluator(key, exercise_cfg, self.cfg)
            now = time.monotonic()
            self.session = {
                "client_session_id": f"station-{uuid.uuid4()}",
                "patient": patient,
                "prescription": prescription,
                "exercise_key": key,
                "side": side,
                "phase": "calibrating",
                "calibration_started": now,
                "started": None,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "frames": 0,
                "frame_errors": 0,
                "fps_samples": [],
            }
            self.evaluator._say("calibrate", "Hold still in the starting position.", "info")
            self.last_summary = None
            return {"client_session_id": self.session["client_session_id"]}

    def stop_session(self, reason: str = "stopped") -> dict | None:
        with self._lock:
            return self._finish_session(time.monotonic(), reason)

    def _finish_session(self, t: float, reason: str) -> dict | None:
        session, ev = self.session, self.evaluator
        if session is None or ev is None:
            return None

        if ev.current is not None:  # stopped mid-repetition
            rep = ev.current
            rep.ended_at, rep.result = t, "incomplete"
            rep.arom = classify_arom(rep.peak_deg, ev.rom_standard, ev.tolerance)
            ev.reps.append(rep)
            ev.current = None

        target = int(session["prescription"]["repetitions_target"])
        valid, invalid, incomplete = ev.valid, ev.count("invalid"), ev.count("incomplete")
        if valid >= target:
            status = "completed"
        elif valid + invalid + incomplete == 0:
            status = "cancelled"
        else:
            status = "incomplete"

        duration = 0 if session["started"] is None else int(round(t - session["started"]))
        arom, peak = ev.session_arom()
        if ev.reps and all(r.tracking_lost for r in ev.reps):
            arom = "Tracking unavailable"
        fps_samples = session["fps_samples"] or [0.0]
        frames = max(1, session["frames"])

        record = {
            "client_session_id": session["client_session_id"],
            "patient_id": session["patient"]["id"],
            "prescription_id": session["prescription"]["id"],
            "exercise_key": session["exercise_key"],
            "exercise_name": session["prescription"]["exercise"]["name"],
            "affected_side": session["side"],
            "status": status,
            "valid_repetitions": valid,
            "invalid_repetitions": invalid,
            "incomplete_repetitions": incomplete,
            "error_count": invalid,
            "error_summary": ev.error_summary(),
            "arom_classification": arom if ev.reps else None,
            "peak_rom_degrees": peak,
            "duration_seconds": duration,
            "device_recorded_at": session["recorded_at"],
            "repetitions_json": json.dumps([r.as_dict() for r in ev.reps]),
            "metrics_json": json.dumps({
                "end_reason": reason,
                "avg_fps": round(sum(fps_samples) / len(fps_samples), 1),
                "min_fps": round(min(fps_samples), 1),
                "frames": session["frames"],
                "frame_errors": session["frame_errors"],
                "error_rate_percent": round(100.0 * session["frame_errors"] / frames, 3),
                "feedback_latency_s": max(ev.feedback_latencies, default=None),
                "rom_standard_deg": ev.rom_standard,
                "baselines_deg": {k: j.state.baseline for k, j in self.twin.joints.items()},
            }),
            "sync_status": "pending",
        }
        self.store.save_session(record)
        self.last_summary = {k: v for k, v in record.items() if not k.endswith("_json")}
        self.last_summary["repetitions"] = json.loads(record["repetitions_json"])
        self.session, self.evaluator = None, None
        if self.on_session_saved:
            self.on_session_saved()
        return self.last_summary

    # ------------------------------------------------------------- main loop
    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        estimator = PoseEstimator(self.settings.pose_model_path)
        cap = None
        last_encode = 0.0
        last_t = time.monotonic()
        is_file = not isinstance(self.settings.camera, int)

        while not self._stop_event.is_set():
            if cap is None:
                try:
                    cap = self._open_camera()
                    self.camera_error = None
                except RuntimeError as exc:
                    self.camera_error = str(exc)
                    self._publish(time.monotonic(), None)
                    time.sleep(2.0)
                    continue

            ok, frame = cap.read()
            if not ok:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.camera_error = "Camera frame not received"
                cap.release()
                cap = None
                continue

            t = time.monotonic()
            dt = t - last_t
            last_t = t
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt) if self.fps else 1.0 / dt
            self.frames += 1

            try:
                started = time.perf_counter()
                landmarks = estimator.detect(frame, int(t * 1000))
                self.pose_ms = 0.9 * self.pose_ms + 0.1 * (time.perf_counter() - started) * 1000
                with self._lock:
                    self._step(landmarks, t)
                    joints = self.twin.as_dict()
                    deviations = set(self.evaluator._active_deviations) if self.evaluator else set()
                if t - last_encode >= 1.0 / self.settings.stream_fps:
                    last_encode = t
                    self._draw_overlay(frame, landmarks, joints, deviations)
                    ok_jpg, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok_jpg:
                        self.jpeg, self.jpeg_seq = buf.tobytes(), self.jpeg_seq + 1
            except Exception:
                self.frame_errors += 1
                if self.session is not None:
                    self.session["frame_errors"] += 1
                log.exception("Frame processing error")

            self._publish(t, landmarks)

            if is_file:  # pace test videos to real time
                time.sleep(max(0.0, 1.0 / self.settings.camera_fps - (time.monotonic() - t)))

        if cap is not None:
            cap.release()
        estimator.close()

    def _step(self, landmarks, t: float) -> None:
        session, ev = self.session, self.evaluator
        calibrating = session is not None and session["phase"] == "calibrating"
        joints = self.twin.update(landmarks, t, calibrating=calibrating)
        if session is None or ev is None:
            return

        session["frames"] += 1
        if self.fps:
            session["fps_samples"].append(self.fps)

        if calibrating:
            required = self.cfg["exercises"][session["exercise_key"]]["required_joints"]
            if not all(joints[j].tracked for j in required):
                self.twin.start_calibration()
                session["calibration_started"] = t
                ev._say("positioning", f"Move into the camera view so your {session['side']} hip, knee, and ankle are visible.", "warning")
            elif t - session["calibration_started"] >= self.cfg["calibration_seconds"]:
                self.twin.finish_calibration(self.cfg["max_baseline_offset_deg"])
                session["phase"], session["started"] = "exercising", t
                ev._say("go", "Begin the exercise.", "info")
            return

        ev.update(joints, t)
        target = int(session["prescription"]["repetitions_target"])
        limit = int(session["prescription"]["duration_limit_seconds"])
        if ev.valid >= target:
            ev._say("done", "Repetition target reached. Session complete.", "success")
            self._finish_session(t, "target_reached")
        elif t - session["started"] >= limit:
            self._finish_session(t, "time_limit")

    # --------------------------------------------------------------- output
    def _draw_overlay(self, frame, landmarks, joints: dict, deviations: set) -> None:
        exercise = self.cfg["exercises"][self.exercise_key]
        dev_joints = {d["joint"] for d in exercise.get("deviations", []) if d["id"] in deviations}
        if landmarks:
            ids = LANDMARKS[self.side]
            chain = ["shoulder", "hip", "knee", "ankle", "foot"]
            pts = {n: landmarks[str(ids[n])] for n in chain}
            for a, b in zip(chain, chain[1:]):
                pa, pb = pts[a], pts[b]
                if min(pa.visibility, pb.visibility) >= self.cfg["min_landmark_visibility"]:
                    cv2.line(frame, (int(pa.x), int(pa.y)), (int(pb.x), int(pb.y)), COLORS["bone"], 4)
            for name in ("hip", "knee", "ankle"):
                p, j = pts[name], joints[name]
                color = COLORS["lost"] if not j["tracked"] else COLORS["deviation"] if name in dev_joints else COLORS["ok"]
                cv2.circle(frame, (int(p.x), int(p.y)), 12, color, -1)
                if j["angle"] is not None and j["tracked"]:
                    cv2.putText(frame, f"{name} {j['angle']:.0f}", (int(p.x) + 16, int(p.y) - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3, cv2.LINE_AA)
                    cv2.putText(frame, f"{name} {j['angle']:.0f}", (int(p.x) + 16, int(p.y) - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
        cv2.putText(frame, f"{self.fps:.1f} FPS", (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

    def _publish(self, t: float, landmarks) -> None:
        with self._lock:
            exercise = self.cfg["exercises"][self.exercise_key]
            session = self.session
            state = {
                "phase": session["phase"] if session else ("finished" if self.last_summary else "idle"),
                "camera_error": self.camera_error,
                "pose_detected": landmarks is not None,
                "fps": round(self.fps, 1),
                "pose_ms": round(self.pose_ms, 1),
                "frames": self.frames,
                "frame_errors": self.frame_errors,
                "side": self.side,
                "exercise_key": self.exercise_key,
                "exercise": {
                    "name": exercise["display_name"],
                    "posture": exercise["posture"],
                    "hip_motion": exercise["hip_motion"],
                    "primary_joint": exercise["primary_joint"],
                    "rom_standard_deg": exercise["rom_standard_deg"],
                    "instructions": exercise["instructions"],
                    "camera_view": exercise["camera_view"],
                },
                "joints": self.twin.as_dict(),
                "session": None,
                "evaluation": self.evaluator.snapshot() if self.evaluator else None,
                "last_summary": self.last_summary,
            }
            if session:
                elapsed = 0 if session["started"] is None else t - session["started"]
                state["session"] = {
                    "client_session_id": session["client_session_id"],
                    "patient": session["patient"],
                    "exercise_name": session["prescription"]["exercise"]["name"],
                    "repetitions_target": session["prescription"]["repetitions_target"],
                    "duration_limit_seconds": session["prescription"]["duration_limit_seconds"],
                    "elapsed_seconds": round(elapsed, 1),
                }
            self.state = state

    def snapshot(self) -> dict:
        with self._lock:
            return self.state
