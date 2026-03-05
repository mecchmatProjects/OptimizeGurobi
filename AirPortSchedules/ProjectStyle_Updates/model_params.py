from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import ast


@dataclass
class Params:
    All_Check_List: List[str] = field(default_factory=lambda: ["Acheck", "Bcheck", "Ccheck", "Dcheck"])
    All_Checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    All_Check_days: Dict[str, int] = field(default_factory=lambda: {"Acheck": 50, "Bcheck": 180, "Ccheck": 540, "Dcheck": 1825})
    All_Check_Done_hours: Dict[str, int] = field(default_factory=lambda: {"Acheck": 48, "Bcheck": 1440, "Ccheck": 4320, "Dcheck": 14600})
    All_Check_durations: Dict[str, int] = field(default_factory=lambda: {"Acheck": 8 * 60, "Bcheck": 48 * 60, "Ccheck": 5 * 24 * 60, "Dcheck": 10 * 24 * 60})
    All_Check_durations_days: Dict[str, int] = field(default_factory=lambda: {"Acheck": 1, "Bcheck": 2, "Ccheck": 5, "Dcheck": 10})
    All_Checks_Done_Days: Dict[str, Any] = field(default_factory=dict)
    Mbig: int = 10**6
    # Optional maintenance capacity mapping (mcap[(m, d)] = capacity)
    mcap: Optional[Dict[Any, int]] = None


def normalize_params(raw: Optional[Any], data: Optional[Dict] = None) -> Params:
    """Return a Params instance merged with defaults.

    raw may be None, a dict-like or an object with attributes. If `data` contains
    maintenance-related keys we also try to use them as defaults.
    """
    defaults = Params()

    # helper to overlay dictionary onto defaults
    def overlay_from_dict(d: Dict, target: Params):
        for k, v in d.items():
            if hasattr(target, k):
                setattr(target, k, v)

    p = Params()

    # 1) If data contains top-level maintenance keys, overlay them
    if isinstance(data, dict):
        for key in [
            'All_Check_List', 'All_Checks', 'All_Check_days', 'All_Check_Done_hours',
            'All_Check_durations', 'All_Check_durations_days', 'All_Checks_Done_Days', 'mcap'
        ]:
            if key in data:
                setattr(p, key, data[key])

    # 2) Overlay raw params if provided
    if raw is None:
        return p

    if isinstance(raw, dict):
        overlay_from_dict(raw, p)
        return p

    # Object with attributes
    for field_name in p.__dataclass_fields__.keys():
        if hasattr(raw, field_name):
            setattr(p, field_name, getattr(raw, field_name))

    # Normalize mcap into {(m, d): int} shape for easier lookups later.
    # Accept shapes:
    # - {(m, d): cap}
    # - {m: {d: cap}}
    # - {"(m,d)": cap} (stringified tuple)
    if p.mcap is not None and isinstance(p.mcap, dict):
        new = {}
        for k, v in list(p.mcap.items()):
            # already a tuple key
            if isinstance(k, tuple) and len(k) == 2:
                try:
                    new[(k[0], int(k[1]))] = int(v)
                except Exception:
                    new[k] = v
                continue

            # stringified tuple like "('A', 1)"
            if isinstance(k, str):
                try:
                    parsed = ast.literal_eval(k)
                    if isinstance(parsed, tuple) and len(parsed) == 2:
                        new[(parsed[0], int(parsed[1]))] = int(v)
                        continue
                except Exception:
                    pass

            # nested dict: {m: {d: cap}}
            if isinstance(v, dict):
                for d, cap in v.items():
                    try:
                        day = int(d)
                    except Exception:
                        # skip invalid day key
                        continue
                    new[(k, day)] = int(cap)
                continue

            # fallback: try to interpret k as airport and default day 1
            try:
                new[(k, 1)] = int(v)
            except Exception:
                # give up on this entry
                continue

        p.mcap = new

    return p


def validate_params(p: Params) -> None:
    """Validate a Params instance and raise ValueError on malformed content.

    Checks performed:
    - All_Check_List is a non-empty list of strings
    - For each check in All_Check_List, dictionaries like All_Check_days,
      All_Check_Done_hours, All_Check_durations, All_Check_durations_days
      contain an entry.
    - Mbig is a positive integer
    - mcap if present is a dict with tuple keys (m,d) mapping to non-negative ints
    """
    if not isinstance(p.All_Check_List, list) or len(p.All_Check_List) == 0:
        raise ValueError("All_Check_List must be a non-empty list of check names")

    for chk in p.All_Check_List:
        for attr_name in ('All_Check_days', 'All_Check_Done_hours', 'All_Check_durations', 'All_Check_durations_days'):
            attr = getattr(p, attr_name, None)
            if not isinstance(attr, dict) or chk not in attr:
                raise ValueError(f"Parameter '{attr_name}' must contain an entry for check '{chk}'")

    if not isinstance(p.Mbig, int) or p.Mbig <= 0:
        raise ValueError("Mbig must be a positive integer")

    if p.mcap is not None:
        if not isinstance(p.mcap, dict):
            raise ValueError("mcap must be a dict mapping (m,d) -> int")
        for k, v in p.mcap.items():
            if not (isinstance(k, tuple) and len(k) == 2):
                raise ValueError("mcap keys must be (m,d) tuples")
            if not isinstance(v, int) or v < 0:
                raise ValueError("mcap capacities must be non-negative integers")

