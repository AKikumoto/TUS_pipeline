#!/usr/bin/env python3
"""
src/run_planTUS.py
Batch runner — Step 4: PlanTUS automated placement (best-vertex selection).

Runs PlanTUS in fully automated mode: generates surfaces + metric maps,
selects the best scalp vertex (no GUI interaction required), runs acoustic
simulation placement, and exports BrainSight coordinates.

Run with the mri conda environment Python (SimNIBS 4.6+ must be pip-installed):
    python run_planTUS.py --site ... --sub ... --target ... --side ...

Algorithm (per subject)
-----------------------
1. prepare_plantus_scene  — build mesh surfaces, metric maps, scene file.
2. select_best_vtx        — automatically select optimal scalp vertex:
                              a. filter by avoidance mask + focal-depth bounds
                              b. pick vertex with highest beam-ROI intersection
                              c. tiebreak on normalised angle + distance
3. run_plantus_placement  — run acoustic simulation for selected vertex.
4. write_brainsight_for_vtx — export BrainSight-compatible coordinate file.

Use ``--skip-scene`` to re-run vertex selection + placement on an existing
scene (skips step 1, useful if prepare_plantus_scene has already been run).

Transducer parameters (focal depth, angle limits, etc.) are read from the
transducer YAML referenced by the site config.

Usage — single subject:
    python run_planTUS.py \\
        --site   config/sites/site_RIKEN_AK.yaml \\
        --sub    sub-NS \\
        --target aMCC_NeuroSynthTopic112 \\
        --side   _R \\
        [--additional-offset 0.0] [--top-pct 0.9] [--dry-run]

Usage — batch:
    python run_planTUS.py \\
        --site      config/sites/site_RIKEN_AK.yaml \\
        --sub-list  subjects.txt \\
        --target    aMCC_NeuroSynthTopic112 \\
        --side      _R

Outputs (per subject, inside m2m_{sub_id_full}/PlanTUS/{target_roi_name}/):
    scene.scene
    vtx{NNNNN}/
        *_transducer.txt
        focus_position_matrix_*.txt
        *_depth_report_vtx{NNNNN}.txt
    {sub_id_full}_T1w_{target}_{side}_target_coordinates_Brainsight_PlanTUS.txt
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate utils.py (same directory as this script)
# ---------------------------------------------------------------------------
_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (
    load_site_config,
    load_transducer_config,
    resolve_data_dir,
    normalise_sub_id,
    resolve_sub_dir,
    parse_sub_list,
    setup_environment,
    transducer_params,
    find_plantus_target_folder,
    prepare_plantus_scene,
    select_best_vtx,
    run_plantus_placement,
    write_brainsight_for_vtx,
)


# ---------------------------------------------------------------------------
# Per-subject automated PlanTUS
# ---------------------------------------------------------------------------

def run_one(
    sub_id: str,
    data_dir: Path,
    site_yaml: Path,
    cfg: dict,
    tp: dict,
    target_name: str,
    target_side: str,
    additional_offset: float,
    top_pct: float,
    skip_scene: bool,
    dry_run: bool,
) -> None:
    """Run automated PlanTUS for a single subject."""
    sub_id_full, sub_id_bare = normalise_sub_id(sub_id)
    sub_dir = resolve_sub_dir(data_dir, sub_id_bare, sub_id_full)
    m2m_dir = sub_dir / f"m2m_{sub_id_full}"

    if not m2m_dir.exists():
        print(f"  ERROR: m2m directory not found: {m2m_dir}")
        return

    print(f"  Subject   : {sub_id_full}")
    print(f"  m2m_dir   : {m2m_dir}")
    print(f"  Target    : {target_name}{target_side}  offset={additional_offset} mm")

    # -- Step 4-1: prepare scene -----------------------------------------------
    if skip_scene:
        target_folder = find_plantus_target_folder(
            m2m_dir, sub_id_full, target_name, target_side
        )
        print(f"  [skip-scene] Using existing scene: {target_folder}")
    else:
        print("  prepare_plantus_scene ...")
        target_folder = prepare_plantus_scene(
            sub_id_full=sub_id_full,
            sub_id_bare=sub_id_bare,
            m2m_dir=m2m_dir,
            target_name=target_name,
            target_side=target_side,
            tp=tp,
            dry_run=dry_run,
        )

    if dry_run:
        print("  [dry-run] Skipping vertex selection and placement.")
        return

    # -- Step 4-2: select best vertex ------------------------------------------
    print("  select_best_vtx ...")
    best_vtx, metrics, angle_exceeded = select_best_vtx(
        target_folder=target_folder,
        max_angle=tp["max_angle"],
        max_distance=tp.get("max_distance"),
        min_distance=tp.get("min_distance"),
        top_pct=top_pct,
    )
    print(f"  Best vertex: {best_vtx}")
    print(f"    distance_mm    : {metrics['distance_mm']:.2f}")
    print(f"    angle_deg      : {metrics['angle_deg']:.1f}"
          + ("  [ANGLE WARNING]" if angle_exceeded else ""))
    print(f"    intersection_mm: {metrics['intersection_mm']:.2f}")
    print(f"    n_valid        : {metrics['n_valid']}")

    # -- Step 4-3: run placement -----------------------------------------------
    print(f"  run_plantus_placement (vertex {best_vtx}) ...")
    run_plantus_placement(
        vertex_idx=best_vtx,
        sub_id_full=sub_id_full,
        sub_id_bare=sub_id_bare,
        m2m_dir=m2m_dir,
        target_name=target_name,
        target_side=target_side,
        tp=tp,
        additional_offset=additional_offset,
        dry_run=False,
    )

    # -- Step 4-4: export BrainSight coordinates --------------------------------
    print("  write_brainsight_for_vtx ...")
    bs_path = write_brainsight_for_vtx(
        m2m_dir=m2m_dir,
        sub_id_full=sub_id_full,
        target_name=target_name,
        target_side=target_side,
        coordinate_system=cfg.get("coordinate_system", "NIfTI:Scanner"),
    )
    print(f"  BrainSight file: {bs_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch PlanTUS automated placement runner (Step 4).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--site", required=True, metavar="YAML",
        help="Path to site config YAML.",
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--sub", metavar="SUB_ID",
        help="Single subject ID (e.g. sub-NS or NS).",
    )
    grp.add_argument(
        "--sub-list", metavar="FILE",
        help="Text file with one subject ID per line (# comments ignored).",
    )
    p.add_argument(
        "--target", required=True,
        help="PlanTUS target label (must match mask label from step 3).",
    )
    p.add_argument(
        "--side", default="",
        help="Side suffix: _R, _L, or '' for bilateral.",
    )
    p.add_argument(
        "--additional-offset", type=float, default=0.0,
        dest="additional_offset",
        help="Extra gel/pad thickness between exit plane and skin (mm).",
    )
    p.add_argument(
        "--top-pct", type=float, default=0.9,
        dest="top_pct",
        help=(
            "Fraction of max intersection defining top-candidate pool for "
            "vertex selection (0.9 = keep vertices with >= 90%% of best intersection)."
        ),
    )
    p.add_argument(
        "--skip-scene", action="store_true",
        dest="skip_scene",
        help="Skip prepare_plantus_scene; use existing scene in PlanTUS output dir.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Validate inputs and build scene only; skip vertex selection and placement.",
    )
    p.add_argument(
        "--overwrite-scene", action="store_true", dest="overwrite_scene",
        help="Re-run prepare_plantus_scene even if scene already exists.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    site_yaml = Path(args.site).expanduser().resolve()
    cfg  = load_site_config(site_yaml)
    tcfg = load_transducer_config(cfg, site_yaml)
    tp   = transducer_params(tcfg)

    setup_environment(cfg)

    data_dir = resolve_data_dir(cfg)
    subjects = [args.sub] if args.sub else parse_sub_list(args.sub_list)

    print(f"Site:       {cfg.get('site', '?')} / {cfg.get('station', '?')}")
    print(f"Transducer: {tcfg.get('name', '?')}")
    print(f"Data dir:   {data_dir}")
    print(f"Target:     {args.target}{args.side}")
    print(f"Subjects:   {len(subjects)}")
    if args.dry_run:
        print("Mode:       DRY RUN")
    print()

    skip_scene = args.skip_scene and not getattr(args, "overwrite_scene", False)

    n_ok = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            run_one(
                sub_id=sub_id,
                data_dir=data_dir,
                site_yaml=site_yaml,
                cfg=cfg,
                tp=tp,
                target_name=args.target,
                target_side=args.side,
                additional_offset=args.additional_offset,
                top_pct=args.top_pct,
                skip_scene=skip_scene,
                dry_run=args.dry_run,
            )
            n_ok += 1
        except Exception as e:
            print(f"  ERROR: PlanTUS failed for {sub_id}: {e}")
            n_fail += 1
        print()

    print("=" * 50)
    print(f"Summary: {n_ok} completed  {n_fail} failed")


if __name__ == "__main__":
    main()
