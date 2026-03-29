# Oscar HPC — `mri` Environment Setup Guide

Instructions for setting up the environment to run the TUS pipeline (Steps 1–5) on Brown University CCV Oscar.

---

## Prerequisites

- Oscar account active (`ssh <username>@ssh.ccv.brown.edu`)
- Steps 1–4 completed locally; `*_brainsight.txt` already generated

---

## 1. Login and module configuration

```bash
ssh akikumot@ssh.ccv.brown.edu

# Initialize conda (first time only)
module load anaconda3/2023.09-0-aqbc
conda init bash
source ~/.bashrc
```

---

## 2. Start an interactive job

**Do not run heavy tasks (installation, testing) on the login node.**

```bash
# CPU only (for installation)
interact -n 4 -m 16g -t 01:00:00

# With GPU (for testing and running simulations)
interact -n 4 -m 16g -t 00:30:00 -q gpu -g 1
```

---

## 3. conda env setup

### 3a. Check existing `mri` env

```bash
conda activate mri
python --version   # should be 3.11.x
```

### 3b. Install SimNIBS dependencies (run in order)

```bash
# Step 1: SimNIBS dependency libraries (all at once)
pip install \
  "git+https://github.com/simnibs/brainnet@v0.2" \
  "git+https://github.com/simnibs/brainsynth@v0.1" \
  "https://github.com/simnibs/cortech/releases/download/v0.1/cortech-0.1-cp311-cp311-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl" \
  "https://github.com/simnibs/fmm3dpy/releases/download/v1.0.4/fmm3dpy-1.0.4-cp311-cp311-manylinux_2_28_x86_64.whl" \
  "https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-manylinux_2_28_x86_64.whl" \
  "https://github.com/oulap/samseg_wheels/releases/download/dev/samseg-0.5a0-cp311-cp311-manylinux_2_28_x86_64.whl"

# Step 2: python-mumps (via conda)
conda install -c conda-forge python-mumps -y

# Step 3: SimNIBS itself
pip install https://github.com/simnibs/simnibs/releases/download/v4.6.0/simnibs-4.6.0-cp311-cp311-linux_x86_64.whl

# Verify
python -c "import simnibs; print(simnibs.__version__)"  # → 4.6.0
```

### 3c. ANTs / templateflow / pynput

```bash
pip install antspyx templateflow pynput

# Verify
python -c "import ants; print(ants.__version__)"     # → 0.6.x
python -c "import templateflow; print('ok')"
# pynput will error in headless environments — this is expected (use USE_PYNPUT=False on HPC)
```

### 3d. BabelViscoFDTD (FDTD solver)

```bash
pip install BabelViscoFDTD

# Verify
python -c "import BabelViscoFDTD; print('ok')"
```

### 3e. pycork (CSG library)

pycork's pybind11 is incompatible with Python 3.11; manually upgrade pybind11 and build from source.

```bash
# Install Eigen3 (required to build pycork)
conda install -c conda-forge eigen=3.4.0 -y

# Clone pycork and upgrade pybind11
cd ~
git clone https://github.com/drlukeparry/pycork.git
cd pycork
git checkout d9efcd1da212c685345f65503ba253373dcdece0
git submodule update --init --recursive
cd external/pybind11
git fetch
git checkout v2.11.0
cd ../..
pip install .

# Verify
python -c "import pycork; print('ok')"
```

### 3f. BabelBrain

```bash
cd ~
git clone https://github.com/ProteusMRIgHIFU/BabelBrain.git

# Add to PYTHONPATH (persist in ~/.bashrc)
echo "export BABELBRAIN_DIR=~/BabelBrain" >> ~/.bashrc
echo "export PYTHONPATH=~/BabelBrain:\$PYTHONPATH" >> ~/.bashrc
source ~/.bashrc

# Verify
python -c "import BabelBrain; print('ok')"
```

### 3g. CuPy (CUDA backend)

```bash
module load cuda/12.9.0-cinr
pip install cupy-cuda12x

# Verify GPU (run on a GPU node)
interact -n 4 -m 16g -t 00:30:00 -q gpu -g 1
module load cuda/12.9.0-cinr
conda activate mri
python -c "import cupy; cupy.cuda.Device(0).use(); print('GPU ok')"
```

### 3h. Additional libraries for batch processing

```bash
pip install itables openpyxl
```

---

## 4. Notes

| Item | Notes |
|---|---|
| `pynput` | Import error in headless environments is expected. Use `USE_PYNPUT=False` to suppress. |
| `metalcomputebabel` | macOS Metal only. Not needed and cannot be installed on Linux. |
| GPU usage | Always run within `interact -q gpu -g 1` or a Slurm job. |
| CUDA module | `module load cuda/12.9.0-cinr` required every session. |
| `~/.bashrc` additions | `BABELBRAIN_DIR` and `PYTHONPATH` are set once on first setup. |

---

## 5. Setup verification script

Run the following to confirm all packages are installed correctly:

```bash
python -c "
import simnibs; print(f'simnibs: {simnibs.__version__}')
import ants; print(f'ants: {ants.__version__}')
import templateflow; print('templateflow: ok')
import BabelViscoFDTD; print('BabelViscoFDTD: ok')
import BabelBrain; print('BabelBrain: ok')
import pycork; print('pycork: ok')
import cupy; print(f'cupy: {cupy.__version__}')
import nibabel; print(f'nibabel: {nibabel.__version__}')
import nilearn; print(f'nilearn: {nilearn.__version__}')
"
```

---

## 6. Pipeline repository setup

TUS pipeline code (notebooks, `src/`, `config/`, `masks_standard/`, etc.) is managed in a git repository. Clone it on Oscar so that the same relative path structure as local can be used.

```bash
# Clone into home directory (replace with actual repo URL)
cd ~
git clone https://github.com/AKikumoto/<repo_name>.git scripts/TUS

# Verify
ls ~/scripts/TUS/
# → config/  masks_standard/  run/  src/  ...
```

**Data is managed separately:**
Code (repository) and data (subject T1w, `m2m_*/`, etc.) are kept separate.

```
~/scripts/TUS/                          ← git-managed (code, config, masks)
  config/sites/
    site_Brown_Oscar_AK.yaml
  masks_standard/                       ← generate locally and push
  run/                                  ← notebooks
  src/

/oscar/data/dbadre/akikumot/TUS/        ← data only (not git-managed)
  sub-NS/
    T1.nii.gz
    m2m_sub-NS/
    ...
```

`data_root` in `site_Brown_Oscar_AK.yaml` points to the data directory; masks are referenced from code via relative paths such as `../masks_standard/`.

---

## 7. Updating BabelBrain

```bash
cd ~/BabelBrain
git pull
```

---

## Related links

- [Oscar documentation](https://docs.ccv.brown.edu/oscar)
- [BabelBrain GitHub](https://github.com/ProteusMRIgHIFU/BabelBrain)
- [SimNIBS installation](https://simnibs.github.io/simnibs/build/html/installation/conda.html)
- [BabelBrain OfflineBatchExamples](https://github.com/ProteusMRIgHIFU/BabelBrain/tree/main/OfflineBatchExamples)
