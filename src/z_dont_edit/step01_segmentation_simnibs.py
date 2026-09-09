"""
Step 01 — SimNIBS segmentation (charm)

Runs the SimNIBS `charm` segmentation for one or more subjects.
Reads all paths and settings from a site config YAML.

charm builds a detailed multi-tissue tetrahedral head mesh from a T1w image,
producing tissue probability maps (GM, WM, CSF, skull, scalp, air) used by
downstream PlanTUS / acoustic simulations.
See: https://simnibs.github.io/simnibs/build/html/documentation/command_line/charm.html

Dependencies
------------
- SimNIBS >= 4.0  (provides the `charm` binary)
- FSL             (optional: `fslorient` for qform fix)
- Python packages: pyyaml (+ src/utils.py in scripts/TUS/)

Input (BIDS)
------------
    {data_root}/{sub_list_dir}/{sub_id_bare}/sub-{sub_id_bare}_T1w.nii[.gz]

Output (SimNIBS)
----------------
    {data_root}/{sub_list_dir}/{sub_id_bare}/m2m_sub-{sub_id_bare}/
      final_tissues.nii.gz      ← multi-label tissue segmentation
      final_tissues_LUT.txt     ← label colour table
      T1.nii.gz                 ← T1 in SimNIBS conform space
      *.msh                     ← tetrahedral head mesh

Usage
-----
Single subject:
    python step01_segmentation_simnibs.py --site config/sites/site_RIKEN_AK.yaml --sub sub-NS

Batch (text file, one sub-ID per line):
    python step01_segmentation_simnibs.py --site config/sites/site_RIKEN_AK.yaml --sub-list subjects.txt

Flags
-----
--fix-qform   run fslorient -copysform2qform before charm (recommended)
--overwrite   re-run charm even if output already exists
--dry-run     print commands without executing
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Allow running from scripts/TUS/run/ — add scripts/TUS/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.utils import (  # noqa: E402
    load_site_config,
    resolve_data_dir,
    parse_sub_list,
    process_subject,
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Run SimNIBS charm segmentation for one or more TUS subjects."
    )
    parser.add_argument(
        "--site",
        required=True,
        metavar="YAML",
        help="Path to site config YAML (e.g. config/sites/site_RIKEN_AK.yaml)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--sub",
        metavar="SUB_ID",
        help="Single subject ID (e.g. sub-NS or NS)",
    )
    group.add_argument(
        "--sub-list",
        metavar="FILE",
        help="Text file with one subject ID per line",
    )
    parser.add_argument(
        "--fix-qform",
        action="store_true",
        help="Run fslorient -copysform2qform before charm",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run charm even if output already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    args = parser.parse_args()

    # Load config
    cfg = load_site_config(args.site)
    data_dir = resolve_data_dir(cfg)

    print(f"Site:     {cfg.get('site', '?')} / {cfg.get('station', '?')}")
    print(f"Data dir: {data_dir}")
    if args.dry_run:
        print("Mode:     DRY RUN (no commands executed)")

    # Build subject list
    if args.sub:
        subjects = [args.sub]
    else:
        subjects = parse_sub_list(args.sub_list)

    print(f"Subjects: {len(subjects)}")
    print()

    # Process
    n_ok = n_skip = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            ok = process_subject(
                sub_id, data_dir, cfg,
                fix_qform=args.fix_qform,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
            if ok:
                n_ok += 1
            else:
                n_skip += 1
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: charm failed for {sub_id}: {e}")
            n_fail += 1
        print()

    print(f"Done. completed={n_ok}  skipped={n_skip}  failed={n_fail}")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
