import { PHASES, params } from './params.js';

/**
 * Phase enum + transition logic for the intercept pipeline.
 * Sim starts post-detection (no throw-classifier modeling).
 */
export function createStateMachine() {
  return {
    phase: PHASES.IDLE,
    phaseElapsed: 0,
    totalElapsed: 0,
    trackingDwellElapsed: 0,
    negativeClosingTime: 0,
  };
}

export function resetStateMachine(sm) {
  sm.phase = PHASES.IDLE;
  sm.phaseElapsed = 0;
  sm.totalElapsed = 0;
  sm.trackingDwellElapsed = 0;
  sm.negativeClosingTime = 0;
}

export function enterPhase(sm, phase) {
  sm.phase = phase;
  sm.phaseElapsed = 0;
  if (phase === PHASES.TRACKING) sm.trackingDwellElapsed = 0;
  if (phase === PHASES.INTERCEPT) sm.negativeClosingTime = 0;
}

/**
 * Advance the state machine given current kinematics / telemetry.
 * Returns true if phase changed this tick.
 */
export function updateStateMachine(sm, dt, ctx) {
  sm.phaseElapsed += dt;
  if (sm.phase !== PHASES.IDLE && sm.phase !== PHASES.HIT && sm.phase !== PHASES.MISS) {
    sm.totalElapsed += dt;
  }

  const prev = sm.phase;

  switch (sm.phase) {
    case PHASES.IDLE:
      break;

    case PHASES.THROWN: {
      // Share physics with STABILIZING; hold briefly so Launch Detect reads on HUD.
      if (sm.phaseElapsed > params.thrownHold) {
        enterPhase(sm, PHASES.STABILIZING);
      }
      break;
    }

    case PHASES.STABILIZING: {
      const angDeg = (ctx.angularSpeed * 180) / Math.PI;
      if (
        angDeg < params.stabilizeAngularThresholdDeg &&
        sm.phaseElapsed >= params.minStabilizeTime
      ) {
        enterPhase(sm, PHASES.TRACKING);
      }
      break;
    }

    case PHASES.TRACKING: {
      sm.trackingDwellElapsed += dt;
      if (sm.trackingDwellElapsed >= params.trackingDwell) {
        enterPhase(sm, PHASES.INTERCEPT);
      }
      break;
    }

    case PHASES.INTERCEPT: {
      if (ctx.distance < params.hitRadius) {
        enterPhase(sm, PHASES.HIT);
        break;
      }
      if (ctx.closingSpeed < 0) {
        sm.negativeClosingTime += dt;
      } else {
        sm.negativeClosingTime = 0;
      }
      if (
        sm.negativeClosingTime > params.missTimeout ||
        sm.totalElapsed > params.maxFlightTime
      ) {
        enterPhase(sm, PHASES.MISS);
      }
      break;
    }

    case PHASES.HIT:
    case PHASES.MISS:
      break;

    default:
      break;
  }

  return sm.phase !== prev;
}
