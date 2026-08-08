/** All tunables for the intercept sim — tweak live via the debug panel. */
export const params = {
  // Throw / stabilize
  handHeight: 1.2,
  tossVelocity: { x: 4.5, y: 6.5, z: 1.2 },
  spinMagnitude: 12, // rad/s peak tumble
  STABILIZE_DAMPING: 2.8, // tumble decay rate
  minStabilizeTime: 0.8,
  stabilizeAngularThresholdDeg: 5, // °/s

  // Tracking dwell before steering
  trackingDwell: 0.3,

  // Guidance / flight envelope
  TURN_RATE_LIMIT: 2.8, // rad/s
  MAX_DRONE_SPEED: 22,
  ACCEL: 28,
  hitRadius: 0.55,
  missTimeout: 2.0,
  maxFlightTime: 12,

  // Target
  targetSpeed: 8,
  targetSpawnDistance: 28,
  targetAltitude: 4.5,
  AMPLITUDE: 3.2,
  FREQ: 1.4,
  ERRATIC_INTERVAL: 0.7,
  erraticConeDeg: 55,

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
