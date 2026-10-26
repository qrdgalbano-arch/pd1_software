import * as THREE from "three";

const vector = () => new THREE.Vector3();
const quaternion = () => new THREE.Quaternion();
const roles = ["hip", "knee", "ankle"];
const ids = {left: [23,25,27,31], right: [24,26,28,32]};

function scenePoint(p) {
  return new THREE.Vector3(p.x, -p.y, -p.z);
}

function frame(x, y) {
  if (x.length() < 1e-5 || y.length() < 1e-5) return null;
  x.normalize();
  y.addScaledVector(x, -y.dot(x));

  if (y.length() < 1e-5) return null;

  y.normalize();
  const z = vector().crossVectors(x, y).normalize();

  return quaternion().setFromRotationMatrix(
    new THREE.Matrix4().makeBasis(x, y, z)
  );
}

export function attachOrientation(avatar) {
  if (avatar.updateOrientation) return;

  if (!avatar.postureGroup || !avatar.root || !avatar.bones ||
      !avatar.camera || !avatar.controls || !avatar.render ||
      !avatar.update || !avatar.setPosture) {
    throw new Error("Orientation patch needs a v5-compatible avatar");
  }

  const group = avatar.postureGroup;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = {
    packet: null, received: 0, phase: "idle",
    side: "left", joint: "knee", enabled: true,
    rest: null, root: null, last: performance.now(),
    cameraReady: false, jump: null, oriented: false,
    statusAt: 0
  };

  const panel = document.createElement("fieldset");
  panel.className = "orientation-controls";

  const legend = document.createElement("legend");
  legend.textContent = "3D orientation";
  panel.append(legend);

  const label = document.createElement("label");
  label.textContent = "Model orientation ";

  const select = document.createElement("select");
  for (const [value, text] of [
    ["auto", "Automatic — match camera"],
    ["hold", "Hold current pose"]
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.append(option);
  }

  label.append(select);
  panel.append(label);

  const mirrorLabel = document.createElement("label");
  const mirror = document.createElement("input");
  mirror.type = "checkbox";
  mirrorLabel.append(mirror, " Match mirrored camera preview");
  panel.append(mirrorLabel);

  const recenter = document.createElement("button");
  recenter.type = "button";
  recenter.textContent = "Recenter joint";
  panel.append(recenter);

  const status = document.createElement("p");
  status.setAttribute("role", "status");
  status.textContent = "Waiting for inferred 3D tracking";
  panel.append(status);

  const warning = document.createElement("p");
  warning.textContent =
    "Research mode: inferred depth. Exercise thresholds are not 3D-validated.";
  panel.append(warning);

  const shell = document.createElement("details");
  shell.className = "orientation-shell";
  const summary = document.createElement("summary");
  summary.textContent = "3D orientation options";
  shell.append(summary, panel);
  avatar.container.insertAdjacentElement("afterend", shell);

  const style = document.createElement("style");
  style.textContent = `
    .orientation-controls {
      display:flex;flex-wrap:wrap;gap:.75rem;min-width:0;
      margin-block:.75rem;padding:.75rem;
      border:1px solid currentColor;border-radius:.5rem;
    }
    .orientation-controls legend {font-weight:700}
    .orientation-controls label {
      display:flex;align-items:center;flex-wrap:wrap;gap:.5rem;
      min-height:44px;max-width:100%;
    }
    .orientation-controls select,.orientation-controls button {
      font:inherit;min-height:44px;max-width:100%;
      padding:.5rem;background:Canvas;color:CanvasText;
      border:1px solid currentColor;border-radius:.25rem;
    }
    .orientation-controls input {width:24px;height:24px}
    .orientation-controls p {
      flex-basis:100%;margin:0;overflow-wrap:anywhere;
    }
    .orientation-controls :focus-visible {
      outline:3px solid currentColor;outline-offset:3px;
    }
  `;
  style.textContent += `
    #avatar { min-height: 260px; }
    .orientation-shell { flex: 0 0 auto; min-width: 0; margin-block: .5rem; }
    .orientation-shell > summary {
      display: flex;
      align-items: center;
      min-height: 44px;
      cursor: pointer;
      font-weight: 700;
    }
    .orientation-shell > .orientation-controls { margin-top: .5rem; }
  `;
  document.head.append(style);

  select.addEventListener("change", () => {
    state.enabled = select.value === "auto";
  });

  mirror.addEventListener("change", () => {
    avatar.renderer.domElement.style.transform =
      mirror.checked ? "scaleX(-1)" : "";
  });

  recenter.addEventListener("click", () => {
    state.cameraReady = false;
  });

  function captureRest() {
    // Restore actual stored rest rotations before deriving model axes.
    group.position.set(0,0,0);
    group.quaternion.identity();

    for (const side of ["left", "right"]) {
      for (const bone of Object.values(avatar.bones[side] || {})) {
        if (bone?.userData.restLocal) {
          bone.quaternion.copy(bone.userData.restLocal);
        }
      }
    }

    group.updateMatrixWorld(true);

    const left = avatar.bones.left;
    const right = avatar.bones.right;

    if (!left.hip || !right.hip || !left.knee || !right.knee) {
      return false;
    }

    const lh = left.hip.getWorldPosition(vector());
    const rh = right.hip.getWorldPosition(vector());
    const midpoint = lh.clone().add(rh).multiplyScalar(.5);

    const knees = left.knee.getWorldPosition(vector())
      .add(right.knee.getWorldPosition(vector())).multiplyScalar(.5);

    const body = frame(lh.clone().sub(rh), midpoint.clone().sub(knees));
    if (!body) return false;

    const chains = {};

    for (const side of ["left", "right"]) {
      chains[side] = [];

      for (let i=0; i<3; i++) {
        const bone = avatar.bones[side][roles[i]];
        if (!bone) continue;

        const child = i<2
          ? avatar.bones[side][roles[i+1]]
          : bone.children.find(c => c.isBone && /toe/i.test(c.name));

        if (!child) continue;

        const world = bone.getWorldQuaternion(quaternion());
        const direction = child.getWorldPosition(vector())
          .sub(bone.getWorldPosition(vector()));

        if (direction.length() < 1e-5) continue;

        chains[side].push({
          bone, pair: [ids[side][i], ids[side][i+1]],
          world,
          localDirection: direction.normalize()
            .applyQuaternion(world.clone().invert())
        });
      }
    }

    state.rest = {body, midpoint, chains};
    state.root = avatar.root;
    return true;
  }

  function point(id) {
    const p = state.packet?.landmarks?.[String(id)];
    if (!p || ![p.x,p.y,p.z,p.visibility].every(Number.isFinite)) {
      return null;
    }
    return scenePoint(p);
  }

  function applyPose(alpha, now) {
    const packet = state.packet;

    if (!packet?.orientation_valid || !packet.basis) return false;

    if (state.root !== avatar.root) {
      state.rest = null;
      state.cameraReady = false;
      state.oriented = false;
    }

    if (!state.rest && !captureRest()) return false;

    const convert = a => new THREE.Vector3(a[0], -a[1], -a[2]);
    const observed = frame(
      convert(packet.basis.left), convert(packet.basis.up)
    );

    if (!observed) return false;

    const desired = observed.multiply(state.rest.body.clone().invert());

    // Require persistence before accepting a large orientation reversal.
    if (state.oriented && group.quaternion.angleTo(desired) > 2.0) {
      if (!state.jump || state.jump.q.angleTo(desired) > .3) {
        state.jump = {q: desired.clone(), since: now};
      }
      if (now-state.jump.since < 600) return false;
    } else {
      state.jump = null;
    }

    group.quaternion.slerp(desired, alpha);
    state.oriented = true;
    group.position.copy(state.rest.midpoint)
      .applyQuaternion(group.quaternion).multiplyScalar(-1);
    if (![...group.quaternion.toArray(), ...group.position.toArray()]
      .every(Number.isFinite)) {
      group.quaternion.identity();
      group.position.set(0, 0, 0);
      state.oriented = false;
      return false;
    }
    group.updateMatrixWorld(true);

    for (const side of ["left", "right"]) {
      for (const item of state.rest.chains[side]) {
        const a = point(item.pair[0]);
        const b = point(item.pair[1]);

        if (!a || !b || a.distanceTo(b) < .025) continue;

        const direction = b.sub(a).normalize();
        const base = group.quaternion.clone().multiply(item.world);
        const from = item.localDirection.clone().applyQuaternion(base);
        const swing = quaternion().setFromUnitVectors(
          from.normalize(), direction
        );

        const parentInverse = item.bone.parent
          .getWorldQuaternion(quaternion()).invert();

        const local = parentInverse.multiply(swing.multiply(base));
        item.bone.quaternion.slerp(local, alpha);
        item.bone.updateWorldMatrix(false, true);
      }
    }

    group.updateMatrixWorld(true);

    // Camera framing and clipping remain owned by frameCamera(dt).

    return true;
  }

  avatar.updateOrientation = (packet, side, phase, joint) => {
    state.packet = packet;
    state.side = side || state.side;
    state.phase = phase;
    state.joint = roles.includes(joint) ? joint : "knee";
    state.received = performance.now();
  };

  const originalUpdate = avatar.update.bind(avatar);
  avatar.update = (...args) => {
    // Do not apply the exercise's hard-coded lying-posture preset.
    const preset = avatar.setPosture;
    avatar.setPosture = () => {};

    try {
      originalUpdate(...args);
    } finally {
      avatar.setPosture = preset;
    }

    avatar.side = args[3];

    for (const side of ["left", "right"]) {
      for (const marker of Object.values(avatar.markers?.[side] || {})) {
        if (marker) marker.visible = side === avatar.side;
      }
    }
  };

  const originalRender = avatar.render.bind(avatar);

  avatar.render = (time = 0) => {
    const now = performance.now();
    const dt = Math.max(0, Math.min(.1, (now-state.last)/1000));
    state.last = now;

    const alpha = reduced ? 1 : 1-Math.exp(-6*dt);
    const fresh = now-state.received < 650;
    let applied = false;

    if (state.enabled && fresh && state.phase !== "paused") {
      applied = applyPose(alpha, now);
    }

    // Prevent the old scalar-angle renderer overwriting XYZ retargeting.
    const target = avatar.target;
    avatar.target = null;

    try {
      originalRender(time);
    } finally {
      avatar.target = target;
    }

    if (now-state.statusAt > 1000) {
      const near = state.packet?.near_side || "uncertain";

      status.textContent = state.phase === "paused"
        ? "Paused — pose held"
        : !state.enabled
          ? "Pose held — choose Automatic to resume"
          : applied
            ? `Inferred 3D · near camera: ${near} · prescribed: ${state.side}`
            : `Orientation held: ${fresh
                ? state.packet?.reason || "Tracking uncertain"
                : "No recent tracking packet"}`;

      state.statusAt = now;
    }
  };
}
