import * as THREE from "three";
import { GLTFLoader } from "../PD1_Software_Design_C/web/vendor/three/examples/jsm/loaders/GLTFLoader.js";

const MODEL_URL = "../PD1_Software_Design_C/avatar/Design%20C/scene.glb";
const AXIS_X = new THREE.Vector3(1, 0, 0);
const rad = THREE.MathUtils.degToRad;

function sideOf(n) {
  n = n.toLowerCase();
  if (/left/.test(n)) return "left";
  if (/right/.test(n)) return "right";
  const m = /(^|[_.\-: ])(l|r)(?=[_.\-]?(thigh|upleg|calf|shin|lowerleg))/.exec(n);
  return m ? (m[2] === "l" ? "left" : "right") : null;
}
function findLegBones(root) {
  const bones = []; root.traverse((o) => o.isBone && bones.push(o));
  const pick = (side, re) => bones.filter((b) => sideOf(b.name) === side && re.test(b.name.toLowerCase()) && !/twist|roll|helper/.test(b.name.toLowerCase()))
    .sort((a, b) => a.name.length - b.name.length)[0];
  const out = { names: bones.map((b) => b.name) };
  for (const side of ["left", "right"]) out[side] = { thigh: pick(side, /thigh|upleg/), shin: pick(side, /calf|shin|lowerleg/) };
  return out;
}
function rotWorld(bone, angle) {
  const wq = new THREE.Quaternion(), pq = new THREE.Quaternion();
  bone.updateWorldMatrix(true, false);
  bone.getWorldQuaternion(wq); bone.parent.getWorldQuaternion(pq);
  const nw = new THREE.Quaternion().setFromAxisAngle(AXIS_X, angle).multiply(wq);
  bone.quaternion.copy(pq.invert().multiply(nw));
}

export async function createAvatar(canvas, flip = 1) {
  const buf = await (await fetch(MODEL_URL)).arrayBuffer();
  const loader = new GLTFLoader();
  const parse = () => new Promise((res, rej) => loader.parse(buf.slice(0), "", res, rej));
  const gLive = await parse(), gGhost = await parse();

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(420, 300, false);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x667788, 1.7));
  const dl = new THREE.DirectionalLight(0xffffff, 1.2); dl.position.set(-2, 3, 2); scene.add(dl);
  const bed = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.04, 2.4), new THREE.MeshStandardMaterial({ color: 0xcfd8dc }));
  bed.position.set(0, -0.02, 0.1); scene.add(bed);
  const camera = new THREE.PerspectiveCamera(35, 420 / 300, 0.1, 50);

  function buildRig(gltf, ghost) {
    const root = gltf.scene, wrap = new THREE.Group(), holder = new THREE.Group();
    wrap.add(root); holder.add(wrap); scene.add(holder);
    root.traverse((o) => {
      if (!(o.isMesh || o.isSkinnedMesh)) return;
      o.frustumCulled = false;
      if (ghost) {
        const f = (m) => { const c = m.clone(); c.transparent = true; c.opacity = 0.3; c.depthWrite = false; if (c.color) c.color.set(0x42a5f5); return c; };
        o.material = Array.isArray(o.material) ? o.material.map(f) : f(o.material);
      }
    });
    holder.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root);
    wrap.scale.setScalar(1.7 / Math.max(box.max.y - box.min.y, 1e-6));
    holder.updateMatrixWorld(true);
    const b = findLegBones(root);
    if (!b.left.thigh || !b.left.shin || !b.right.thigh || !b.right.shin) {
      console.warn("3D avatar: leg bones not found. Bone names:", b.names);
      throw new Error("leg bones not found in scene.glb (see console for bone names)");
    }
    const hip = new THREE.Vector3().addVectors(b.left.thigh.getWorldPosition(new THREE.Vector3()), b.right.thigh.getWorldPosition(new THREE.Vector3())).multiplyScalar(0.5);
    wrap.position.sub(hip); holder.updateMatrixWorld(true);
    const all = [b.left.thigh, b.left.shin, b.right.thigh, b.right.shin];
    all.forEach((x) => (x.userData.rest = x.quaternion.clone()));
    const marks = {};
    if (!ghost) for (const k of ["thigh", "shin"]) {
      const ms = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0xff1744, transparent: true, opacity: 0.55, depthTest: false }));
      ms.visible = false; ms.renderOrder = 10; marks[k] = ms; scene.add(ms);
    }
    return { holder, bones: b, all, marks };
  }
  const live = buildRig(gLive, false), ghost = buildRig(gGhost, true);
  window.__avatarBones = live.bones.names;

  function pose(r, side, exId, hip, knee) {
    r.all.forEach((x) => x.quaternion.copy(x.userData.rest));
    const b = r.bones[side];
    rotWorld(b.thigh, (exId === "slr" ? -rad(hip) : rad(hip)) * flip);
    r.holder.updateMatrixWorld(true);
    rotWorld(b.shin, rad(knee) * flip);
    r.holder.updateMatrixWorld(true);
  }
  function mark(side, red) {
    const b = live.bones[side], on = { thigh: red === "thigh" || red === "leg", shin: red === "knee" || red === "leg" };
    for (const k of ["thigh", "shin"]) {
      const m = live.marks[k]; m.visible = !!on[k]; if (!on[k]) continue;
      const a = b[k].getWorldPosition(new THREE.Vector3());
      const next = k === "thigh" ? b.shin : (b.shin.children.find((c) => c.isBone) || b.shin);
      const e = next.getWorldPosition(new THREE.Vector3());
      m.position.copy(a).add(e).multiplyScalar(0.5); m.scale.setScalar(0.09);
    }
  }
  return {
    setExercise(id) {
      const sx = id === "slr" ? -1 : 1;
      for (const r of [live, ghost]) { r.holder.rotation.set((id === "slr" ? -1 : 1) * Math.PI / 2, 0, 0); r.holder.position.set(0, 0.13, 0); }
      camera.position.set(sx * 3.0, 0.5, 0.1); camera.lookAt(0, 0.35, 0.05);
    },
    update({ side, ex, hip, knee, ghostHip, ghostKnee, red }) {
      pose(live, side, ex, hip, knee);
      pose(ghost, side, ex, ghostHip, ghostKnee);
      mark(side, red);
      renderer.render(scene, camera);
    }
  };
}
