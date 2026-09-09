#!/usr/bin/env python3
"""
src/run_babelbrain.py
Batch runner — Step 5: BabelBrain domain, acoustic and thermal simulation.

Runs everything step05_babelbrain.ipynb runs, for one subject or many, with no
notebook. The notebook stays the place to look at a single run; this is for
sweeping subjects and targets, where editing a settings cell per combination is
the bottleneck.

Run with the mri conda environment Python (BabelBrain must be importable; the
path comes from `babelbrain_dir` in the site config).

Algorithm (per subject)
-----------------------
0. resolve_vtx              — VTX (or the newest placement) picks the vertex;
                              that vertex supplies the trajectory AND the depth
                              report, so the two cannot disagree.
1. run_domain_BB            — tissue domain from the SimNIBS mesh + trajectory.
2. compute_z_steering_BB    — electronic steering from the depth report.
3. run_acoustic_BB          — FDTD acoustic solve (+ water reference run).
4. summarise_acoustic_BB    — metrics table -> HTML.
   save_acoustic_gui_BB     — beam-aligned field, identical to the BabelBrain GUI.
   plot_acoustic_qc_BB      — anatomical QC on native T1, with the ROI contour.
5. patch_babelvisco_BB      — the intparams dtype fix; idempotent, safe per run.
   run_thermal_BB           — BHTE solve for every DC/PRF/Duration combination.
6. write_tpo_summary_BB     — free-field ISPPA back-calculation -> *_Summary.csv.
7. plot_thermal_qc_BB       — dT / CEM43 figures, one per combination.

The interactive viewer (view_acoustic_interactive_BB) is deliberately omitted:
it renders an HTML widget for a notebook and has no meaning in a batch run.

Usage — single subject:
    python run_babelbrain.py \\
        --site   config/sites/site_UMD_AK.yaml \\
        --sub    sub-z004 \\
        --target hippocampus_anterior_L_Weizhen_0.05 \\
        --side   _L \\
        --stim   config/stimulation/stimulation_hippocampus_offline_Pan2025.yaml \\
        [--vtx 10202] [--additional-offset 20] [--ppw 6] [--reuse-files]
        [--skip-thermal] [--dry-run]

Usage — many subjects:
    python run_babelbrain.py \\
        --site     config/sites/site_UMD_AK.yaml \\
        --sub-list subjects.txt \\
        --target   LC --side _L \\
        --stim     config/stimulation/stimulation_hippocampus_offline_Pan2025.yaml

Outputs (per subject, in m2m_{sub}/ and {sub}/figures/):
    {prefix}BabelViscoInput.nii.gz
    {prefix}DataForSim.h5                       and _Water_DataForSim.h5
    {prefix}DataForSim-ThermalField_AllCombinations.h5
    {prefix}DataForSim-ThermalField_Summary.csv
    {prefix}acoustic_summary.html, *_gui_field.png, *_acoustic_qc.png
    {prefix}*_thermal_qc.png

where prefix carries the vertex, so placements never overwrite each other.
"""

import argparse
import sys
import traceback
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (
    compute_z_steering_BB,
    find_plantus_target_folder,
    fig_dir_for,
    find_roi_mask,
    load_babelbrain_tx_yaml,
    load_site_config,
    normalise_sub_id,
    parse_sub_list,
    patch_babelvisco_BB,
    plot_acoustic_qc_BB,
    plot_thermal_qc_BB,
    read_trajectory_id_BB,
    resolve_data_dir,
    resolve_sub_dir,
    resolve_vtx,
    stem_for,
    run_acoustic_BB,
    run_domain_BB,
    run_thermal_BB,
    save_acoustic_gui_BB,
    summarise_acoustic_BB,
    write_tpo_summary_BB,
)


def run_one(
    sub_id: str,
    cfg: dict,
    data_dir: Path,
    bb_dir: str,
    target_name: str,
    target_side: str,
    thermal_profile: list,
    base_isppa: float,
    stim_label: str,
    vtx: int | None,
    additional_offset: float,
    ppw: int,
    z_beyond: float,
    reuse_files: bool,
    skip_thermal: bool,
    dry_run: bool,
) -> None:
    """Run step 5 end to end for a single subject."""
    import matplotlib
    matplotlib.use("Agg")          # no display in a batch run

    sub_id_full, sub_id_bare = normalise_sub_id(sub_id)
    sub_dir = resolve_sub_dir(data_dir, sub_id_bare, sub_id_full)
    m2m_dir = sub_dir / f"m2m_{sub_id_full}"
    t1w = str(m2m_dir / "T1.nii.gz")
    # Acoustic figures do not depend on the stimulation protocol, so they sit
    # one level above it; thermal figures go under the protocol.
    fig_dir = fig_dir_for(sub_dir, target_name)
    fig_dir_thermal = fig_dir_for(sub_dir, target_name, stim_label)

    tx_cfg = cfg.get("transducer_cfg", {})
    if not tx_cfg:
        raise ValueError("transducer_cfg not found in site config.")
    tx_system = tx_cfg["babelbrain_id"]
    frequency = tx_cfg["frequency_kHz"] * 1e3
    aperture = tx_cfg["active_diameter_mm"] / 1e3
    focal_length = tx_cfg["radius_of_curvature_mm"] / 1e3
    bb_yaml = load_babelbrain_tx_yaml(bb_dir, tx_system)
    backend = cfg["computing_backend"]
    device = cfg["computing_device"]

    # --- 5-0: which placement --------------------------------------------------
    folder = find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)
    vtx_eff = resolve_vtx(folder, vtx)
    label = stem_for(sub_id_full, target_name, target_side)
    trajectory = folder / f"{label}_vtx{vtx_eff}_brainsight.txt"
    if not trajectory.is_file():
        raise FileNotFoundError(
            f"No trajectory for vtx{vtx_eff}: {trajectory.name}\n"
            f"  Run step 4c for this vertex (run_planTUS.py, or the notebook) first."
        )

    run_id = read_trajectory_id_BB(str(trajectory)) + f"_vtx{vtx_eff}"
    # BabelBrain's own convention, not ours: it rebuilds this name internally
    # from field_target as "{field_target}_{freq}kHz_{ppw}PPW_..." and loads the
    # domain by that path. Writing DPX500-500kHz-6ppw instead made step 5b look
    # for a file step 5a had not written. Same class of boundary as the vtx
    # padding and the thermal output name -- the prefix up to the transducer is
    # ours, everything after it is theirs.
    prefix = f"{run_id}_{tx_system}_{int(frequency / 1e3)}kHz_{ppw}PPW_"
    field_target = f"{run_id}_{tx_system}"
    print(f"  vertex : vtx{vtx_eff}")
    print(f"  prefix : {prefix}")

    if dry_run:
        print("  [dry-run] inputs resolved; nothing written.")
        return

    # --- 5a: domain ------------------------------------------------------------
    domain_file = run_domain_BB(
        m2m_dir, t1w, str(trajectory), prefix, backend, device,
        frequency, ppw, str(m2m_dir / f"{prefix}BabelViscoInput.nii.gz"),
        reuse_files=reuse_files, dry_run=False,
    )

    # --- 5b: steering + acoustic ----------------------------------------------
    z_steering, tx_mech_adj_z = compute_z_steering_BB(
        folder, tx_cfg, additional_offset_mm=additional_offset,
        bb_tx_yaml=bb_yaml, vtx=vtx_eff,
    )[:2]

    acoustic_file = run_acoustic_BB(
        m2m_dir, field_target, tx_system, frequency, aperture, focal_length,
        bb_yaml["InDiameters"], bb_yaml["OutDiameters"], backend, device, ppw,
        z_steering=z_steering, tx_mech_adj_z=tx_mech_adj_z,
        z_beyond=z_beyond, use_ct=False,
        reuse_files=reuse_files, dry_run=False,
    )

    # --- 5b QC -----------------------------------------------------------------
    roi_nii = find_roi_mask(folder)
    summarise_acoustic_BB(acoustic_file, fig_dir=fig_dir)
    save_acoustic_gui_BB(acoustic_file, fig_dir=fig_dir)
    plot_acoustic_qc_BB(acoustic_file, fig_dir, run_id, tx_system,
                        frequency, ppw, roi_nii=roi_nii)

    if skip_thermal:
        print("  --skip-thermal: stopping after the acoustic stage.")
        return

    # --- 5c: thermal -----------------------------------------------------------
    patch_babelvisco_BB()
    allcomb_h5 = run_thermal_BB(
        acoustic_file, thermal_profile, base_isppa, frequency, tx_system,
        backend, device, reuse_files=reuse_files, dry_run=False,
    )

    write_tpo_summary_BB(acoustic_file, allcomb_h5, tx_cfg,
                         sub_id_full, target_name, target_side)

    plot_thermal_qc_BB(
        allcomb_h5, field_target, m2m_dir, fig_dir_thermal, run_id,
        sub_id_full, target_name, target_side, tx_system, frequency,
        acoustic_file=acoustic_file, stim_label=stim_label,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[1],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--site", required=True, metavar="FILE",
                   help="Path to site config YAML.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--sub", metavar="SUB_ID",
                     help="Single subject ID (e.g. sub-z004 or z004).")
    grp.add_argument("--sub-list", metavar="FILE",
                     help="Text file with one subject ID per line (# comments ignored).")
    p.add_argument("--target", required=True, metavar="LABEL",
                   help="Target label, matching the mask label from step 3.")
    p.add_argument("--side", default="_L", choices=["_L", "_R", ""],
                   help="Hemisphere suffix; '' for bilateral.")
    p.add_argument("--stim", required=True, metavar="FILE",
                   help="Stimulation protocol YAML (BaseIsppa + AllDC_PRF_Duration).")
    p.add_argument("--vtx", type=int, default=None, metavar="N",
                   help="Placement to simulate. Default: the newest one.")
    p.add_argument("--additional-offset", type=float, default=0.0, metavar="MM",
                   help="Gel/pad offset in mm, added to the exit-plane-to-ROI "
                        "depth. aMCC needs ~20; the hippocampus needs 0.")
    p.add_argument("--ppw", type=int, default=6, metavar="N",
                   help="Points per wavelength. BabelBrain forces 6 above 350 kHz.")
    p.add_argument("--z-beyond", type=float, default=40e-3, metavar="M",
                   help="Simulated depth beyond the target, in metres.")
    p.add_argument("--reuse-files", action="store_true",
                   help="Skip a stage when its output already exists. Off by "
                        "default, so a run is self-consistent end to end.")
    p.add_argument("--skip-thermal", action="store_true",
                   help="Stop after the acoustic stage and its QC.")
    p.add_argument("--dry-run", action="store_true",
                   help="Resolve inputs and print the prefix; write nothing.")
    return p.parse_args()


def main() -> None:
    import yaml

    args = parse_args()
    site_yaml = str(Path(args.site).resolve())
    cfg = load_site_config(site_yaml)
    data_dir = resolve_data_dir(cfg)

    bb_dir = str(Path(cfg.get("babelbrain_dir", "")).expanduser().resolve())
    if bb_dir and bb_dir not in sys.path:
        sys.path.insert(0, bb_dir)

    stim_path = Path(args.stim).resolve()
    with open(stim_path) as fh:
        stim = yaml.safe_load(fh)
    thermal_profile = stim["AllDC_PRF_Duration"]
    base_isppa = stim["BaseIsppa"]
    stim_label = stim_path.stem.removeprefix("stimulation_")

    subjects = ([args.sub] if args.sub
                else parse_sub_list(Path(args.sub_list).resolve()))

    print(f"Site       : {site_yaml}")
    print(f"BabelBrain : {bb_dir}")
    print(f"Target     : {args.target}{args.side}")
    print(f"Stimulation: {stim_label}  "
          f"(BaseIsppa {base_isppa} W/cm², {len(thermal_profile)} combination(s))")
    print(f"Subjects   : {len(subjects)}\n")

    n_ok = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            run_one(
                sub_id=sub_id, cfg=cfg, data_dir=data_dir, bb_dir=bb_dir,
                target_name=args.target, target_side=args.side,
                thermal_profile=thermal_profile, base_isppa=base_isppa,
                stim_label=stim_label, vtx=args.vtx,
                additional_offset=args.additional_offset, ppw=args.ppw,
                z_beyond=args.z_beyond, reuse_files=args.reuse_files,
                skip_thermal=args.skip_thermal, dry_run=args.dry_run,
            )
            n_ok += 1
        except Exception as e:
            print(f"  ERROR: step 5 failed for {sub_id}: {e}")
            traceback.print_exc()
            n_fail += 1
        print()

    print("=" * 50)
    print(f"Summary: {n_ok} completed  {n_fail} failed")


if __name__ == "__main__":
    main()
