"""Paces-alvo para uma FC de referencia, a partir das parciais por km.

Duas coisas os dados DIZEM hoje:
  1. ancora: o pace do 1o km e a FC dele — o ponto menos contaminado por deriva.
  2. deriva: quantos bpm a FC sobe por minuto no mesmo pace.

Uma coisa os dados NAO dizem: quanto o pace precisa cair para chegar a 140 bpm.
Todas as corridas de rua estao entre ~6:13 e ~6:54/km e entre 158 e 164 bpm de
media — nao ha alavanca para extrapolar. Por isso a sensibilidade (segundos por
km para cada bpm) entra como PREMISSA declarada, nao como ajuste, ate existirem
corridas de verdade na faixa 130-148.

Quando houver >= 6 parciais abaixo de 150 bpm, o script passa a usar a regressao
dos dados reais no lugar da premissa e avisa na saida.

Uso: python scripts/pace_model.py [--sens 5.0]   (segundos/km por bpm)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

RAW = Path("data/raw")
SENS_DEFAULT = 5.0  # s/km por bpm — premissa para corrida facil
MIN_EASY_SPLITS = 6  # parciais abaixo de 150 bpm para o ajuste substituir a premissa

sens = SENS_DEFAULT
if "--sens" in sys.argv:
    sens = float(sys.argv[sys.argv.index("--sens") + 1])


def mmss(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def pace_of(speed_ms: float) -> float:
    """m/s -> segundos por km."""
    return 1000 / speed_ms


acts = {str(a["activityId"]): a for a in json.loads((RAW / "activities.json").read_text("utf-8"))}

runs = []
for f in sorted((RAW / "splits").glob("*.json")):
    act = acts.get(f.stem, {})
    kind = str(act.get("activityType", {}).get("typeKey", ""))
    laps = [l for l in (json.loads(f.read_text("utf-8")).get("lapDTOs") or [])
            if (l.get("distance") or 0) > 400 and l.get("averageHR")]
    if len(laps) < 3:
        continue
    runs.append({
        "date": (act.get("startTimeLocal") or "")[:10],
        "hora": (act.get("startTimeLocal") or "")[11:16],
        "esteira": "treadmill" in kind,
        "km": (act.get("distance") or 0) / 1000,
        "laps": laps,
    })

road = [r for r in runs if not r["esteira"]]

# ── 1. ancoras: 1o km de cada corrida de rua ────────────────────────────────
print("=" * 74)
print("ANCORA — o 1o km de cada corrida (antes da deriva entrar)")
print("=" * 74)
print(f"{'data':<12}{'hora':<7}{'pace km1':>10}{'FC km1':>8}{'pace medio':>12}{'FC media':>10}")
anchors = []
for r in road:
    l0 = r["laps"][0]
    p0, hr0 = pace_of(l0["averageSpeed"]), l0["averageHR"]
    dur = sum(l["duration"] for l in r["laps"])
    dist = sum(l["distance"] for l in r["laps"])
    hr_avg = float(np.mean([l["averageHR"] for l in r["laps"]]))
    anchors.append((p0, hr0))
    print(f"{r['date']:<12}{r['hora']:<7}{mmss(p0):>10}{hr0:>8.0f}"
          f"{mmss(dur / (dist / 1000)):>12}{hr_avg:>10.0f}")

p_anchor = float(np.mean([a[0] for a in anchors]))
hr_anchor = float(np.mean([a[1] for a in anchors]))
print(f"\nmedia: {mmss(p_anchor)}/km a {hr_anchor:.0f} bpm, fresco")

# ── 2. deriva medida dentro de cada corrida ─────────────────────────────────
print("\n" + "=" * 74)
print("DERIVA — quantos bpm a FC sobe por minuto, no mesmo pace")
print("=" * 74)
drifts = []
for r in road:
    t, hrs = [], []
    acc = 0.0
    for l in r["laps"]:
        acc += l["duration"]
        t.append((acc - l["duration"] / 2) / 60)
        hrs.append(l["averageHR"])
    slope = float(np.polyfit(t, hrs, 1)[0])
    drifts.append(slope)
    print(f"{r['date']:<12}{r['km']:>5.1f} km   {slope:+.2f} bpm/min   "
          f"({slope * 30:+.0f} bpm a cada 30 min)")
drift = float(np.mean(drifts))
print(f"\nmedia: {drift:+.2f} bpm/min ({drift * 30:+.0f} a cada 30 min)")
print("Essa deriva e alta PORQUE ele corre forte. Em esforco facil ela encolhe —")
print("esperar algo como metade disso quando as corridas estiverem dentro do teto.")

# ── 3. o ajuste ja e utilizavel? ────────────────────────────────────────────
easy = [(pace_of(l["averageSpeed"]), l["averageHR"])
        for r in road for l in r["laps"] if l["averageHR"] < 150]
all_hr = [l["averageHR"] for r in road for l in r["laps"]]
print("\n" + "=" * 74)
print("BASE DE EXTRAPOLACAO")
print("=" * 74)
print(f"parciais de rua: {len(all_hr)}   faixa de FC: {min(all_hr):.0f}-{max(all_hr):.0f} bpm")
print(f"parciais abaixo de 150 bpm: {len(easy)}  (precisa de {MIN_EASY_SPLITS} para o ajuste valer)")

if len(easy) >= MIN_EASY_SPLITS:
    p_arr = np.array([e[0] for e in easy])
    h_arr = np.array([e[1] for e in easy])
    sens_fit = float(-np.polyfit(h_arr, p_arr, 1)[0])
    print(f"AJUSTE REAL: {sens_fit:.1f} s/km por bpm — usando os seus dados, nao a premissa.")
    sens = sens_fit
else:
    print(f"PREMISSA: {sens:.1f} s/km por bpm (valor tipico de corrida facil).")
    print("Substitua rodando de novo depois de 2 semanas de treinos dentro do teto.")

# ── 4. tabela de paces ──────────────────────────────────────────────────────
print("\n" + "=" * 74)
print(f"PACE ESTIMADO POR FC — rua, a partir de {mmss(p_anchor)}/km a {hr_anchor:.0f} bpm")
print("=" * 74)
print(f"{'FC':<6}{'pace':>9}   (fresco, inicio da corrida)")
for hr_t in [130, 135, 138, 140, 142, 145, 148]:
    print(f"{hr_t:<6}{mmss(p_anchor + (hr_anchor - hr_t) * sens):>9}")

print("\n" + "=" * 74)
print("PACE POR SESSAO - construido de tras para frente, a partir do teto")
print("=" * 74)

# Deriva satura, nao cresce reto: D(t) = D_MAX * (1 - e^(-t/TAU)).
# Extrapolar a deriva linear por 2h daria paces finais absurdos (10:53/km).
D_MAX = 12.0  # bpm de deriva total em esforco facil, com calor
TAU = 40.0    # minutos ate ~63% dela aparecer
MARGIN = 2    # folga abaixo do teto no fim da corrida


def drift_at(t: float) -> float:
    return D_MAX * (1 - np.exp(-t / TAU))


print(f"(deriva modelada saturando em {D_MAX:.0f} bpm, constante de {TAU:.0f} min —")
print(f" a sua deriva medida hoje, {drift * 30:+.0f} bpm/30min, e de esforco FORTE e vai encolher)")
print(f"\n{'sessao':<26}{'FC 1o km':>9}{'FC fim':>8}{'teto':>6}{'pace inicio -> fim':>21}")
print("-" * 70)
sessions = [
    ("Rodagem curta 30-35 min", 33, 148),
    ("Rodagem 40 min", 40, 148),
    ("Rodagem longa 45-55 min", 50, 148),
    ("Longo 60-75 min", 68, 145),
    ("Longo 90-110 min", 100, 145),
    ("Longo 120+ min", 130, 145),
]
for name, mins, ceil in sessions:
    d = drift_at(mins)
    hr_end = ceil - MARGIN
    hr_start = hr_end - d
    p_start = p_anchor + (hr_anchor - hr_start) * sens
    p_end = p_start + d * sens
    print(f"{name:<26}{hr_start:>9.0f}{hr_end:>8.0f}{ceil:>6}"
          f"{mmss(p_start) + ' -> ' + mmss(p_end):>21}")

print("\nLeia assim: comece nesse pace e aceite terminar naquele. Segurar a FC")
print("significa desacelerar ao longo da corrida - nao e queda de forma, e o treino")
print("funcionando. Se o pace do inicio ja te leva acima da FC do 1o km, va mais devagar:")
print("a coluna de FC manda, a de pace so avisa o que esperar.")
print("\nNa esteira, ignore estes numeros: a distancia dela esta descalibrada.")
print("La, so tempo e FC.")
