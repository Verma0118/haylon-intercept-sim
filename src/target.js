import * as THREE from 'three';
import { params } from './params.js';

export function createTargetState() {
  return {
    behavior: 'straight',
    pos: new THREE.Vector3(),
    vel: new THREE.Vector3(),
    basePos: new THREE.Vector3(),
    lateralAxis: new THREE.Vector3(0, 0, 1),
    t: 0,
    erraticTimer: 0,
    heading: new THREE.Vector3(1, 0, 0),
    desiredHeading: new THREE.Vector3(1, 0, 0),
    active: false,
  };
}

export function resetTarget(target) {
  target.pos.set(0, -10, 0);
  target.vel.set(0, 0, 0);
  target.basePos.set(0, 0, 0);
  target.t = 0;
  target.erraticTimer = 0;
  target.active = false;
  target.heading.set(-1, 0, 0);
  target.desiredHeading.set(-1, 0, 0);
}

/** Spawn target ahead of the throw corridor, inbound. */
export function spawnTarget(target, behavior = target.behavior) {
  target.behavior = behavior;
  target.active = true;
  target.t = 0;
  target.erraticTimer = 0;

  const dist = params.targetSpawnDistance;
  const y = params.targetAltitude + (Math.random() - 0.5) * 1.2;
  const z = (Math.random() - 0.5) * 4;

  target.basePos.set(dist, y, z);
  target.pos.copy(target.basePos);

  // Fly generally toward / past the throw origin
  target.heading.set(-1, (Math.random() - 0.5) * 0.05, (Math.random() - 0.5) * 0.15).normalize();
  target.desiredHeading.copy(target.heading);
  target.vel.copy(target.heading).multiplyScalar(params.targetSpeed);

  // Lateral axis for weave (perpendicular to inbound path in XZ)
  target.lateralAxis.set(0, 0, 1);
  if (Math.abs(target.heading.dot(target.lateralAxis)) > 0.9) {
    target.lateralAxis.set(0, 1, 0);
  }
  const forward = target.heading.clone();
  target.lateralAxis.crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();
  if (target.lateralAxis.lengthSq() < 0.5) {
    target.lateralAxis.set(0, 0, 1);
  }
}

function pickErraticHeading(target) {
  const cone = (params.erraticConeDeg * Math.PI) / 180;
  const base = new THREE.Vector3(-1, 0, 0);
  const yaw = (Math.random() - 0.5) * 2 * cone;
  const pitch = (Math.random() - 0.5) * cone * 0.4;
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(pitch, yaw, 0, 'YXZ'));
  target.desiredHeading.copy(base).applyQuaternion(q).normalize();
}

export function updateTarget(target, dt) {
  if (!target.active) return;

  target.t += dt;

  switch (target.behavior) {
    case 'straight': {
      target.vel.copy(target.heading).multiplyScalar(params.targetSpeed);
      target.pos.addScaledVector(target.vel, dt);
      target.basePos.copy(target.pos);
      break;
    }

    case 'weaving': {
      target.basePos.addScaledVector(
        target.heading.clone().multiplyScalar(params.targetSpeed),
        dt,
      );
      const offset = Math.sin(params.FREQ * target.t) * params.AMPLITUDE;
      target.pos
        .copy(target.basePos)
        .addScaledVector(target.lateralAxis, offset);
      // Approximate velocity for guidance
      const cosTerm = Math.cos(params.FREQ * target.t) * params.FREQ * params.AMPLITUDE;
      target.vel
        .copy(target.heading)
        .multiplyScalar(params.targetSpeed)
        .addScaledVector(target.lateralAxis, cosTerm);
      break;
    }

    case 'erratic': {
      target.erraticTimer += dt;
      if (target.erraticTimer >= params.ERRATIC_INTERVAL) {
        target.erraticTimer = 0;
        pickErraticHeading(target);
      }
      // Blend toward new heading over ~0.3s
      const blend = 1 - Math.exp(-dt / 0.3);
      target.heading.lerp(target.desiredHeading, blend).normalize();
      target.vel.copy(target.heading).multiplyScalar(params.targetSpeed);
      target.pos.addScaledVector(target.vel, dt);
      target.basePos.copy(target.pos);
      break;
    }

    default:
      break;
  }
}

export function setTargetBehavior(target, behavior) {
  target.behavior = behavior;
  if (behavior === 'weaving') {
    target.basePos.copy(target.pos);
    target.t = 0;
  }
  if (behavior === 'erratic') {
    target.erraticTimer = 0;
    target.desiredHeading.copy(target.heading);
  }
}
