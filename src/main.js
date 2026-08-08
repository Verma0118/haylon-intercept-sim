import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { params, PHASES } from './params.js';
import {
  createStateMachine,
  resetStateMachine,
  enterPhase,
  updateStateMachine,
} from './stateMachine.js';
import {
  createDroneState,
  resetDrone,
  throwDrone,
  updateThrowStabilize,
  angularSpeed,
} from './physics.js';
import { updateIntercept, computeLeadPoint } from './guidance.js';
import {
  createTargetState,
  resetTarget,
  spawnTarget,
  updateTarget,
  setTargetBehavior,
} from './target.js';
import { createHUD } from './hud.js';
import { updateFollowCamera } from './cameraFollow.js';

const FIXED_DT = 1 / 60;
const MAX_SUBSTEPS = 5;

const canvas = document.querySelector('#scene');
const hudRoot = document.querySelector('#hud');

// ── Scene ──────────────────────────────────────────────────────────
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a1510);
scene.fog = new THREE.FogExp2(0x0a1510, 0.018);

const camera = new THREE.PerspectiveCamera(
  50,
  window.innerWidth / window.innerHeight,
  0.1,
  500,
);
camera.position.set(-8, 6, 14);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.target.set(6, 3, 0);
controls.maxPolarAngle = Math.PI * 0.48;
controls.minDistance = 4;
controls.maxDistance = 80;

// Lights
const hemi = new THREE.HemisphereLight(0xb8d4c4, 0x1a2a20, 0.85);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff2d6, 1.15);
sun.position.set(-20, 30, 10);
scene.add(sun);
const rim = new THREE.DirectionalLight(0xd4ff4f, 0.35);
rim.position.set(10, 4, -15);
scene.add(rim);

// Ground grid + subtle terrain plane
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(200, 200),
  new THREE.MeshStandardMaterial({
    color: 0x13241c,
    roughness: 0.95,
    metalness: 0.05,
  }),
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = 0;
scene.add(ground);

const grid = new THREE.GridHelper(80, 40, 0x3a5a44, 0x1e3328);
grid.position.y = 0.01;
scene.add(grid);

// Soft sky dome gradient via large sphere
{
  const skyGeo = new THREE.SphereGeometry(180, 32, 16);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {},
    vertexShader: `
      varying vec3 vPos;
      void main() {
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vPos;
      void main() {
        float h = normalize(vPos).y * 0.5 + 0.5;
        vec3 low = vec3(0.04, 0.09, 0.07);
        vec3 high = vec3(0.12, 0.22, 0.28);
        vec3 col = mix(low, high, h);
        col += vec3(0.08, 0.12, 0.02) * pow(max(0.0, 1.0 - h), 3.0);
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));
}

// ── Drone mesh ─────────────────────────────────────────────────────
const droneGroup = new THREE.Group();
const bodyMat = new THREE.MeshStandardMaterial({
  color: 0xe8f0e4,
  roughness: 0.35,
  metalness: 0.4,
});
const accentMat = new THREE.MeshStandardMaterial({
  color: 0xd4ff4f,
  roughness: 0.4,
  metalness: 0.2,
  emissive: 0x3a4a10,
  emissiveIntensity: 0.6,
});
const body = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.14, 0.35), bodyMat);
droneGroup.add(body);
const nose = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.28, 8), accentMat);
nose.rotation.z = -Math.PI / 2;
nose.position.set(0.38, 0, 0);
droneGroup.add(nose);
for (const [x, z] of [
  [0.2, 0.22],
  [0.2, -0.22],
  [-0.2, 0.22],
  [-0.2, -0.22],
]) {
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.04, 0.28), bodyMat);
  arm.position.set(x * 0.3, 0.02, z);
  droneGroup.add(arm);
  const rotor = new THREE.Mesh(
    new THREE.CylinderGeometry(0.16, 0.16, 0.02, 16),
    new THREE.MeshStandardMaterial({
      color: 0x2a3a30,
      transparent: true,
      opacity: 0.7,
      roughness: 0.2,
    }),
  );
  rotor.position.set(x * 0.55, 0.06, z * 1.1);
  droneGroup.add(rotor);
}
droneGroup.visible = true;
scene.add(droneGroup);

// Trail
const trailPositions = new Float32Array(120 * 3);
const trailGeo = new THREE.BufferGeometry();
trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
const trail = new THREE.Line(
  trailGeo,
  new THREE.LineBasicMaterial({ color: 0xd4ff4f, transparent: true, opacity: 0.55 }),
);
scene.add(trail);
let trailCount = 0;

// ── Target mesh ────────────────────────────────────────────────────
const targetGroup = new THREE.Group();
const targetBody = new THREE.Mesh(
  new THREE.ConeGeometry(0.35, 1.1, 6),
  new THREE.MeshStandardMaterial({
    color: 0xff7a45,
    roughness: 0.45,
    metalness: 0.25,
    emissive: 0x401808,
    emissiveIntensity: 0.5,
  }),
);
targetBody.rotation.z = Math.PI / 2;
targetGroup.add(targetBody);
const targetRing = new THREE.Mesh(
  new THREE.TorusGeometry(0.7, 0.03, 8, 32),
  new THREE.MeshBasicMaterial({ color: 0xff7a45, transparent: true, opacity: 0.5 }),
);
targetRing.rotation.x = Math.PI / 2;
targetGroup.add(targetRing);
targetGroup.visible = false;
scene.add(targetGroup);

// Lead point marker + range line
const leadMarker = new THREE.Mesh(
  new THREE.SphereGeometry(0.18, 12, 12),
  new THREE.MeshBasicMaterial({ color: 0x5dffb0 }),
);
leadMarker.visible = false;
scene.add(leadMarker);

const linkGeo = new THREE.BufferGeometry().setFromPoints([
  new THREE.Vector3(),
  new THREE.Vector3(),
]);
const linkLine = new THREE.Line(
  linkGeo,
  new THREE.LineDashedMaterial({
    color: 0x8aa63a,
    dashSize: 0.4,
    gapSize: 0.25,
    transparent: true,
    opacity: 0.65,
  }),
);
linkLine.visible = false;
scene.add(linkLine);

// ── Simulation state ───────────────────────────────────────────────
const sm = createStateMachine();
const drone = createDroneState();
const target = createTargetState();
let leadPoint = null;
let accumulator = 0;
let lastTime = performance.now();
let prevPhase = PHASES.IDLE;
let timeScale = 1;
let burstParticles = null;

// Impact burst (simple point sprites via small meshes)
function createBurst() {
  const group = new THREE.Group();
  const matHit = new THREE.MeshBasicMaterial({ color: 0x5dffb0 });
  const matMiss = new THREE.MeshBasicMaterial({ color: 0xff5c7a });
  const pieces = [];
  for (let i = 0; i < 28; i++) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.08, 0.08), matHit);
    mesh.visible = false;
    group.add(mesh);
    pieces.push({
      mesh,
      vel: new THREE.Vector3(),
      life: 0,
    });
  }
  scene.add(group);
  return { group, pieces, matHit, matMiss };
}

burstParticles = createBurst();

function triggerBurst(origin, kind) {
  const mat = kind === 'hit' ? burstParticles.matHit : burstParticles.matMiss;
  for (const p of burstParticles.pieces) {
    p.mesh.material = mat;
    p.mesh.visible = true;
    p.mesh.position.copy(origin);
    p.vel.set(
      (Math.random() - 0.5) * 12,
      Math.random() * 8 + 2,
      (Math.random() - 0.5) * 12,
    );
    p.life = 0.55 + Math.random() * 0.35;
  }
}

function updateBurst(dt) {
  for (const p of burstParticles.pieces) {
    if (!p.mesh.visible) continue;
    p.life -= dt;
    if (p.life <= 0) {
      p.mesh.visible = false;
      continue;
    }
    p.vel.y -= 12 * dt;
    p.mesh.position.addScaledVector(p.vel, dt);
    const s = Math.max(0.15, p.life);
    p.mesh.scale.setScalar(s);
  }
}

function clearTrail() {
  trailCount = 0;
  trailPositions.fill(0);
  trailGeo.attributes.position.needsUpdate = true;
  trailGeo.setDrawRange(0, 0);
}

function pushTrail(pos) {
  if (trailCount < 120) {
    const i = trailCount * 3;
    trailPositions[i] = pos.x;
    trailPositions[i + 1] = pos.y;
    trailPositions[i + 2] = pos.z;
    trailCount++;
  } else {
    trailPositions.copyWithin(0, 3);
    const i = (120 - 1) * 3;
    trailPositions[i] = pos.x;
    trailPositions[i + 1] = pos.y;
    trailPositions[i + 2] = pos.z;
  }
  trailGeo.attributes.position.needsUpdate = true;
  trailGeo.setDrawRange(0, trailCount);
}

function telemetry() {
  let distance = null;
  let closingSpeed = null;
  if (
    target.active &&
    sm.phase !== PHASES.IDLE &&
    sm.phase !== PHASES.THROWN
  ) {
    const r = new THREE.Vector3().subVectors(target.pos, drone.pos);
    distance = r.length();
    if (distance > 1e-5) {
      const los = r.clone().normalize();
      const relVel = new THREE.Vector3().subVectors(target.vel, drone.vel);
      // Positive closing = approaching
      closingSpeed = -relVel.dot(los);
    }
  }
  return {
    distance,
    closingSpeed,
    angularSpeed: angularSpeed(drone),
  };
}

function resetSim() {
  resetStateMachine(sm);
  resetDrone(drone);
  resetTarget(target);
  leadPoint = null;
  timeScale = 1;
  prevPhase = PHASES.IDLE;
  clearTrail();
  targetGroup.visible = false;
  leadMarker.visible = false;
  linkLine.visible = false;
  droneGroup.visible = true;
  droneGroup.position.copy(drone.pos);
  droneGroup.quaternion.copy(drone.orientation);
  for (const p of burstParticles.pieces) p.mesh.visible = false;
}

function startThrow() {
  if (sm.phase !== PHASES.IDLE && sm.phase !== PHASES.HIT && sm.phase !== PHASES.MISS) {
    return;
  }
  resetSim();
  userOrbitLock = false;
  throwDrone(drone);
  spawnTarget(target, target.behavior);
  targetGroup.visible = true;
  enterPhase(sm, PHASES.THROWN);
  prevPhase = PHASES.THROWN;
  clearTrail();
  pushTrail(drone.pos);
}

// Manual orbit temporarily disables follow until re-toggled or next throw
let userOrbitLock = false;
controls.addEventListener('start', () => {
  if (params.followCam) userOrbitLock = true;
});

const hud = createHUD(hudRoot, {
  onThrow: startThrow,
  onReset: resetSim,
  onBehaviorChange: (b) => {
    setTargetBehavior(target, b);
  },
  onFollowChange: (on) => {
    if (on) userOrbitLock = false;
  },
  onParamChange: () => {},
});

function step(dt) {
  const telem = telemetry();

  if (
    sm.phase === PHASES.THROWN ||
    sm.phase === PHASES.STABILIZING ||
    sm.phase === PHASES.TRACKING ||
    sm.phase === PHASES.INTERCEPT
  ) {
    updateTarget(target, dt);
  }

  if (sm.phase === PHASES.THROWN || sm.phase === PHASES.STABILIZING) {
    updateThrowStabilize(drone, dt);
    leadPoint = null;
  } else if (sm.phase === PHASES.TRACKING) {
    // Coast ballistic while dwell runs — solve lead point but don't steer yet
    updateThrowStabilize(drone, dt);
    leadPoint = computeLeadPoint(
      drone.pos,
      Math.max(drone.speed, params.MAX_DRONE_SPEED * 0.35),
      target.pos,
      target.vel,
    );
  } else if (sm.phase === PHASES.INTERCEPT) {
    leadPoint = updateIntercept(drone, target.pos, target.vel, dt);
  }

  const nextTelem = telemetry();
  const changed = updateStateMachine(sm, dt, {
    angularSpeed: nextTelem.angularSpeed,
    distance: nextTelem.distance ?? Infinity,
    closingSpeed: nextTelem.closingSpeed ?? 0,
  });

  if (changed && sm.phase !== prevPhase) {
    if (sm.phase === PHASES.HIT) {
      triggerBurst(drone.pos.clone().lerp(target.pos, 0.5), 'hit');
      timeScale = 0.28;
    } else if (sm.phase === PHASES.MISS) {
      triggerBurst(drone.pos.clone(), 'miss');
      timeScale = 0.55;
    }
    prevPhase = sm.phase;
  }

  if (sm.phase === PHASES.HIT || sm.phase === PHASES.MISS) {
    // Ease time scale back toward normal after the beat
    timeScale += (1 - timeScale) * Math.min(1, dt * 1.8);
  }

  if (
    sm.phase !== PHASES.IDLE &&
    sm.phase !== PHASES.HIT &&
    sm.phase !== PHASES.MISS
  ) {
    pushTrail(drone.pos);
  }

  updateBurst(dt);
}

function syncMeshes(now) {
  droneGroup.position.copy(drone.pos);
  if (sm.phase === PHASES.INTERCEPT || sm.phase === PHASES.HIT) {
    const q = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(1, 0, 0),
      drone.heading,
    );
    droneGroup.quaternion.slerp(q, 0.35);
  } else {
    droneGroup.quaternion.copy(drone.orientation);
  }

  if (target.active) {
    targetGroup.position.copy(target.pos);
    if (target.vel.lengthSq() > 1e-4) {
      const q = new THREE.Quaternion().setFromUnitVectors(
        new THREE.Vector3(1, 0, 0),
        target.vel.clone().normalize(),
      );
      targetGroup.quaternion.slerp(q, 0.2);
    }
    const pulse = 0.5 + 0.5 * Math.sin(now * 0.006);
    targetRing.scale.setScalar(0.9 + pulse * 0.25);
    targetRing.material.opacity =
      sm.phase === PHASES.TRACKING || sm.phase === PHASES.INTERCEPT
        ? 0.45 + pulse * 0.4
        : 0.25;
  }

  const showLead =
    leadPoint &&
    (sm.phase === PHASES.TRACKING || sm.phase === PHASES.INTERCEPT);
  leadMarker.visible = Boolean(showLead);
  linkLine.visible = Boolean(
    target.active &&
      sm.phase !== PHASES.IDLE &&
      sm.phase !== PHASES.THROWN,
  );

  if (showLead) {
    leadMarker.position.copy(leadPoint);
  }

  if (linkLine.visible) {
    const pos = linkGeo.attributes.position;
    pos.setXYZ(0, drone.pos.x, drone.pos.y, drone.pos.z);
    pos.setXYZ(1, target.pos.x, target.pos.y, target.pos.z);
    pos.needsUpdate = true;
    linkLine.computeLineDistances();
  }
}

function updateHUD() {
  const telem = telemetry();
  hud.update({
    phase: sm.phase,
    elapsed: sm.totalElapsed,
    distance: telem.distance,
    closingSpeed: telem.closingSpeed,
    droneSpeed: sm.phase === PHASES.IDLE ? null : drone.speed,
    angularSpeedDeg:
      sm.phase === PHASES.IDLE
        ? null
        : (telem.angularSpeed * 180) / Math.PI,
  });
}

function frame(now) {
  const frameDt = Math.min(0.05, (now - lastTime) / 1000);
  lastTime = now;
  accumulator += frameDt * timeScale;

  let steps = 0;
  while (accumulator >= FIXED_DT && steps < MAX_SUBSTEPS) {
    step(FIXED_DT);
    accumulator -= FIXED_DT;
    steps++;
  }
  if (steps === MAX_SUBSTEPS) accumulator = 0;

  if (params.followCam && !userOrbitLock && sm.phase !== PHASES.IDLE) {
    updateFollowCamera(camera, controls, drone, target, sm.phase, frameDt);
  }

  syncMeshes(now);
  updateHUD();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

window.addEventListener('keydown', (e) => {
  if (e.code === 'Space') {
    e.preventDefault();
    startThrow();
  } else if (e.code === 'KeyR') {
    resetSim();
  }
});

resetSim();
requestAnimationFrame(frame);
