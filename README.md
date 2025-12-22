# stream-triggering-data
A repository for holding scripts and data used in the various runs of our stream-triggering paper experiments.

Each major version of this repository represents a specific paper submission. 

The repository is laid out as follows:
- `build-scripts` - A bash script for building on LLNL's Tioga, LLNL's Tuolumne, and ORNL's Frontier. See script for more details on how it works.
- `data` - Contains all of the data used to generate the data in the paper. Any `old` folders contain some of the older data preserved from runs before the LLNL DAT on Tuo.
- `plot-scripts` - The scripts used to generate the plots, along with a `python-requirements.txt` to describe the modules needed for the scripts. The scripts will create PNG files, and generally assume the location of the CSV files as they are currently laid out.
- `run-scripts` - The scripts used to run CabanaGhost and collect data. The main scripts, `XXXX-all-queue.sh` should be used to start any runs, with `XXXX = flux` on LLNL, and `XXXX = slurm` on ORNL. **NOTE:** These scripts **will** override any previous runs that have not been turned into a CSV file, so take care! Additionally, an `output` directory will be created to store the data, though it may need to be created manually first for the runs to produce output files. The `out-to-csv.py` can be used after runs have been completed to take the output and create a CSV file. This script will **not** overwrite previous CSV files. Finally, a second set of run scripts are in the `Archive` directory, which are preserved since they were used to get the original set of run data.


These scripts and files are specific to LLNL's (or ORNL's) cluster, and will need some tweaks when ported to a different system. The main build and run scripts should be portable from user to user (assuming they have the correct permissions on the git repos), but one should double check before doing real runs.
