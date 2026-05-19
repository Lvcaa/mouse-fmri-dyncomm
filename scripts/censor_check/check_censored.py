''' Script used to check how many frames were censored for each subject and session.
    It takes as input the parcellated BOLD csv files and counts NaN rows (censored frames).
    It prints the number of frames censored and the percentage of frames censored.
'''

import pandas as pd
import os
from glob import glob

data_folder = '/home/lucagalli/Projects/Progetto_Gozzi/for_ludo'


def process_subject(csv_path):

    # Read the csv file
    df = pd.read_csv(csv_path, index_col=0)

    # Count the total number of frames
    total = len(df)

    # Count the number of censored frames
    censored = df.isnull().all(axis=1).sum()

    # Calculate the percentage of censored frames
    pct = 100 * censored / total if total > 0 else 0
    return total, censored, pct


def retrieve_subject_list_scans(data_folder):
    """ Group each subject's scans (runs a/b/c/d) by folder and subject ID """
    subject_list_scans = {}

    # Iterate over each folder in the data directory
    for folder_path in sorted(glob(os.path.join(data_folder, '*', '*'))):
        if not os.path.isdir(folder_path):
            continue

        csv_files = glob(os.path.join(folder_path, '*.csv'))
        if not csv_files:
            continue

        folder_name = os.path.relpath(folder_path, data_folder).split(os.sep)[0]
        subject_list_scans[folder_name] = {}

        for csv_path in csv_files:
            basename = os.path.basename(csv_path)
            # e.g. sub-ag230911a_SHAM_bold_parcellated.csv → subject ID = "230911"
            subject_id = basename[6:12]

            # Add the csv path to the subject's list of scans
            subject_list_scans[folder_name].setdefault(subject_id, []).append(csv_path)

        # Sort the list of scans for each subject
        for subject_id in subject_list_scans[folder_name]:
            subject_list_scans[folder_name][subject_id].sort()

    return subject_list_scans


if __name__ == '__main__':
    subject_list_scans = retrieve_subject_list_scans(data_folder)

    log_path = os.path.join(os.path.dirname(__file__), 'censored_frames.txt')
    report_path = os.path.join(os.path.dirname(__file__), 'censoring_report.txt')
    folder_censoring = {}

    # Write the results to a log file
    with open(log_path, 'w') as log:
        for folder_name, folder_subjects in sorted(subject_list_scans.items()):
            log.write(f'Folder {folder_name}:\n\n')
            folder_censoring[folder_name] = []

            for subject_id, csv_paths in sorted(folder_subjects.items()):
                log.write(f'Subject {subject_id}:\n')

                # Iterate over the subject's scans and process each one
                for csv_path in csv_paths:
                    run_name = os.path.basename(csv_path).replace('_bold_parcellated.csv', '')
                    total, censored, pct = process_subject(csv_path)
                    folder_censoring[folder_name].append((pct, run_name))
                    line = f'  {run_name}: {censored}/{total} frames censored ({pct:.1f}%)'
                    print(line)
                    log.write(line + '\n')

                log.write('\n')

            log.write('\n')

    # Write a folder-level report of censoring percentages
    with open(report_path, 'w') as report:
        for folder_name, censoring_values in sorted(folder_censoring.items()):
            if not censoring_values:
                continue

            percentages = [pct for pct, _ in censoring_values]
            min_pct, min_run = min(censoring_values)
            max_pct, max_run = max(censoring_values)
            avg_pct = sum(percentages) / len(percentages)

            report.write(f'Folder {folder_name}:\n')
            report.write(f'  Min censoring: {min_pct:.1f}% ({min_run})\n')
            report.write(f'  Max censoring: {max_pct:.1f}% ({max_run})\n')
            report.write(f'  Average censoring: {avg_pct:.1f}%\n\n')
