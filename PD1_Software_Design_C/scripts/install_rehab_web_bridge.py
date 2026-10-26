import ast
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
SERVER = ROOT / "station" / "server.py"
ENGINE = ROOT / "station" / "engine.py"
HTML = ROOT / "web" / "index.html"
BACKEND = ROOT / "station" / "rehab_extension" / "web_bridge.py"
FRONTEND = ROOT / "web" / "rehab-web-bridge.js"
MARKER = "# PD1_REHAB_WEB_BRIDGE_V1"
HTML_MARKER = "<!-- PD1_REHAB_WEB_BRIDGE_V1 -->"

BACKEND_CODE = r'''
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
'''

FRONTEND_CODE = r'''
// Synchronizes renderer scope metadata only; no clinical computations.
const scopeMap = {
  component: "component", asset: "leg", system: "whole_body"
};
let queue = Promise.resolve();
let lastSuccessfulScope = null;

function scopeMessage(text) {
  let element = document.getElementById("rehab-scope-status");
  const selector = document.getElementById("twin-design");
  if (!selector) return;
  if (!element) {
    element = document.createElement("p");
    element.id = "rehab-scope-status";
    element.className = "hint";
    element.setAttribute("role", "status");
    selector.insertAdjacentElement("afterend", element);
  }
  element.textContent = text;
}

function sendScope(force = false) {
  const selector = document.getElementById("twin-design");
  const scope = scopeMap[selector?.value];
  if (!scope) return;
  queue = queue.catch(() => {}).then(async () => {
    if (!force && lastSuccessfulScope === scope) return;
    try {
      const response = await fetch("/api/rehab/design-scope", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({design_scope: scope}),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      lastSuccessfulScope = scope;
      scopeMessage(`Scope: ${scope}. Evaluation is unchanged.`);
    } catch (error) {
      scopeMessage(
        "Design renders locally, but scope metadata could not be saved. " +
        "Check station connection."
      );
      console.warn("Design-scope synchronization:", error);
    }
  });
}

const selector = document.getElementById("twin-design");
selector?.addEventListener("change", () => sendScope());
sendScope(true);
window.addEventListener("online", () => sendScope(true));
window.addEventListener("focus", () => sendScope(true));

// Also catch programmatic selection updates after avatar initialization.
const live = document.getElementById("screen-live");
if (live) {
  new MutationObserver(() => {
    if (!live.hidden) sendScope();
  }).observe(live, {attributes: true, attributeFilter: ["hidden"]});
}

async function refreshReferences() {
  const dialog = document.getElementById("rehab-about-dialog");
  if (!dialog) return;
  let section = document.getElementById("rehab-current-config");
  if (!section) {
    section = document.createElement("section");
    section.id = "rehab-current-config";
    dialog.append(section);
  }

  section.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = "Current configuration — live";
  section.append(heading);

  function paragraph(text) {
    const p = document.createElement("p");
    p.textContent = text;
    section.append(p);
  }

  try {
    const response = await fetch("/api/rehab/config-status", {
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    paragraph("Clinical deployment: NOT APPROVED.");
    paragraph(data.disclaimer);
    paragraph(
      `Mode: ${data.unapproved_mode}; extension enabled: ` +
      `${data.extension_enabled}; config: ${data.config_version}.`
    );
    paragraph(
      `Reference edition: ${data.reference_edition ?? "Not set"}. ` +
      `${data.reference_verification ?? ""}`
    );
    paragraph(`Configuration SHA-256: ${data.config_sha256}`);
    paragraph(
      "Approval flags are not authenticated PT approvals. " +
      "Approved clinical execution is still unavailable."
    );

    const list = document.createElement("ul");
    for (const [name, status] of Object.entries(data.exercise_status)) {
      const item = document.createElement("li");
      item.textContent =
        `${name}: configured approval flag ${status.configured_approval_flag}; ` +
        "verified approval: false";
      list.append(item);
    }
    section.append(list);

    for (const ref of data.references) {
      const title = document.createElement("h3");
      title.textContent = ref.title;
      section.append(title);
      for (const key of ["use", "status", "limitation", "requested_rule"]) {
        if (ref[key]) paragraph(ref[key]);
      }
      if (typeof ref.url === "string" && ref.url.startsWith("https://")) {
        const a = document.createElement("a");
        a.textContent = "Open reference";
        a.href = ref.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        section.append(a);
      }
    }
  } catch (error) {
    paragraph(
      "Current configuration could not be loaded. " +
      "The installation snapshot above is not approval evidence."
    );
    console.warn("Reference refresh:", error);
  }
}

document.getElementById("rehab-about-open")
  ?.addEventListener("click", refreshReferences);
'''

def main():
    required = [
        SERVER, ENGINE, HTML,
        ROOT / "station" / "rehab_extension" / "approval.py",
        ROOT / "web" / "rehab-about.js",
    ]
    if not all(path.is_file() for path in required):
        raise SystemExit(
            "STOP: server, approval guard, and About installation are required."
        )

    server_original = SERVER.read_bytes()
    html_original = HTML.read_bytes()
    server = server_original.decode("utf-8-sig")
    html = html_original.decode("utf-8-sig")

    if (
        MARKER in server or HTML_MARKER in html
        or BACKEND.exists() or FRONTEND.exists()
    ):
        raise SystemExit(
            "Bridge files/markers already exist. Nothing overwritten."
        )

    tree = ast.parse(server)
    definitions = {
        n.name for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "start_session" not in definitions:
        raise SystemExit("STOP: server structure differs.")
    if html.count("</body>") != 1:
        raise SystemExit("STOP: expected one HTML body.")

    server_new = (
        server + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.web_bridge import install "
        "as _install_rehab_web_bridge\n"
        "_install_rehab_web_bridge(app, engine)\n"
    )
    html_new = html.replace(
        "</body>",
        HTML_MARKER + "\n"
        '<script type="module" src="/static/rehab-web-bridge.js?v=1">'
        "</script>\n</body>",
        1,
    )

    compile(BACKEND_CODE, str(BACKEND), "exec")
    compile(server_new, str(SERVER), "exec")

    # Check scope mapping and actual FastAPI route registration using a stub.
    namespace = {"__file__": str(BACKEND)}
    exec(compile(BACKEND_CODE, str(BACKEND), "exec"), namespace)
    normalize = namespace["normalize_scope"]
    assert normalize("asset") == "leg"
    assert normalize("system") == "whole_body"
    assert normalize("component") == "component"
    try:
        normalize("invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid scope was accepted")

    from fastapi import FastAPI
    class Stub:
        def start_session(self, *args, **kwargs):
            raise ValueError("Unapproved exercise")
        def snapshot(self):
            return {"session": None}

    app, stub = FastAPI(), Stub()
    namespace["install"](app, stub)
    routes = {route.path: route for route in app.routes}
    assert "/api/rehab/design-scope" in routes
    assert "/api/rehab/config-status" in routes
    assert stub.snapshot()["rehab_design"]["metadata_only"] is True
    try:
        stub.start_session()
    except RuntimeError as exc:
        assert str(exc) == "Unapproved exercise"
    else:
        raise AssertionError("Approval rejection was not preserved")

    # Test the scope endpoint without starting a camera or server.
    import asyncio
    class RequestStub:
        async def json(self):
            return {"design_scope": "leg"}

    result = asyncio.run(
        routes["/api/rehab/design-scope"].endpoint(RequestStub())
    )
    assert result["evaluation_changed"] is False
    assert stub.snapshot()["rehab_design"]["design_scope"] == "leg"

    node = shutil.which("node")
    if node:
        result = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=FRONTEND_CODE, text=True, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = ROOT / "patch_backups" / f"web_bridge_{stamp}"
    backup.mkdir(parents=True)
    shutil.copy2(SERVER, backup / "server.py")
    shutil.copy2(HTML, backup / "index.html")

    if (
        SERVER.read_bytes() != server_original
        or HTML.read_bytes() != html_original
    ):
        raise RuntimeError("Project files changed during installation")

    try:
        BACKEND.write_text(BACKEND_CODE, encoding="utf-8")
        FRONTEND.write_text(FRONTEND_CODE, encoding="utf-8")
        SERVER.write_text(server_new, encoding="utf-8")
        HTML.write_text(html_new, encoding="utf-8")
    except Exception:
        SERVER.write_bytes(server_original)
        HTML.write_bytes(html_original)
        BACKEND.unlink(missing_ok=True)
        FRONTEND.unlink(missing_ok=True)
        raise

    print("WEB BRIDGE INSTALLED.")
    print("Scope mapping, route registration, and rejection checks passed.")
    print("JavaScript syntax: " + ("passed" if node else "not checked; Node unavailable"))
    print(f"Backup: {backup}")
    print("Clinical evaluation and model coloring remain unchanged.")
    print("Browser/camera verification is still required.")

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
