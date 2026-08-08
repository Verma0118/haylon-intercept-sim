import * as THREE from 'three';
import { params } from './params.js';

function randomUnitVector() {
  const v = new THREE.Vector3(
    Math.random() * 2 - 1,
    Math.random() * 2 - 1,
    Math.random() * 2 - 1,
  );
  if (v.lengthSq() < 1e-6) v.set(1, 0, 0);
  return v.normalize();
}

/** Integrate quaternion by angular velocity (rad/s). */
export function integrateOrientation(orientation, angularVel, dt) {
  const w = angularVel;
  const qDot = new THREE.Quaternion(
    0.5 * (w.x * orientation.w + w.y * orientation.z - w.z * orientation.y),
    0.5 * (-w.x * orientation.z + w.y * orientation.w + w.z * orientation.x),
    0.5 * (w.x * orientation.y - w.y * orientation.x + w.z * orientation.w),
    0.5 * (-w.x * orientation.x - w.y * orientation.y - w.z * orientation.z),
  );
  orientation.x += qDot.x * dt;
  orientation.y += qDot.y * dt;
  orientation.z += qDot.z * dt;
  orientation.w += qDot.w * dt;
  orientation.normalize();
}

export function createDroneState() {
  return {
    pos: new THREE.Vector3(0, params.handHeight, 0),
    vel: new THREE.Vector3(),
    orientation: new THREE.Quaternion(),
    angularVel: new THREE.Vector3(),
    speed: 0,
    heading: new THREE.Vector3(1, 0, 0),
  };
}

export function resetDrone(drone) {
  drone.pos.set(0, params.handHeight, 0);
  drone.vel.set(0, 0, 0);
  drone.orientation.identity();
  drone.angularVel.set(0, 0, 0);
  drone.speed = 0;
  drone.heading.set(1, 0, 0);
}

/** Enter THROWN with randomized toss + tumble. */
export function throwDrone(drone) {
  const tv = params.tossVelocity;
  const jitter = 0.35;
  drone.pos.set(0, params.handHeight, 0);
  drone.vel.set(
    tv.x + (Math.random() - 0.5) * jitter,
    tv.y + (Math.random() - 0.5) * jitter * 0.5,
    tv.z + (Math.random() - 0.5) * jitter,
  );
  drone.speed = drone.vel.length();
  drone.heading.copy(drone.vel).normalize();

  const axis = randomUnitVector();
  const mag = params.spinMagnitude * (0.75 + Math.random() * 0.5);
  drone.angularVel.copy(axis).multiplyScalar(mag);
  drone.orientation.setFromEuler(
    new THREE.Euler(
      Math.random() * Math.PI,
      Math.random() * Math.PI,
      Math.random() * Math.PI,
    ),
  );
}

/**
 * Ballistic flight + exponential attitude damping (PID stand-in).
 * Used during THROWN / STABILIZING.
 */
export function updateThrowStabilize(drone, dt) {
  drone.vel.y -= params.GRAVITY * dt;
  drone.pos.addScaledVector(drone.vel, dt);

  // Soft floor so a bad toss doesn't bury the mesh
  if (drone.pos.y < params.groundY + 0.15) {
    drone.pos.y = params.groundY + 0.15;
    if (drone.vel.y < 0) drone.vel.y *= -0.15;
  }

  const damp = Math.exp(-params.STABILIZE_DAMPING * dt);
  drone.angularVel.multiplyScalar(damp);
  integrateOrientation(drone.orientation, drone.angularVel, dt);

  drone.speed = drone.vel.length();
  if (drone.speed > 0.05) {
    drone.heading.copy(drone.vel).normalize();
  }
}

export function angularSpeed(drone) {
  return drone.angularVel.length();
}
