import math
from typing import Dict, Any, List, Tuple


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower().replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_cv(value: Any) -> float | None:
    v = _to_float(value)
    if v is None:
        return None
    if v > 1:
        return v / 100.0
    return v


def choose_design(rsabe: bool, cv_intra: float | None) -> Dict[str, Any]:
    if rsabe:
        return {
            "design": "replicate",
            "periods": 3,
            "sequences": 3,
            "washout_days": None,
            "rationale": "RSABE requested",
        }
    if cv_intra is not None and cv_intra >= 0.30:
        return {
            "design": "replicate",
            "periods": 3,
            "sequences": 3,
            "washout_days": None,
            "rationale": "High intra-subject variability (CV ≥ 30%)",
        }
    return {
        "design": "2x2",
        "periods": 2,
        "sequences": 2,
        "washout_days": None,
        "rationale": "Low intra-subject variability",
    }


def compute_washout_days(t12_h: float | None, min_days: int = 7) -> int:
    if not t12_h:
        return min_days
    # >= 5 * T1/2
    days = math.ceil((5 * t12_h) / 24.0)
    return max(min_days, days)


def sample_size(
    cv_intra: float | None,
    drop_out: float = 0.0,
    screen_fail: float = 0.0,
    alpha: float = 0.05,
    power: float = 0.8,
    delta: float = math.log(1.25),
) -> Dict[str, Any]:
    if cv_intra is None:
        cv_intra = 0.25

    z_alpha = 1.96  # two-sided 0.05
    z_beta = 0.84   # power 80%
    s2 = math.log(1 + cv_intra ** 2)
    n0 = 2 * (z_alpha + z_beta) ** 2 * s2 / (delta ** 2)
    n0 = math.ceil(n0)
    if n0 % 2 == 1:
        n0 += 1

    drop_out = max(0.0, min(0.9, drop_out))
    screen_fail = max(0.0, min(0.9, screen_fail))
    n_dropout = math.ceil(n0 / (1 - drop_out)) if drop_out else n0
    n_total = math.ceil(n_dropout / (1 - screen_fail)) if screen_fail else n_dropout

    return {
        "n_required": n0,
        "n_dropout_adjusted": n_dropout,
        "n_screening": n_total,
        "assumptions": {
            "alpha": alpha,
            "power": power,
            "delta": delta,
            "cv_intra": cv_intra,
        },
    }


def generate_timeline(tmax_h: float | None, t12_h: float | None) -> Dict[str, Any]:
    # Base grid
    grid = [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 24, 36, 48, 72]

    if tmax_h:
        # ensure dense around tmax
        around = [max(0, tmax_h - 1), tmax_h - 0.5, tmax_h, tmax_h + 0.5, tmax_h + 1]
        grid.extend([round(x, 2) for x in around if x >= 0])

    horizon = 72
    if t12_h:
        horizon = max(horizon, int(math.ceil(4 * t12_h)))

    grid = sorted(set([x for x in grid if x <= horizon]))
    return {
        "sampling_horizon_h": horizon,
        "timepoints_h": grid,
        "rationale": "Dense around Tmax; horizon ≥ 4×T1/2",
    }


def summarize_rag(rag: Dict[str, Any]) -> Dict[str, Any]:
    cvintra = rag.get("cvintra") or {}
    pk = rag.get("pk") or {}
    return {
        "cvintra_cmax": cvintra.get("cmax"),
        "cvintra_auc": cvintra.get("auc"),
        "tmax_h": pk.get("tmax_h"),
        "t12_h": pk.get("t12_h"),
    }
