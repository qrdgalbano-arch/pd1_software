
"""Isolated, local-only demo. Never imports the patched clinical engine."""
import asyncio
import copy
import hashlib
import json
import math
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from station.config import get_settings
from station.pose import PoseEstimator
from station.orientation import OrientationTracker
from station.rehab_extension.angles import (
    measure, read_point, unit, sub, dot, hip_flexion
)
from station.rehab_extension.core import assess_arom, redness

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "demo_profile.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8-sig"))
DATA = ROOT / "data" / "isolated_demo"
LOGS = ROOT / "debug_pose_logs" / "isolated_demo"

def clean(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value

def cross(a, b):
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    )

def magnitude_stats(values):
    return {
        "average": sum(values)/len(values) if values else None,
        "best": max(values) if values else None,
    }

class Demo:
    def __init__(self, folder=DATA, logs=LOGS):
        self.folder, self.logs = Path(folder), Path(logs)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.jpeg = None
        self.error = None
        self.session = None
        self.summary = None
        self.file = None
        self.angles = {"left": {}, "right": {}}
        self.filtered = {}
        self.neutral = {}
        self.orientation = None
        self.feedback = {}
        self.prompt = {"text": "Demo ready.", "priority": 0, "seq": 0}
        self.prompt_at = 0
        self.previous = None
        self.profile_hash = hashlib.sha256(
            json.dumps(PROFILE, sort_keys=True).encode()
        ).hexdigest()
        self.recovered = 0
        for path in self.folder.glob("*.running.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                record.update(status="interrupted", clinical_approval=False)
                destination = self.folder / (path.stem + ".interrupted.json")
                destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
                path.unlink()
                self.recovered += 1
            except Exception as exc:
                self.error = "Demo recovery: " + str(exc)

    def write(self, event, **payload):
        if self.file:
            try:
                row = {
                    "event": event,
                    "utc": datetime.now(timezone.utc).isoformat(),
                    **payload,
                }
                self.file.write(json.dumps(clean(row), allow_nan=False) + "\n")
                self.file.flush()
            except Exception as exc:
                self.error = "Demo logging failed: " + str(exc)

    def say(self, text, priority, now):
        if text == self.prompt["text"]:
            return
        if (
            priority <= self.prompt["priority"]
            and now - self.prompt_at < PROFILE["feedback_hold_seconds"]
        ):
            return
        self.prompt = {
            "text": text, "priority": priority, "seq": self.prompt["seq"] + 1
        }
        self.prompt_at = now

    def start(self, key, side, scope):
        with self.lock:
            if self.session:
                raise ValueError("A demo exercise is already running")
            if key not in PROFILE["exercises"] or side not in ("left", "right"):
                raise ValueError("Unknown exercise or side")
            if scope not in ("component", "asset", "system"):
                raise ValueError("Unknown design")
            now = time.monotonic()
            identity = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
            self.filtered.clear()
            self.neutral.clear()
            self.previous = None
            self.summary = None
            self.feedback = {}
            self.session = {
                "id": identity,
                "exercise": key,
                "side": side,
                "scope": scope,
                "started": now,
                "utc": datetime.now(timezone.utc).isoformat(),
                "paused": False,
                "pause_started": None,
                "paused_seconds": 0.0,
                "reps": [],
                "current": None,
                "peaks": {},
                "times": {},
                "clinical_approval": False,
                "profile_hash": self.profile_hash,
                "hip_zero": "First tracked thigh direction relative to torso",
            }
            self.file = (self.logs / (identity + ".txt")).open("x", encoding="utf-8")
            marker = self.folder / (identity + ".running.json")
            marker.write_text(json.dumps({
                "id": identity, "exercise": key, "side": side,
                "status": "running", "profile_hash": self.profile_hash,
            }), encoding="utf-8")
            self.write("start", session=self.session, demo_profile=PROFILE)
            self.prompt_at = 0
            self.say(
                "DEMO: begin from your intended neutral position.",
                100, now
            )
            return {"started": True, "demo_only": True}

    def pause(self):
        with self.lock:
            if not self.session:
                raise ValueError("No demo session")
            session = self.session
            now = time.monotonic()
            if session["paused"]:
                session["paused_seconds"] += now - session["pause_started"]
                session["pause_started"] = None
                session["paused"] = False
                session["current"] = None
                self.write("resume")
            else:
                session["paused"] = True
                session["pause_started"] = now
                self.write("pause")
            self.previous = None
            return {"paused": session["paused"]}

    def readings(self, world):
        threshold = PROFILE["visibility"]
        frame = None
        try:
            lh = read_point(world, 23, threshold)
            rh = read_point(world, 24, threshold)
            ls = read_point(world, 11, threshold)
            rs = read_point(world, 12, threshold)
            x = unit(sub(lh, rh))
            up = sub(
                tuple((a+b)/2 for a,b in zip(ls, rs)),
                tuple((a+b)/2 for a,b in zip(lh, rh)),
            )
            y = unit(tuple(up[i] - dot(up, x)*x[i] for i in range(3)))
            z = unit(cross(x, y))
            frame = (x, y, z)
        except (ValueError, TypeError):
            pass

        result = {}
        for side, hip_id, knee_id in (("left",23,25), ("right",24,26)):
            joints = measure(world, side, threshold)
            if frame:
                try:
                    thigh = unit(sub(
                        read_point(world, knee_id, threshold),
                        read_point(world, hip_id, threshold)
                    ))
                    if side not in self.neutral:
                        self.neutral[side] = tuple(dot(thigh, a) for a in frame)
                    local = self.neutral[side]
                    down = tuple(
                        sum(local[j]*frame[j][i] for j in range(3))
                        for i in range(3)
                    )
                    angle = hip_flexion(
                        read_point(world, hip_id, threshold),
                        read_point(world, knee_id, threshold),
                        down, frame[2],
                    )
                    joints["hip"] = {
                        "angle": angle, "tracked": True,
                        "state": "Demo torso-referenced estimate",
                    }
                except (ValueError, TypeError):
                    pass
            for joint, reading in joints.items():
                key = (side, joint)
                raw = reading.get("angle")
                reading["raw_angle"] = raw
                if reading.get("tracked") and isinstance(raw, (int,float)):
                    old = self.filtered.get(key, raw)
                    smooth = old + PROFILE["smoothing_alpha"]*(raw-old)
                    self.filtered[key] = smooth
                    reading["angle"] = smooth
                else:
                    self.filtered.pop(key, None)
            joints["ankle"]["knee_position_deg"] = joints["knee"]["angle"]
            result[side] = joints
        return result

    def evaluate(self, now):
        session = self.session
        if not session or session["paused"]:
            self.previous = None
            self.feedback = {}
            return
        cfg = PROFILE["exercises"][session["exercise"]]
        joints = self.angles[session["side"]]
        moving = cfg["moving"]
        tolerance = PROFILE["support_tolerance_deg"]
        full_scale = PROFILE["redness_full_scale_deg"]
        feedback = {}
        candidates = []
        for joint in ("hip", "knee", "ankle"):
            reading = joints.get(joint, {})
            angle = reading.get("angle")
            if not reading.get("tracked") or angle is None:
                feedback[joint] = {
                    "tracked": False, "intensity": 0, "state": "Tracking uncertain"
                }
                continue
            if joint == moving:
                low, high = cfg["range"]
                deviation = angle - min(max(angle, low), high)
                inside = low <= angle <= high
            elif joint in cfg["support"]:
                deviation = angle - cfg["support"][joint]
                inside = abs(deviation) <= tolerance
            else:
                feedback[joint] = {
                    "tracked": True, "intensity": 0, "state": "Not monitored"
                }
                continue

            outside = abs(deviation) > tolerance
            feedback[joint] = {
                "tracked": True,
                "intensity": redness(
                    deviation, tolerance, full_scale,
                    approved=True, moving=joint == moving,
                    inside_prescribed_range=inside,
                ),
                "state": "Outside demo limits" if outside else "Within demo limits",
                "outside": outside,
                "clinical_approval": False,
                "rule_source": "synthetic_demo_profile",
            }
            if outside:
                candidates.append((80, f"DEMO: check {joint} position."))

        if self.previous:
            previous_t, previous_feedback = self.previous
            dt = now - previous_t
            if 0 < dt <= PROFILE["maximum_sample_gap_seconds"]:
                for joint in cfg["support"]:
                    totals = session["times"].setdefault(
                        joint, {"within":0.0, "outside":0.0, "uncertain":0.0}
                    )
                    before = previous_feedback.get(joint, {})
                    after = feedback.get(joint, {})
                    if not before.get("tracked") or not after.get("tracked"):
                        totals["uncertain"] += dt
                    elif before.get("outside") == after.get("outside"):
                        totals["outside" if after.get("outside") else "within"] += dt
                    else:
                        totals["uncertain"] += dt
        self.previous = (now, copy.deepcopy(feedback))
        self.feedback = feedback

        reading = joints.get(moving, {})
        if not reading.get("tracked") or reading.get("angle") is None:
            if session["current"]:
                session["current"]["tracking_lost"] = True
            self.say("Tracking uncertain. Keep the exercised leg visible.", 100, now)
            return

        value = reading["angle"]
        direction = "negative" if moving == "ankle" and value < 0 else "positive"
        magnitude = abs(value) if moving == "ankle" else value
        session["peaks"][direction] = max(
            session["peaks"].get(direction, 0), magnitude
        )

        other = self.angles["right" if session["side"] == "left" else "left"].get(moving,{})
        if (
            magnitude < cfg["start"]
            and other.get("tracked")
            and abs(other.get("angle") or 0) > cfg["start"]
        ):
            candidates.append((90, "DEMO: check that you are moving the selected leg."))

        if session["current"] is None and magnitude > cfg["start"]:
            session["current"] = {
                "peak": magnitude, "direction": direction,
                "tracking_lost": False, "outside": False,
                "started": now,
            }
        rep = session["current"]
        if rep:
            if direction == rep["direction"]:
                rep["peak"] = max(rep["peak"], magnitude)
            rep["outside"] |= any(
                feedback.get(joint,{}).get("outside", False)
                for joint in cfg["support"]
            )
            if magnitude <= cfg["rest"] or direction != rep["direction"]:
                target = cfg["targets"][rep["direction"]]
                rep["target_reached"] = (
                    not rep["tracking_lost"] and rep["peak"] >= target
                )
                rep["valid"] = not rep["tracking_lost"] and not rep["outside"]
                rep["ended"] = now
                session["reps"].append(rep)
                session["current"] = None
                candidates.append((
                    40 if not rep["valid"] else 10,
                    "DEMO: repetition recorded ? check form."
                    if not rep["valid"] else "Good. Demo repetition recorded."
                ))

        priority, text = max(
            candidates or [(10, "DEMO: continue slowly and follow the selected exercise.")],
            key=lambda item:item[0],
        )
        self.say(text, priority, now)
        if len(session["reps"]) >= PROFILE["repetitions"]:
            self.finish("demo_rep_count_reached")
        elif now - session["started"] - session["paused_seconds"] >= PROFILE["duration_seconds"]:
            self.finish("demo_time_limit")

    def finish(self, reason):
        with self.lock:
            session = self.session
            if not session:
                return self.summary
            cfg = PROFILE["exercises"][session["exercise"]]
            previous = []
            for path in self.folder.glob("*.summary.json"):
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    if (
                        item["exercise"] == session["exercise"]
                        and item["side"] == session["side"]
                        and item["profile_hash"] == self.profile_hash
                    ):
                        previous.append(item)
                except (ValueError, KeyError):
                    pass
            previous.sort(key=lambda item:item["utc"])
            previous = previous[-PROFILE["trend_sessions"]:]
            latest = previous[-1] if previous else None

            directions = {}
            for direction, reference in cfg["reference"].items():
                peaks = [
                    rep["peak"] for rep in session["reps"]
                    if rep["direction"] == direction and not rep["tracking_lost"]
                ]
                stats = magnitude_stats(peaks)
                prior = latest["directions"].get(direction,{}) if latest else {}
                peak = session["peaks"].get(direction)
                change = (
                    stats["average"] - prior["average"]
                    if stats["average"] is not None and prior.get("average") is not None
                    else None
                )
                directions[direction] = {
                    **stats, "peak_arom": peak, "reference": reference,
                    "assessment": assess_arom(peak, reference, None),
                    "previous_average": prior.get("average"),
                    "previous_best": prior.get("best"), "difference": change,
                    "trend": [
                        {"utc":item["utc"],"average":item["directions"].get(direction,{}).get("average")}
                        for item in previous
                    ],
                }

            support = {}
            for joint in cfg["support"]:
                counts = session["times"].get(
                    joint, {"within":0,"outside":0,"uncertain":0}
                )
                tracked = counts["within"] + counts["outside"]
                total = tracked + counts["uncertain"]
                support[joint] = {
                    **counts,
                    "within_percent":100*counts["within"]/tracked if tracked else None,
                    "coverage_percent":100*tracked/total if total else None,
                }

            summary = {
                "id":session["id"], "utc":session["utc"],
                "exercise":session["exercise"], "side":session["side"],
                "design_scope":session["scope"],
                "profile_hash":self.profile_hash,
                "mode":"SYNTHETIC DEMO ? NOT CLINICALLY APPROVED",
                "reason":reason,
                "reps_completed":len(session["reps"]),
                "valid_demo_reps":sum(rep["valid"] for rep in session["reps"]),
                "target_reached":sum(rep["target_reached"] for rep in session["reps"]),
                "target_not_reached":sum(not rep["target_reached"] for rep in session["reps"]),
                "unfinished_rep":session["current"] is not None,
                "directions":directions, "support":support,
                "repetitions":session["reps"],
                "has_previous":bool(previous),
                "clinical_approval":False,
                "hip_method":"First tracked torso-relative thigh direction defined as demo zero",
                "reference_note":(
                    "SLR reference is a synthetic demo expected AROM, not 120 degrees."
                    if session["exercise"] == "straight_leg_raise"
                    else "Population reference; not a safety limit or mandatory endpoint."
                ),
            }
            path = self.folder / (session["id"] + ".summary.json")
            path.write_text(json.dumps(clean(summary), indent=2, allow_nan=False), encoding="utf-8")
            marker = self.folder / (session["id"] + ".running.json")
            marker.unlink(missing_ok=True)
            self.write("end", summary=summary)
            if self.file:
                self.file.close()
                self.file = None
            self.summary = summary
            self.session = None
            self.feedback = {}
            self.say("Demo session finished. Review the summary.", 110, time.monotonic())
            return summary

    def snapshot(self):
        with self.lock:
            session = self.session
            elapsed = 0
            if session:
                now = session["pause_started"] if session["paused"] else time.monotonic()
                elapsed = now - session["started"] - session["paused_seconds"]
            return clean(copy.deepcopy({
                "demo_only":True, "clinical_approval":False,
                "camera_error":self.error,
                "session":session,
                "angles":self.angles,
                "orientation3d":self.orientation,
                "feedback":self.feedback,
                "prompt":self.prompt,
                "summary":self.summary,
                "elapsed":elapsed,
                "recovered_sessions":self.recovered,
                "profile":PROFILE,
            }))

    def run(self):
        cap = estimator = None
        try:
            settings = get_settings()
            estimator = PoseEstimator(settings.pose_model_path)
            tracker = OrientationTracker(PROFILE["visibility"])
            sources = [settings.camera]
            if isinstance(settings.camera, int) and settings.camera != 0:
                sources.append(0)
            for source in sources:
                candidate = (
                    cv2.VideoCapture(source, cv2.CAP_DSHOW)
                    if isinstance(source, int) else cv2.VideoCapture(source)
                )
                if candidate.isOpened():
                    cap = candidate
                    break
                candidate.release()
            if cap is None:
                raise RuntimeError("Camera could not be opened")
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    with self.lock:
                        self.error = "Camera frame unavailable"
                        self.feedback = {}
                    time.sleep(0.1)
                    continue
                now = time.monotonic()
                try:
                    landmarks = estimator.detect(frame, int(now*1000))
                    world = getattr(landmarks, "world_landmarks", None) or {}
                    readings = self.readings(world)
                    orientation = tracker.update(world, now)
                    with self.lock:
                        self.error = None
                        self.angles = readings
                        self.orientation = orientation
                        self.evaluate(now)
                        if self.session:
                            packed = {
                                str(i):{
                                    key:float(getattr(point,key))
                                    for key in ("x","y","z","visibility")
                                    if hasattr(point,key)
                                }
                                for i,point in world.items()
                            }
                            self.write(
                                "sample", monotonic_seconds=now,
                                world_landmarks=packed, angles=readings,
                                feedback=self.feedback, displayed_prompt=self.prompt,
                                paused=self.session["paused"],
                                profile_hash=self.profile_hash,
                            )
                    ok, encoded = cv2.imencode(".jpg", frame)
                    if ok:
                        self.jpeg = encoded.tobytes()
                except Exception as exc:
                    with self.lock:
                        self.error = "Demo tracking: " + str(exc)
                        self.feedback = {}
                    time.sleep(0.05)
        except Exception as exc:
            self.error = "Demo startup: " + str(exc)
        finally:
            if cap is not None:
                cap.release()
            if estimator is not None:
                estimator.close()

demo = Demo()

@asynccontextmanager
async def lifespan(app):
    demo.thread = threading.Thread(target=demo.run, daemon=True)
    demo.thread.start()
    yield
    demo.stop_event.set()
    demo.thread.join(timeout=3)
    demo.finish("demo_server_shutdown")

app = FastAPI(title="PD1 isolated demo", lifespan=lifespan)

@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "rehab-demo.html")

@app.get("/api/demo/state")
def state():
    return demo.snapshot()

@app.post("/api/demo/start")
def start(payload:dict):
    try:
        return demo.start(
            payload["exercise"], payload["side"], payload["scope"]
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc))

@app.post("/api/demo/pause")
def pause():
    try:
        return demo.pause()
    except ValueError as exc:
        raise HTTPException(409, str(exc))

@app.post("/api/demo/stop")
def stop():
    return demo.finish("demo_user_stop")

@app.post("/api/demo/neutral")
def neutral():
    with demo.lock:
        if demo.session:
            raise HTTPException(409,"Set demo zero before starting")
        demo.neutral.clear()
        demo.filtered.clear()
    return {"next_tracked_frame_is_demo_zero":True}

@app.post("/api/demo/scope")
def scope(payload:dict):
    selected = payload.get("scope")
    if selected not in ("component","asset","system"):
        raise HTTPException(422,"Unknown scope")
    with demo.lock:
        if demo.session:
            demo.session["scope"] = selected
            demo.write("scope", scope=selected)
    return {"scope":selected,"evaluation_changed":False}

@app.get("/api/demo/references")
def references():
    result = {}
    for name in ("references.json","rom_reference.json"):
        path = ROOT / "config" / "rehab_extension" / name
        if path.exists():
            result[name] = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "clinical_approval":False,
        "reference_verification":"Not performed by this demo",
        "documents":result,
    }

@app.get("/config/avatar_map.json")
def avatar_map():
    data = json.loads(
        (ROOT / "config" / "avatar_map.json").read_text(encoding="utf-8-sig")
    )
    designs = data.setdefault("designs", {})
    system = designs.get("system", {})
    if system:
        asset = copy.deepcopy(system)
        asset["enabled"] = True
        asset["normalized_height_m"] = 1.7
        asset["model_url"] = (
            "/avatar/Design%20B/scene.glb"
            if (ROOT/"avatar"/"Design B"/"scene.glb").exists()
            else system.get("model_url", "/avatar/Design%20C/scene.glb")
        )
        asset["leg_top_margin_m"] = 0.10
        asset["leg_midline_margin_m"] = 0.01
        designs["asset"] = asset
    return data

@app.get("/video.mjpg")
async def video():
    async def frames():
        while True:
            if demo.jpeg:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + demo.jpeg + b"\r\n"
                )
            await asyncio.sleep(0.1)
    return StreamingResponse(
        frames(), media_type="multipart/x-mixed-replace; boundary=frame"
    )

app.mount("/static", StaticFiles(directory=ROOT/"web"), name="static")
app.mount("/avatar", StaticFiles(directory=ROOT/"avatar"), name="avatar")
