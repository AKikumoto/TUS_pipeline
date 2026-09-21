"""
scripts/TUS/run/step04_CoM_run.py
Step 04 (CoM mode) — Centre-of-mass targeting, independent of PlanTUS.

Computes the centre of mass (CoM) of a native-space mask (produced by
step05_inverseReg) and writes a BrainSight-compatible coordinate file.

Because no PlanTUS transducer placement is performed, the rotation block in the
output file uses an identity matrix.  Transducer orientation must be set
manually in BrainSight if orientation matters for your protocol.

Usage
-----
  python step04_CoM_run.py \\
      --mask  /path/to/sub-SK_aMCC_NeuroSynthTopic112_mask_native.nii.gz \\
      --label aMCC_NeuroSynthTopic112 \\
      [--threshold 0.0] \\
      [--coordinate-system "NIfTI:Scanner"] \\
      [--out /path/to/output.txt]

Output
------
A BrainSight-compatible .txt file with one target row (CoM point, identity
rotation) and no entry row.
"""

import argparse
import sys
from pathlib import Path

SRC_DIR = str(Path(__file__).parent.resolve())
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils import compute_com_native


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 04 (CoM mode) — compute CoM and write BrainSight file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--mask", required=True,
        help="Native-space mask NIfTI (output of step05_inverseReg).",
    )
    p.add_argument(
        "--label", required=True,
        help="Short label used in output filename and BrainSight target name.",
    )
    p.add_argument(
        "--threshold", type=float, default=0.0,
        help="Voxel threshold: voxels <= threshold are excluded before CoM.",
    )
    p.add_argument(
        "--coordinate-system", default="NIfTI:Scanner",
        dest="coordinate_system",
        help="Coordinate system string written to BrainSight header.",
    )
    p.add_argument(
        "--out", default=None,
        help=(
            "Output .txt path.  Defaults to <mask_dir>/<label>_CoM_target.txt"
        ),
    )
    return p.parse_args(argv)


def write_brainsight_com(
    com_mm: "np.ndarray",
    label: str,
    out_path: Path,
    coordinate_system: str = "NIfTI:Scanner",
) -> None:
    """Write a single-point BrainSight target file using an identity rotation.

    Parameters
    ----------
    com_mm:
        CoM coordinate in native scanner space (mm), shape (3,).
    label:
        Name used in the BrainSight target row and filename.
    out_path:
        Output .txt path.
    coordinate_system:
        String written to the BrainSight header.
    """
    import numpy as np

    # Identity rotation (no transducer orientation assumed)
    R = np.eye(3)

    header = (
        "# Version: 13\n"
        f"# Coordinate system: {coordinate_system}\n"
        "# Created by: step04_CoM_run.py (LabWiki scripts/TUS/run/)\n"
        "# Units: millimetres, degrees, milliseconds, and microvolts\n"
        "# Encoding: UTF-8\n"
        "# Notes: Each column is delimited by a tab. "
        "Each value within a column is delimited by a semicolon.\n"
        "# Rotation is identity — set transducer orientation manually in BrainSight.\n"
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
    with open(out_path, "w") as f:
        f.write(header)
        f.write(row)

    print(f"BrainSight CoM file saved: {out_path}")
    print(f"  Target (CoM, mm): {com_mm}")


def run(args: argparse.Namespace) -> None:
    import numpy as np

    mask_path = Path(args.mask).expanduser().resolve()
    if not mask_path.exists():
        sys.exit(f"ERROR: mask not found: {mask_path}")

    com_mm, com_vox = compute_com_native(mask_path, z_threshold=args.threshold)

    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else mask_path.parent / f"{args.label}_CoM_target.txt"
    )

    write_brainsight_com(
        com_mm=com_mm,
        label=args.label,
        out_path=out_path,
        coordinate_system=args.coordinate_system,
    )

    print()
    print("=" * 50)
    print(f"Target:           {args.label}")
    print(f"Mask:             {mask_path.name}")
    print(f"CoM (native, mm): x={com_mm[0]:.2f}  y={com_mm[1]:.2f}  z={com_mm[2]:.2f}")
    print(f"CoM (voxel):      i={com_vox[0]:.1f}  j={com_vox[1]:.1f}  k={com_vox[2]:.1f}")
    print("=" * 50)


def main() -> None:
    args = _parse_args()
    run(args)


if __name__ == "__main__":
    main()
