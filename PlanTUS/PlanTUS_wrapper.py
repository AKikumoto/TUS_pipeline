#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PlanTUS wrapper — unified, config-driven
@author: Maximilian Lueckel, mlueckel@uni-mainz.de
         (config integration: LabWiki)

Usage — direct (edit defaults below, then run):
    simnibs_python PlanTUS_wrapper.py

Usage — called by step04_planTUS.ipynb or run_prepTUS.py:
    simnibs_python PlanTUS_wrapper.py \\
        --site  ../config/sites/site_RIKEN_AK.yaml \\
        --sub   sub-NS \\
        --target aMCC_NeuroSynthTopic112 \\
        --side  _R \\
        [--additional-offset 3.0] \\
        [--dry-run]

CLI args override the default values in "Specify variables" below.
"""
#==============================================================================
#==============================================================================
# Specify variables — EDIT THIS SECTION for direct use
# (CLI args override these when called from a script)
#==============================================================================
#==============================================================================
import argparse
import os, sys
import subprocess
from pathlib import Path
import yaml

# ── DEFAULTS (used when no CLI args are provided) ─────────────────────────────
# Change SITE_CONFIG to switch site / transducer:
#   site_RIKEN_AK.yaml  → CTX-500  (RIKEN)
#   site_UMD_AK.yaml    → DPX-500  (UMD)   ← fill in TBD values first
_DEFAULT_SITE   = str(Path(__file__).parent.parent / "config" / "sites" / "site_RIKEN_AK.yaml")
_DEFAULT_SUB    = "sub-02HI"
_DEFAULT_TARGET = "aMCC_NeuroSynthTopic112"
_DEFAULT_SIDE   = "_R"
_DEFAULT_OFFSET = 0.0

# ── CLI args (override defaults when called from step04 / run_prepTUS.py) ─────
_p = argparse.ArgumentParser(add_help=True)
_p.add_argument("--site",              default=None)
_p.add_argument("--sub",               default=None)
_p.add_argument("--target",            default=None)
_p.add_argument("--side",              default=None)
_p.add_argument("--additional-offset", type=float, default=None, dest="additional_offset")
_p.add_argument("--dry-run",           action="store_true",       dest="dry_run")
_args, _ = _p.parse_known_args()

SITE_CONFIG         = Path(_args.site   or _DEFAULT_SITE)
sub_id              = _args.sub         or _DEFAULT_SUB
targetLabel         = _args.target      or _DEFAULT_TARGET
targetside          = _args.side        if _args.side is not None else _DEFAULT_SIDE
additional_offset_s = _args.additional_offset if _args.additional_offset is not None else _DEFAULT_OFFSET
DRY_RUN             = _args.dry_run

#==============================================================================
# Load site + transducer config — do not edit below this line
#==============================================================================

def _load_yaml(path):
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path(__file__).parent / p).resolve()
    with open(p) as fh:
        return yaml.safe_load(fh)

site_cfg = _load_yaml(SITE_CONFIG)
t_cfg    = _load_yaml(
    Path(__file__).parent.parent / "config" / "transducers" / f"{site_cfg['transducer']}.yaml"
)

# ── TOOL PATHS (from site config) ─────────────────────────────────────────────
# https://github.com/mlueckel/PlanTUS
os.environ["PATH"] += ":" + str(Path(site_cfg["fsl_bin"]).expanduser())
os.environ["PATH"] += ":" + str(Path(site_cfg["workbench_bin"]).expanduser())
os.environ["PATH"] += ":" + str(Path(site_cfg["freesurfer_home"]).expanduser() / "bin")
os.environ["FREESURFER_HOME"] = str(Path(site_cfg["freesurfer_home"]).expanduser())
print("wb_command:", subprocess.getoutput("which wb_command"))
print("mris_convert:", subprocess.getoutput("which mris_convert"))
print("fslmaths:", subprocess.getoutput("which fslmaths"))

# # GLOBAL SCREEN SETTINGS FOR WORKBENCH (uncomment if display scaling issues arise)
# os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
# os.environ["QT_SCALE_FACTOR"] = "1"
# os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

# ── DATA PATHS (from site config) ─────────────────────────────────────────────
DIR_HERE = Path(__file__).resolve().parent
DIR_DATA = Path(site_cfg["data_root"]).expanduser()
_simnibs_py    = Path(site_cfg.get("simnibs_python", "")).expanduser()
_sp_candidates = sorted((_simnibs_py.parent.parent / "lib").glob("python3.*"))
SIMNIBS_SITE_PACKAGES = (_sp_candidates[0] / "site-packages") if _sp_candidates else _simnibs_py.parent

# ── SUBJECT FILES ──────────────────────────────────────────────────────────────
# Pre-requisites:
# 1. (optional) fslorient -copysform2qform T1.nii.gz
# 2. charm <subid> <path>/T1.nii.gz
DIR_TISSUES = list(DIR_DATA.rglob('final_tissues.nii.gz'))
m2m_dir_all = [p.parent.name for p in DIR_TISSUES]
sub_idx     = m2m_dir_all.index(f"m2m_{sub_id}")
subject_dir = DIR_TISSUES[sub_idx].parent

# Available target labels:
#   aMCC_NeuroSynthTopic112 / BST_BNST / Ce_CeA / IFJ / FEF / dIg_L_OR_dIg_R / LCMask
t1_filepath           = subject_dir / "T1.nii.gz"
simnibs_mesh_filepath = subject_dir / f"{sub_id}.msh"
target_roi_filepath   = list(subject_dir.parent.rglob(f"*_{targetLabel}_mask_native{targetside}.nii.gz"))[0]

# ── TRANSDUCER PARAMS (from transducer config) ─────────────────────────────────
min_distance        = t_cfg["min_focal_depth_mm"]
max_distance        = t_cfg["max_focal_depth_mm"]
transducer_diameter = t_cfg["transducer_diameter_mm"]
max_angle           = t_cfg["max_angle_deg"]
plane_offset        = t_cfg["plane_offset_mm"]
additional_offset   = float(t_cfg.get("additional_offset_mm", 0))
if additional_offset_s:
    additional_offset = float(additional_offset_s)
focal_distance_list = list(t_cfg["calibration"]["tpo_settings_mm"])
flhm_list           = list(t_cfg["calibration"]["axial_flhm_mm"])

# ── PLANTUS PATHS (from transducer config) ────────────────────────────────────
plantus_main_folder               = DIR_HERE
planning_scene_template_filepath  = plantus_main_folder / "resources" / "scene_templates" / t_cfg["scene_template"]
placement_scene_template_filepath = plantus_main_folder / "resources" / "scene_templates" / "TUSTransducerPlacement_TEMPLATE.scene"
transducer_surface_model_filepath = plantus_main_folder / "resources" / "transducer_models" / t_cfg["transducer_model"]
plantus_code_path                 = plantus_main_folder / "code"

#=============================================================================
# DRY_RUN: validate paths then exit
#=============================================================================
if DRY_RUN:
    print("[DRY_RUN] Input validation:")
    print(f"  site_config          : {SITE_CONFIG}")
    print(f"  sub_id               : {sub_id}")
    print(f"  target               : {targetLabel}{targetside}")
    print(f"  t1_filepath          : {t1_filepath}  {'OK' if t1_filepath.exists() else 'MISSING'}")
    print(f"  simnibs_mesh         : {simnibs_mesh_filepath}  {'OK' if simnibs_mesh_filepath.exists() else 'MISSING'}")
    print(f"  target_roi           : {target_roi_filepath}  {'OK' if Path(target_roi_filepath).exists() else 'MISSING'}")
    print(f"  focal_distance_list  : {focal_distance_list}")
    print(f"  additional_offset_mm : {additional_offset}")
    print("[DRY_RUN] Done. Exiting without running PlanTUS.")
    sys.exit(0)

#=============================================================================
#=============================================================================
# Run PlanTUS
#=============================================================================
#=============================================================================
import os
import shutil
import numpy as np
import math
import subprocess
import re
import threading
from pynput import mouse

# PlanTUS code / simnibs code paths must be added
sys.path.insert(0, str(plantus_code_path))
sys.path.insert(0, str(SIMNIBS_SITE_PACKAGES))
os.chdir(plantus_code_path)
import PlanTUS

#=============================================================================
#
#=============================================================================

target_roi_filename = os.path.split(target_roi_filepath)[1]
target_roi_name = target_roi_filename.replace(".nii", "")
target_roi_name = target_roi_name.replace(".gz", "")

output_path = os.path.split(simnibs_mesh_filepath)[0]
output_path = output_path + "/PlanTUS/" + target_roi_name
os.makedirs(output_path, exist_ok=True)

shutil.copy(target_roi_filepath, output_path + "/")
target_roi_filepath = output_path + "/" + target_roi_filename


#=============================================================================
# Convert SimNIBS mesh(es) to surface file(s)
#=============================================================================

# Skin
PlanTUS.convert_simnibs_mesh_to_surface(simnibs_mesh_filepath, [1005], "skin", output_path)
PlanTUS.add_structure_information(output_path + "/skin.surf.gii", "CORTEX_LEFT")

# Skull
PlanTUS.convert_simnibs_mesh_to_surface(simnibs_mesh_filepath, [1007, 1008], "skull", output_path)
PlanTUS.add_structure_information(output_path + "/skull.surf.gii", "CORTEX_RIGHT")


#==============================================================================
#
#==============================================================================

PlanTUS.create_avoidance_mask(simnibs_mesh_filepath, output_path + "/skin.surf.gii", transducer_diameter/2)


#==============================================================================
#
#==============================================================================

# distances between skin and (center of) target
target_center = PlanTUS.roi_center_of_gravity(target_roi_filepath)
skin_target_distances = PlanTUS.distance_between_surface_and_point(output_path + "/skin.surf.gii", target_center)
PlanTUS.create_metric_from_pseudo_nifti("distances", skin_target_distances, output_path + "/skin.surf.gii")
PlanTUS.mask_metric(output_path + "/distances_skin.func.gii", output_path + "/avoidance_skin.func.gii")
PlanTUS.add_structure_information(output_path + "/distances_skin.func.gii", "CORTEX_LEFT")
PlanTUS.threshold_metric(output_path + "/distances_skin.func.gii", max_distance)
PlanTUS.mask_metric(output_path + "/distances_skin_thresholded.func.gii", output_path + "/avoidance_skin.func.gii")
PlanTUS.add_structure_information(output_path + "/distances_skin_thresholded.func.gii", "CORTEX_LEFT")

# ===== From here: function to compute depth / fd / gel_needed =====
def report_depth_and_gel(vertex_idx,
                         skin_target_distances,
                         plane_offset,
                         additional_offset,
                         focal_distance_list,
                         out_dir,
                         target_roi_name,
                         subject_id):
    """
    Report distance, focal distance, and required gel thickness for the clicked vertex.

    Two clearly distinguished quantities are reported:

      (A) gel_needed_mm_abs  : ABSOLUTE total pad thickness needed so that
                               exit_plane → ROI == fd
                               = fd - skin_to_ROI_distance_mm
                               (this is the "true required pad thickness")

      (B) gel_delta_from_assumed_mm : DELTA relative to the currently assumed
                                      additional_offset_mm
                                      = gel_needed_mm_abs - additional_offset_mm
                                      (this is the fine-tune amount)

    Definitions:
      - skin_to_ROI_distance_mm:
          Distance from skin to the ROI center (value computed in Workbench)
      - plane_offset_mm:
          Fixed offset from the transducer radiating surface → exit plane
          (solid-water dome thickness)
      - additional_offset_mm:
          Currently assumed gel/pad thickness (exit plane → skin)
      - exit_plane_to_ROI_distance_mm:
          = skin_to_ROI_distance_mm + additional_offset_mm
      - focal_distance_fd_mm:
          Nominal focal distance of DPX/CTX (exit plane → acoustic focus)
      - gel_needed_mm_abs:
          ABSOLUTE pad thickness needed so that exit_plane → ROI = fd
      - gel_delta_from_assumed_mm:
          Difference from the currently assumed pad thickness
    """

    # skin → ROI
    dist_skin_roi = float(skin_target_distances[vertex_idx])

    # exit plane → ROI (current assumed setup)
    exit_plane_to_roi = dist_skin_roi + additional_offset

    # fd: choose the focal distance closest to exit_plane_to_ROI
    #fd = min(focal_distance_list, key=lambda x: abs(x - exit_plane_to_roi))
    fd = round(exit_plane_to_roi, 1) # .1 mm precision

    # (A) ABSOLUTE pad thickness required (independent of additional_offset)
    gel_needed_mm_abs = fd - dist_skin_roi

    # (B) DELTA from current assumption
    gel_delta_from_assumed_mm = gel_needed_mm_abs - additional_offset

    # ----------- Print to console -----------
    print("===== PlanTUS depth report =====")
    print(f"Subject                           : {subject_id}")
    print(f"Target ROI                        : {target_roi_name}")
    print(f"Vertex index                      : {vertex_idx}")
    print(f"skin → ROI distance (mm)         : {dist_skin_roi:.4f}")
    print(f"plane_offset_mm (radiator → exit plane)      : {plane_offset:.4f}")
    print(f"assumed_additional_offset_mm (exit plane → skin) : {additional_offset:.4f}")
    print(f"exit plane → ROI distance (mm)   : {exit_plane_to_roi:.4f}")
    print(f"focal_distance_fd_mm (exit plane → focus)     : {fd:.4f}")
    print(f"gel_needed_mm_abs (TOTAL pad thickness)       : {gel_needed_mm_abs:.4f}")
    print(f"gel_delta_from_assumed_mm (delta from assumed): {gel_delta_from_assumed_mm:.4f}")
    print("================================")

    # ----------- Output file name format -----------
    out_txt = Path(out_dir) / f"{subject_id}_{target_roi_name}_PlanTUS_depth_report_vtx{vertex_idx:05d}.txt"

    # ----------- Write file -----------
    with open(out_txt, "w") as f:
        f.write(f"# MODE EXPLANATION\n")
        f.write(f"# gel_needed_mm_abs        : ABSOLUTE total pad thickness required\n")
        f.write(f"# gel_delta_from_assumed_mm: Adjustment needed relative to currently assumed pad thickness\n\n")

        f.write(f"# Definitions:\n")
        f.write(f"# skin_to_ROI_distance_mm: skin → ROI center\n")
        f.write(f"# plane_offset_mm: radiator → exit plane (solid-water dome thickness)\n")
        f.write(f"# additional_offset_mm (assumed): exit plane → skin (gel/pad thickness)\n")
        f.write(f"# exit_plane_to_ROI_distance_mm: exit plane → ROI center (with assumption)\n")
        f.write(f"# focal_distance_fd_mm: nominal focus (exit plane → focus)\n")
        f.write(f"# gel_needed_mm_abs: fd - skin_to_ROI_distance_mm\n")
        f.write(f"# gel_delta_from_assumed_mm: gel_needed_mm_abs - additional_offset_mm\n\n")

        f.write(f"subject_id: {subject_id}\n")
        f.write(f"ROI: {target_roi_name}\n")
        f.write(f"vertex_index: {vertex_idx}\n")
        f.write(f"skin_to_ROI_distance_mm: {dist_skin_roi:.4f}\n")
        f.write(f"plane_offset_mm: {plane_offset:.4f}\n")
        f.write(f"additional_offset_mm_assumed: {additional_offset:.4f}\n")
        f.write(f"exit_plane_to_ROI_distance_mm: {exit_plane_to_roi:.4f}\n")
        f.write(f"focal_distance_fd_mm: {fd:.4f}\n")
        f.write(f"gel_needed_mm_abs: {gel_needed_mm_abs:.4f}\n")
        f.write(f"gel_delta_from_assumed_mm: {gel_delta_from_assumed_mm:.4f}\n")

    print("Depth report saved to:", out_txt)
# ===== End: depth / fd / gel_needed function =====



# angles between skin normal vectors and skin-target vectors
skin_target_angles = []
_, skin_normals = PlanTUS.compute_surface_metrics(output_path + "/skin.surf.gii")
skin_target_vectors = PlanTUS.vectors_between_surface_and_point(output_path + "/skin.surf.gii", target_center)
for i in np.arange(len(skin_target_vectors)):
    skin_target_angles.append((math.degrees(PlanTUS.angle_between_vectors(skin_target_vectors[i], skin_normals[i]))))
skin_target_angles = np.abs(np.asarray(skin_target_angles))
PlanTUS.create_metric_from_pseudo_nifti("angles", skin_target_angles, output_path + "/skin.surf.gii")
PlanTUS.mask_metric(output_path + "/angles_skin.func.gii", output_path + "/avoidance_skin.func.gii")
PlanTUS.add_structure_information(output_path + "/angles_skin.func.gii", "CORTEX_LEFT")
#PlanTUS.smooth_metric(output_path + "/angles_skin.func.gii", output_path + "/skin.surf.gii", transducer_diameter)
#PlanTUS.mask_metric(output_path + "/angles_skin_s" + str(transducer_diameter) + ".func.gii", output_path + "/avoidance_skin.func.gii")
#PlanTUS.add_structure_information(output_path + "/angles_skin_s" + str(transducer_diameter) + ".func.gii", "CORTEX_LEFT")


# intersection between skin normal vectors and target region
PlanTUS.stl_from_nii(target_roi_filepath, 0.25)
skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(output_path + "/skin.surf.gii")
skin_target_intersections = PlanTUS.compute_vector_mesh_intersections(skin_coordinates, skin_normals, output_path + "/" + target_roi_name + "_3Dmodel.stl", 200)

skin_target_intersection_values = []
for i in np.arange(len(skin_target_intersections)):
    if len(skin_target_intersections[i]) == 1:
        skin_target_intersection_values.append(0)
    elif len(skin_target_intersections[i]) == 2:
        d = np.linalg.norm(np.asarray(skin_target_intersections[i][1])-np.asarray(skin_target_intersections[i][0]))
        skin_target_intersection_values.append(d)
    elif len(skin_target_intersections[i]) == 3:
        d = np.linalg.norm(np.asarray(skin_target_intersections[i][1])-np.asarray(skin_target_intersections[i][0]))
        skin_target_intersection_values.append(d)
    elif len(skin_target_intersections[i]) == 4:
        d = (np.linalg.norm(np.asarray(skin_target_intersections[i][1])-np.asarray(skin_target_intersections[i][0]))+(np.linalg.norm(np.asarray(skin_target_intersections[i][3])-np.asarray(skin_target_intersections[i][2]))))
        skin_target_intersection_values.append(d)
    elif len(skin_target_intersections[i]) > 4:
        skin_target_intersection_values.append (np.nan)
    else:
        skin_target_intersection_values.append(0)
skin_target_intersection_values = np.asarray(skin_target_intersection_values)

PlanTUS.create_metric_from_pseudo_nifti("target_intersection", skin_target_intersection_values, output_path + "/skin.surf.gii")
PlanTUS.mask_metric(output_path + "/target_intersection_skin.func.gii", output_path + "/avoidance_skin.func.gii")
PlanTUS.add_structure_information(output_path + "/target_intersection_skin.func.gii", "CORTEX_LEFT")
#PlanTUS.smooth_metric(output_path + "/target_intersection_skin.func.gii", output_path + "/skin.surf.gii", transducer_diameter)
#PlanTUS.mask_metric(output_path + "/target_intersection_skin_s" + str(transducer_diameter) + ".func.gii", output_path + "/avoidance_skin.func.gii")
#PlanTUS.add_structure_information(output_path + "/target_intersection_skin_s" + str(transducer_diameter) + ".func.gii", "CORTEX_LEFT")


# angles between skin and skull normals
skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(output_path + "/skin.surf.gii")
skull_coordinates, skull_normals = PlanTUS.compute_surface_metrics(output_path + "/skull.surf.gii")
skin_skull_intersections = PlanTUS.compute_vector_mesh_intersections(skin_coordinates, skin_normals, output_path + "/skull.stl", 40)

indices_closest_skull_vertices = []
for i in np.arange(len(skin_coordinates)):
    try:
        intersection_coordinate = skin_skull_intersections[i][0]
        ED_skull_list = np.linalg.norm((skull_coordinates - intersection_coordinate), axis=1)
        indices_closest_skull_vertices.append((np.argmin(ED_skull_list)))
    except:
        indices_closest_skull_vertices.append((np.nan))
indices_closest_skull_vertices = np.asarray(indices_closest_skull_vertices).astype(int)

skin_skull_angle_list = []
for i in np.arange(len(skin_coordinates)):
    try:
        skin_normal = skin_normals[i]
        skull_normal = skull_normals[indices_closest_skull_vertices[i]]
        skin_skull_angle = math.degrees(PlanTUS.angle_between_vectors(skin_normal, skull_normal))
        skin_skull_angle_list.append(skin_skull_angle)
    except:
        skin_skull_angle_list.append(0)
skin_skull_angles = np.asarray(skin_skull_angle_list)

PlanTUS.create_metric_from_pseudo_nifti("skin_skull_angles", skin_skull_angles, output_path + "/skin.surf.gii")
PlanTUS.mask_metric(output_path + "/skin_skull_angles_skin.func.gii", output_path + "/avoidance_skin.func.gii")
PlanTUS.add_structure_information(output_path + "/skin_skull_angles_skin.func.gii", "CORTEX_LEFT")
#PlanTUS.smooth_metric(output_path + "/skin_skull_angles_skin.func.gii", output_path + "/skin.surf.gii", transducer_diameter)
#PlanTUS.mask_metric(output_path + "/skin_skull_angles_skin_s" + str(transducer_diameter) + ".func.gii", output_path + "/avoidance_skin.func.gii")
#PlanTUS.add_structure_information(output_path + "/skin_skull_angles_skin_s" + str(transducer_diameter) + ".func.gii", "CORTEX_LEFT")




scene_variable_names = [
    'SKIN_SURFACE_FILENAME',
    'SKIN_SURFACE_FILEPATH',
    'SKULL_SURFACE_FILENAME',
    'SKULL_SURFACE_FILEPATH',
    'DISTANCES_FILENAME',
    'DISTANCES_FILEPATH',
    'INTERSECTION_FILENAME',
    'INTERSECTION_FILEPATH',
    'ANGLES_FILENAME',
    'ANGLES_FILEPATH',
    'ANGLES_SKIN_SKULL_FILENAME',
    'ANGLES_SKIN_SKULL_FILEPATH',
    'DISTANCES_MAX_FILENAME',
    'DISTANCES_MAX_FILEPATH',
    'T1_FILENAME',
    'T1_FILEPATH',
    'MASK_FILENAME',
    'MASK_FILEPATH']

scene_variable_values = [
    'skin.surf.gii',
    './skin.surf.gii',
    'skull.surf.gii',
    './skull.surf.gii',
    'distances_skin.func.gii',
    './distances_skin.func.gii',
    'target_intersection_skin.func.gii',
    './target_intersection_skin.func.gii',
    'angles_skin.func.gii',
    './angles_skin.func.gii',
    'skin_skull_angles_skin.func.gii',
    './skin_skull_angles_skin.func.gii',
    'distances_skin_thresholded.func.gii',
    './distances_skin_thresholded.func.gii',
    'T1.nii.gz',
    '../../T1.nii.gz',
    target_roi_filename,
    './' + target_roi_filename]


PlanTUS.create_scene(planning_scene_template_filepath, output_path + "/scene.scene", scene_variable_names, scene_variable_values)


# Define the command
command = "wb_view -logging FINER " + output_path + "/scene.scene"

# Regular expression pattern to match the phrase and the number
pattern = re.compile(r"Switched vertex to triangle nearest vertex\s+(\.\d+)")

# Initialize the variable to store the number and a flag to trigger processing
triangle_number = None
process_line = False

# Function to monitor mouse clicks
def on_click(x, y, button, pressed):
    global process_line
    if pressed:
        process_line = True

# Start listening for mouse clicks in a separate thread
listener = mouse.Listener(on_click=on_click)
listener.start()

# Start the process to run the command
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=output_path, text=True)

# Function to read the process output
def read_output():
    global triangle_number, process_line

    while True:
        output = process.stderr.readline()
        if output == '' and process.poll() is not None:
            break

        if process_line:
            # Process the latest line only when a mouse click is detected
            match = pattern.search(output)
            if match:
                triangle_number = match.group(1)
                triangle_number = int(triangle_number.replace(".", ""))
                print(f"Switched vertex to triangle nearest vertex: {triangle_number}")

                # Ask the user if they want to generate the transducer placement
                response = input(f"Generate transducer placement for vertex {triangle_number}? (yes/no): ").strip().lower()
                if response == "yes":
                    print(f"Generating transducer placement for vertex {triangle_number}")

                    # ▼ Compute and report depth / fd / gel_needed here
                    report_depth_and_gel(
                        vertex_idx=triangle_number,
                        skin_target_distances=skin_target_distances,
                        plane_offset=plane_offset,
                        additional_offset=additional_offset,
                        focal_distance_list=focal_distance_list,
                        out_dir=output_path,
                        target_roi_name=target_roi_name,
                        subject_id=sub_id
                    )
                    PlanTUS.prepare_acoustic_simulation(triangle_number,
                                                        output_path,
                                                        target_roi_filepath,
                                                        t1_filepath,
                                                        max_distance,
                                                        min_distance,
                                                        transducer_diameter,
                                                        max_angle,
                                                        plane_offset,
                                                        additional_offset,
                                                        transducer_surface_model_filepath,
                                                        focal_distance_list,
                                                        flhm_list,
                                                        placement_scene_template_filepath)
                else:
                    print("No action taken.")

                # Reset the flag
                process_line = False

# Start the output reading in a separate thread
output_thread = threading.Thread(target=read_output)
output_thread.start()

# Wait for the process and threads to finish
process.wait()
output_thread.join()
listener.stop()
