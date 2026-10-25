import asyncio
import importlib.util
import json
import struct
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, quote
from urllib.request import Request, urlopen

ROOT = Path.cwd()
BASE = "http://127.0.0.1:18080"
results = []

def record(test, status, detail):
    results.append(dict(test=test, status=status, detail=str(detail)))
    print(f"[{status}] {test}: {detail}", flush=True)

def get_json(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)

def check_http(path):
    request = Request(BASE + path, method="HEAD")
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")

def parse_model(path):
    if path.suffix.lower() == ".gltf":
        return json.loads(path.read_text(encoding="utf-8-sig"))

    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError("Truncated GLB header")
        magic, version, length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise ValueError("Expected GLB version 2")
        if length != path.stat().st_size:
            raise ValueError("GLB declared length differs from file size")
        while handle.tell() < length:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise ValueError("Truncated GLB chunk")
            size, kind = struct.unpack("<II", chunk_header)
            if handle.tell() + size > length:
                raise ValueError("Invalid GLB chunk length")
            if kind == 0x4E4F534A:
                return json.loads(handle.read(size))
            handle.seek(size, 1)
    raise ValueError("No GLB JSON chunk")

def test_design(label, key, configuration):
    name = f"Design {label}"
    try:
        spec = configuration.get("designs", {}).get(key)
        if not spec and key == "component":
            spec = configuration
        if not spec:
            raise ValueError("No configuration entry")
        if spec.get("enabled", True) is False:
            raise ValueError("Design is disabled")
        url = spec["model_url"]
        parsed = urlsplit(url)
        if parsed.netloc or not parsed.path.startswith("/avatar/"):
            raise ValueError("Expected a station-local /avatar/ model URL")

        check_http(url)
        relative = unquote(parsed.path.removeprefix("/avatar/"))
        avatar_root = (ROOT / "avatar").resolve()
        local = (avatar_root / relative).resolve()
        if not local.is_relative_to(avatar_root):
            raise ValueError("Model path escapes avatar directory")
        if not local.is_file():
            raise ValueError("Configured model missing locally")

        model = parse_model(local)
        nodes = model.get("nodes", [])
        indices = {
            index
            for skin in model.get("skins", [])
            for index in skin.get("joints", [])
        }
        if not indices:
            raise ValueError("Model has no skin joints")
        if any(not isinstance(i, int) or not 0 <= i < len(nodes) for i in indices):
            raise ValueError("Invalid skin joint index")

        names = {nodes[i].get("name", "") for i in indices}
        mappings = spec.get("bones", {})
        unresolved = []
        for side in spec.get("sides", ["left", "right"]):
            for role in ("hip", "knee", "ankle"):
                bone = mappings.get(side, {}).get(role)
                if bone is None:
                    unresolved.append(f"{side}.{role}")
                elif bone not in names:
                    raise ValueError(f"Missing mapped bone: {side}.{role}={bone}")

        dependencies = []
        for item in model.get("buffers", []) + model.get("images", []):
            uri = item.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            dependency = urljoin(url, quote(uri, safe="/%"))
            split = urlsplit(dependency)
            if split.scheme or split.netloc:
                raise ValueError("External model dependency needs separate review")
            check_http(dependency)
            dependencies.append(dependency)

        record(
            name + " asset/rig",
            "PASS",
            f"{local.name}; {len(indices)} skin joints; "
            f"{len(dependencies)} external assets reachable",
        )
        if unresolved:
            record(
                name + " bone mapping",
                "REVIEW",
                "Automatic mapping required: " + ", ".join(unresolved),
            )
        else:
            record(name + " bone mapping", "PASS", "All configured controls exist")

        record(
            name + " rendering/movement",
            "NOT TESTED",
            "Requires browser and visual movement checks",
        )
    except Exception as exc:
        record(name, "FAIL", exc)

async def test_websocket():
    try:
        import websockets
    except ImportError:
        record("Live WebSocket", "NOT TESTED", "Python websockets package unavailable")
        return
    try:
        async with websockets.connect(
            "ws://127.0.0.1:18080/ws/state",
            open_timeout=10,
        ) as socket:
            message = await asyncio.wait_for(socket.recv(), timeout=10)
            state = json.loads(message)
            if not isinstance(state, dict):
                raise ValueError("Expected a JSON state object")
            record(
                "Live WebSocket", "PASS",
                f"Connected; phase={state.get('phase', 'unknown')}",
            )
            record(
                "Extension stream",
                "PASS" if "rehab_measurements" in state else "REVIEW",
                state.get("rehab_measurements", {}).get(
                    "state", "rehab_measurements field absent"
                ),
            )
            error = state.get("rehab_recording_error")
            if error:
                record("Extension recording status", "FAIL", error)
    except Exception as exc:
        record("Live WebSocket", "FAIL", exc)

def main():
    try:
        configuration = get_json("/config/avatar_map.json")
        record("Station/configuration", "PASS", BASE)
    except Exception as exc:
        record("Station/configuration", "FAIL", exc)
        configuration = {}

    if configuration:
        for label, key in (
            ("A", "component"), ("B", "asset"), ("C", "system")
        ):
            test_design(label, key, configuration)

    try:
        response = get_json("/api/patients")
        patients = response.get("patients", [])
        record(
            "Shared patient loading",
            "PASS" if patients else "REVIEW",
            f"{len(patients)} patients; source={response.get('source')}",
        )
    except Exception as exc:
        record("Shared patient loading", "FAIL", exc)

    asyncio.run(test_websocket())

    folder = ROOT / "data" / "rehab_extension_reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (
        "design_tests_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    )
    path.write_text(
        json.dumps(
            {"station": BASE, "results": results}, indent=2
        ) + "\n",
        encoding="utf-8",
    )
    failures = sum(r["status"] == "FAIL" for r in results)
    print(f"\nFailures: {failures}")
    print(f"Report: {path}")
    print("Asset/rig PASS does not establish correct rendering or clinical accuracy.")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
