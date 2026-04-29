import pandas as pd
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import glob
import argparse

# ==========================================
# CONFIGURATION VARIABLES
# ==========================================

parser = argparse.ArgumentParser(description="General plots comparing Speedup to various attributes")
parser.add_argument('--csv-dir', required=True, help="Directory to read in the CSV files from.")
parser.add_argument('--plot-dir', required=True, help="Directory to save the resulting plots (png files).")
parser.add_argument('--systems', required=True, help="Comma-separated list of systems to look for data from.")
parser.add_argument('--matrix-filter', help="Comma-separated list of matrices to show.")
args = parser.parse_args()

FIGURE_DIR = args.plot_dir
CLI_SYSTEMS = args.systems.split(",")

# Experiment configurations
BASELINE_BACKEND = 'Cray MPICH'
OTHER_BACKENDS = ["RCCL", "Stream-Triggered"]

# Visual customizations
BACKEND_COLORS = {
    "Stream-Triggered": "tab:blue",
    "RCCL": "tab:red"
}

MATRIX_MARKERS = {
    'audikw_1' : 'o',
     'Bump_2911' : 'v',
      'Cube_Coup_dt0' : '^',
       'Flan_1565' : '<',
        'Queen_4147': '>',
        'Serena' : '8',
        'nd24k' : 's',
         'ldoor': 'p',
          'agg14m': 'P',
           'guenda11m' :'X'}


if args.matrix_filter and args.matrix_filter == 'all':
    MATRICES = []
elif args.matrix_filter:
    MATRICES = args.matrix_filter.split(",")
else:
    MATRICES = ['audikw_1', 'Queen_4147', 'Serena']
print("Using filter:", MATRICES)

# ==========================================
# Plot function
# ==========================================
def acg_plot(x_data, x_data_name, x_data_label, curr_system=""):
    # 4. Merge X and Y data
    plot_data = pd.merge(df_solver, x_data, on=['system', 'total_ranks', 'Matrix'], how='inner')

    # Filter for the plots
    plot_data = plot_data[plot_data['Backend'].isin(OTHER_BACKENDS)]
    if MATRICES:
        plot_data = plot_data[plot_data['Matrix'].isin(MATRICES)]
    plot_data = plot_data[plot_data['system'] == curr_system]

    plt.figure(figsize=(10, 6))

    ax = sns.lineplot(
        data=plot_data,
        x=x_data_name,
        y='Percent Speedup Improvement',
        hue='Backend',
        style='Matrix',
        palette=BACKEND_COLORS,
        markers=MATRIX_MARKERS,
        dashes=False,           
        errorbar=('ci', 95)     
    )

    plt.xscale('log', base=2)
    plt.grid()
    plt.axhline(0, color='black', linestyle='--', linewidth=1, alpha=0.5) 
    plt.xlabel(f'{x_data_label} [Log Scale]')
    plt.ylabel(f'Point Change in Speedup vs {BASELINE_BACKEND}')
    plt.title(f'Change in Parallel Efficiency vs {x_data_label} relative to {BASELINE_BACKEND}')

    plt.legend(title='Legend', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()

    if curr_system:
        curr_system=f'{curr_system}-'
    output_file=(f'{curr_system}speedup-{x_data_name}.png').replace(" ", "_")
    plt.savefig(os.path.join(FIGURE_DIR, output_file), dpi=300, bbox_inches='tight')
    print(f"Plot successfully generated and saved to {os.path.join(FIGURE_DIR, output_file)}")

# ==========================================
# DATA PROCESSING
# ==========================================

# 1. Read CSVs
MPI_CSV    = os.path.join(args.csv_dir, '*/mpi_stats.csv')
SOLVER_CSV = os.path.join(args.csv_dir, '*/solver_times.csv')
all_files = glob.glob(SOLVER_CSV)
df_solver = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)
all_files = glob.glob(MPI_CSV)
df_mpi = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Clean up some of the fields:
df_solver = df_solver.rename(columns={'backend':'Backend', 'matrix':"Matrix"})
df_mpi = df_mpi.rename(columns={'matrix':"Matrix"})

# Fix the names of the backends to be more readable
df_solver['Backend'] = df_solver['Backend'].replace({"st":"Stream-Triggered",
                                                     "rccl": "RCCL",
                                                     "mpi":"Cray MPICH"})

# Calculate total ranks
df_solver['total_ranks'] = df_solver['nodes'] * df_solver['ppn']
df_mpi['total_ranks'] = df_mpi['nodes'] * df_mpi['ppn']

# 2. Process MPI Stats for X-axis (Average Message Size)
if MATRICES:
    df_mpi = df_mpi[df_mpi['Matrix'].isin(MATRICES)]
df_mpi['rank_avg_msg_size'] = df_mpi['bytes sent per iteration'] / df_mpi['messages sent per iteration'].replace(0, np.nan)

# For Plot 1
x_data_avg_msg_size = df_mpi.groupby(['system', 'total_ranks', 'Matrix'])['rank_avg_msg_size'].mean().reset_index()
x_data_avg_msg_size.rename(columns={'rank_avg_msg_size': 'avg_msg_size'}, inplace=True)

# For Plot 2
# Filter out 1 rank runs, as those don't send anything
x_data_tbs = df_mpi[df_mpi['total_ranks'] > 1]
x_data_tbs = x_data_tbs.groupby(['system', 'total_ranks', 'Matrix', 'rank'])['bytes sent per iteration'].mean().reset_index()
x_data_tbs = x_data_tbs.groupby(['system', 'total_ranks', 'Matrix'])['bytes sent per iteration'].mean().reset_index()

# For Plot 3
# Filter out 1 rank runs, as those don't send anything
x_data_msg_count = df_mpi[df_mpi['total_ranks'] > 1]
x_data_msg_count = x_data_msg_count.groupby(['system', 'total_ranks', 'Matrix', 'rank'])['messages sent per iteration'].mean().reset_index()
x_data_msg_count = x_data_msg_count.groupby(['system', 'total_ranks', 'Matrix'])['messages sent per iteration'].mean().reset_index()

# 3. Process Solver Times for Y-axis (User's Parallel Efficiency/Speedup)
# Create the pivot_df as requested to find the 'min' runtime
pivot_df = df_solver.groupby(['system', 'Matrix', 'total_ranks', 'Backend'])['solver_time'].agg(['min', 'mean']).reset_index()
pivot_df.set_index(['system', 'Matrix', 'total_ranks', 'Backend'], inplace=True)

# Isolate baseline data to find the minimum ranks per problem
df_base = df_solver[df_solver['Backend'] == BASELINE_BACKEND]

def speedup_func(row):
    system = row['system']
    matrix = row['Matrix']
    
    # Dynamically find the smallest number of ranks for this system/matrix from the baseline
    mask = (df_base['system'] == system) & (df_base['Matrix'] == matrix)
    if not mask.any():
        return np.nan
        
    speedup_base = df_base[mask]['total_ranks'].min()

    try:
        base_rt = pivot_df.loc[(system, matrix, speedup_base, BASELINE_BACKEND), 'min']
        return (speedup_base * base_rt) / row['solver_time']
    except KeyError:
        return np.nan

def relative_speedup_func(row):
    base_speedup = speedup_df.loc[(row['system'], row['Matrix'], row['nodes'], row['total_ranks'], BASELINE_BACKEND), 'mean']
    return 100 * (row['speedup'] - base_speedup) / base_speedup

# Apply your speedup function
df_solver['speedup'] = df_solver.apply(speedup_func, axis=1)

speedup_df = pd.pivot_table(df_solver,
                     index = ['system', 'Matrix', 'nodes', 'total_ranks', 'Backend'],
                     values = ['speedup'],
                     aggfunc = ["min", "mean", "std", "max"])
speedup_df.columns = speedup_df.columns.droplevel(1)
df_solver['Percent Speedup Improvement'] = df_solver.apply(relative_speedup_func, axis=1)

# ==========================================
# PLOTTING
# ==========================================
for curr_system in CLI_SYSTEMS:
    acg_plot(x_data_avg_msg_size, 'avg_msg_size', "Average Message Size (Bytes)", curr_system)
    acg_plot(x_data_tbs, 'bytes sent per iteration', "Bytes Sent per Iteration (averaged across all ranks) (Bytes)", curr_system)
    acg_plot(x_data_msg_count, 'messages sent per iteration', "Messages Sent Per Iteration (averaged across all ranks)", curr_system)

    all_data = pd.merge(df_solver, x_data_avg_msg_size, on=['total_ranks', 'Matrix'], how='inner')
    all_data = pd.merge(all_data, x_data_msg_count, on=['total_ranks', 'Matrix'], how='inner')

    # Filter for the plots
    all_data = all_data[all_data['Backend'].isin(OTHER_BACKENDS)]
    if MATRICES:
        all_data = all_data[all_data['Matrix'].isin(MATRICES)]
    all_data = all_data[all_data['system'] == curr_system]

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(projection='3d')

    grouped = all_data.groupby(['Matrix', 'Backend'])
    for value, group_df in grouped:
        matrix, backend = value
        sc = ax.scatter(
            xs=group_df['avg_msg_size'],
            zs=group_df['messages sent per iteration'],
            ys=group_df['Percent Speedup Improvement'],
            marker=MATRIX_MARKERS[matrix],
            color=BACKEND_COLORS[backend],
            label=f"Matrix: {matrix}, Backend: {backend}"
        )

    backendLegend = []
    for x, y in BACKEND_COLORS.items():
        legend_patch = mlines.Line2D([], [], color=y, marker='_', linestyle='None',
                            markersize=10, label=f'{x}')
        backendLegend.append(legend_patch)
    matrixLegend = []
    for x, y in MATRIX_MARKERS.items():
        legend_patch = mlines.Line2D([], [], color='black', marker=y, linestyle='None',
                            markersize=8, label=f'{x}')
        matrixLegend.append(legend_patch)

    ax.set_xlabel('avg_msg_size')
    ax.set_zlabel('messages sent per iteration')
    ax.set_ylabel('Percent Speedup Improvement')
    first_legend = ax.legend(handles=backendLegend, loc='upper left', title="Backend")
    ax.add_artist(first_legend) # This keeps the first legend from being deleted

    # 5. Add the second legend (Colors)
    ax.legend(handles=matrixLegend, loc='upper right', title="Matrix")
    plt.savefig(os.path.join(FIGURE_DIR, f"{curr_system}-test.png"), dpi=300, bbox_inches='tight')


    # plt.xscale('log', base=2)
    # plt.grid()
    # plt.axhline(0, color='black', linestyle='--', linewidth=1, alpha=0.5) 
    # plt.xlabel(f'{x_data_label} [Log Scale]')
    # plt.ylabel(f'Point Change in Speedup vs {BASELINE_BACKEND}')
    # plt.title(f'Change in Parallel Efficiency vs {x_data_label} relative to {BASELINE_BACKEND}')

    # plt.legend(title='Legend', bbox_to_anchor=(1.05, 1), loc='upper left')
    # plt.tight_layout()

    # output_file=(f'speedup-{x_data_name}.png').replace(" ", "_")

    # print(f"Plot successfully generated and saved to {os.path.join(FIGURE_DIR, output_file)}")
