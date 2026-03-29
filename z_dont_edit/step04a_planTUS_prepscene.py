#!/usr/bin/env python3
"""
scripts/TUS/run/step04a_planTUS_prepscene.py
Prepare PlanTUS surfaces, metric maps, and Workbench scene file (Step 4a).

Run this BEFORE opening Workbench. After completion, open the generated
scene.scene in Workbench, inspect the metric overlays (distance, angle,
target intersection), and note the vertex index you wish to target.
Then run step04b_planTUS_placement.py with that vertex index.

Must be run with the SimNIBS Python interpreter, e.g.:

    {simnibs_python} step04a_planTUS_prepscene.py \\
        --site  ../config/sites/site_RIKEN_AK.yaml \\
        --sub   sub-NS \\
        --target aMCC_NeuroSynthTopic112 \\
        --side  _R

Output
------
- PlanTUS scene folder: {m2m_dir}/PlanTUS/{sub_id_full}_T1w_{target}_mask_native{side}/
  - scene.scene                    → open in wb_view to select vertex
  - skin_target_distances.npy      → loaded by step04b
  - distances_skin.func.gii        → distance map overlay
  - angles_skin.func.gii           → angle map overlay
  - target_intersection_skin.func.gii → intersection map overlay
  - skin_skull_angles_skin.func.gii   → skull-skin angle overlay

Workflow
--------
1. Run this script → generates scene + metric files
2. Open scene.scene in Workbench:
       wb_view <output_dir>/scene.scene
3. Inspect overlays, click a candidate vertex, note its index
4. Run step04b_planTUS_placement.py --vtx <INDEX>

Alternatively, use step04_planTUS.ipynb for the full interactive GUI workflow
(Steps 1-4 combined, with pynput-based vertex capture).
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
    prepare_plantus_scene,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepare PlanTUS scene (Step 4a — surfaces, maps, scene file)."
    )
    p.add_argument("--site",   required=True, help="Path to site YAML config")
    p.add_argument("--sub",    required=True, help="Subject ID (with or without 'sub-' prefix)")
    p.add_argument("--target", required=True, help="Target label, e.g. aMCC_NeuroSynthTopic112")
    p.add_argument("--side",   default="",    help="Side suffix: _R, _L, or '' for bilateral")
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
    print(f"Transducer: {tcfg.get('name')}  ({tcfg.get('transducer_serial', '')})")
    print(f"m2m_dir   : {m2m_dir}")

    output_path = prepare_plantus_scene(
        sub_id_full=sub_id_full,
        sub_id_bare=sub_id_bare,
        m2m_dir=m2m_dir,
        target_name=args.target,
        target_side=args.side,
        tp=tp,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print()
        print("=" * 60)
        print("Scene ready. Next steps:")
        print(f"  1. wb_view {output_path}/scene.scene")
        print("  2. Inspect overlays and select a vertex — note its index")
        print("  3. Run:")
        print(f"       step04b_planTUS_placement.py \\")
        print(f"           --site {args.site} --sub {args.sub} \\")
        print(f"           --target {args.target} --side '{args.side}' \\")
        print(f"           --vtx <VERTEX_INDEX> [--additional-offset MM]")
        print("=" * 60)


if __name__ == "__main__":
    main()
