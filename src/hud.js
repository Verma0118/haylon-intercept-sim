import { PHASE_TO_MODULE, TARGET_BEHAVIORS, params } from './params.js';
import { PRESETS, PRESET_KEYS } from './presets.js';

const MODULE_ORDER = [
  { key: 'Launch Detect', phases: ['THROWN'] },
  { key: 'Stabilize', phases: ['STABILIZING'] },
  { key: 'Track', phases: ['TRACKING'] },
  { key: 'Guidance', phases: ['INTERCEPT', 'HIT', 'MISS'] },
];

/**
 * DOM overlay: phase, telemetry, target dropdown, throw/reset, architecture legend.
 */
export function createHUD(root, handlers) {
  root.innerHTML = `
    <div class="fx-flash" id="fx-flash" aria-hidden="true"></div>
    <div class="outcome-banner" id="outcome-banner" hidden></div>

    <header class="hud-brand">
      <div class="brand-mark">HAYLON</div>
      <div class="brand-sub">Intercept Simulation</div>
    </header>

    <section class="hud-phase" aria-live="polite">
      <div class="phase-status">
        <span class="phase-label" id="phase-label">IDLE</span>
        <span class="phase-sep" aria-hidden="true">/</span>
        <span class="phase-module" id="phase-module">Standby</span>
      </div>
      <div class="lock-badge" id="lock-badge" hidden>ACQUIRED</div>
    </section>

    <aside class="hud-telemetry" aria-label="Telemetry">
      <div class="telem-row"><span>t</span><strong id="t-elapsed">0.00 s</strong></div>
      <div class="telem-row"><span>range</span><strong id="t-range">—</strong></div>
      <div class="telem-row"><span>closing</span><strong id="t-closing">—</strong></div>
    </aside>

    <div class="hud-bottom">
      <nav class="hud-controls">
        <div class="control-actions">
          <button type="button" id="btn-throw" class="btn primary">Throw</button>
          <button type="button" id="btn-reset" class="btn">Reset</button>
        </div>
        <details class="hud-setup">
          <summary>Setup</summary>
          <div class="setup-body">
            <label class="field">
              <span>Preset</span>
              <select id="scenario-preset">
                ${PRESET_KEYS.map(
                  (k) =>
                    `<option value="${k}" ${k === params.activePreset ? 'selected' : ''}>${PRESETS[k].label}</option>`,
                ).join('')}
              </select>
            </label>
            <label class="field">
              <span>Target</span>
              <select id="target-behavior">
                ${TARGET_BEHAVIORS.map((b) => `<option value="${b}">${b}</option>`).join('')}
              </select>
            </label>
            <label class="toggle">
              <input type="checkbox" id="follow-cam" ${params.followCam ? 'checked' : ''} />
              <span>Follow cam</span>
            </label>
            <label class="toggle">
              <input type="checkbox" id="auto-demo" ${params.autoDemo ? 'checked' : ''} />
              <span>Auto demo</span>
            </label>
          </div>
        </details>
      </nav>

      <footer class="hud-legend" aria-label="Architecture">
        <ol class="legend-steps" id="legend-steps">
          ${MODULE_ORDER.map(
            (m) => `<li data-module="${m.key}"><span>${m.key}</span></li>`,
          ).join('')}
        </ol>
      </footer>
    </div>

    <details class="hud-debug">
      <summary>Tunables</summary>
      <div class="debug-grid" id="debug-grid"></div>
    </details>

    <div class="hud-hint" id="hud-hint">Space throw · R reset · drag orbit</div>
  `;

  const els = {
    phaseLabel: root.querySelector('#phase-label'),
    phaseModule: root.querySelector('#phase-module'),
    lockBadge: root.querySelector('#lock-badge'),
    elapsed: root.querySelector('#t-elapsed'),
    range: root.querySelector('#t-range'),
    closing: root.querySelector('#t-closing'),
    throwBtn: root.querySelector('#btn-throw'),
    resetBtn: root.querySelector('#btn-reset'),
    behavior: root.querySelector('#target-behavior'),
    preset: root.querySelector('#scenario-preset'),
    followCam: root.querySelector('#follow-cam'),
    autoDemo: root.querySelector('#auto-demo'),
    legend: root.querySelector('#legend-steps'),
    debugGrid: root.querySelector('#debug-grid'),
    flash: root.querySelector('#fx-flash'),
    outcome: root.querySelector('#outcome-banner'),
    hint: root.querySelector('#hud-hint'),
    setup: root.querySelector('.hud-setup'),
  };

  let lastPhase = 'IDLE';

  els.throwBtn.addEventListener('click', () => handlers.onThrow());
  els.resetBtn.addEventListener('click', () => handlers.onReset());
  els.behavior.addEventListener('change', (e) => {
    handlers.onBehaviorChange(e.target.value);
  });
  els.preset.addEventListener('change', (e) => {
    handlers.onPresetChange?.(e.target.value);
  });
  els.followCam.addEventListener('change', (e) => {
    params.followCam = e.target.checked;
    handlers.onFollowChange?.(e.target.checked);
  });
  els.autoDemo.addEventListener('change', (e) => {
    params.autoDemo = e.target.checked;
    handlers.onAutoDemoChange?.(e.target.checked);
  });

  // Close setup when clicking outside
  document.addEventListener('pointerdown', (e) => {
    if (!els.setup.open) return;
    if (els.setup.contains(e.target)) return;
    els.setup.open = false;
  });

  buildDebugPanel(els.debugGrid, handlers.onParamChange);

  return {
    update(snapshot) {
      const { phase, elapsed, distance, closingSpeed } = snapshot;

      if (phase !== lastPhase) {
        els.phaseLabel.classList.remove('phase-pulse');
        void els.phaseLabel.offsetWidth;
        els.phaseLabel.classList.add('phase-pulse');
        lastPhase = phase;

        if (phase === 'HIT') {
          flash(els, 'hit');
          showOutcome(els, 'HIT', 'Intercept complete');
        } else if (phase === 'MISS') {
          flash(els, 'miss');
          showOutcome(els, 'MISS', 'Break lock · reset to retry');
        } else if (phase === 'IDLE') {
          hideOutcome(els);
        } else {
          hideOutcome(els);
        }
      }

      els.phaseLabel.textContent = phase;
      els.phaseLabel.dataset.phase = phase;
      els.phaseModule.textContent = PHASE_TO_MODULE[phase] ?? phase;

      const locked = phase === 'TRACKING' || phase === 'INTERCEPT';
      els.lockBadge.hidden = !locked;
      els.lockBadge.classList.toggle('tracking', phase === 'TRACKING');
      els.lockBadge.classList.toggle('guiding', phase === 'INTERCEPT');
      els.lockBadge.textContent = phase === 'TRACKING' ? 'ACQUIRED' : 'GUIDING';

      els.elapsed.textContent = `${elapsed.toFixed(2)} s`;
      els.range.textContent =
        distance == null ? '—' : `${distance.toFixed(2)} m`;
      els.closing.textContent =
        closingSpeed == null ? '—' : `${closingSpeed.toFixed(2)} m/s`;

      const moduleName = PHASE_TO_MODULE[phase];
      els.legend.querySelectorAll('li').forEach((li) => {
        const active =
          li.dataset.module === moduleName ||
          (phase === 'HIT' && li.dataset.module === 'Guidance') ||
          (phase === 'MISS' && li.dataset.module === 'Guidance');
        li.classList.toggle('active', active);
        li.classList.toggle('done', isModuleDone(li.dataset.module, phase));
      });

      const flying =
        phase !== 'IDLE' && phase !== 'HIT' && phase !== 'MISS';
      els.throwBtn.disabled = flying;
      els.hint.hidden = phase !== 'IDLE';
      root.dataset.phase = phase;
    },
    setBehavior(value) {
      els.behavior.value = value;
    },
    setPreset(value) {
      els.preset.value = value;
    },
    setFollow(value) {
      els.followCam.checked = value;
    },
    setAutoDemo(value) {
      els.autoDemo.checked = value;
    },
    refreshDebug() {
      els.debugGrid.querySelectorAll('input[data-path]').forEach((input) => {
        input.value = String(getParam(input.dataset.path));
      });
    },
  };
}

function flash(els, kind) {
  els.flash.dataset.kind = kind;
  els.flash.classList.remove('on');
  void els.flash.offsetWidth;
  els.flash.classList.add('on');
}

function showOutcome(els, title, sub) {
  els.outcome.hidden = false;
  els.outcome.dataset.kind = title.toLowerCase();
  els.outcome.innerHTML = `<strong>${title}</strong><span>${sub}</span>`;
}

function hideOutcome(els) {
  els.outcome.hidden = true;
  els.outcome.innerHTML = '';
}

function isModuleDone(moduleName, phase) {
  const order = ['Launch Detect', 'Stabilize', 'Track', 'Guidance'];
  const phaseOrder = {
    IDLE: -1,
    THROWN: 0,
    STABILIZING: 1,
    TRACKING: 2,
    INTERCEPT: 3,
    HIT: 4,
    MISS: 4,
  };
  const mi = order.indexOf(moduleName);
  const pi = phaseOrder[phase] ?? -1;
  return mi >= 0 && pi > mi;
}

const DEBUG_FIELDS = [
  ['tossVelocity.x', 'Toss Vx'],
  ['tossVelocity.y', 'Toss Vy'],
  ['spinMagnitude', 'Spin'],
  ['STABILIZE_DAMPING', 'Stabilize damp'],
  ['minStabilizeTime', 'Min stabilize'],
  ['thrownHold', 'Thrown hold'],
  ['trackingDwell', 'Track dwell'],
  ['TURN_RATE_LIMIT', 'Turn rate'],
  ['MAX_DRONE_SPEED', 'Max speed'],
  ['ACCEL', 'Accel'],
  ['targetSpeed', 'Target speed'],
  ['AMPLITUDE', 'Weave amp'],
  ['FREQ', 'Weave freq'],
  ['ERRATIC_INTERVAL', 'Erratic Δt'],
  ['hitRadius', 'Hit radius'],
  ['missTimeout', 'Miss timeout'],
  ['autoDemoDelay', 'Auto demo delay'],
];

function getParam(path) {
  const parts = path.split('.');
  let v = params;
  for (const p of parts) v = v[p];
  return v;
}

function setParam(path, value) {
  const parts = path.split('.');
  let obj = params;
  for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
  obj[parts[parts.length - 1]] = value;
}

function buildDebugPanel(grid, onChange) {
  for (const [path, label] of DEBUG_FIELDS) {
    const row = document.createElement('label');
    row.className = 'debug-row';
    const val = getParam(path);
    row.innerHTML = `<span>${label}</span><input type="number" step="any" data-path="${path}" value="${val}" />`;
    grid.appendChild(row);
  }
  grid.addEventListener('change', (e) => {
    const input = e.target;
    if (!(input instanceof HTMLInputElement)) return;
    const path = input.dataset.path;
    const num = Number(input.value);
    if (!Number.isFinite(num)) return;
    setParam(path, num);
    onChange?.(path, num);
  });
}
