"""List skeleton joints in a glTF avatar so config/avatar_map.json can be filled in.

Usage:  python scripts/list_avatar_bones.py avatar/scene.gltf   (.gltf or .glb)
"""

import json
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "avatar/scene.gltf")
if path.suffix.lower() == ".glb":
    data = path.read_bytes()
    chunk_length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + chunk_length].decode("utf-8"))
else:
    gltf = json.loads(path.read_text(encoding="utf-8"))
nodes = gltf.get("nodes", [])
joints = {j for skin in gltf.get("skins", []) for j in skin.get("joints", [])}
children = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}


meshes = gltf.get("meshes", [])
accessors = gltf.get("accessors", [])
triangles = 0
for mesh in meshes:
    for prim in mesh.get("primitives", []):
        acc = accessors[prim["indices"]] if "indices" in prim else accessors[prim["attributes"]["POSITION"]]
        triangles += acc["count"] // 3

print(f"{path}: {len(joints)} skeleton joints, {triangles} triangles")


def walk(index: int, level: int) -> None:
    if index in joints:
        print("  " * level + nodes[index].get("name", f"node{index}"))
        level += 1
    for child in nodes[index].get("children", []):
        walk(child, level)


for root in [i for i in range(len(nodes)) if i not in children]:
    walk(root, 0)
