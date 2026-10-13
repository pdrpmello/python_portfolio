"""Le data/raw/ e imprime um retrato do treino: volume, distribuicao por zona,
deriva de FC nas parciais e o contexto de wellness.

Roda offline - nao precisa de sessao do Garmin.
Uso: python scripts/analyze.py
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAW = Path("data/raw")


def load(name, default=None):
    p = RAW / f"{name}.json"
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def mmss(seconds: float) -> str:
    if not seconds:
        return "--"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def pace_per_km(speed_ms: float | None) -> str:
    """m/s -> min:seg por km."""
    if not speed_ms:
        return "--"
    return mmss(1000 / speed_ms)


def hhmm(seconds: float) -> str:
    h, rem = divmod(int(round(seconds)), 3600)
    return f"{h}h{rem // 60:02d}" if h else f"{rem // 60}min"


def iso_week(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-S{w:02d}"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# ── zonas ───────────────────────────────────────────────────────────────────

zones_cfg = (load("hr_zones") or [{}])[0]
FLOORS = [zones_cfg.get(f"zone{i}Floor") for i in range(1, 6)]
HR_MAX_CFG = zones_cfg.get("maxHeartRateUsed")
HR_REST_CFG = zones_cfg.get("restingHeartRateUsed")

activities = load("activities", []) or []
runs = [a for a in activities if "running" in str(a.get("activityType", {}).get("typeKey", ""))]
meta = load("meta", {}) or {}

rule("SETUP")
print(f"coleta: {meta.get('fetchedAt', '?')[:16].replace('T', ' ')}")
print(f"historico: {meta.get('oldestActivity')} -> {meta.get('newestActivity')}")
print(f"{len(activities)} atividades, {len(runs)} corridas")
print(f"\nzonas por %FCmax (metodo {zones_cfg.get('trainingMethod')}), max={HR_MAX_CFG} repouso={HR_REST_CFG}")
for i, floor in enumerate(FLOORS, start=1):
    ceil = FLOORS[i] - 1 if i < 5 else HR_MAX_CFG
    print(f"  Z{i}: {floor}-{ceil} bpm")

# ── atividades ──────────────────────────────────────────────────────────────

rule("ATIVIDADES (todas)")
hdr = f"{'data':<11}{'tipo':<13}{'km':>6}{'tempo':>7}{'pace':>7}{'FCm':>5}{'FCx':>5}  {'Z1-Z5 (% do tempo)':<26}{'efeito'}"
print(hdr)
print("-" * len(hdr))

zone_totals = defaultdict(float)  # segundos em zona, so corridas
observed_max_hr = 0

for a in activities:
    d = (a.get("startTimeLocal") or "")[:10]
    type_key = str(a.get("activityType", {}).get("typeKey", "?"))
    kind = type_key.replace("_running", "_run")  # so para caber na coluna
    dist_km = (a.get("distance") or 0) / 1000
    dur = a.get("duration") or 0
    zs = [a.get(f"hrTimeInZone_{i}") or 0 for i in range(1, 6)]
    tot = sum(zs) or 1
    pct = "".join(f"{100 * z / tot:>5.0f}" for z in zs)
    observed_max_hr = max(observed_max_hr, a.get("maxHR") or 0)
    if "running" in type_key:  # inclui treadmill_running
        for i, z in enumerate(zs, start=1):
            zone_totals[i] += z
    print(
        f"{d:<11}{kind[:12]:<13}{dist_km:>6.1f}{hhmm(dur):>7}"
        f"{pace_per_km(a.get('averageSpeed')):>7}"
        f"{a.get('averageHR') or 0:>5.0f}{a.get('maxHR') or 0:>5.0f}  {pct:<26}"
        f"{str(a.get('trainingEffectLabel', '')).lower()}"
    )

# ── volume semanal ──────────────────────────────────────────────────────────

rule("VOLUME SEMANAL (corridas)")
weeks = defaultdict(lambda: {"km": 0.0, "s": 0.0, "n": 0})
for a in runs:
    w = weeks[iso_week((a.get("startTimeLocal") or "")[:10])]
    w["km"] += (a.get("distance") or 0) / 1000
    w["s"] += a.get("duration") or 0
    w["n"] += 1
print(f"{'semana':<10}{'sessoes':>8}{'km':>7}{'tempo':>8}")
for w in sorted(weeks):
    v = weeks[w]
    print(f"{w:<10}{v['n']:>8}{v['km']:>7.1f}{hhmm(v['s']):>8}")

if runs:
    longest = max(runs, key=lambda a: a.get("distance") or 0)
    print(
        f"\nmaior corrida: {(longest.get('distance') or 0) / 1000:.1f} km em "
        f"{hhmm(longest.get('duration') or 0)} ({(longest.get('startTimeLocal') or '')[:10]})"
    )

# ── distribuicao por zona ───────────────────────────────────────────────────

rule("DISTRIBUICAO DE FC - SO CORRIDAS")
total_z = sum(zone_totals.values()) or 1
for i in range(1, 6):
    s = zone_totals[i]
    bar = "#" * int(round(50 * s / total_z))
    print(f"Z{i} {FLOORS[i - 1]:>3}+ {hhmm(s):>7} {100 * s / total_z:>5.1f}%  {bar}")
print(f"\ntempo total correndo: {hhmm(total_z)}")
easy = zone_totals[1] + zone_totals[2]
print(f"facil (Z1+Z2): {100 * easy / total_z:.1f}%   forte (Z3+Z4+Z5): {100 * (total_z - easy) / total_z:.1f}%")
print(f"\nFC max observada no historico: {observed_max_hr} bpm (configurada: {HR_MAX_CFG})")

# ── parciais: deriva de FC ──────────────────────────────────────────────────

split_files = sorted((RAW / "splits").glob("*.json")) if (RAW / "splits").exists() else []
by_id = {str(a["activityId"]): a for a in activities}
if split_files:
    rule("PARCIAIS POR KM - DERIVA DE FC")
    for f in split_files:
        act = by_id.get(f.stem, {})
        laps = (json.loads(f.read_text(encoding="utf-8")) or {}).get("lapDTOs") or []
        laps = [l for l in laps if (l.get("distance") or 0) > 400]  # ignora sobras
        if len(laps) < 3:
            continue
        d = (act.get("startTimeLocal") or "")[:10]
        print(f"\n{d}  {(act.get('distance') or 0) / 1000:.1f} km  ({act.get('activityName', '')})")
        cells = [
            f"{pace_per_km(l.get('averageSpeed'))}@{l.get('averageHR') or 0:.0f}"
            for l in laps
        ]
        for i in range(0, len(cells), 6):
            print("   " + "  ".join(f"{c:>11}" for c in cells[i : i + 6]))
        hrs = [l.get("averageHR") for l in laps if l.get("averageHR")]
        if len(hrs) >= 4:
            half = len(hrs) // 2
            print(
                f"   FC 1a metade {statistics.mean(hrs[:half]):.0f} -> 2a metade "
                f"{statistics.mean(hrs[half:]):.0f} bpm (deriva {statistics.mean(hrs[half:]) - statistics.mean(hrs[:half]):+.0f})"
            )

# ── wellness ────────────────────────────────────────────────────────────────

rule("WELLNESS")
daily = load("daily_summary", {}) or {}
rows = []
for d in sorted(daily):
    v = daily[d]
    rhr = v.get("restingHeartRate")
    if rhr is None:
        continue
    rows.append(
        (
            d,
            rhr,
            v.get("totalSteps"),
            (v.get("sleepingSeconds") or 0) / 3600,
            v.get("averageStressLevel"),
            v.get("bodyBatteryHighestValue"),
            v.get("moderateIntensityMinutes") or 0,
            v.get("vigorousIntensityMinutes") or 0,
        )
    )

if rows:
    print(f"dias com FC de repouso: {len(rows)} ({rows[0][0]} -> {rows[-1][0]})")
    rhrs = [r[1] for r in rows]
    print(f"FC repouso: min {min(rhrs)} / mediana {statistics.median(rhrs):.0f} / max {max(rhrs)} bpm")
    sleeps = [r[3] for r in rows if r[3]]
    if sleeps:
        print(f"sono: mediana {statistics.median(sleeps):.1f} h em {len(sleeps)} noites")
    print(f"\n{'data':<11}{'FCrep':>6}{'passos':>8}{'sono':>6}{'stress':>7}{'BBmax':>6}{'mod':>5}{'vig':>5}")
    for d, rhr, steps, sl, st, bb, mod, vig in rows[-21:]:
        print(
            f"{d:<11}{rhr:>6}{steps or 0:>8}{sl:>6.1f}{st if st is not None else '-':>7}"
            f"{bb if bb is not None else '-':>6}{mod:>5}{vig:>5}"
        )
else:
    print("nenhum dia com FC de repouso registrada")

hrv = load("hrv", {}) or {}
if hrv:
    print(f"\nHRV - {len(hrv)} noites registradas:")
    for d in sorted(hrv):
        s = (hrv[d] or {}).get("hrvSummary") or {}
        print(
            f"  {d}  media {s.get('lastNightAvg')} ms  pico5min {s.get('lastNight5MinHigh')} ms  "
            f"status {s.get('status')}  baseline {s.get('baseline')}"
        )

readiness = load("readiness", {}) or {}
ready_rows = [(d, v) for d, v in sorted(readiness.items()) if isinstance(v, list) and v]
if ready_rows:
    print("\nprontidao de treino:")
    for d, v in ready_rows[-10:]:
        r = v[0]
        print(
            f"  {d}  score {r.get('score')} ({r.get('level')})  sono {r.get('sleepScore')}  "
            f"recuperacao {r.get('recoveryTime')}min  carga aguda {r.get('acuteLoad')}"
        )

vo2 = load("vo2max", {}) or {}
gen = (vo2.get("generic") or {}) if isinstance(vo2, dict) else {}
if gen:
    print(
        f"\nVO2max: {gen.get('vo2MaxPreciseValue') or gen.get('vo2MaxValue')} ml/kg/min "
        f"em {gen.get('calendarDate', '?')}"
    )

# ── recordes ────────────────────────────────────────────────────────────────

PR_LABELS = {
    1: "1 km", 2: "1 milha", 3: "5 km", 4: "10 km", 5: "meia maratona",
    6: "maratona", 7: "maior corrida", 8: "maior subida",
    12: "passos/dia", 13: "passos/semana", 14: "passos/mes",
}
prs = load("personal_records", []) or []
rule("RECORDES")
for p in prs:
    tid = p.get("typeId")
    label = PR_LABELS.get(tid, f"tipo {tid}")
    val = p.get("value")
    when = p.get("prStartTimeGmtFormatted") or p.get("activityStartDateTimeLocalFormatted") or ""
    if tid in (1, 2, 3, 4, 5, 6) and val:
        print(f"  {label:<15}{mmss(val):>9}   {str(when)[:10]}")
    elif tid == 7 and val:
        print(f"  {label:<15}{val / 1000:>8.1f} km  {str(when)[:10]}")
    elif tid in (12, 13, 14) and val:
        print(f"  {label:<15}{int(val):>9}   {str(when)[:10]}")
