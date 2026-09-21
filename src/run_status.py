#!/usr/bin/env python3
"""
src/run_status.py
Cross-subject record of adopted placements: ADOPTED_PLACEMENTS.md and .csv.

One row per placement that has a thermal summary, for one subject or many,
with every value read from the pipeline's own outputs (depth report,
Brainsight export, acoustic h5, thermal h5, TPO summary). This is the table to
open before an experiment day and after any re-run: it carries the TPO focal
depth, the pad, the entry geometry, the focus metrics, the derating and the
free-field ISPPA, the temperature rise and the standoff tripwire.

Usage:
    python run_status.py --site config/sites/site_UMD_AK.yaml --sub-list subjects.txt
    python run_status.py --site config/sites/site_UMD_AK.yaml --sub sub-M3827 --sub sub-z002

Outputs (in the data directory of the site config unless --out is given):
    ADOPTED_PLACEMENTS.md      one section per subject
    ADOPTED_BY_TARGET.md       the same rows grouped by target, subjects side by side
    ADOPTED_PLACEMENTS.csv     every field
    ADOPTED_PLACEMENTS.pdf     per target: the table, then each placement's acoustic and thermal QC
"""

import argparse
import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (
    load_babelbrain_tx_yaml,
    load_site_config,
    parse_sub_list,
    resolve_data_dir,
    write_adopted_placements,
    write_adopted_report_pdf,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[1],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--site", required=True, metavar="FILE", help="Path to site config YAML.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--sub", action="append", metavar="SUB_ID",
                     help="Subject ID; repeat for several.")
    grp.add_argument("--sub-list", metavar="FILE",
                     help="Text file with one subject ID per line (# comments ignored).")
    p.add_argument("--out", metavar="DIR", default=None,
                   help="Directory for the files. Default: the site's data directory.")
    p.add_argument("--no-pdf", action="store_true",
                   help="Skip the PDF (tables and figures per target).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_site_config(str(Path(args.site).resolve()))
    data_dir = resolve_data_dir(cfg)
    bb_dir = Path(cfg["babelbrain_dir"]).expanduser().resolve()
    if str(bb_dir) not in sys.path:
        sys.path.insert(0, str(bb_dir))
    tx_cfg = cfg["transducer_cfg"]
    bb_yaml = load_babelbrain_tx_yaml(bb_dir, tx_cfg["babelbrain_id"])
    subjects = args.sub if args.sub else parse_sub_list(Path(args.sub_list).resolve())
    md, by_target, csv_path = write_adopted_placements(data_dir, subjects, tx_cfg, bb_yaml,
                                                        out_dir=args.out)
    print(f"By subject: {md}")
    print(f"By target : {by_target}")
    print(f"CSV       : {csv_path}")
    if not args.no_pdf:
        pdf = write_adopted_report_pdf(data_dir, csv_path,
                                       out_path=Path(args.out) / "ADOPTED_PLACEMENTS.pdf" if args.out else None)
        print(f"PDF       : {pdf}")


if __name__ == "__main__":
    main()
