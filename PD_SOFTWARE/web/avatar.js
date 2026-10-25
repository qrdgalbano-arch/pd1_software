// One renderer, one model, three explicit scopes. No procedural-model fallback.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const DEG = Math.PI / 180;
const BODY_X = new THREE.Vector3(1, 0, 0);
const BODY_Z = new THREE.Vector3(0, 0, 1);
const ROLES = ["hip", "knee", "ankle"];
const SIDES = ["left", "right"];
const COLORS = { ok: 0x3fbf5f, deviation: 0xef4444, lost: 0x8a96a3 };
const SKELETON_A = {
  left: { hip: "lThigh_0100", knee: "lShin_0101", ankle: "lFoot_0102" },
  right: { hip: "rThigh_083", knee: "rShin_084", ankle: "rFoot_085" },
};

function sideOf(name) {
  if (/left/i.test(name) || /(^|[^a-z0-9])l($|[^a-z0-9])/i.test(name) || /^l[A-Z]/.test(name)) return "left";
  if (/right/i.test(name) || /(^|[^a-z0-9])r($|[^a-z0-9])/i.test(name) || /^r[A-Z]/.test(name)) return "right";
  return null;
}
function roleOf(name) {
  const n = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (/toe|twist|roll|end\d*$|nub/.test(n)) return null;
  if (/thigh|upleg|upperleg/.test(n)) return "hip";
  if (/shin|calf|lowerleg|lowleg|knee/.test(n)) return "knee";
  if (/foot|ankle/.test(n)) return "ankle";
  // Anatomical accessory bones are not preferred over the main controls.
  if (/femur/.test(n)) return "hip";
  if (/tibia|leg/.test(n)) return "knee";
  return null;
}
function disposeTree(root) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  root.traverse((o) => {
    if (o.geometry) geometries.add(o.geometry);
    for (const m of Array.isArray(o.material) ? o.material : o.material ? [o.material] : []) {
      materials.add(m);
      for (const value of Object.values(m)) if (value?.isTexture) textures.add(value);
    }
    if (o.isSkinnedMesh) o.skeleton?.dispose();
  });
  for (const t of textures) { t.dispose(); if (typeof t.image?.close === "function") t.image.close(); }
  for (const m of materials) m.dispose();
  for (const g of geometries) g.dispose();
}

export class TwinAvatar {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xedf2f0);
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.005, 100);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.localClippingEnabled = true;
    this.renderer.domElement.setAttribute("aria-hidden", "true");
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enablePan = false;
    this.controls.enableDamping = false;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(2, 4, 3);
    this.scene.add(sun);
    this.postureGroup = new THREE.Group();
    this.scene.add(this.postureGroup);
    this.design = "component";
    this.focusJoint = "knee";
    this.follow = true;
    this.bones = { left: {}, right: {} };
    this.markers = { left: {}, right: {} };
    this.display = { hip: 0, knee: 0, ankle: 0 };
    this.sign = {};
    this.source = "none";
    this.generation = 0;
    this.disposed = false;
    this.focusDirty = true;
    this.planes = [BODY_X, BODY_X.clone().negate(), new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, -1, 0), BODY_Z, BODY_Z.clone().negate()]
      .map((n) => new THREE.Plane(n.clone(), 0));
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(container);
    this.resize();
    this.renderer.setAnimationLoop((time) => this.render(time));
  }

  setTheme(dark) { this.scene.background.set(dark ? 0x1d2a23 : 0xedf2f0); }
  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.focusDirty = true;
  }
  async load(mapUrl = "/config/avatar_map.json") {
    const response = await fetch(mapUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`Avatar configuration HTTP ${response.status}`);
    this.map = await response.json();
    return this.setDesign(this.map.default_design || "component");
  }
  configFor(design) {
    const configured = this.map?.designs?.[design];
    if (configured) return configured;
    // Compatibility with the original v5 configuration; only A inherits it.
    if (design === "component") return {
      model_url: this.map?.model_url || "/avatar/Design%20A/scene.gltf",
      model_yaw_deg: this.map?.model_yaw_deg || 0,
      bones: this.map?.bones || SKELETON_A,
      sign: this.map?.sign || {}, enabled: true,
    };
    return { enabled: false, unavailable_message: `Design ${design === "asset" ? "B" : "C"} is not configured yet.` };
  }
  clearModel() {
    if (this.root) { this.postureGroup.remove(this.root); disposeTree(this.root); }
    this.root = null;
    this.bones = { left: {}, right: {} };
    this.markers = { left: {}, right: {} };
    this.source = "none";
    this.triangles = 0;
    this.posture = null;
    this.side = null;
    this.restBox = null;
    this.display = { hip: 0, knee: 0, ankle: 0 };
  }
  async setDesign(design) {
    if (!["component", "asset", "system"].includes(design)) throw new Error("Unknown twin design");
    const generation = ++this.generation;
    this.clearModel();
    this.design = design;
    this.spec = this.configFor(design);
    this.sign = this.spec.sign || {};
    this.focusDirty = true;
    if (this.spec.enabled === false || !this.spec.model_url) return {
      ready: false, source: "not configured", triangles: 0,
      reason: this.spec.unavailable_message || "This design's own model is not configured yet.",
    };
    let root;
    try {
      const gltf = await new GLTFLoader().loadAsync(this.spec.model_url);
      root = gltf.scene;
      if (generation !== this.generation || this.disposed) { disposeTree(root); return { stale: true }; }
      // A wrapper preserves any authored scene-root transforms.
      const wrapper = new THREE.Group();
      wrapper.add(root);
      root = wrapper;
      root.rotation.y = (this.spec.model_yaw_deg || 0) * DEG;
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      if (!Number.isFinite(size.y) || size.y <= 0) throw new Error("Model has no measurable geometry");
      root.scale.setScalar((this.spec.normalized_height_m || (design === "asset" ? 0.95 : 1.7)) / size.y);
      root.updateMatrixWorld(true);
      const fitted = new THREE.Box3().setFromObject(root);
      const center = fitted.getCenter(new THREE.Vector3());
      root.position.sub(new THREE.Vector3(center.x, fitted.min.y, center.z));
      this.root = root;
      this.postureGroup.rotation.set(0, 0, 0);
      this.postureGroup.position.set(0, 0, 0);
      this.postureGroup.add(root);
      this.findBones(root, this.spec.bones || {});
      // An unrigged download must not masquerade as a moving digital twin.
      for (const s of SIDES) {
        if (this.spec.sides && !this.spec.sides.includes(s)) continue;
        for (const role of ROLES) if (!this.bones[s][role]) throw new Error(`Missing ${s} ${role} control bone; check this design's bones mapping`);
      }
      this.triangles = 0;
      root.traverse((o) => {
        if (o.isSkinnedMesh) o.frustumCulled = false;
        if (!o.geometry || !o.material) return;
        if (o.isMesh) this.triangles += (o.geometry.index?.count ?? o.geometry.attributes.position.count) / 3;
        const prepare = (m) => {
          m.clippingPlanes = design === "component" ? this.planes : design === "asset" ? this.legClipPlanes() : null;
          m.clipIntersection = false;
          m.needsUpdate = true;
          return m;
        };
        o.material = Array.isArray(o.material) ? o.material.map(prepare) : prepare(o.material);
      });
      this.captureRest();
      this.addMarkers();
      this.source = "glTF";
      this.setPosture("standing", this.spec.sides?.[0] || "left");
      if (this.latestFrame) this.update(...this.latestFrame);
      console.info("Twin model loaded:", design, this.spec.model_url);
      return { ready: true, source: "glTF", triangles: Math.round(this.triangles), model_url: this.spec.model_url };
    } catch (error) {
      if (generation !== this.generation || this.disposed) {
        if (root) disposeTree(root);
        return { stale: true };
      }
      if (this.root) this.clearModel(); else if (root) disposeTree(root);
      console.warn(`Twin ${design} unavailable:`, error);
      return { ready: false, source: "unavailable", triangles: 0,
        reason: `Could not use this design's model: ${error.message}. No substitute model was loaded.` };
    }
  }
  findBones(root, overrides) {
    const all = [];
    root.traverse((o) => { if (o.isBone) all.push(o); });
    for (const side of SIDES) for (const role of ROLES) {
      const wanted = overrides?.[side]?.[role];
      const candidates = all.filter((b) => sideOf(b.name) === side && roleOf(b.name) === role)
        .sort((a, b) => a.name.length - b.name.length);
      this.bones[side][role] = wanted ? all.find((b) => b.name === wanted) || null : candidates[0] || null;
    }
    console.info("Avatar bones:", Object.fromEntries(SIDES.map((s) => [s,
      Object.fromEntries(ROLES.map((r) => [r, this.bones[s][r]?.name || null]))])));
  }
  captureRest() {
    this.postureGroup.updateMatrixWorld(true);
    const inv = this.postureGroup.getWorldQuaternion(new THREE.Quaternion()).invert();
    for (const s of SIDES) for (const bone of Object.values(this.bones[s])) {
      if (!bone) continue;
      bone.userData.restLocal = bone.quaternion.clone();
      bone.userData.restModelInv = inv.clone().multiply(bone.getWorldQuaternion(new THREE.Quaternion())).invert();
    }
  }
  addMarkers() {
    const geometry = new THREE.SphereGeometry(0.018, 12, 8);
    for (const s of SIDES) for (const [role, bone] of Object.entries(this.bones[s])) {
      if (!bone) continue;
      const marker = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: COLORS.lost, depthTest: false }));
      marker.renderOrder = 10;
      bone.add(marker);
      const scale = bone.getWorldScale(new THREE.Vector3());
      marker.scale.setScalar(1 / Math.max(Math.abs(scale.x), 0.0001));
      marker.visible = false;
      this.markers[s][role] = marker;
    }
  }
  setFocusJoint(joint) {
    if (!ROLES.includes(joint) || joint === this.focusJoint) return;
    this.focusJoint = joint;
    this.focusDirty = true;
  }
  setFollow(enabled) { this.follow = Boolean(enabled); this.focusDirty = true; }
  recenter() { this.focusDirty = true; }
  setPosture(posture, side) {
    if (!this.root || (this.posture === posture && this.side === side)) return;
    this.posture = posture;
    this.side = side;
    this.display = { hip: 0, knee: 0, ankle: 0 };
    for (const s of SIDES) for (const bone of Object.values(this.bones[s]))
      if (bone) bone.quaternion.copy(bone.userData.restLocal);
    const g = this.postureGroup;
    g.position.set(0, 0, 0);
    g.rotation.set(0, 0, 0);
    if (posture === "supine") g.rotation.x = -Math.PI / 2;
    else if (posture === "prone") g.rotation.x = Math.PI / 2;
    else if (posture === "side") g.rotation.z = side === "left" ? Math.PI / 2 : -Math.PI / 2;
    g.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(this.root);
    const center = box.getCenter(new THREE.Vector3());
    g.position.set(-center.x, -box.min.y, -center.z);
    g.updateMatrixWorld(true);
    this.restBox = new THREE.Box3().setFromObject(this.root);
    this.focusDirty = true;
  }
  rotate(bone, axisBody, angle) {
    if (!bone) return;
    const axis = axisBody.clone().applyQuaternion(bone.userData.restModelInv).normalize();
    bone.quaternion.copy(bone.userData.restLocal).multiply(new THREE.Quaternion().setFromAxisAngle(axis, angle));
  }
  update(angles, status, exercise, side) {
    this.latestFrame = [angles, status, exercise, side];
    if (!this.root || !exercise || !SIDES.includes(side)) return;
    if (this.spec.sides && !this.spec.sides.includes(side)) {
      this.root.visible = false;
      return;
    }
    this.root.visible = true;
    this.setPosture(exercise.posture, side);
    this.target = angles;
    this.status = status;
    this.hipMotion = exercise.hip_motion;
  }
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

  frameCamera(dt) {
    if (!this.root?.visible) return;
    const center = new THREE.Vector3();
    let radius;
    if (this.design === "component") {
      const bone = this.bones[this.side]?.[this.focusJoint];
      if (!bone) return;
      bone.getWorldPosition(center);
      radius = this.spec.focus_radius_m?.[this.focusJoint] || { hip: 0.20, knee: 0.17, ankle: 0.16 }[this.focusJoint];
      // The model/rig is intact. This moving clipping window hides everything
      // outside the selected joint region without deleting bones or weights.
      for (const plane of this.planes) plane.constant = radius - plane.normal.dot(center);
    } else if (this.design === "asset") {
 this.updateLegClip();
      const points = ROLES.map((r) => this.bones[this.side]?.[r]?.getWorldPosition(new THREE.Vector3())).filter(Boolean);
      const box = new THREE.Box3().setFromPoints(points);
      if (box.isEmpty()) box.copy(this.restBox);
      box.getCenter(center);
      radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2 + 0.16, 0.35);
    } else {
      const currentBox = new THREE.Box3().setFromObject(this.root);
      currentBox.getCenter(center);
      radius = currentBox.getSize(new THREE.Vector3()).length() / 2 + 0.12;
    }
    for (const s of SIDES) for (const [r, marker] of Object.entries(this.markers[s])) {
      marker.visible = s === this.side && (this.design !== "component" || r === this.focusJoint);
      marker.material.color.setHex(COLORS[this.status?.[r] || "lost"]);
    }
    if (!this.follow && !this.focusDirty) return;
    const halfFov = Math.min(this.camera.fov * DEG / 2, Math.atan(Math.tan(this.camera.fov * DEG / 2) * this.camera.aspect));
    const distance = radius * (this.design === "component" ? 1.45 : 1.12) / Math.sin(halfFov);
    if (this.focusDirty) {
      const dir = this.updateOrientation ? new THREE.Vector3(0, 0, 1) : (this.posture === "side" ? new THREE.Vector3(0, 0.1, 1) : new THREE.Vector3(this.side === "left" ? 1 : -1, 0.1, 0.08));
      this.controls.target.copy(center);
      this.camera.position.copy(center).add(dir.normalize().multiplyScalar(distance));
      this.controls.minDistance = distance * 0.65;
      this.controls.maxDistance = distance * 2;
      this.focusDirty = false;
    } else {
      const movement = center.sub(this.controls.target).multiplyScalar(1 - Math.exp(-14 * dt));
      this.controls.target.add(movement);
      this.camera.position.add(movement);
    }
  }
  render(time = 0) {
    const dt = this.lastTime == null ? 1 / 60 : Math.min(Math.max((time - this.lastTime) / 1000, 0), 0.1);
    this.lastTime = time;
    if (this.root && this.target && this.side) {
      const alpha = 1 - Math.exp(-26 * dt);
      for (const role of ROLES) if (Number.isFinite(this.target[role])) this.display[role] += (this.target[role] - this.display[role]) * alpha;
      const b = this.bones[this.side], sign = (key) => this.sign[key] ?? 1, hip = this.display.hip * DEG;
      if (this.hipMotion === "abduction") this.rotate(b.hip, BODY_Z, (this.side === "left" ? 1 : -1) * hip * sign("hip_abduction"));
      else if (this.hipMotion === "extension") this.rotate(b.hip, BODY_X, hip * sign("hip_extension"));
      else this.rotate(b.hip, BODY_X, -hip * sign("hip_flexion"));
      this.rotate(b.knee, BODY_X, this.display.knee * DEG * sign("knee_flexion"));
      this.rotate(b.ankle, BODY_X, -this.display.ankle * DEG * sign("ankle_dorsiflexion"));
    }
    this.postureGroup.updateMatrixWorld(true);
    this.frameCamera(dt);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
  dispose() {
    this.disposed = true;
    ++this.generation;
    this.renderer.setAnimationLoop(null);
    this.observer.disconnect();
    this.clearModel();
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

// POSE_ORIENTATION_PATCH_V1
