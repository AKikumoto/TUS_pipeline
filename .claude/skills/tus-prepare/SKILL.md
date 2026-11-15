---
name: tus-prepare
description: Take an experiment's subjects from a T1 to a simulated TUS placement with this package's scripts, one stage per run; stops for the vertex choice and never judges safety
---

Runs the preparation in [README_TUS.md](../../../README_TUS.md) with the scripts in `src/`.
Each run reads what the outputs on disk say, does the next stage for every placement at
that stage, and stops. The steps themselves are documented in the README and in the
docstring of `src/run_prepall.py`; this skill fixes only their order and the points where
a person decides.

## Where this runs

"The package" is the folder holding this `.claude/`: it has `src/`, `config/` and
`README_TUS.md`, wherever it was downloaded. Run every command from there. The scripts need
the `mri` conda environment (README_TUS.md,
[Python environment](../../../README_TUS.md#python-environment)). Find its Python once,
`conda run -n mri python -c "import sys; print(sys.executable)"`, and call it by that path,
so a job started under nohup runs in the same environment.

## 1. Find the inputs

- **Site YAML**: this machine's file in `config/sites/`. Ask which one when there are
  several. None: go to step 2.
- **Pipeline YAML**: the experiment's file, in the project, never in the package
  ([Multi-subject batch](../../../README_TUS.md#multi-subject-batch-pipeline-yaml-recommended)).
  Ask where it is. None: copy `config/template_pipeline.yaml` to the place the person names
  (for example `analysis/configs/pipeline_TUS.yaml`) and fill it with them: targets, side,
  pad, stimulation protocol. Never fill a field they did not give.
- **Subject folder**: `data_root` from the site YAML joined with the pipeline YAML's
  `sub_list_dir`.
- **Masks**: every target's mask must exist in `masks/standardized/`. A missing one is made
  by a person in Step 2 ([Step 2](../../../README_TUS.md#step-2-mni-mask-generation)): stop.

## 2. First run on a machine: the site YAML

- Copy `config/sites/template_site.yaml` to `site_<SITE>_<STATION>.yaml`, as its header says.
- Fill the software paths only with what is found here (`which charm`, `$FSLDIR`,
  `which wb_command`, `$FREESURFER_HOME`, the BabelBrain application). Show each with
  where it was found.
- A tool not found: stop. Installs and the FreeSurfer licence are the person's
  ([Software Dependencies](../../../README_TUS.md#software-dependencies)).
- Ask for every other field: transducer, neuronavigation and its version, coordinate
  system, computing device and backend, pipeline choices, data paths. Never infer one.
- This file holds this machine's paths. Do not commit it.

## 3. Bring the subject list up to date

- List the `sub-*` folders in the subject folder. A folder the pipeline YAML does not list:
  ask its side or sides, then add one entry per side.
- A new participant: ask for the T1 as NIfTI (DICOM conversion is not part of this
  package). Make `sub-<ID>/` and copy the T1, never move it, to `sub-<ID>/sub-<ID>_T1w.nii.gz`
  (`.nii` if that is what was given).
- Never remove a subject from the YAML, and never remove a `skip: true`.

## 4. Read each placement's stage

A placement is one subject entry, one side and one target. Read its stage from the files,
never from an earlier session, and show every placement in one table.

| Found | Stage |
|---|---|
| No T1 in `sub-<ID>/` | needs a T1: step 3 |
| No `VERTICES_EXPLORED.md` in `m2m_<sub>/PlanTUS/<sub>_<target>_mask-<L or R>/` | to sweep: step 5 |
| The table, but no thermal summary for the protocol | to choose: step 6 |
| `m2m_<sub>/<sub>_<target>-<L or R>_target_vtx*-ThermalField_<protocol>_Summary.csv` | done: step 7 |

`<protocol>` is the stimulation YAML's file name without `stimulation_` and `.yaml`. For
side `''` the `-L` or `-R` is absent.

First look at the newest file in `<subject folder>/logs/`. If it has no `Finished` line:

- its process still running (`pgrep -f` on its command): show its last step lines and stop
- no process: the job died; show the log's end and stop for the person

A log that finished with a failed or skipped step: show that step's error lines and stop.
Never re-run with other settings unless the person says so.

## 5. To sweep: seg, reg and sweep under nohup

- Start only when every placement to sweep has its T1.
- Mark `skip: true  # swept` on each subject entry whose every target is past the sweep, so
  this run does not solve it again.
- Dry run first and show the commands:
  `<python> src/run_prepall.py --config <pipeline YAML> --steps seg,reg,sweep --dry-run`.
- Costs are in each runner's docstring (a sweep is about 5 minutes per candidate). Ask
  before starting.
- Start it so it outlives the session; the log goes beside the data, never into the package
  or a repository:

  ```bash
  mkdir -p "<subject folder>/logs"
  nohup "<python>" src/run_prepall.py --config "<pipeline YAML>" --steps seg,reg,sweep \
      > "<subject folder>/logs/prepall_$(date +%Y%m%d_%H%M).log" 2>&1 &
  ```

- Stop. Give the person the log's path; the next run starts from the outputs.

## 6. To choose: the person picks the vertex

- For each placement, show its `VERTICES_EXPLORED.md` as written and the registration check,
  `sub-<ID>/figures/registration/<sub>_MNI2native_regcheck.png`.
- Point to [Choosing a placement](../../../README_TUS.md#choosing-a-placement-sweep-judge-then-thermal)
  for how to read the table.
- Who chooses depends on the study. Do not rank, recommend or pre-select a vertex. Ask for
  one vertex per placement.
- Write no reason for a choice, anywhere.
- More candidates (`run_sweep.py --stratify`, `--seed-vtx`) only when the person asks.
- Write one `run_babelbrain.py` line per chosen placement into
  `<subject folder>/logs/babel_<YYYYmmdd_HHMM>.sh`, ending with
  `echo "Finished $(date '+%Y-%m-%d %H:%M:%S')"`:

  ```bash
  "<python>" src/run_babelbrain.py --site "<site YAML>" --sub-list-dir "<sub_list_dir>" \
      --sub <sub> --target <target> --side <side> --stim "<stimulation YAML>" --vtx <N>
  ```

- The protocol is the pipeline YAML's `stim`, unless the person names another.
- Never pass `--reuse-files` to a thermal run.
- Show the file, ask, then start it with nohup, its log beside it under the same name.
  Stop.

## 7. Done: record and show the numbers

- Run `run_status.py` when any thermal summary is newer than
  `<subject folder>/ADOPTED_PLACEMENTS.csv`, or that file is missing. Otherwise show the
  existing tables.
- Pass every `sub-*` folder in the subject folder that holds a thermal summary, one `--sub`
  each, not only this experiment's: the tables are rewritten whole.

  ```bash
  "<python>" src/run_status.py --site "<site YAML>" --sub-list-dir "<sub_list_dir>" \
      --sub <sub> [--sub <sub> ...]
  ```

- Show this experiment's rows of `ADOPTED_BY_TARGET.md`, and the PDF's path.
- Temperature rise, MI and the standoff check are shown as numbers. Never call a value
  safe, acceptable or within a limit: that review is a person's, before stimulation.

## End of every run

Report two lists:

- what changed: files written, entries added or marked, jobs started with their logs
- what waits for a person: installs, hardware facts, masks, T1s, vertex choices, the safety review

Nothing here touches git. The pipeline YAML is the project's, for its owner to commit.
