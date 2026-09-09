- Segmentation

  - Segmentation of either 3T or 7T MRI data into different brain tissues. In this step I used SPM, a Matlab based medical data processing library.

    https://www.fil.ion.ucl.ac.uk/spm/software/spm12/

    this tool worked pretty well for our data, we segmented data into scalp, skull, CSF, white matter and  gray matter. *But I am not sure whether this tool works for the brain stem region*.

- Create a brain mat for Matlab
  - After the segmentation I allocated a specific value to each brain component (e.g. 1 for scalp, 2 for skull, etc.) and create a .mat file contains all the components together. This process was done using python3. See `TUS_processing.ipynb` for detail.
  - The purpose of this step is that we want to determine the physical properties for different tissues in the simulation to improve the accuracy of the calculation. For LC, you might need to refer some previous study to decide the parameters.
- Simulation
  - Intensity simulation
  - Thermal simulation