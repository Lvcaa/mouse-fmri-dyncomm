In the subfolders are stored the parcellated timeseries for each subject in a CSV format, 
containing the following columns: Time (sec),DMNa,DMNp,SAL,OLF,STR,AUD,VIS,TH,MOp,SSp,SSs,HCa,SUB,CTXsp,BF,HY.
Empty entries in the parcels columns are timeframes that were censored. 

* Bf_PV_awk: The BF neuromodulation of PV neurons through DREADDs, in awake mice. Here, each scan was 
    already subdivided into two separate CSV, one for baseline (<22min) and one for the CNO period
    post-injection (>22min)
* Bf_PV_anes: Same as Bf_PV_awk, but for anesthetized mice.
* Bf_DTA_awk: Dataset with BF lesion through DTA, scanning in awake mice.
* Bf_DTA_anes: Dataset with BF lesion through DTA, scanning in anesthetized mice.

For all datasets, scans with EXP in the file name correspond to the experimental group, and vice versa for SHAM.
All datasets were preprocessed through framewise displacement censoring, bandpass filter at 0.01-0.1Hz, smoothing at 0.6mm,
nuisance regression of CSF + motion parameters (6 parameters for anesthetized and 24 for awake data).
The first 30 seconds of data was removed before preprocessing to remove saturated volumes.

Other files:
* extract_parcellated_timeseries.py  : script for extracting parcellated timeseries
* final_atlas_N16_rabies_space_dta.nii.gz  : parcellation resampled onto the DTA data
* final_atlas_N16_rabies_space_pv.nii.gz  : parcellation resampled onto the PV data  
* parcellation.csv : info about the parcellation, including the original set of Allen parcels that compose each regions of
    the final parcellation.
