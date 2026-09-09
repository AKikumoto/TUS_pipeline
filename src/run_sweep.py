#!/usr/bin/env python3
"""
src/run_sweep.py
Batch runner — placement sweep: try each shortlisted vertex and measure it.

Why this exists
---------------
Step 4's surface metrics cannot say which placement will actually focus on the
target. Measured over eight EC placements, beam-in-ROI overlap ran 5.3-14.0 mm
with no monotonic relation to the intensity delivered; over 24 swept candidates
the top-scoring one was the best actually measured in 1 case out of 5. The
score is good enough to produce a shortlist and no better, so the shortlist has
to be run and judged on the result.

That is worth doing: across the eight EC targets this took placements with the
target inside the focal lobe from 5/8 to 8/8, median intensity at target from
0.56 to 0.94, and median centroid offset from 9.8 mm to 4.9 mm.

Algorithm (per subject and target)
----------------------------------
0. prepare_plantus_scene  — step 4a, only when the target has never been
                            placed; a sweep is meant to be usable straight
                            after step 3.
1. select_best_vtx        — shortlist of n candidates, >= 10 mm apart so they
                            are distinct approaches and not neighbours sharing
                            one path through the skull.
2. per candidate:
   run_plantus_placement  — step 4c, skipped when its trajectory already exists
   run_babelbrain.py      — step 5a + 5b only (--skip-thermal)
3. score every candidate on the outlier-resistant focal metrics and print them
   ranked by intensity at target.

Thermal is deliberately NOT run here. It costs ~45 s per candidate to answer a
question that only matters for the one placement finally chosen; run
run_babelbrain.py --vtx <winner> afterwards for that.

Cost: about 5 minutes per candidate (placement ~30 s, domain ~55 s, acoustic
~135 s, scoring ~15 s). Eight targets at three candidates took 122 minutes.

Run with the mri conda environment Python.

Usage:
    python run_sweep.py \\
        --site      config/sites/site_UMD_AK.yaml \\
        --sub-list  subjects.txt \\
        --target    alEC_PRCpref_left_Maass2015 pmEC_PHCpref_left_Maass2015 \\
        --side      "" \\
        --stim      config/stimulation/stimulation_EC_offline_Pan2025.yaml \\
        [--n-shortlist 3] [--sep-mm 10] [--additional-offset 0]

--stim is required because run_babelbrain.py takes it, but with --skip-thermal
its contents never affect the result. Any protocol for the target will do.
"""

import argparse
import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import numpy as np

from utils import (
    find_plantus_target_folder,
    score_candidate,
    find_roi_mask,
    mask_suffix,
    stem_for,
    prepare_plantus_scene,
    load_site_config,
    load_transducer_config,
    normalise_sub_id,
    parse_sub_list,
    resolve_data_dir,
    resolve_sub_dir,
    run_plantus_placement,
    select_best_vtx,
    setup_environment,
    transducer_params,
    write_brainsight_for_vtx,
)


@contextlib.contextmanager
def _suppress_wb_view():
    """PlanTUS opens a blocking Workbench window after every placement.

    See run_planTUS.py for the full note. Only wb_view is intercepted; the
    wb_command calls PlanTUS also makes through os.system must pass through,
    and they need Workbench on PATH -- setup_environment() puts it there. Miss
    that and PlanTUS fails on a missing *_coordinates.func.gii, which is the
    file wb_command was meant to have just written.
    """
    _real = os.system

    def _guard(cmd):
        return 0 if "wb_view" in cmd else _real(cmd)

    os.system = _guard
    try:
        yield
    finally:
        os.system = _real

def sweep_one(sub_id, cfg, data_dir, tp, target, side, stim, site_yaml,
              n_shortlist, sep_mm, additional_offset, top_pct, seed_vtx=()):
    sub_full, sub_bare = normalise_sub_id(sub_id)
    sub_dir = resolve_sub_dir(data_dir, sub_bare, sub_full)
    m2m = sub_dir / f"m2m_{sub_full}"
    # Step 4a may never have run for this target: no surfaces, no metric maps,
    # no folder to shortlist from. Build it here rather than making the caller
    # run run_planTUS.py first for the side effect -- a sweep should be a usable
    # entry point for a target that has only been registered.
    #
    # Tested by globbing rather than by catching find_plantus_target_folder:
    # that function reports failure with sys.exit(), so it raises SystemExit,
    # which is a BaseException and slips straight through `except Exception`.
    # Widening the except would also swallow its "multiple folders match" exit,
    # where building another scene is precisely the wrong response.
    if not [p for p in (m2m / "PlanTUS").glob(f"*{target}{mask_suffix(side)}")
            if p.is_dir()]:
        print(f"  [scene] {target}{side} — step 4a has not run, building it "
              f"(~2-3 min)", flush=True)
        with _suppress_wb_view():
            prepare_plantus_scene(
                sub_id_full=sub_full, sub_id_bare=sub_bare, m2m_dir=m2m,
                target_name=target, target_side=side, tp=tp, dry_run=False)
    folder = find_plantus_target_folder(m2m, sub_full, target, side)

    # A pad moves the exit plane away from the scalp, so a vertex only has to
    # reach min_distance - additional_offset from the ROI. run_planTUS.py already
    # did this; run_sweep did not, and every aMCC candidate was rejected -- the
    # scalp sits 38-42 mm from that ROI against a 50 mm floor.
    _min_dist = tp.get("min_distance")
    if _min_dist is not None and additional_offset:
        _min_dist = max(0.0, _min_dist - additional_offset)
        print(f"  distance floor {tp['min_distance']:.0f} -> {_min_dist:.0f} mm "
              f"(pad {additional_offset:.0f} mm)", flush=True)

    _, metrics, _ = select_best_vtx(
        folder, max_angle=tp["max_angle"], max_distance=tp.get("max_distance"),
        min_distance=_min_dist, top_pct=top_pct,
        n_shortlist=n_shortlist, shortlist_sep_mm=sep_mm, write_marker=False)
    shortlist = metrics["shortlist"]

    # Vertices carried over from an earlier sweep of the same target. The scalp
    # mesh is rebuilt from the same SimNIBS head model every time, so an index
    # found before still points at the same point on the scalp -- there is no
    # reason to rediscover it, and no guarantee the scorer would: the best
    # placement for sub-z002 LC right scored below seven worse ones and was only
    # found by sweeping every vertex whose beam meets the ROI.
    for _v in seed_vtx:
        if _v not in shortlist:
            shortlist = [_v] + shortlist
            print(f"  [seed] carrying vtx{_v} over from the previous sweep",
                  flush=True)
    print(f"\n{'=' * 66}\n{sub_full}  {target}{side}\n  shortlist {shortlist}",
          flush=True)

    results = []
    for vtx in shortlist:
        label = stem_for(sub_full, target, side)
        traj = folder / f"{label}_vtx{vtx}_brainsight.txt"
        if not traj.is_file():
            print(f"  [place] vtx{vtx}", flush=True)
            with _suppress_wb_view():
                run_plantus_placement(
                    vertex_idx=vtx, sub_id_full=sub_full, sub_id_bare=sub_bare,
                    m2m_dir=m2m, target_name=target, target_side=side, tp=tp,
                    additional_offset=additional_offset, dry_run=False)
            write_brainsight_for_vtx(m2m, sub_full, target, side, vtx=vtx)

        print(f"  [acoustic] vtx{vtx}", flush=True)
        rc = subprocess.run(
            [sys.executable, f"{_SRC_DIR}/run_babelbrain.py",
             "--site", site_yaml, "--sub", sub_id, "--target", target,
             "--side", side, "--stim", stim, "--vtx", str(vtx),
             "--additional-offset", str(additional_offset), "--skip-thermal",
             # Safe here and only here: domain and acoustic outputs are named by
             # the geometry that determines them (vertex, PPW, transducer), so a
             # match really is the same computation. The thermal reuse trap does
             # not apply -- thermal is skipped.
             "--reuse-files"],
            check=False).returncode
        if rc != 0:
            print(f"  [warn] acoustic failed for vtx{vtx} (rc={rc})", flush=True)
            continue
        # `_target` sits between the label and the vertex: run_id comes from
        # read_trajectory_id_BB, which returns the trajectory's own ID column,
        # and that ends in _target. Globbing without it silently found nothing,
        # so 26 completed acoustic solves were discarded unscored.
        hits = sorted(m2m.glob(f"{label}_target_vtx{vtx}_*_DataForSim.h5"))
        hits = [h for h in hits if "Water" not in h.name]
        if not hits:
            print(f"  [warn] no acoustic output for vtx{vtx}", flush=True)
            continue
        results.append((vtx, score_candidate(hits[-1], find_roi_mask(folder))))
    return results


def report(rows):
    print(f"\n{'=' * 66}\nSweep results — ranked by intensity at target\n")
    for (sub, target, side), res in rows.items():
        print(f"{sub}  {target}{side}")
        for vtx, m in sorted(res, key=lambda r: -r[1]["I_at_target"]):
            print(f"   vtx{vtx:<7d} lobe {m['lobe_mm3']:6.0f} mm3   "
                  f"I@target {m['I_at_target']:5.2f}   "
                  f"{'inside' if m['target_inside'] else 'OUTSIDE':>7s}   "
                  f"offset {m['offset_mm']:5.1f} mm   "
                  f"cover {100*m['coverage']:4.0f}% of {100*m['ceiling']:3.0f}% max"
                  f"  (eff {100*m['efficiency']:4.0f}%)   "
                  f"off-target {100*m['off_target']:4.0f}%   "
                  f"outlier {m['focal_peak_outlier']:4.2f}x")
        print()
    print("Pick per target, then run the thermal stage on it:")
    print("  python run_babelbrain.py --site ... --sub ... --target ... "
          "--side ... --stim ... --vtx <winner>")


def main():
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[1],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--site", required=True, metavar="FILE")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sub", metavar="SUB_ID")
    g.add_argument("--sub-list", metavar="FILE")
    p.add_argument("--target", required=True, nargs="+", metavar="LABEL")
    p.add_argument("--side", default="_L", choices=["_L", "_R", ""])
    p.add_argument("--stim", required=True, metavar="FILE",
                   help="Required by run_babelbrain.py; with --skip-thermal its "
                        "contents do not affect the result.")
    p.add_argument("--n-shortlist", type=int, default=3, metavar="N")
    p.add_argument("--sep-mm", type=float, default=10.0, metavar="MM",
                   help="Minimum separation between shortlisted vertices.")
    p.add_argument("--additional-offset", type=float, default=0.0, metavar="MM")
    p.add_argument("--seed-vtx", metavar="SPEC", action="append", default=[],
                   help="Vertices to include regardless of score, as "
                        "sub:target:side:vtx[,vtx...] — e.g. "
                        "sub-z002:rHipp_BN:_L:27429. Repeatable. Use to carry a "
                        "known-good placement across a re-run.")
    p.add_argument("--top-pct", type=float, default=0.5, metavar="F",
                   help="Candidate pool: keep vertices whose beam-ROI overlap "
                        "is at least this fraction of the best. Lower than the "
                        "0.8 select_best_vtx defaults to, because a sweep exists "
                        "to compare alternatives and a tight pool leaves none: "
                        "at 0.8, sub-z004 rHipp right admitted a single vertex.")
    args = p.parse_args()

    site_yaml = str(Path(args.site).resolve())
    stim = str(Path(args.stim).resolve())
    cfg = load_site_config(site_yaml)
    setup_environment(cfg)          # Workbench on PATH — PlanTUS needs it
    data_dir = resolve_data_dir(cfg)
    tp = transducer_params(load_transducer_config(cfg, site_yaml))
    subjects = ([args.sub] if args.sub
                else parse_sub_list(Path(args.sub_list).resolve()))

    seeds = {}
    for spec in args.seed_vtx:
        _sub, _tgt, _side, _vtxs = spec.split(":")
        seeds[(_sub, _tgt, _side)] = tuple(int(v) for v in _vtxs.split(",") if v)

    t0 = time.time()
    rows, n = {}, 0
    for sub in subjects:
        for target in args.target:
            try:
                res = sweep_one(sub, cfg, data_dir, tp, target, args.side, stim,
                                site_yaml, args.n_shortlist, args.sep_mm,
                                args.additional_offset, args.top_pct,
                                seeds.get((sub, target, args.side), ()))
            except Exception as e:
                print(f"  ERROR: sweep failed for {sub} {target}: {e}")
                continue
            rows[(sub, target, args.side)] = res
            n += len(res)
            print(f"  [sweep] {n} candidates, {(time.time() - t0) / 60:.1f} min",
                  flush=True)
    report(rows)


if __name__ == "__main__":
    main()
