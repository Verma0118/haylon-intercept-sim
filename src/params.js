/** All tunables for the intercept sim — tweak live via the debug panel. */
export const params = {
  // Throw / stabilize
  handHeight: 1.2,
  tossVelocity: { x: 4.2, y: 7.2, z: 0.8 },
  spinMagnitude: 14, // rad/s peak tumble
  STABILIZE_DAMPING: 2.1, // tumble settles over ~1s (pitch-readable)
  minStabilizeTime: 1.0,
  stabilizeAngularThresholdDeg: 5, // °/s
  thrownHold: 0.35, // keep Launch Detect on HUD long enough to read

  // Tracking dwell before steering
  trackingDwell: 0.9,

  // Guidance / flight envelope
  TURN_RATE_LIMIT: 2.4, // rad/s
  MAX_DRONE_SPEED: 18,
  ACCEL: 18,
  hitRadius: 0.55,
  missTimeout: 2.0,
  maxFlightTime: 14,

  // Target
  targetSpeed: 6.5,
  targetSpawnDistance: 38,
  targetAltitude: 5.0,
  AMPLITUDE: 3.6,
  FREQ: 1.2,
  ERRATIC_INTERVAL: 0.75,
  erraticConeDeg: 55,

  // Camera
  followCam: true,

  // World
  GRAVITY: 9.81,
  groundY: 0,
};

export const PHASES = {
  IDLE: 'IDLE',
  THROWN: 'THROWN',
  STABILIZING: 'STABILIZING',
  TRACKING: 'TRACKING',
  INTERCEPT: 'INTERCEPT',
  HIT: 'HIT',
  MISS: 'MISS',
};

/** Maps sim phases → architecture modules pitched to Namin. */
export const PHASE_TO_MODULE = {
  IDLE: 'Standby',
  THROWN: 'Launch Detect',
  STABILIZING: 'Stabilize',
  TRACKING: 'Track',
  INTERCEPT: 'Guidance',
  HIT: 'Intercept',
  MISS: 'Miss',
};

export const TARGET_BEHAVIORS = ['straight', 'weaving', 'erratic'];
