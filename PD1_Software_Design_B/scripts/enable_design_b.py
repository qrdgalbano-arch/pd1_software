import json, shutil, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "avatar" / "Design B" / "legs_rigged.glb"
CFG = ROOT / "config" / "avatar_map.json"
WANTED = {
    "left": {"hip": "CC_Base_L_Thigh", "knee": "CC_Base_L_Calf", "ankle": "CC_Base_L_Foot"},
    "right": {"hip": "CC_Base_R_Thigh", "knee": "CC_Base_R_Calf", "ankle": "CC_Base_R_Foot"},
}

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
joint_ids = {j for skin in gltf.get("skins", []) for j in skin.get("joints", [])}
if not joint_ids:
    sys.exit("legs_rigged.glb has no skin joints. Re-export it from Blender with Skinning on.")

names = sorted(nodes[i].get("name", "") for i in joint_ids)
print(f"{len(names)} skin joints found in {GLB.name}.")

missing = [n for side in WANTED.values() for n in side.values() if n not in names]
if missing:
    print("Missing expected bones:", ", ".join(missing))
    print("Leg-related joints that do exist:")
    for n in names:
        if any(k in n.lower() for k in ("thigh", "calf", "shin", "foot", "leg")):
            print("   ", n)
    sys.exit("No changes made. Paste this output so the mapping can be corrected.")

cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
shutil.copy2(CFG, CFG.with_name("avatar_map.before_design_b.json"))

asset = cfg["designs"]["asset"]
asset["enabled"] = True
asset["model_url"] = "/avatar/Design%20B/legs_rigged.glb"
asset["bones"] = WANTED
asset.pop("unavailable_message", None)
credit = dict(cfg["designs"]["system"].get("attribution", {}))
if credit:
    credit["title"] = credit.get("title", "Design C model") + " (legs-only derivative)"
    asset["attribution"] = credit

CFG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("Design B enabled. Backup saved as config\\avatar_map.before_design_b.json")
