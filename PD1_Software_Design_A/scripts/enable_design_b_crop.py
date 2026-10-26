import json, re, shutil, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "avatar" / "Design B" / "scene.glb"
CFG = ROOT / "config" / "avatar_map.json"
AVATAR_JS = ROOT / "web" / "avatar.js"
APP_JS = ROOT / "web" / "app.js"
WANTED = {
    "left": {"hip": "CC_Base_L_Thigh", "knee": "CC_Base_L_Calf", "ankle": "CC_Base_L_Foot"},
    "right": {"hip": "CC_Base_R_Thigh", "knee": "CC_Base_R_Calf", "ankle": "CC_Base_R_Foot"},
}

METHODS = r'''
  legClipPlanes() {
    if (!this.legPlanes) this.legPlanes = [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), 0),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    ];
    return this.legPlanes;
  }

  // Design B: same rig and model as Design C, but only the affected leg is drawn.
  updateLegClip() {
    const own = this.bones[this.side]?.hip;
    const other = this.bones[this.side === "left" ? "right" : "left"]?.hip;
    if (!own || !other) return;
    const a = own.getWorldPosition(new THREE.Vector3());
    const b = other.getWorldPosition(new THREE.Vector3());
    const lateral = a.clone().sub(b);
    if (lateral.lengthSq() < 1e-8) return;
    lateral.normalize();
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const up = new THREE.Vector3(0, 1, 0)
      .applyQuaternion(this.postureGroup.getWorldQuaternion(new THREE.Quaternion()));
    const midMargin = this.spec.leg_midline_margin_m ?? 0.01;
    const topMargin = this.spec.leg_top_margin_m ?? 0.10;
    const [side, top] = this.legClipPlanes();
    side.normal.copy(lateral);
    side.constant = midMargin - lateral.dot(mid);
    top.normal.copy(up).negate();
    top.constant = up.dot(a) + topMargin;
  }
'''

def read_gltf_json(path):
    data = path.read_bytes()
    if data[:4] != b"glTF":
        sys.exit("Not a binary GLB file.")
    offset = 12
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        if kind == 0x4E4F534A:
            return json.loads(data[offset + 8: offset + 8 + length])
        offset += 8 + length
    sys.exit("No JSON chunk found in the GLB.")

gltf = read_gltf_json(GLB)
nodes = gltf.get("nodes", [])
joint_ids = {j for s in gltf.get("skins", []) for j in s.get("joints", [])}
names = {nodes[i].get("name", "") for i in joint_ids}
missing = [n for side in WANTED.values() for n in side.values() if n not in names]
if not joint_ids or missing:
    sys.exit("Design B scene.glb is missing rig joints: %s. No changes made." % (missing or "no skin"))
print("Design B model has %d skin joints and all six control bones." % len(joint_ids))

src = AVATAR_JS.read_text(encoding="utf-8")
if "updateLegClip" in src:
    print("avatar.js already patched; skipping.")
else:
    new, n1 = re.subn(
        r'm\.clippingPlanes\s*=\s*design\s*===\s*"component"\s*\?\s*this\.planes\s*:\s*null;',
        'm.clippingPlanes = design === "component" ? this.planes : design === "asset" ? this.legClipPlanes() : null;',
        src)
    new, n2 = re.subn(r'\n[ \t]*frameCamera\(dt\)\s*\{', lambda m: METHODS + m.group(0), new)
    new, n3 = re.subn(r'(\}\s*else if\s*\(this\.design\s*===\s*"asset"\)\s*\{)',
                      lambda m: m.group(1) + "\n this.updateLegClip();", new)
    if (n1, n2, n3) != (1, 1, 1):
        sys.exit("avatar.js did not match the expected code (%s, %s, %s). No changes made." % (n1, n2, n3))
    shutil.copy2(AVATAR_JS, AVATAR_JS.with_name("avatar.before_design_b_crop.js"))
    AVATAR_JS.write_text(new, encoding="utf-8")
    print("avatar.js patched.")

app = APP_JS.read_text(encoding="utf-8")
app2, n4 = re.subn(r'(avatar\.js\?v=)single-twin-1', lambda m: m.group(1) + "single-twin-2", app)
if n4:
    shutil.copy2(APP_JS, APP_JS.with_name("app.before_design_b_crop.js"))
    APP_JS.write_text(app2, encoding="utf-8")
    print("app.js cache version bumped.")
else:
    print("app.js version string not found; use Ctrl+F5 in the browser.")

cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
shutil.copy2(CFG, CFG.with_name("avatar_map.before_design_b_crop.json"))
asset = cfg["designs"]["asset"]
asset.update({
    "enabled": True,
    "model_url": "/avatar/Design%20B/scene.glb",
    "normalized_height_m": 1.7,
    "bones": WANTED,
    "leg_top_margin_m": 0.10,
    "leg_midline_margin_m": 0.01,
})
asset.pop("unavailable_message", None)
credit = dict(cfg["designs"]["system"].get("attribution", {}))
if credit:
    credit["title"] = credit.get("title", "Design C model") + " (affected-leg crop)"
    asset["attribution"] = credit
CFG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("Config updated: Design B now uses the cropped whole-body model.")
