// Component Twin avatar: each joint component (hip, knee, ankle) drives its own bone.
// Uses the Sketchfab glTF at /avatar/scene.gltf when present, otherwise a built-in
// low-poly articulated avatar. Body frame: Y up, model faces +Z, model's left = +X.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const DEG = Math.PI / 180;
const BODY_X = new THREE.Vector3(1, 0, 0);
const BODY_Z = new THREE.Vector3(0, 0, 1);
const STATUS_COLORS = { ok: 0x3fbf5f, deviation: 0xef4444, lost: 0x8a96a3 };

function normalize(name) {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function sideOf(name) {
  const n = name.toLowerCase();
  if (n.includes("left") || /(^|[^a-z0-9])l($|[^a-z0-9])/.test(n) || /^l[A-Z]/.test(name)) return "left";
  if (n.includes("right") || /(^|[^a-z0-9])r($|[^a-z0-9])/.test(n) || /^r[A-Z]/.test(name)) return "right";
  return null;
}

function roleOf(name) {
  const n = normalize(name);
  if (/toe|twist|roll|end$|nub/.test(n)) return null;
  if (/thigh|upleg|upperleg|femur/.test(n)) return "hip";
  if (/shin|calf|lowerleg|lowleg|tibia|knee/.test(n) || n.includes("leg")) return "knee";
  if (/foot|ankle/.test(n)) return "ankle";
  return null;
}

export class TwinAvatar {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0b1118);
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(2, 4, 3);
    this.scene.add(sun);
    this.grid = new THREE.GridHelper(4, 16, 0x2c3b4a, 0x1d2833);
    this.scene.add(this.grid);

    this.postureGroup = new THREE.Group();
    this.scene.add(this.postureGroup);
    this.bones = { left: {}, right: {} };
    this.markers = { left: {}, right: {} };
    this.display = { hip: 0, knee: 0, ankle: 0 };
    this.sign = {};
    this.posture = null;
    this.side = null;
    this.triangles = 0;
    this.source = "none";

    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.renderer.setAnimationLoop(() => this.render());
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  async load(mapUrl = "/config/avatar_map.json") {
    const map = await (await fetch(mapUrl)).json();
    this.sign = map.sign || {};
    let root = null;
    try {
      const gltf = await new GLTFLoader().loadAsync(map.model_url);
      root = gltf.scene;
      root.rotation.y = (map.model_yaw_deg || 0) * DEG;
      this.source = "glTF";
    } catch (err) {
      console.warn("Avatar model not found, using built-in Component Twin avatar.", err);
      root = this.buildProceduralAvatar();
      this.source = "built-in";
    }

    // Normalise height to 1.7 units, feet on y = 0, centred.
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const scale = 1.7 / (size.y || 1);
    root.scale.multiplyScalar(scale);
    const box2 = new THREE.Box3().setFromObject(root);
    const centre = box2.getCenter(new THREE.Vector3());
    root.position.sub(new THREE.Vector3(centre.x, box2.min.y, centre.z));
    this.postureGroup.add(root);
    this.root = root;

    this.triangles = 0;
    root.traverse((o) => {
      if (o.isMesh && o.geometry) {
        const g = o.geometry;
        this.triangles += (g.index ? g.index.count : g.attributes.position.count) / 3;
      }
    });

    if (this.source === "glTF") this.findBones(root, map.bones || {});
    if (!this.bones.left.hip || !this.bones.right.hip) {
      console.warn("Leg bones not detected; edit config/avatar_map.json. Bones found:",
        (() => { const n = []; root.traverse((o) => o.isBone && n.push(o.name)); return n; })());
    }
    this.captureRest();
    this.addMarkers();
    return { source: this.source, triangles: Math.round(this.triangles) };
  }

  findBones(root, overrides) {
    const all = [];
    root.traverse((o) => { if (o.isBone) all.push(o); });
    for (const side of ["left", "right"]) {
      for (const role of ["hip", "knee", "ankle"]) {
        const wanted = overrides?.[side]?.[role];
        let bone = wanted ? all.find((b) => b.name === wanted) : null;
        if (!bone) {
          const candidates = all
            .filter((b) => sideOf(b.name) === side && roleOf(b.name) === role)
            .sort((a, b) => a.name.length - b.name.length);
          bone = candidates[0] || null;
        }
        this.bones[side][role] = bone;
      }
    }
    console.info("Avatar bones:", Object.fromEntries(
      ["left", "right"].map((s) => [s, Object.fromEntries(
        Object.entries(this.bones[s]).map(([r, b]) => [r, b ? b.name : null]))])));
  }

  captureRest() {
    this.postureGroup.rotation.set(0, 0, 0);
    this.postureGroup.updateMatrixWorld(true);
    const rootInv = this.postureGroup.getWorldQuaternion(new THREE.Quaternion()).invert();
    for (const side of ["left", "right"]) {
      for (const bone of Object.values(this.bones[side])) {
        if (!bone) continue;
        bone.userData.restLocal = bone.quaternion.clone();
        const model = rootInv.clone().multiply(bone.getWorldQuaternion(new THREE.Quaternion()));
        bone.userData.restModelInv = model.invert();
      }
    }
  }

  addMarkers() {
    const geometry = new THREE.SphereGeometry(0.035, 12, 8);
    for (const side of ["left", "right"]) {
      for (const [role, bone] of Object.entries(this.bones[side])) {
        if (!bone) continue;
        const material = new THREE.MeshBasicMaterial({ color: STATUS_COLORS.lost, depthTest: false });
        const marker = new THREE.Mesh(geometry, material);
        marker.renderOrder = 10;
        bone.add(marker);
        const ws = bone.getWorldScale(new THREE.Vector3());
        marker.scale.setScalar(1 / (ws.x || 1));
        marker.visible = false;
        this.markers[side][role] = marker;
      }
    }
  }

  buildProceduralAvatar() {
    const skin = new THREE.MeshStandardMaterial({ color: 0xc8a27a, flatShading: true });
    const cloth = new THREE.MeshStandardMaterial({ color: 0x3b6ea8, flatShading: true });
    const root = new THREE.Group();
    const add = (parent, geometry, material, x, y, z) => {
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(x, y, z);
      parent.add(mesh);
      return mesh;
    };
    add(root, new THREE.BoxGeometry(0.34, 0.16, 0.2), cloth, 0, 0.95, 0);
    add(root, new THREE.BoxGeometry(0.36, 0.5, 0.2), cloth, 0, 1.28, 0);
    add(root, new THREE.SphereGeometry(0.11, 10, 8), skin, 0, 1.66, 0);
    for (const sx of [1, -1]) add(root, new THREE.BoxGeometry(0.08, 0.55, 0.08), skin, sx * 0.23, 1.25, 0);

    for (const [side, sx] of [["left", 1], ["right", -1]]) {
      const hip = new THREE.Group(); hip.name = `${side}_hip`; hip.position.set(sx * 0.1, 0.9, 0); root.add(hip);
      add(hip, new THREE.CylinderGeometry(0.065, 0.055, 0.44, 8), cloth, 0, -0.22, 0);
      const knee = new THREE.Group(); knee.name = `${side}_knee`; knee.position.set(0, -0.44, 0); hip.add(knee);
      add(knee, new THREE.CylinderGeometry(0.05, 0.04, 0.42, 8), skin, 0, -0.21, 0);
      const ankle = new THREE.Group(); ankle.name = `${side}_ankle`; ankle.position.set(0, -0.42, 0); knee.add(ankle);
      add(ankle, new THREE.BoxGeometry(0.08, 0.06, 0.22), cloth, 0, -0.03, 0.07);
      this.bones[side] = { hip, knee, ankle };
    }
    return root;
  }

  setPosture(posture, side) {
    if (posture === this.posture && side === this.side) return;
    this.posture = posture;
    this.side = side;
    for (const s of ["left", "right"]) {
      for (const bone of Object.values(this.bones[s])) if (bone) bone.quaternion.copy(bone.userData.restLocal);
    }
    const g = this.postureGroup;
    g.position.set(0, 0, 0);
    g.rotation.set(0, 0, 0);
    if (posture === "supine") g.rotation.x = -Math.PI / 2;
    else if (posture === "prone") g.rotation.x = Math.PI / 2;
    else if (posture === "side") g.rotation.z = side === "left" ? Math.PI / 2 : -Math.PI / 2;
    g.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(this.root);
    const centre = box.getCenter(new THREE.Vector3());
    g.position.set(-centre.x, -box.min.y, -centre.z);
    const target = new THREE.Vector3(0, (box.max.y - box.min.y) / 2 + 0.15, 0);
    const d = 2.6;
    if (posture === "side") this.camera.position.set(0, 0.9, d);
    else this.camera.position.set(side === "left" ? d : -d, 0.9, 0);
    this.controls.target.copy(target);
    this.controls.update();
    for (const s of ["left", "right"]) {
      for (const m of Object.values(this.markers[s])) if (m) m.visible = s === side;
    }
  }

  rotate(bone, axisBody, angle) {
    if (!bone) return;
    const axis = axisBody.clone().applyQuaternion(bone.userData.restModelInv).normalize();
    bone.quaternion.copy(bone.userData.restLocal).multiply(new THREE.Quaternion().setFromAxisAngle(axis, angle));
  }

  // angles: {hip, knee, ankle} in degrees; status: {hip: 'ok'|'deviation'|'lost', ...}
  update(angles, status, exercise, side) {
    if (!this.root) return;
    this.setPosture(exercise.posture, side);
    this.target = angles;
    this.status = status;
    this.hipMotion = exercise.hip_motion;
  }

  render() {
    if (this.target && this.side) {
      for (const j of ["hip", "knee", "ankle"]) {
        const t = this.target[j];
        if (typeof t === "number") this.display[j] += (t - this.display[j]) * 0.35;
      }
      const b = this.bones[this.side];
      const s = (k) => this.sign[k] ?? 1;
      const hip = this.display.hip * DEG;
      if (this.hipMotion === "abduction") this.rotate(b.hip, BODY_Z, (this.side === "left" ? 1 : -1) * hip * s("hip_abduction"));
      else if (this.hipMotion === "extension") this.rotate(b.hip, BODY_X, hip * s("hip_extension"));
      else this.rotate(b.hip, BODY_X, -hip * s("hip_flexion"));
      this.rotate(b.knee, BODY_X, this.display.knee * DEG * s("knee_flexion"));
      this.rotate(b.ankle, BODY_X, -this.display.ankle * DEG * s("ankle_dorsiflexion"));
      for (const [j, m] of Object.entries(this.markers[this.side])) {
        if (m) m.material.color.setHex(STATUS_COLORS[this.status?.[j] || "lost"]);
      }
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
