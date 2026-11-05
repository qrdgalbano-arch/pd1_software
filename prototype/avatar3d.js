import * as THREE from "three";
import { GLTFLoader } from "../PD1_Software_Design_C/web/vendor/three/examples/jsm/loaders/GLTFLoader.js";

const MODEL_URL = "../PD1_Software_Design_C/avatar/Design%20C/scene.glb";
const rad = THREE.MathUtils.degToRad;
const RE = { thigh: /thigh|upleg/, shin: /calf|shin|lowerleg/, foot: /foot/, uarm: /shldr|upperarm|upper_arm/, farm: /forearm|lowerarm|lower_arm/, hand: /hand/ };
const EXCL = /twist|roll|helper|toe|collar|clav|scap|pole|target/;
const CHILD = { thigh: "shin", shin: "foot", uarm: "farm", farm: "hand" };
const ORDER = ["thigh", "shin", "uarm", "farm"];

function sideOf(n) {
  n = n.toLowerCase();
  if (/left/.test(n)) return "left";
  if (/right/.test(n)) return "right";
  const m = /(^|[_.\-: ])(l|r)(?=[_.\-]?(thigh|upleg|calf|shin|lowerleg|foot|shldr|upperarm|upper_arm|forearm|lowerarm|hand))/.exec(n);
  return m ? (m[2] === "l" ? "left" : "right") : null;
}
function findBones(root) {
  const all = []; root.traverse((o) => o.isBone && all.push(o));
  const out = { names: all.map((b) => b.name), left: {}, right: {} };
  for (const side of ["left", "right"]) for (const k of Object.keys(RE)) {
    out[side][k] = all.filter((b) => { const n = b.name.toLowerCase(); return sideOf(b.name) === side && RE[k].test(n) && !EXCL.test(n); })
      .sort((a, b) => a.name.length - b.name.length)[0];
  }
  return out;
}
function rotWorldQ(bone, q) {
  const wq = new THREE.Quaternion(), pq = new THREE.Quaternion();
  bone.updateWorldMatrix(true, false);
  bone.getWorldQuaternion(wq); bone.parent.getWorldQuaternion(pq);
  bone.quaternion.copy(pq.invert().multiply(q.clone().multiply(wq)));
}

export async function createAvatar(canvas) {
  const buf = await (await fetch(MODEL_URL)).arrayBuffer();
  const loader = new GLTFLoader();
  const parse = () => new Promise((res, rej) => loader.parse(buf.slice(0), "", res, rej));
  const gLive = await parse(), gTarget = await parse();

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(420, 300, false);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x667788, 1.7));
  const dl = new THREE.DirectionalLight(0xffffff, 1.2); dl.position.set(-2, 3, 2); scene.add(dl);
  const bed = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.04, 2.4), new THREE.MeshStandardMaterial({ color: 0xcfd8dc }));
  bed.position.set(0, -0.02, 0.1); scene.add(bed);
  const camera = new THREE.PerspectiveCamera(35, 420 / 300, 0.1, 50);
  let fz = 1;

  function buildRig(gltf, target) {
    const root = gltf.scene, wrap = new THREE.Group(), holder = new THREE.Group();
    wrap.add(root); holder.add(wrap); scene.add(holder);
    root.traverse((o) => {
      if (!(o.isMesh || o.isSkinnedMesh)) return;
      o.frustumCulled = false;
      if (target) {
        const f = (m) => { const c = m.clone(); c.transparent = true; c.opacity = 0.85; c.depthWrite = false; if (c.color) c.color.set(0x66bb6a); return c; };
        o.material = Array.isArray(o.material) ? o.material.map(f) : f(o.material);
      }
    });
    holder.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root);
    wrap.scale.setScalar(1.7 / Math.max(box.max.y - box.min.y, 1e-6));
    holder.updateMatrixWorld(true);
    const b = findBones(root);
    if (!b.left.thigh || !b.left.shin || !b.right.thigh || !b.right.shin) {
      console.warn("3D avatar: leg bones not found. Bone names:", b.names);
      throw new Error("leg bones not found in scene.glb (see console for bone names)");
    }
    const hip = new THREE.Vector3().addVectors(b.left.thigh.getWorldPosition(new THREE.Vector3()), b.right.thigh.getWorldPosition(new THREE.Vector3())).multiplyScalar(0.5);
    wrap.position.sub(hip); holder.updateMatrixWorld(true);
    const items = [];
    for (const side of ["left", "right"]) for (const k of ORDER) {
      const bone = b[side][k], child = b[side][CHILD[k]] || (bone && bone.children.find((c) => c.isBone));
      if (bone && child) items.push({ id: side + "_" + k, side, key: k, bone, child, rest: bone.quaternion.clone() });
    }
    const marks = {};
    if (!target) for (const k of ["thigh", "shin"]) {
      const ms = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0xff1744, transparent: true, opacity: 0.55, depthTest: false }));
      ms.visible = false; ms.renderOrder = 10; marks[k] = ms; scene.add(ms);
    }
    return { holder, bones: b, items, marks };
  }
  const live = buildRig(gLive, false), target = buildRig(gTarget, true);
  window.__avatarBones = live.bones.names;

  const v1 = new THREE.Vector3(), v2 = new THREE.Vector3();
  function applyDirs(rig, dirs) {
    rig.items.forEach((it) => it.bone.quaternion.copy(it.rest));
    rig.holder.updateMatrixWorld(true);
    for (const it of rig.items) {
      const d = dirs[it.id]; if (!d) continue;
      it.bone.getWorldPosition(v1); it.child.getWorldPosition(v2);
      const cur = v2.clone().sub(v1); if (cur.lengthSq() < 1e-10) continue;
      const tgt = new THREE.Vector3(d[0], d[1], d[2]); if (tgt.lengthSq() < 1e-10) continue;
      rotWorldQ(it.bone, new THREE.Quaternion().setFromUnitVectors(cur.normalize(), tgt.normalize()));
      rig.holder.updateMatrixWorld(true);
    }
  }
  function startDirs() {
    const d = {};
    for (const s of ["left", "right"]) { d[s + "_thigh"] = [0, 0, fz]; d[s + "_shin"] = [0, 0, fz]; }
    return d;
  }
  function mark(side, red) {
    for (const k of ["thigh", "shin"]) {
      const m = live.marks[k], it = side && live.items.find((i) => i.id === side + "_" + k);
      const on = it && (k === "thigh" ? (red === "thigh" || red === "leg") : (red === "knee" || red === "leg"));
      m.visible = !!on; if (!on) continue;
      const a = it.bone.getWorldPosition(new THREE.Vector3()), e = it.child.getWorldPosition(new THREE.Vector3());
      m.position.copy(a).add(e).multiplyScalar(0.5); m.scale.setScalar(0.09);
    }
  }
  return {
    setExercise(id) {
      fz = id === "slr" ? 1 : -1;
      for (const r of [live, target]) { r.holder.rotation.set((id === "slr" ? -1 : 1) * Math.PI / 2, 0, 0); r.holder.position.set(0, 0.13, 0); }
      camera.position.set((id === "slr" ? -1 : 1) * 3.0, 0.5, 0.1); camera.lookAt(0, 0.35, 0.05);
    },
    update({ showLive, dirs, red, side }) {
      live.holder.visible = !!showLive;
      target.holder.visible = !showLive;
      if (showLive) applyDirs(live, dirs || {}); else applyDirs(target, startDirs());
      mark(showLive ? side : null, red);
      renderer.render(scene, camera);
    }
  };
}
