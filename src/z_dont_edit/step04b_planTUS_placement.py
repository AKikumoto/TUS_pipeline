#!/usr/bin/env python3
"""
scripts/TUS/run/step04b_planTUS_placement.py
Run acoustic simulation placement for a selected vertex (Step 4b).

Run AFTER step04a_planTUS_prepscene.py and after selecting a vertex in
Workbench. Provide the vertex index you noted from wb_view.

Must be run with the SimNIBS Python interpreter, e.g.:

    {simnibs_python} step04b_planTUS_placement.py \\
        --site  ../config/sites/site_RIKEN_AK.yaml \\
        --sub   sub-NS \\
        --target aMCC_NeuroSynthTopic112 \\
        --side  _R \\
        --vtx   12345 \\
        [--additional-offset 2.0]

Input
-----
- PlanTUS scene folder written by step04a, including skin_target_distances.npy

Output
------
- {m2m_dir}/PlanTUS/<target_roi_name>/vtx{NNNNN}/
  - *_transducer.txt           → 4×4 transducer matrix (Scanner/RAS)
  - focus_position_matrix_*.txt
  - depth_report_*.txt
  - *_depth_report_vtx{NNNNN}.txt

See Also
--------
- step04a_planTUS_prepscene.py  — generates surfaces, maps, and scene file
- step04_planTUS.ipynb          — full interactive GUI workflow (pynput)
"""

import argparse
import sys
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
    run_plantus_placement,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run PlanTUS placement for a selected vertex (Step 4b)."
    )
    p.add_argument("--site",   required=True, help="Path to site YAML config")
    p.add_argument("--sub",    required=True, help="Subject ID (with or without 'sub-' prefix)")
    p.add_argument("--target", required=True, help="Target label, e.g. aMCC_NeuroSynthTopic112")
    p.add_argument("--side",   default="",    help="Side suffix: _R, _L, or '' for bilateral")
    p.add_argument("--vtx",    required=True, type=int,
                   help="Vertex index noted from Workbench (wb_view log)")
    p.add_argument("--additional-offset", type=float, default=0.0,
                   help="Extra gel/pad offset between exit plane and skin (mm, default 0)")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate inputs and print paths without running")
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

    print(f"Site      : {cfg.get('site')} / {cfg.get('station')}")
    print(f"Subject   : {sub_id_full}")
    print(f"Target    : {args.target}{args.side}")
    print(f"Vertex    : {args.vtx}")
    print(f"Transducer: {tcfg.get('name')}  ({tcfg.get('transducer_serial', '')})")
    print(f"m2m_dir   : {m2m_dir}")

    run_plantus_placement(
        vertex_idx=args.vtx,
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
