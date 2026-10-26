"""Camera -> BlazePose Full -> Component Twin -> evaluation loop."""













import json






import logging






import sys






import threading






import time






import uuid






from datetime import datetime, timezone













import cv2













from station.orientation import OrientationTracker






from station.component_twin import ComponentTwinModel






from station.config import StationSettings, load_exercise_config






from station.exercises import ExerciseEvaluator, classify_arom






from station.pose import LANDMARKS, PoseEstimator






from station.storage import LocalStore













log = logging.getLogger("station.engine")













COLORS = {






    "ok": (80, 200, 80),






    "deviation": (40, 40, 230),






    "lost": (150, 150, 150),






    "bone": (255, 220, 120),






}




















class ExerciseEngine(threading.Thread):






    def __init__(






        self,






        settings: StationSettings,






        store: LocalStore,






        on_session_saved=None,






    ):






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






        self.orientation_tracker = OrientationTracker(






            self.cfg["min_landmark_visibility"]






        )






        self.orientation_state = None













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













    # ------------------------------------------------------------------






    # Setup






    # ------------------------------------------------------------------













    def _new_twin(self, side: str) -> ComponentTwinModel:






        return ComponentTwinModel(






            side,






            self.cfg["min_landmark_visibility"],






            self.cfg["filter"],






        )













    def _open_camera(self) -> cv2.VideoCapture:






        source = self.settings.camera






        if isinstance(source, int):






            backend = cv2.CAP_DSHOW if sys.platform == "win32" else (cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY)






            






            # Auto-fallback sequence: try configured index first, then alternative EMEET index






            candidates = [source, 0] if source == 1 else [source]






            cap = None













            for idx in candidates:






                temp_cap = cv2.VideoCapture(idx, backend)






                if temp_cap.isOpened():






                    if sys.platform != "win32":






                        temp_cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))






                    temp_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)






                    temp_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)






                    temp_cap.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)






                    temp_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)













                    # Validate that the stream actually produces valid image data






                    ret, test_frame = temp_cap.read()






                    if ret and test_frame is not None and test_frame.size > 0:






                        cap = temp_cap






                        break






                    else:






                        temp_cap.release()













            if cap is None:






                raise RuntimeError(f"Cannot acquire valid video feed from camera sources: {candidates}")






            return cap






        else:






            cap = cv2.VideoCapture(source)






            if not cap.isOpened():






                raise RuntimeError(f"Cannot open camera source {source!r}")






            return cap













    # ------------------------------------------------------------------






    # Session control






    # ------------------------------------------------------------------













    def set_preview(self, exercise_key: str, side: str) -> None:






        if (






            exercise_key not in self.cfg["exercises"]






            or side not in ("left", "right")






        ):






            raise ValueError("Unknown exercise or side")













        with self._lock:






            if self.session is not None:






                raise RuntimeError("A session is running")













            self.exercise_key = exercise_key






            self.side = side






            self.twin = self._new_twin(side)













    def start_session(






        self,






        patient: dict,






        prescription: dict,






        side: str,






    ) -> dict:






        key = prescription["exercise_key"]






        exercise_cfg = self.cfg["exercises"][key]













        with self._lock:






            if self.session is not None:






                raise RuntimeError("A session is already running")













            self.exercise_key = key






            self.side = side






            self.twin = self._new_twin(side)






            self.twin.start_calibration()













            self.evaluator = ExerciseEvaluator(






                key,






                exercise_cfg,






                self.cfg,






            )













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













            self.evaluator._say(






                "calibrate",






                "Hold still in the starting position.",






                "info",






            )













            from station.debug_pose_log import start as debug_start





            debug_start(self)





            self.last_summary = None













            return {






                "client_session_id": self.session["client_session_id"]






            }













    def pause_session(self) -> dict:






        """Freeze evaluation and session time, not just the browser display."""






        with self._lock:






            if self.session is None:






                raise RuntimeError("No session is running")






            if self.session["phase"] != "paused":






                self.session["phase_before_pause"] = self.session["phase"]






                self.session["pause_started"] = time.monotonic()






                self.session["phase"] = "paused"






            return {"phase": "paused"}













    def resume_session(self) -> dict:






        """Exclude paused time from duration, rep timing, hold, and deviations."""






        with self._lock:






            session = self.session






            if session is None:






                raise RuntimeError("No session is running")






            if session["phase"] == "paused":






                now = time.monotonic()






                paused_for = now - session.pop("pause_started")






                session["phase"] = session.pop("phase_before_pause")






                if session["started"] is not None:






                    session["started"] += paused_for






                if session["phase"] == "calibrating":






                    self.twin.start_calibration()






                    session["calibration_started"] = now






                # Reset derivatives after rest without erasing session ROM.






                self.twin.reset_tracking()






                for twin in self.twin.joints.values():






                    twin._last_t = None






                    twin.state.velocity_dps = 0.0






                ev = self.evaluator






                if ev is not None:






                    if ev.current is not None:






                        ev.current.started_at += paused_for






                    ev._last_t = None  # Do not credit paused time as a hold.






                    ev._deviation_since = {






                        key: since + paused_for






                        for key, since in ev._deviation_since.items()






                    }






            return {"phase": session["phase"]}













    def stop_session(self, reason: str = "stopped") -> dict | None:






        with self._lock:






            return self._finish_session(time.monotonic(), reason)













    def _finish_session(self, t: float, reason: str) -> dict | None:






        session = self.session






        ev = self.evaluator













        if session is None or ev is None:






            return None













        # A stop while paused must not add the current rest period to duration.






        if session["phase"] == "paused":






            t = session["pause_started"]













        if ev.current is not None:






            # The session stopped before the current repetition finished.






            rep = ev.current






            rep.ended_at = t






            rep.result = "incomplete"






            rep.arom = classify_arom(






                rep.peak_deg,






                ev.rom_standard,






                ev.tolerance,






            )






            ev.reps.append(rep)






            ev.current = None













        target = int(session["prescription"]["repetitions_target"])













        valid = ev.valid






        invalid = ev.count("invalid")






        incomplete = ev.count("incomplete")













        if valid >= target:






            status = "completed"






        elif valid + invalid + incomplete == 0:






            status = "cancelled"






        else:






            status = "incomplete"













        duration = (






            0






            if session["started"] is None






            else int(round(t - session["started"]))






        )













        arom, peak = ev.session_arom()













        if ev.reps and all(r.tracking_lost for r in ev.reps):






            arom = "Tracking unavailable"













        fps_samples = session["fps_samples"] or [0.0]






        frames = max(1, session["frames"])













        metrics = {






            "end_reason": reason,






            "measurement_space": "world_3d_inferred",






            "angle_method": "three_point_xyz_proxy",






            "clinical_3d_validated": False,






            "depth_sensor": False,






            "avg_fps": round(






                sum(fps_samples) / len(fps_samples),






                1,






            ),






            "min_fps": round(min(fps_samples), 1),






            "frames": session["frames"],






            "frame_errors": session["frame_errors"],






            "error_rate_percent": round(






                100.0 * session["frame_errors"] / frames,






                3,






            ),






            "feedback_latency_s": max(






                ev.feedback_latencies,






                default=None,






            ),






            "rom_standard_deg": ev.rom_standard,






            "baselines_deg": {






                key: joint.state.baseline






                for key, joint in self.twin.joints.items()






            },






        }













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






            "repetitions_json": json.dumps(






                [rep.as_dict() for rep in ev.reps]






            ),






            "metrics_json": json.dumps(metrics),






            "sync_status": "pending",






        }













        self.store.save_session(record)













        self.last_summary = {






            key: value






            for key, value in record.items()






            if not key.endswith("_json")






        }






        self.last_summary["repetitions"] = json.loads(






            record["repetitions_json"]






        )













        from station.debug_pose_log import end as debug_end





        debug_end(self, reason)





        self.session = None






        self.evaluator = None













        if self.on_session_saved:






            self.on_session_saved()













        return self.last_summary













    # ------------------------------------------------------------------






    # Main loop






    # ------------------------------------------------------------------













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






                    with self._lock:






                        self.twin.reset_tracking()






                    continue













                self.camera_error = "Camera frame not received"






                cap.release()






                cap = None






                continue













            t = time.monotonic()






            dt = t - last_t






            last_t = t













            if dt > 0:






                self.fps = (






                    0.9 * self.fps + 0.1 * (1.0 / dt)






                    if self.fps






                    else 1.0 / dt






                )













            self.frames += 1






            landmarks = None













            try:






                started = time.perf_counter()






                landmarks = estimator.detect(frame, int(t * 1000))













                self.pose_ms = (






                    0.9 * self.pose_ms






                    + 0.1 * (time.perf_counter() - started) * 1000






                )













                with self._lock:






                    self._step(landmarks, t)






                    joints = self.twin.as_dict()






                    deviations = (






                        set(self.evaluator._active_deviations)






                        if self.evaluator






                        else set()






                    )













                if t - last_encode >= 1.0 / self.settings.stream_fps:






                    last_encode = t













                    self._draw_overlay(






                        frame,






                        landmarks,






                        joints,






                        deviations,






                    )













                    ok_jpg, buf = cv2.imencode(






                        ".jpg",






                        frame,






                        [cv2.IMWRITE_JPEG_QUALITY, 70],






                    )













                    if ok_jpg:






                        self.jpeg = buf.tobytes()






                        self.jpeg_seq += 1













            except Exception:






                self.frame_errors += 1













                with self._lock:






                    if self.session is not None:






                        self.session["frame_errors"] += 1













                log.exception("Frame processing error")













                # Fallback: encode raw frame so webpage never shows a blank box






                ok_jpg, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])






                if ok_jpg:






                    self.jpeg, self.jpeg_seq = buf.tobytes(), self.jpeg_seq + 1













            self._publish(t, landmarks)













            if is_file:






                # Pace test videos to real time.






                time.sleep(






                    max(






                        0.0,






                        1.0 / self.settings.camera_fps






                        - (time.monotonic() - t),






                    )






                )













        if cap is not None:






            cap.release()













        estimator.close()













    def _step(self, landmarks, t: float) -> None:






        session = self.session






        ev = self.evaluator













        # Continue the raw camera stream while paused, but freeze all twin and






        # evaluator metrics (including hold and measured joint ROM).






        if session is not None and session["phase"] == "paused":






            return













        calibrating = (






            session is not None






            and session["phase"] == "calibrating"






        )













        world_landmarks = getattr(






            landmarks, "world_landmarks", None






        )













        session_id = (






            session.get("client_session_id") if session else None






        )






        if session_id != self.orientation_tracker.previous_session:






            self.orientation_tracker.reset()






            self.orientation_tracker.previous_session = session_id













        self.orientation_state = self.orientation_tracker.update(






            world_landmarks, t






        )













        joints = self.twin.update(






            world_landmarks,






            t,






            calibrating=calibrating,






        )






        from station.debug_pose_log import sample as debug_sample





        debug_sample(self, landmarks, t)












        if session is None or ev is None:






            return






        session["frames"] += 1













        if self.fps:






            session["fps_samples"].append(self.fps)













        if calibrating:






            required = self.cfg["exercises"][






                session["exercise_key"]






            ]["required_joints"]













            if not all(joints[joint].tracked for joint in required):






                self.twin.start_calibration()






                session["calibration_started"] = t













                ev._say(






                    "positioning",






                    (






                        "Move into the camera view so your "






                        f"{session['side']} hip, knee, and ankle "






                        "are visible."






                    ),






                    "warning",






                )













            elif (






                t - session["calibration_started"]






                >= self.cfg["calibration_seconds"]






            ):






                self.twin.finish_calibration(






                    self.cfg["max_baseline_offset_deg"]






                )













                session["phase"] = "exercising"






                session["started"] = t













                ev._say(






                    "go",






                    "Begin the exercise.",






                    "info",






                )













            return













        ev.update(joints, t)













        target = int(






            session["prescription"]["repetitions_target"]






        )






        limit = int(






            session["prescription"]["duration_limit_seconds"]






        )













        if ev.valid >= target:






            ev._say(






                "done",






                "Repetition target reached. Session complete.",






                "success",






            )






            self._finish_session(t, "target_reached")













        elif t - session["started"] >= limit:






            self._finish_session(t, "time_limit")













    # ------------------------------------------------------------------






    # Output






    # ------------------------------------------------------------------













    def _draw_overlay(self, frame, landmarks, joints: dict, deviations: set) -> None:






        exercise = self.cfg["exercises"][self.exercise_key]






        dev_joints = {d["joint"] for d in exercise.get("deviations", []) if d["id"] in deviations}






        if landmarks:






            ids = LANDMARKS[self.twin.active_side]






            chain = ["shoulder", "hip", "knee", "ankle", "foot"]






            pts = {n: landmarks[str(ids[n])] for n in chain}













            for first, second in zip(chain, chain[1:]):






                pa = pts[first]






                pb = pts[second]













                if (






                    min(pa.visibility, pb.visibility)






                    >= self.cfg["min_landmark_visibility"]






                ):






                    cv2.line(






                        frame,






                        (int(pa.x), int(pa.y)),






                        (int(pb.x), int(pb.y)),






                        COLORS["bone"],






                        4,






                    )













            for name in ("hip", "knee", "ankle"):






                point = pts[name]






                joint = joints[name]













                if not joint["tracked"]:






                    color = COLORS["lost"]






                elif name in dev_joints:






                    color = COLORS["deviation"]






                else:






                    color = COLORS["ok"]













                cv2.circle(






                    frame,






                    (int(point.x), int(point.y)),






                    12,






                    color,






                    -1,






                )













                if joint["angle"] is not None and joint["tracked"]:






                    label = f"{name} {joint['angle']:.0f}"






                    position = (






                        int(point.x) + 16,






                        int(point.y) - 10,






                    )













                    cv2.putText(






                        frame,






                        label,






                        position,






                        cv2.FONT_HERSHEY_SIMPLEX,






                        0.9,






                        (255, 255, 255),






                        3,






                        cv2.LINE_AA,






                    )













                    cv2.putText(






                        frame,






                        label,






                        position,






                        cv2.FONT_HERSHEY_SIMPLEX,






                        0.9,






                        color,






                        2,






                        cv2.LINE_AA,






                    )













        cv2.putText(






            frame,






            f"{self.fps:.1f} FPS",






            (16, 36),






            cv2.FONT_HERSHEY_SIMPLEX,






            1.0,






            (0, 255, 255),






            2,






            cv2.LINE_AA,






        )













    def _publish(self, t: float, landmarks) -> None:






        with self._lock:






            exercise = self.cfg["exercises"][self.exercise_key]






            session = self.session













            phase = (






                session["phase"]






                if session






                else "finished"






                if self.last_summary






                else "idle"






            )













            state = {






                "phase": phase,






                "camera_error": self.camera_error,






                "pose_detected": landmarks is not None,






                "orientation3d": (






                    self.orientation_state






                    if landmarks is not None else None






                ),






                "measurement_space": "world_3d_inferred",






                "clinical_3d_validated": False,






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






                "evaluation": (






                    self.evaluator.snapshot()






                    if self.evaluator






                    else None






                ),






                "last_summary": self.last_summary,






            }













            if session:






                elapsed = (






                    0






                    if session["started"] is None






                    else (session.get("pause_started", t) - session["started"])






                )













                state["session"] = {






                    "client_session_id": session["client_session_id"],






                    "patient": session["patient"],






                    "exercise_name": (






                        session["prescription"]["exercise"]["name"]






                    ),






                    "repetitions_target": (






                        session["prescription"]["repetitions_target"]






                    ),






                    "duration_limit_seconds": (






                        session["prescription"]["duration_limit_seconds"]






                    ),






                    "elapsed_seconds": round(elapsed, 1),






                }













            self.state = state













    def snapshot(self) -> dict:






        with self._lock:






            return self.state













# POSE3D_BACKEND_PATCH_V1













# POSE_ORIENTATION_PATCH_V1












# PD1_DEBUG_POSE_LOG_V1















# PD1_REHAB_LIVE_MEASUREMENTS_V1




from station.rehab_extension.live import install as _install_live_measurements




_install_live_measurements(ExerciseEngine)












# PD1_APPROVAL_GUARD_V1



from station.rehab_extension.approval import install as _install_approval_guard



_install_approval_guard(ExerciseEngine)









# PD1_REHAB_SESSION_BRIDGE_V1


from station.rehab_extension.session_bridge import install as _install_rehab_sessions


_install_rehab_sessions(ExerciseEngine)






# PD1_REHAB_JOINT_FEEDBACK_V1

from station.rehab_extension.joint_feedback import install as _install_joint_feedback

_install_joint_feedback(ExerciseEngine)



# PD1_HISTORY_RECOVERY_V1
from station.rehab_extension.history_recovery import install_recovery as _install_rehab_recovery
_install_rehab_recovery(ExerciseEngine)


# Reject prescriptions whose exercise was removed from this variant.
_pd1_variant_original_start = ExerciseEngine.start_session
def _pd1_variant_start(self, patient, prescription, side):
    key = prescription.get("exercise_key")
    if key not in self.cfg["exercises"]:
        raise RuntimeError(
            "This exercise is unavailable in this application. "
            "Select an ankle-pump prescription; an old prone-flexion "
            "prescription is not automatically converted."
        )
    return _pd1_variant_original_start(self, patient, prescription, side)
ExerciseEngine.start_session = _pd1_variant_start
