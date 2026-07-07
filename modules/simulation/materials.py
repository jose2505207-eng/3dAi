"""Material properties for the mass check (Layer 1) and FEA (Layer 2).

Material is configuration (env MATERIAL), not inference. When MATERIAL is
unset we compute with a NAMED default assumption (aluminum_6061) and say so —
per the honesty rule the mass-budget comparison is then `not_run`
(assumption-based), never a `pass` built on a guess. FEA verdicts always
carry the material source so an assumption-based pass is auditable.
"""

from __future__ import annotations

import os

DEFAULT_MATERIAL = "aluminum_6061"

# density g/cm^3; E and yield in MPa; nu dimensionless. Room-temperature
# typical engineering values (polymer values are printed/molded typicals and
# vary by grade — they are recorded assumptions, not measurements).
PROPERTIES = {
    "aluminum_6061": {"density_g_cm3": 2.70, "e_mpa": 68_900, "nu": 0.33, "yield_mpa": 276},
    "aluminum_7075": {"density_g_cm3": 2.81, "e_mpa": 71_700, "nu": 0.33, "yield_mpa": 503},
    "steel_1018": {"density_g_cm3": 7.87, "e_mpa": 205_000, "nu": 0.29, "yield_mpa": 370},
    "stainless_304": {"density_g_cm3": 8.00, "e_mpa": 193_000, "nu": 0.29, "yield_mpa": 215},
    "titanium_6al4v": {"density_g_cm3": 4.43, "e_mpa": 113_800, "nu": 0.34, "yield_mpa": 880},
    "brass_c360": {"density_g_cm3": 8.50, "e_mpa": 97_000, "nu": 0.31, "yield_mpa": 310},
    "abs": {"density_g_cm3": 1.04, "e_mpa": 2_300, "nu": 0.35, "yield_mpa": 40},
    "pla": {"density_g_cm3": 1.24, "e_mpa": 3_500, "nu": 0.36, "yield_mpa": 60},
    "petg": {"density_g_cm3": 1.27, "e_mpa": 2_100, "nu": 0.40, "yield_mpa": 50},
    "nylon_pa12": {"density_g_cm3": 1.01, "e_mpa": 1_700, "nu": 0.39, "yield_mpa": 48},
}

# Layer 1 compatibility: name -> density only.
DENSITY_G_CM3 = {name: p["density_g_cm3"] for name, p in PROPERTIES.items()}


class UnknownMaterialError(Exception):
    """MATERIAL was set explicitly but is not in the properties table."""


def resolve_material() -> dict:
    """Returns {name, density_g_cm3, e_mpa, nu, yield_mpa, source} where
    source is 'env' (explicit configuration) or 'default_assumption'. Raises
    UnknownMaterialError for an explicit-but-unknown MATERIAL — never guesses."""
    raw = os.environ.get("MATERIAL", "").strip().lower()
    if not raw:
        return {"name": DEFAULT_MATERIAL, **PROPERTIES[DEFAULT_MATERIAL],
                "source": "default_assumption"}
    if raw not in PROPERTIES:
        raise UnknownMaterialError(
            f"MATERIAL={raw!r} is not in the properties table "
            f"(known: {', '.join(sorted(PROPERTIES))})")
    return {"name": raw, **PROPERTIES[raw], "source": "env"}
