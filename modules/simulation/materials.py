"""Material densities for the mass check.

Material is configuration (env MATERIAL), not inference. When MATERIAL is
unset we compute with a NAMED default assumption (aluminum_6061) and say so —
per the honesty rule the mass-budget comparison is then `not_run`
(assumption-based), never a `pass` built on a guess.
"""

from __future__ import annotations

import os

DEFAULT_MATERIAL = "aluminum_6061"

# g/cm^3, room temperature, common engineering references.
DENSITY_G_CM3 = {
    "aluminum_6061": 2.70,
    "aluminum_7075": 2.81,
    "steel_1018": 7.87,
    "stainless_304": 8.00,
    "titanium_6al4v": 4.43,
    "brass_c360": 8.50,
    "abs": 1.04,
    "pla": 1.24,
    "petg": 1.27,
    "nylon_pa12": 1.01,
}


class UnknownMaterialError(Exception):
    """MATERIAL was set explicitly but is not in the density table."""


def resolve_material() -> dict:
    """Returns {name, density_g_cm3, source} where source is 'env' (explicit
    configuration) or 'default_assumption'. Raises UnknownMaterialError for
    an explicit-but-unknown MATERIAL — never guesses a density."""
    raw = os.environ.get("MATERIAL", "").strip().lower()
    if not raw:
        return {"name": DEFAULT_MATERIAL,
                "density_g_cm3": DENSITY_G_CM3[DEFAULT_MATERIAL],
                "source": "default_assumption"}
    if raw not in DENSITY_G_CM3:
        raise UnknownMaterialError(
            f"MATERIAL={raw!r} is not in the density table "
            f"(known: {', '.join(sorted(DENSITY_G_CM3))})")
    return {"name": raw, "density_g_cm3": DENSITY_G_CM3[raw], "source": "env"}
