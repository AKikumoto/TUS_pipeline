#!/usr/bin/env python3
"""
src/run_seg.py
Batch runner — Step 1: SimNIBS charm segmentation.

Runs `charm` (CharActerization of head anatomy from MR images) for one or more
subjects.  All paths are resolved from a site config YAML.

Algorithm
---------
For each subject:
1. (Optional) fix qform/sform mismatch with ``fslorient -copysform2qform``.
2. Run ``charm <sub_id_full> <t1_path>`` in the subject directory.
3. Verify expected output files: final_tissues.nii.gz, T1.nii.gz, *.msh.

This script runs in the standard Python environment (no SimNIBS Python required
for the script itself; SimNIBS ``charm`` binary must be in PATH).

Usage — single subject:
    python run_seg.py \\
        --site  config/sites/site_RIKEN_AK.yaml \\
        --sub   sub-NS \\
        [--fix-qform] [--overwrite] [--dry-run]

Usage — batch:
    python run_seg.py \\
        --site      config/sites/site_RIKEN_AK.yaml \\
        --sub-list  subjects.txt \\
        [--fix-qform] [--overwrite] [--dry-run]

Outputs (per subject):
    {data_dir}/{sub_id_bare}/m2m_{sub_id_full}/
        final_tissues.nii.gz
        final_tissues_LUT.txt
        T1.nii.gz
        {sub_id_full}.msh
"""

import argparse
import subprocess
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
    resolve_data_dir,
    normalise_sub_id,
    parse_sub_list,
    process_subject,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch charm segmentation runner (Step 1).",
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
        "--fix-qform", action="store_true",
        help="Run fslorient -copysform2qform before charm (recommended).",
    )
    p.add_argument(
        "--overwrite", action="store_true",
        help="Re-run charm even if m2m output directory already exists.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print commands without executing.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    site_yaml = Path(args.site).expanduser().resolve()
    cfg = load_site_config(site_yaml)
    data_dir = resolve_data_dir(cfg)

    print(f"Site:     {cfg.get('site', '?')} / {cfg.get('station', '?')}")
    print(f"Data dir: {data_dir}")
    if args.dry_run:
        print("Mode:     DRY RUN")
    print()

    # Build subject list
    subjects = [args.sub] if args.sub else parse_sub_list(args.sub_list)
    print(f"Subjects: {len(subjects)}")
    print()

    n_ok = n_skip = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            ok = process_subject(
                sub_id,
                data_dir,
                cfg,
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

    print("=" * 50)
    print(f"Summary: {n_ok} completed  {n_skip} skipped  {n_fail} failed")


if __name__ == "__main__":
    main()
