import * as THREE from 'three';
import { params } from './params.js';

const _r = new THREE.Vector3();
const _predicted = new THREE.Vector3();
const _desired = new THREE.Vector3();
const _axis = new THREE.Vector3();
const _quat = new THREE.Quaternion();

/**
 * Lead-pursuit intercept point (quarterback-leads-receiver narrative).
 * Iterates tGo a few times so the estimate converges for a moving target.
 */
export function computeLeadPoint(dronePos, droneSpeed, targetPos, targetVel) {
  const speed = Math.max(droneSpeed, 1);
  _r.subVectors(targetPos, dronePos);
  let tGo = _r.length() / speed;

  for (let i = 0; i < 3; i++) {
    _predicted.copy(targetPos).addScaledVector(targetVel, tGo);
    tGo = _predicted.distanceTo(dronePos) / speed;
  }

  return _predicted.clone();
}

/** Rotate currentDir toward desiredDir by at most maxAngle radians. */
export function rotateToward(currentDir, desiredDir, maxAngle) {
  const cur = currentDir.clone().normalize();
  const des = desiredDir.clone().normalize();
  const angle = cur.angleTo(des);
  if (angle < 1e-5 || maxAngle <= 0) return cur;
  if (angle <= maxAngle) return des;

  _axis.crossVectors(cur, des);
  if (_axis.lengthSq() < 1e-10) {
    // Nearly opposite — pick an arbitrary perpendicular axis
    _axis.set(0, 1, 0).cross(cur);
    if (_axis.lengthSq() < 1e-10) _axis.set(1, 0, 0).cross(cur);
  }
  _axis.normalize();
  _quat.setFromAxisAngle(_axis, maxAngle);
  return cur.applyQuaternion(_quat).normalize();
}

function approach(current, target, rate, dt) {
  if (current < target) return Math.min(target, current + rate * dt);
  return Math.max(target, current - rate * dt);
}

/**
 * Steer with turn-rate limit + accelerate toward MAX_DRONE_SPEED.
 * Returns lead point for HUD visualization.
 */
export function updateIntercept(drone, targetPos, targetVel, dt) {
  const leadPoint = computeLeadPoint(
    drone.pos,
    Math.max(drone.speed, params.MAX_DRONE_SPEED * 0.35),
    targetPos,
    targetVel,
  );

  _desired.subVectors(leadPoint, drone.pos);
  if (_desired.lengthSq() < 1e-8) _desired.copy(drone.heading);
  else _desired.normalize();

  const angleDelta = drone.heading.angleTo(_desired);
  const maxTurn = params.TURN_RATE_LIMIT * dt;
  const newDir = rotateToward(drone.heading, _desired, Math.min(angleDelta, maxTurn));
  drone.heading.copy(newDir);

  drone.speed = approach(drone.speed, params.MAX_DRONE_SPEED, params.ACCEL, dt);
  drone.vel.copy(drone.heading).multiplyScalar(drone.speed);
  drone.pos.addScaledVector(drone.vel, dt);

  // Keep a mild upright attitude once under guidance
  const upright = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 0, 1),
    drone.heading,
  );
  drone.orientation.slerp(upright, 1 - Math.exp(-6 * dt));
  drone.angularVel.set(0, 0, 0);

  return leadPoint;
}
