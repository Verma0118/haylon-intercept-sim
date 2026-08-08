import * as THREE from 'three';
import { PHASES } from './params.js';

const _mid = new THREE.Vector3();
const _desiredPos = new THREE.Vector3();
const _desiredTarget = new THREE.Vector3();
const _side = new THREE.Vector3();
const _fwd = new THREE.Vector3();

/**
 * Cinematic follow framing for live demos.
 * Frames drone during toss/stabilize; frames drone+target once tracking.
 */
export function updateFollowCamera(camera, controls, drone, target, phase, dt) {
  if (phase === PHASES.IDLE) return;

  if (
    target.active &&
    (phase === PHASES.TRACKING ||
      phase === PHASES.INTERCEPT ||
      phase === PHASES.HIT ||
      phase === PHASES.MISS)
  ) {
    _mid.copy(drone.pos).add(target.pos).multiplyScalar(0.5);
    _fwd.subVectors(target.pos, drone.pos);
    if (_fwd.lengthSq() < 1e-4) _fwd.set(1, 0, 0);
    else _fwd.normalize();
  } else {
    _mid.copy(drone.pos);
    _fwd.copy(drone.heading).normalize();
    if (_fwd.lengthSq() < 1e-4) _fwd.set(1, 0, 0);
  }

  _side.crossVectors(_fwd, new THREE.Vector3(0, 1, 0));
  if (_side.lengthSq() < 1e-4) _side.set(0, 0, 1);
  else _side.normalize();

  const span =
    target.active && phase !== PHASES.THROWN && phase !== PHASES.STABILIZING
      ? drone.pos.distanceTo(target.pos)
      : 8;
  const back = THREE.MathUtils.clamp(10 + span * 0.35, 12, 34);
  const up = THREE.MathUtils.clamp(5 + span * 0.12, 5, 14);

  _desiredPos
    .copy(_mid)
    .addScaledVector(_fwd, -back * 0.35)
    .addScaledVector(_side, back * 0.55)
    .addScaledVector(new THREE.Vector3(0, 1, 0), up);

  _desiredTarget.copy(_mid).addScaledVector(new THREE.Vector3(0, 1, 0), 1.2);

  // Snappier during intercept terminal, smoother during tumble
  const alpha = 1 - Math.exp(-(phase === PHASES.INTERCEPT ? 3.2 : 2.0) * dt);
  camera.position.lerp(_desiredPos, alpha);
  controls.target.lerp(_desiredTarget, alpha);
}
