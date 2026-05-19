import SimpleITK as sitk
import glob
import pathlib
import pandas as pd
import numpy as np
import os


'''
Select dataset parameters
'''

Pv_data=False
parcellation_nifti = 'final_atlas_N16_rabies_space_dta.nii.gz'

out_dir_name = 'Bf_DTA_awk'
rabies_out = '/media/DATA3/gdesrosiersgregoire/preproc/BF_Valeria_data/DTA_BasalForebrain/rabies_BF_DTA_awk_20260330'
CR_name = 'FD_cut30frames_bandpass0.01-0.1_cut30edges_mot24_CSF_smooth6'

out_dir_name = 'Bf_DTA_anes'
rabies_out = '/media/DATA3/gdesrosiersgregoire/preproc/BF_Valeria_data/DTA_BasalForebrain/rabies_BF_DTA_anes_20260330'
CR_name = 'FD_cut30frames_bandpass0.01-0.1_cut30edges_mot6_CSF_smooth6'


Pv_data=True
parcellation_nifti = 'final_atlas_N16_rabies_space_pv.nii.gz'

out_dir_name = 'Bf_PV_awk'
rabies_out = f'/media/DATA3/gdesrosiersgregoire/preproc/BF_Valeria_data/Bf_Pv_Gq/rabies_BF_PvGq_awk_20260326'
CR_name = 'FD_cut30frames_bandpass0.01-0.1_cut30edges_mot24_CSF_smooth6'

out_dir_name = 'Bf_PV_anes'
rabies_out = f'/media/DATA3/gdesrosiersgregoire/preproc/BF_Valeria_data/Bf_Pv_Gq/rabies_BF_PvGq_anes_20260327'
CR_name = 'FD_cut30frames_bandpass0.01-0.1_cut30edges_mot6_CSF_smooth6'

'''
Select dataset parameters
'''


cutoff = 22*60 # 22 minutes in seconds, time of CNO injection
cutoff -= 30 #first 30 frames were removed

TR = 1.0

brain_mask_file = f'{rabies_out}/bold_datasink/commonspace_mask/commonspace_template_brain_mask_resampled.nii.gz'
mask_img = sitk.ReadImage(brain_mask_file)
volume_idx = sitk.GetArrayFromImage(mask_img).astype(bool)

parcels_df = pd.read_csv('parcellation.csv')
labels_arr = sitk.GetArrayFromImage(sitk.ReadImage(parcellation_nifti))[volume_idx]
parcel_d = {}
for parcel_id,network in zip(parcels_df['label ID'].values,parcels_df['Network'].values):
    parcel_d[network] = labels_arr==parcel_id

def parcellate_timeseries(timeseries, parcel_d, frame_mask):
    parcellated_timeseries_d = {}
    for network in parcel_d:
        parcellated_timeseries_d[network] = np.array([np.nan]*len(frame_mask))
        parcellated_timeseries_d[network][frame_mask] = timeseries[:, parcel_d[network]].mean(axis=1)
    return parcellated_timeseries_d

def export_csv(parcellated_timeseries_d, out_filename):
    df = pd.DataFrame(parcellated_timeseries_d)
    cols = df.columns.tolist()
    df = df[[cols[-1]] + cols[:-1]]
    df.to_csv(out_filename, index=False)

CR_out_dir = f'{rabies_out}/{CR_name}'

out_dir = f'/media/DATA3/gdesrosiersgregoire/preproc/for_ludo/{out_dir_name}/{CR_name}/'
os.makedirs(out_dir, exist_ok=True)


timeseries_file_list = glob.glob(f'{CR_out_dir}/confound_correction_datasink/cleaned_timeseries/*/*cleaned.nii.gz')
timeseries_file_list.sort()
framemask_file_list = glob.glob(f'{CR_out_dir}/confound_correction_datasink/frame_censoring_mask/*/*.csv')
framemask_file_list.sort()
print(len(timeseries_file_list))

for f_img,f_csv in zip(timeseries_file_list, framemask_file_list):
    print(pathlib.Path(f_img).name, pathlib.Path(f_csv).name)
    frame_mask = pd.read_csv(f_csv)['False = Masked Frames']
    num_censored_baseline = (frame_mask[:cutoff]==False).sum()

    time = np.array(range(0,len(frame_mask)))*TR
    
    fname = pathlib.Path(f_img).name
    img = sitk.ReadImage(f_img)

    if not len(frame_mask)-(frame_mask==False).sum() == img.GetSize()[3]:
        raise

    if Pv_data:
        timeseries_baseline = sitk.GetArrayFromImage(img[:,:,:,:cutoff-num_censored_baseline])[:,volume_idx]
        timeseries_CNO = sitk.GetArrayFromImage(img[:,:,:,cutoff-num_censored_baseline:])[:,volume_idx]
        del img

        parcellated_timeseries_d_baseline = parcellate_timeseries(timeseries_baseline, parcel_d, frame_mask[:cutoff])
        parcellated_timeseries_d_baseline['Time (sec)'] = time[:cutoff]
        parcellated_timeseries_d_CNO = parcellate_timeseries(timeseries_CNO, parcel_d, frame_mask[cutoff:])
        parcellated_timeseries_d_CNO['Time (sec)'] = time[cutoff:]

        out_filename = out_dir + fname.replace('cleaned.nii.gz', 'baseline_parcellated.csv')
        export_csv(parcellated_timeseries_d_baseline, out_filename)

        out_filename = out_dir + fname.replace('cleaned.nii.gz', 'CNO_parcellated.csv')
        export_csv(parcellated_timeseries_d_CNO, out_filename)

    else:
        parcellated_timeseries_d = parcellate_timeseries(sitk.GetArrayFromImage(img)[:,volume_idx], parcel_d, frame_mask)
        parcellated_timeseries_d['Time (sec)'] = time

        out_filename = out_dir + fname.replace('cleaned.nii.gz', 'parcellated.csv')
        export_csv(parcellated_timeseries_d, out_filename)

            