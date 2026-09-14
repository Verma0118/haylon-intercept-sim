# Host stack — v0 contracts

Normative message shapes for the laptop control pipeline.
Design rationale: [`ARCHITECTURE.md`](../ARCHITECTURE.md) §4. **Do not invent ad-hoc fields in feature PRs** — change this file and Architecture together.

Publish rate target for `GuidanceCommand` / `ChannelFrame`: **20–50 Hz** (fixed rate).

---

## Enums

| Name | Values |
|---|---|
| `PixelFormat` | `rgb` \| `bgr` \| `gray` \| `encoded` |
| `TrackStatus` | `SEARCHING` \| `TRACKING` \| `LOST` |
| `GuidanceMode` | `IDLE` \| `HOLD` \| `TRACK_CENTER` \| `INTERCEPT` \| `ABORT` |

---

## `CameraFrame`

One video frame entering Capture.

| Field | Type | Unit / range | Notes |
|---|---|---|---|
| `frame_id` | `uint64` | monotonic | Increments per captured frame |
| `timestamp_ms` | `float64` | ms, host clock | Capture time (or receive time if that is all we have — document which) |
| `width` | `uint32` | pixels | |
| `height` | `uint32` | pixels | |
| `format` | `PixelFormat` | | `encoded` = compressed blob (JPEG/H264/etc.) |
| `data` | bytes or handle | | Implementation-defined buffer; not serialized in logs by default |

**Invariants:** `width > 0`, `height > 0`, `data` matches `format`.

---

## `BBox`

Axis-aligned box in **image pixel coordinates** (origin top-left, x right, y down).

| Field | Type | Unit / range |
|---|---|---|
| `x` | `float64` | pixels, left edge |
| `y` | `float64` | pixels, top edge |
| `w` | `float64` | pixels, width &gt; 0 |
| `h` | `float64` | pixels, height &gt; 0 |

---

## `TrackEstimate`

Output of Detect + Track for the active target hypothesis.

| Field | Type | Unit / range | Notes |
|---|---|---|---|
| `timestamp_ms` | `float64` | ms | Align with source `CameraFrame.timestamp_ms` when possible |
| `status` | `TrackStatus` | | |
| `track_id` | `uint64` \| `null` | | `null` when `SEARCHING` or after hard reset |
| `bbox` | `BBox` \| `null` | | Required when `status == TRACKING`; typically `null` when `LOST` / `SEARCHING` |
| `confidence` | `float64` | `0..1` | Detector/tracker confidence |
| `bearing_rad` | `{ yaw, pitch }` \| `null` | radians | Optional; camera frame; +yaw = target right of center (document if flipped) |
| `range_proxy` | `float64` \| `null` | arbitrary + | Optional; e.g. bbox area or marker scale — **not** meters unless calibrated |

**Status rules:**

| Status | Meaning |
|---|---|
| `SEARCHING` | No lock yet this mission / after reset |
| `TRACKING` | Valid estimate this cycle |
| `LOST` | Had a lock; missing longer than lost-timeout |

---

## `GuidanceCommand`

Platform-agnostic steering desire. **Not** Betaflight channel numbers.

| Field | Type | Unit / range | Notes |
|---|---|---|---|
| `timestamp_ms` | `float64` | ms | Command publish time |
| `mode` | `GuidanceMode` | | |
| `yaw_rate` | `float64` | **normalized `-1..1`** | + = yaw right (body) |
| `pitch_rate` | `float64` | **normalized `-1..1`** | + = nose up / climb desire (stick sense finalized in StickMap) |
| `roll_rate` | `float64` | **normalized `-1..1`** | + = roll right |
| `throttle` | `float64` | **`0..1`** | 0 = min, 1 = max commanded |
| `flags.operator_override` | `bool` | | Host must yield when true |
| `flags.lost_target` | `bool` | | Echo of track loss for logging |
| `flags.link_ok` | `bool` | | Host’s view of uplink health if known |

**Mode intent:**

| Mode | Expected axes |
|---|---|
| `IDLE` | All rates ~0; throttle safe idle (arming is separate — see below) |
| `HOLD` | Rates ~0; hold via FC modes as configured |
| `TRACK_CENTER` | Yaw/pitch (optionally roll) to keep target centered |
| `INTERCEPT` | Closing / lead behavior (later milestone) |
| `ABORT` | Immediate safe rates; failsafe path |

**Invariants:** rate fields clamped to `[-1, 1]`; `throttle` to `[0, 1]` before StickMap.

**Arming:** v0 host must **not** auto-arm. Arming stays with the operator / FC.

---

## `ChannelFrame`

Raw RC channels ready for a TX bridge (mock or live).

| Field | Type | Unit / range | Notes |
|---|---|---|---|
| `timestamp_ms` | `float64` | ms | |
| `channels` | `float64[16]` (use first N) | **µs, typically `1000..2000`** | Classic RC pulse range; CRSF bridge may convert |

---

## `StickMap`

Maps `GuidanceCommand` → `ChannelFrame` for one FC/radio profile.

| Field | Type | Notes |
|---|---|---|
| `name` | `string` | e.g. `betaflight_default`, `alternate` |
| `channel_order` | list of axis tags | e.g. `[roll, pitch, throttle, yaw, …]` (AETR vs TAER etc.) |
| `scale` | per-axis gain + min/max µs | Includes caps already reflected in normalized cmd |
| `deadband` | per-axis `0..1` | Applied in normalized space before µs conversion |
| `toChannels(cmd)` | function | Pure mapping; no vision side effects |

**Portability rule:** guidance code emits only `GuidanceCommand`. All platform differences live in `StickMap` profiles.

---

## Failsafe matrix (normative)

| Condition | Required command behavior |
|---|---|
| `TrackEstimate.status == LOST` longer than lost-timeout | `mode = ABORT` or `HOLD`; `yaw_rate` / `pitch_rate` / `roll_rate` → 0 within **one** publish period |
| `flags.operator_override == true` | Stop applying host rates (or blend out immediately) |
| `flags.link_ok == false` | Stop aggressive cmds; rely on FC link-loss failsafe |
| Any publish | Rate/throttle caps always applied — never bypassed |

---

## JSON examples (fixtures / logs)

```json
{
  "frame_id": 1042,
  "timestamp_ms": 1710000000123.4,
  "width": 1280,
  "height": 720,
  "format": "bgr",
  "data": null
}
```

```json
{
  "timestamp_ms": 1710000000123.4,
  "status": "TRACKING",
  "track_id": 7,
  "bbox": { "x": 610.0, "y": 320.0, "w": 80.0, "h": 60.0 },
  "confidence": 0.92,
  "bearing_rad": { "yaw": 0.05, "pitch": -0.02 },
  "range_proxy": 4800.0
}
```

```json
{
  "timestamp_ms": 1710000000140.0,
  "mode": "TRACK_CENTER",
  "yaw_rate": -0.35,
  "pitch_rate": 0.10,
  "roll_rate": 0.0,
  "throttle": 0.45,
  "flags": {
    "operator_override": false,
    "lost_target": false,
    "link_ok": true
  }
}
```

---

## Change control

1. Propose field/unit changes here **and** in `ARCHITECTURE.md` §4 in the same PR.
2. Downstream host code must match these names before merge.
3. Do not widen scope (e.g. full SLAM poses) until a later milestone needs them.
