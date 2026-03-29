#!/usr/bin/env python3
"""
src/run_com.py
Batch runner — Centre-of-Mass (CoM) targeting and BrainSight export.

Computes the CoM of a native-space mask and writes a BrainSight-compatible
coordinate file with an identity rotation matrix.  Can be used as an
alternative to PlanTUS (when no acoustic transducer placement is needed) or
alongside PlanTUS (to compare CoM vs guided-placement coordinates).

NOTE: Transducer orientation is NOT computed — the output rotation is an
identity matrix.  Orientation must be set manually in BrainSight if needed.

Dependency
----------
The native mask must already exist (output of run_reg.py / step 3).
If running an end-to-end pipeline, ensure ``reg`` precedes ``com`` in
``--steps`` (enforced automatically by run_prepall.py).

Two usage modes
---------------
Site-config mode (batch, recommended):
    python run_com.py \\
        --site       config/sites/site_RIKEN_AK.yaml \\
        --sub-list   subjects.txt \\
        --mask-label aMCC_NeuroSynthTopic112 \\
        [--threshold 0.0] [--side _R]

    Native mask is resolved automatically:
        {data_dir}/{sub_id_bare}/{sub_id_full}_{mask_label}_mask_native{side}.nii.gz

Direct mode (single mask, standalone):
    python run_com.py \\
        --mask  /path/to/sub-SK_aMCC_NeuroSynthTopic112_mask_native.nii.gz \\
        --label aMCC_NeuroSynthTopic112 \\
        [--threshold 0.0] [--out /path/to/output.txt]

Output (per subject or per direct call):
    <mask_dir>/<label>_CoM_target.txt   (BrainSight-compatible, identity rotation)
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
    compute_com_native,
    load_site_config,
    normalise_sub_id,
    parse_sub_list,
    resolve_data_dir,
)


# ---------------------------------------------------------------------------
# BrainSight CoM writer (identity rotation — no transducer placement)
# ---------------------------------------------------------------------------

def write_brainsight_com(
    com_mm: "np.ndarray",
    label: str,
    out_path: Path,
    coordinate_system: str = "NIfTI:Scanner",
    append: bool = False,
) -> None:
    """Write (or append) a BrainSight target row with identity rotation.

    Parameters
    ----------
    com_mm:
        Target coordinate in **RAS / NIfTI:Scanner** space (mm), shape (3,).
        This function writes the value directly to the BrainSight target file
        without any coordinate transformation.  Pass the output of
        ``compute_com_native()`` or ``compute_peak_native()``, both of which
        return RAS-corrected coordinates (ANTs LPS → RAS conversion applied
        internally by those functions).
    label:
        Name used in the BrainSight target row.
    out_path:
        Output .txt path.
    coordinate_system:
        String written to the BrainSight header (ignored when append=True).
    append:
        If False (default), create a new file with header + row.
        If True, append only the data row to an existing file (no header).
    """
    import numpy as np

    R = np.eye(3)

    header = (
        "# Version: 13\n"
        f"# Coordinate system: {coordinate_system}\n"
        "# Created by: run_com.py (LabWiki scripts/TUS/src/)\n"
        "# Units: millimetres, degrees, milliseconds, and microvolts\n"
        "# Encoding: UTF-8\n"
        "# Notes: Each column is delimited by a tab. "
        "Each value within a column is delimited by a semicolon.\n"
        "# Rotation is identity (orientation unspecified) — use PlanTUS output (Step 4) for optimal transducer orientation.\n"
        "# Target Name\tLoc. X\tLoc. Y\tLoc. Z\t"
        "m0n0\tm0n1\tm0n2\tm1n0\tm1n1\tm1n2\tm2n0\tm2n1\tm2n2\n"
    )
    row = (
        f"{label}_CoM\t"
        f"{com_mm[0]:.4f}\t{com_mm[1]:.4f}\t{com_mm[2]:.4f}\t"
        f"{R[0,0]:.4f}\t{R[0,1]:.4f}\t{R[0,2]:.4f}\t"
        f"{R[1,0]:.4f}\t{R[1,1]:.4f}\t{R[1,2]:.4f}\t"
        f"{R[2,0]:.4f}\t{R[2,1]:.4f}\t{R[2,2]:.4f}\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(out_path, mode) as f:
        if not append:
            f.write(header)
        f.write(row)

    print(f"  BrainSight CoM file: {out_path}  ({'appended' if append else 'created'})")
    print(f"  CoM (mm): x={com_mm[0]:.2f}  y={com_mm[1]:.2f}  z={com_mm[2]:.2f}")


# ---------------------------------------------------------------------------
# Per-subject runner (site-config mode)
# ---------------------------------------------------------------------------

def run_one_subject(
    sub_id: str,
    data_dir: Path,
    mask_label: str,
    side: str,
    threshold: float,
    coordinate_system: str,
    dry_run: bool,
    combine_lr: bool = False,
) -> None:
    """Compute CoM and write BrainSight file for a single subject (site-config mode).

    When combine_lr=True, processes both _L and _R masks and writes a single
    combined BrainSight file with one row per hemisphere.
    """
    _, sub_bare = normalise_sub_id(sub_id)
    sub_id_full = f"sub-{sub_bare}"
    sub_dir = data_dir / sub_bare

    print(f"  Subject  : {sub_id_full}")

    if dry_run:
        print("  [dry-run] Skipping CoM computation.")
        return

    if combine_lr:
        # ── Combined L+R mode — one output file ──────────────────────────────
        out_path = sub_dir / f"{sub_id_full}_{mask_label}_CoM_target.txt"
        first = True
        for _side in ("_L", "_R"):
            _mask_path = sub_dir / f"{sub_id_full}_{mask_label}_mask_native{_side}.nii.gz"
            if not _mask_path.exists():
                print(f"  WARNING: mask not found, skipping {_side}: {_mask_path.name}")
                continue
            print(f"  Mask ({_side}): {_mask_path.name}")
            _com_mm, _com_vox = compute_com_native(_mask_path, z_threshold=threshold)
            write_brainsight_com(
                com_mm=_com_mm,
                label=f"{sub_id_full}_{mask_label}{_side}",
                out_path=out_path,
                coordinate_system=coordinate_system,
                append=not first,
            )
            print(f"  CoM{_side} (vox): i={_com_vox[0]:.1f}  j={_com_vox[1]:.1f}  k={_com_vox[2]:.1f}")
            first = False
        return

    # ── Single-side mode (original behaviour) ────────────────────────────────
    mask_path = sub_dir / f"{sub_id_full}_{mask_label}_mask_native{side}.nii.gz"

    if not mask_path.exists():
        print(f"  ERROR: native mask not found: {mask_path}")
        print(f"  (Run run_reg.py first, or check --mask-label and --side)")
        raise FileNotFoundError(mask_path)

    print(f"  Mask     : {mask_path.name}")

    com_mm, com_vox = compute_com_native(mask_path, z_threshold=threshold)

    out_path = sub_dir / f"{sub_id_full}_{mask_label}{side}_CoM_target.txt"
    write_brainsight_com(
        com_mm=com_mm,
        label=f"{sub_id_full}_{mask_label}{side}",
        out_path=out_path,
        coordinate_system=coordinate_system,
    )
    print(f"  CoM (vox): i={com_vox[0]:.1f}  j={com_vox[1]:.1f}  k={com_vox[2]:.1f}")


# ---------------------------------------------------------------------------
# Direct runner (explicit mask path mode)
# ---------------------------------------------------------------------------

def run_direct(
    mask_path: Path,
    label: str,
    threshold: float,
    coordinate_system: str,
    out_path: Path | None,
) -> None:
    """Compute CoM and write BrainSight file from an explicit mask path."""
    if not mask_path.exists():
        sys.exit(f"ERROR: mask not found: {mask_path}")

    com_mm, com_vox = compute_com_native(mask_path, z_threshold=threshold)

    resolved_out = (
        out_path
        if out_path is not None
        else mask_path.parent / f"{label}_CoM_target.txt"
    )
    write_brainsight_com(
        com_mm=com_mm,
        label=label,
        out_path=resolved_out,
        coordinate_system=coordinate_system,
    )
    print(f"  CoM (vox): i={com_vox[0]:.1f}  j={com_vox[1]:.1f}  k={com_vox[2]:.1f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CoM targeting and BrainSight export (run_com).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Site-config mode (batch):\n"
            "  python run_com.py --site YAML --sub SUB --mask-label LABEL\n\n"
            "Direct mode (single mask):\n"
            "  python run_com.py --mask FILE --label LABEL\n"
        ),
    )

    # ── Site-config mode ──────────────────────────────────────────────────
    site_grp = p.add_argument_group("site-config mode (batch)")
    site_grp.add_argument("--site",       metavar="YAML",  help="Site config YAML.")
    site_grp.add_argument("--mask-label", metavar="LABEL", dest="mask_label",
                          help="Mask label matching run_reg.py output (e.g. aMCC_NeuroSynthTopic112).")
    site_grp.add_argument("--side",       metavar="_R|_L|''", default="",
                          help="Side suffix used in native mask filename (default: '').")
    site_grp.add_argument("--combine-lr", action="store_true", dest="combine_lr",
                          help="Process both _L and _R masks and write a combined single BrainSight file.")
    sub_grp = site_grp.add_mutually_exclusive_group()
    sub_grp.add_argument("--sub",      metavar="SUB_ID",
                         help="Single subject ID.")
    sub_grp.add_argument("--sub-list", metavar="FILE",
                         help="Text file with one subject ID per line.")

    # ── Direct mode ───────────────────────────────────────────────────────
    direct_grp = p.add_argument_group("direct mode (single mask)")
    direct_grp.add_argument("--mask",  metavar="FILE",  help="Native-space mask NIfTI.")
    direct_grp.add_argument("--label", metavar="LABEL", help="Label for output filename and BrainSight row.")
    direct_grp.add_argument("--out",   metavar="FILE",  default=None,
                             help="Output .txt path (default: <mask_dir>/<label>_CoM_target.txt).")

    # ── Shared options ────────────────────────────────────────────────────
    p.add_argument("--threshold",  type=float, default=0.0,
                   help="Voxel threshold for CoM (exclude voxels <= threshold).")
    p.add_argument("--coordinate-system", default="NIfTI:Scanner",
                   dest="coordinate_system",
                   help="Coordinate system string in BrainSight header.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate paths without computing or writing.")

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ── Determine mode ────────────────────────────────────────────────────
    is_direct    = bool(args.mask)
    is_site_mode = bool(args.site or args.sub or args.sub_list)

    if is_direct and is_site_mode:
        sys.exit("ERROR: Cannot mix --mask/--label (direct mode) with --site/--sub (site-config mode).")

    if is_direct:
        # Direct mode
        if not args.label:
            sys.exit("ERROR: --label is required in direct mode.")
        run_direct(
            mask_path=Path(args.mask).expanduser().resolve(),
            label=args.label,
            threshold=args.threshold,
            coordinate_system=args.coordinate_system,
            out_path=Path(args.out).expanduser().resolve() if args.out else None,
        )
        return

    # Site-config mode
    if not args.site:
        sys.exit("ERROR: --site is required in site-config mode.")
    if not args.mask_label:
        sys.exit("ERROR: --mask-label is required in site-config mode.")
    if not args.sub and not args.sub_list:
        sys.exit("ERROR: --sub or --sub-list is required in site-config mode.")

    cfg      = load_site_config(args.site)
    data_dir = resolve_data_dir(cfg)
    subjects = [args.sub] if args.sub else parse_sub_list(args.sub_list)

    print(f"Site:     {cfg.get('site', '?')} / {cfg.get('station', '?')}")
    print(f"Data dir: {data_dir}")
    print(f"Label:    {args.mask_label}{args.side}")
    print(f"Subjects: {len(subjects)}")
    if args.dry_run:
        print("Mode:     DRY RUN")
    print()

    n_ok = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            run_one_subject(
                sub_id=sub_id,
                data_dir=data_dir,
                mask_label=args.mask_label,
                side=args.side,
                threshold=args.threshold,
                coordinate_system=cfg.get("coordinate_system", args.coordinate_system),
                dry_run=args.dry_run,
                combine_lr=args.combine_lr,
            )
            n_ok += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            n_fail += 1
        print()

    print("=" * 50)
    print(f"Summary: {n_ok} completed  {n_fail} failed")


if __name__ == "__main__":
    main()
