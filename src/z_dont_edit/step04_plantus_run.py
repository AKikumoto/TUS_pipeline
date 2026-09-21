#!/usr/bin/env python3
"""
scripts/TUS/run/step04_plantus_run.py
Config-driven PlanTUS wrapper (Step 4 — Target Specification, Path B).

Must be run with the SimNIBS Python interpreter, e.g.:

    {simnibs_python} step04_plantus_run.py \\
        --site  ../config/sites/site_RIKEN_AK.yaml \\
        --sub   sub-NS \\
        --target aMCC_NeuroSynthTopic112 \\
        --side  _R

All transducer parameters (focal depth range, FLHM, plane offset, etc.) are
read from the transducer YAML referenced by the site config.
All software paths (wb_command, FreeSurfer, FSL) are read from the site config.

Dependencies
------------
- SimNIBS >= 4.0   (must use simnibs_env Python)
- Connectome Workbench >= 1.5   (wb_view, wb_command)
- FreeSurfer >= 8.0   (mris_convert)
- FSL >= 6.0   (fslmaths)
- pynput   (installed in simnibs_env: pip install pynput)
- PlanTUS  (scripts/TUS/PlanTUS/code/)

Input
-----
- SimNIBS m2m directory:        {data_dir}/{sub_id_bare}/m2m_{sub_id_full}/
- Target mask (native space):   {data_dir}/{sub_id_bare}/*_{target_name}_mask_native{side}.nii.gz

Output
------
- PlanTUS output folder:  {m2m_dir}/PlanTUS/{sub_id_full}_T1w_{target_name}_mask_native{side}/
  - scene.scene            → open in Workbench to inspect / select vertex
  - vtx{NNNNN}/            → per-vertex placement outputs
    - *_transducer.txt     → 4×4 transducer matrix (Scanner/RAS)
    - focus_position_matrix_*.txt
    - depth_report_*.txt

Usage
-----
    python step04_plantus_run.py --site YAML --sub ID --target LABEL [--side SIDE]
                                 [--additional-offset MM] [--dry-run]
"""

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate src/utils.py (two levels up: run/ → TUS/ → src/)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from src.utils import (
    load_site_config,
    load_transducer_config,
    resolve_data_dir,
    normalise_sub_id,
    setup_environment,
    transducer_params,
    run_plantus,
)


# ---------------------------------------------------------------------------
# (Functions are defined in src/utils.py — see there for implementation.)
# ---------------------------------------------------------------------------

# Dummy reference to suppress "unused import" warnings — remove if linter complains.
def _dummy() -> None:  # noqa: F401
    """Placeholder — no local functions defined in this step script."""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Config-driven PlanTUS wrapper (Step 4 — TUS target planning)."
    )
    p.add_argument("--site",   required=True, help="Path to site YAML config")
    p.add_argument("--sub",    required=True, help="Subject ID (with or without 'sub-' prefix)")
    p.add_argument("--target", required=True, help="Target label, e.g. aMCC_NeuroSynthTopic112")
    p.add_argument("--side",   default="",    help="Side suffix: _R, _L, or '' for bilateral")
    p.add_argument("--additional-offset", type=float, default=0.0,
                   help="Extra gel/pad offset between exit plane and skin (mm, default 0)")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate inputs and print paths without running PlanTUS")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    site_yaml = Path(args.site).expanduser().resolve()
    cfg  = load_site_config(site_yaml)
    tcfg = load_transducer_config(cfg, site_yaml)
    tp   = transducer_params(tcfg)

    setup_environment(cfg)

    data_dir = resolve_data_dir(cfg)
    sub_id_full, sub_id_bare = normalise_sub_id(args.sub)
    m2m_dir = data_dir / sub_id_bare / f"m2m_{sub_id_full}"

    if not m2m_dir.exists():
        sys.exit(f"ERROR: m2m directory not found: {m2m_dir}")

    print(f"Site     : {cfg.get('site')} / {cfg.get('station')}")
    print(f"Subject  : {sub_id_full}")
    print(f"Target   : {args.target}{args.side}")
    print(f"Transducer: {tcfg.get('name')}  ({tcfg.get('transducer_serial', '')})")
    print(f"m2m_dir  : {m2m_dir}")

    run_plantus(
        sub_id_full=sub_id_full,
        sub_id_bare=sub_id_bare,
        m2m_dir=m2m_dir,
        target_name=args.target,
        target_side=args.side,
        tp=tp,
        additional_offset=args.additional_offset,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
