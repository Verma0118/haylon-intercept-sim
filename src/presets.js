/**
 * Call-ready scenario presets — flip mid-demo without hunting tunables.
 * Each preset mutates `params` and returns the target behavior to apply.
 */
export const PRESETS = {
  nominal: {
    label: 'Nominal',
    behavior: 'straight',
    apply(params) {
      params.tossVelocity = { x: 4.2, y: 7.2, z: 0.8 };
      params.spinMagnitude = 14;
      params.STABILIZE_DAMPING = 2.1;
      params.minStabilizeTime = 1.0;
      params.TURN_RATE_LIMIT = 2.4;
      params.MAX_DRONE_SPEED = 18;
      params.ACCEL = 18;
      params.targetSpeed = 6.5;
      params.targetSpawnDistance = 38;
      params.AMPLITUDE = 3.6;
      params.FREQ = 1.2;
      params.hitRadius = 0.55;
      params.missTimeout = 2.0;
      params.maxFlightTime = 14;
    },
  },
  weaveStress: {
    label: 'Weave stress',
    behavior: 'weaving',
    apply(params) {
      params.tossVelocity = { x: 4.0, y: 6.8, z: 0.6 };
      params.spinMagnitude = 12;
      params.STABILIZE_DAMPING = 2.2;
      params.minStabilizeTime = 0.9;
      params.TURN_RATE_LIMIT = 2.6;
      params.MAX_DRONE_SPEED = 19;
      params.ACCEL = 20;
      params.targetSpeed = 7.5;
      params.targetSpawnDistance = 36;
      params.AMPLITUDE = 5.2;
      params.FREQ = 1.6;
      params.hitRadius = 0.55;
      params.missTimeout = 2.2;
      params.maxFlightTime = 14;
    },
  },
  dodge: {
    label: 'Erratic dodge',
    behavior: 'erratic',
    apply(params) {
      params.tossVelocity = { x: 3.8, y: 6.5, z: 0.5 };
      params.spinMagnitude = 13;
      params.STABILIZE_DAMPING = 2.0;
      params.minStabilizeTime = 1.0;
      params.TURN_RATE_LIMIT = 2.2;
      params.MAX_DRONE_SPEED = 17;
      params.ACCEL = 16;
      params.targetSpeed = 8.0;
      params.targetSpawnDistance = 34;
      params.ERRATIC_INTERVAL = 0.45;
      params.erraticConeDeg = 70;
      params.hitRadius = 0.5;
      params.missTimeout = 1.8;
      params.maxFlightTime = 14;
    },
  },
  missDemo: {
    label: 'Forced miss',
    behavior: 'weaving',
    apply(params) {
      // Underpowered / slow-turning interceptor so MISS is likely for the narrative
      params.tossVelocity = { x: 3.2, y: 5.5, z: 0.4 };
      params.spinMagnitude = 10;
      params.STABILIZE_DAMPING = 2.4;
      params.minStabilizeTime = 1.0;
      params.TURN_RATE_LIMIT = 0.85;
      params.MAX_DRONE_SPEED = 11;
      params.ACCEL = 10;
      params.targetSpeed = 9.5;
      params.targetSpawnDistance = 40;
      params.AMPLITUDE = 5.5;
      params.FREQ = 1.8;
      params.hitRadius = 0.4;
      params.missTimeout = 1.4;
      params.maxFlightTime = 10;
    },
  },
};

export const PRESET_KEYS = Object.keys(PRESETS);

export function applyPreset(params, key) {
  const preset = PRESETS[key];
  if (!preset) return null;
  preset.apply(params);
  return preset.behavior;
}
