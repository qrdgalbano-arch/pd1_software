"""No camera or backend required: session lifecycle uses an in-memory store."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from station.config import StationSettings
from station.engine import ExerciseEngine
from station.exercises import Repetition


@pytest.fixture
def engine(monkeypatch):
    settings = StationSettings(_env_file=None)
    station = ExerciseEngine(settings, Mock())
    station.start_session(
        {"id": 1, "full_name": "Test fixture (not a real patient)"},
        {"id": 1, "exercise_key": "straight_leg_raising", "exercise": {"name": "Straight Leg Raising"}, "repetitions_target": 10, "duration_limit_seconds": 180},
        "left",
    )
    station.session["phase"] = "exercising"
    station.session["started"] = 100.0
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 110.0)
    return station


def test_pause_freezes_elapsed_and_is_idempotent(engine, monkeypatch):
    assert engine.pause_session() == {"phase": "paused"}
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 150.0)
    assert engine.pause_session() == {"phase": "paused"}
    assert engine.session["pause_started"] == 110.0
    engine._publish(150.0, None)
    assert engine.snapshot()["session"]["elapsed_seconds"] == 10.0


def test_resume_excludes_rest_from_clocks_and_rep_hold(engine, monkeypatch):
    engine.evaluator.current = Repetition(number=1, started_at=105.0)
    engine.evaluator._last_t = 109.0
    engine.evaluator._deviation_since = {"knee_bent": 108.0}
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 150.0)
    assert engine.resume_session() == {"phase": "exercising"}
    assert engine.session["started"] == 140.0
    assert engine.evaluator.current.started_at == 145.0
    assert engine.evaluator._last_t is None
    assert engine.evaluator._deviation_since["knee_bent"] == 148.0
    engine._publish(155.0, None)
    assert engine.snapshot()["session"]["elapsed_seconds"] == 15.0


def test_paused_step_does_not_evaluate_or_reach_time_limit(engine):
    engine.pause_session()
    evaluator = engine.evaluator
    evaluator.update = Mock()
    engine.twin.update = Mock(return_value={})
    engine._step(None, 900.0)
    evaluator.update.assert_not_called()
    engine.twin.update.assert_not_called()
    assert engine.session is not None


def test_stop_while_paused_uses_active_duration(engine, monkeypatch):
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 250.0)
    summary = engine.stop_session()
    assert summary["duration_seconds"] == 10
    assert summary["status"] == "cancelled"
    engine.store.save_session.assert_called_once()


def test_stop_mid_rep_while_paused_excludes_rest(engine, monkeypatch):
    engine.evaluator.current = Repetition(number=1, started_at=105.0)
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 250.0)
    summary = engine.stop_session()
    assert summary["repetitions"][0]["duration_s"] == 5.0
    assert summary["incomplete_repetitions"] == 1


def test_resume_calibration_restarts_still_position_window(engine, monkeypatch):
    engine.session["phase"] = "calibrating"
    engine.session["started"] = None
    engine.twin.start_calibration = Mock()
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 150.0)
    assert engine.resume_session() == {"phase": "calibrating"}
    assert engine.session["calibration_started"] == 150.0
    engine.twin.start_calibration.assert_called_once()


def test_multiple_pauses_exclude_all_rest(engine, monkeypatch):
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 130.0)
    engine.resume_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 140.0)
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 160.0)
    engine.resume_session()
    engine._publish(170.0, None)
    assert engine.snapshot()["session"]["elapsed_seconds"] == 30.0


def test_pause_and_resume_without_session_raise(engine):
    engine.session = None
    with pytest.raises(RuntimeError, match="No session"):
        engine.pause_session()
    with pytest.raises(RuntimeError, match="No session"):
        engine.resume_session()


def test_http_pause_resume_routes_return_conflict_without_session(monkeypatch):
    from fastapi.testclient import TestClient
    from station import server

    monkeypatch.setattr(server, "engine", SimpleNamespace(
        pause_session=Mock(side_effect=RuntimeError("No session is running")),
        resume_session=Mock(side_effect=RuntimeError("No session is running")),
    ))
    # Do not start lifespan: no camera, model, or sync worker in this test.
    client = TestClient(server.app)
    assert client.post("/api/session/pause").status_code == 409
    assert client.post("/api/session/resume").status_code == 409


def test_resume_resets_derivatives_without_erasing_rom(engine, monkeypatch):
    knee = engine.twin.joints["knee"]
    knee.state.rom_max = 72.0
    knee.state.hold_seconds = 2.5
    knee._last_t = 109.0
    knee.state.velocity_dps = 40.0
    engine.pause_session()
    monkeypatch.setattr("station.engine.time.monotonic", lambda: 150.0)
    engine.resume_session()
    assert knee._last_t is None
    assert knee.state.velocity_dps == 0.0
    assert knee.state.rom_max == 72.0
    assert knee.state.hold_seconds == 2.5


def test_http_pause_resume_success(monkeypatch):
    from fastapi.testclient import TestClient
    from station import server

    monkeypatch.setattr(server, "engine", SimpleNamespace(
        pause_session=Mock(return_value={"phase": "paused"}),
        resume_session=Mock(return_value={"phase": "exercising"}),
    ))
    client = TestClient(server.app)
    assert client.post("/api/session/pause").json() == {"phase": "paused"}
    assert client.post("/api/session/resume").json() == {"phase": "exercising"}
