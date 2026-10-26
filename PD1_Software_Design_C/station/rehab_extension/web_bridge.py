
"""UI metadata and reference integration; never changes clinical evaluation."""
import hashlib
import json
import threading
from pathlib import Path
from functools import wraps

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "rehab_extension"

SCOPES = {
    "component": "component",
    "asset": "leg",
    "system": "whole_body",
}

def normalize_scope(value):
    if value in SCOPES:
        return SCOPES[value]
    if value in ("component", "leg", "whole_body"):
        return value
    raise ValueError("Unknown design scope")

def install(app, engine):
    if getattr(engine, "_rehab_web_bridge_installed", False):
        return

    from fastapi import HTTPException, Request

    # FastAPI resolves the Request annotation from module globals.
    globals()["Request"] = Request

    engine._rehab_scope_lock = threading.Lock()
    engine._rehab_scope = None
    engine._rehab_scope_events = []

    original_start = engine.start_session

    @wraps(original_start)
    def guarded_start(*args, **kwargs):
        try:
            return original_start(*args, **kwargs)
        except ValueError as exc:
            # Existing server already maps RuntimeError to HTTP 409.
            raise RuntimeError(str(exc)) from exc

    engine.start_session = guarded_start
    original_snapshot = engine.snapshot

    def snapshot():
        state = dict(original_snapshot())
        with engine._rehab_scope_lock:
            current = engine._rehab_scope
            events = [dict(event) for event in engine._rehab_scope_events]

        state["rehab_design"] = {
            "design_scope": current,
            "metadata_only": True,
            "scope_events": events,
        }
        if state.get("session") is not None:
            state["session"] = dict(state["session"])
            state["session"]["design_scope"] = current
        return state

    engine.snapshot = snapshot

    @app.post("/api/rehab/design-scope")
    async def set_scope(request: Request):
        try:
            payload = await request.json()
            scope = normalize_scope(payload.get("design_scope"))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, "Expected a valid design_scope")

        from datetime import datetime, timezone
        with engine._rehab_scope_lock:
            if scope != engine._rehab_scope:
                engine._rehab_scope = scope
                engine._rehab_scope_events.append({
                    "utc": datetime.now(timezone.utc).isoformat(),
                    "design_scope": scope,
                })
                # Only the latest transitions are included in live state.
                engine._rehab_scope_events = engine._rehab_scope_events[-20:]
        return {"design_scope": scope, "evaluation_changed": False}

    @app.get("/api/rehab/config-status")
    def config_status():
        try:
            documents = {}
            for name in (
                "settings.json", "exercises.json",
                "rom_reference.json", "references.json",
            ):
                documents[name] = json.loads(
                    (CONFIG / name).read_text(encoding="utf-8-sig")
                )
            settings = documents["settings.json"]
            exercises = documents["exercises.json"]
            canonical = json.dumps(
                documents, sort_keys=True, separators=(",", ":"),
                allow_nan=False,
            )
            return {
                "clinical_deployment_ready": False,
                "approval_verification_implemented": False,
                "config_sha256": hashlib.sha256(
                    canonical.encode("utf-8")
                ).hexdigest(),
                "config_version": settings.get("config_version"),
                "extension_enabled": settings.get("extension_enabled"),
                "unapproved_mode": settings.get("unapproved_mode"),
                "exercise_status": {
                    key: {
                        # This is a config flag, not verified approval.
                        "configured_approval_flag": value.get(
                            "approval", {}
                        ).get("approved", False),
                        "verified_approval": False,
                    }
                    for key, value in exercises["exercises"].items()
                },
                "reference_edition": documents[
                    "rom_reference.json"
                ].get("reference_edition"),
                "reference_verification": documents[
                    "rom_reference.json"
                ].get("verification_status"),
                "references": documents["references.json"]["references"],
                "disclaimer": settings["disclaimer"],
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                503, "Clinical configuration unavailable or invalid"
            ) from exc

    engine._rehab_web_bridge_installed = True


# Standalone Design C: no other scope is accepted.
def normalize_scope(value):
    if value not in ('system', 'whole_body'):
        raise ValueError("This application implements Design C only")
    return 'whole_body'
