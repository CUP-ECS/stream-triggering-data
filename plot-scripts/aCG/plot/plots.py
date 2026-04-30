import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import glob
import argparse

# ==========================================
# CONFIGURATION VARIABLES
# ==========================================

parser = argparse.ArgumentParser(
    description="General plots comparing Speedup to various attributes"
)
parser.add_argument(
    "--csv-dir", required=True, help="Directory to read in the CSV files from."
)
parser.add_argument(
    "--plot-dir",
    required=True,
    help="Directory to save the resulting plots (png files).",
)
parser.add_argument(
    "--systems",
    required=True,
    help="Comma-separated list of systems to look for data from.",
)
parser.add_argument("--matrix-filter", help="Comma-separated list of matrices to show.")
args = parser.parse_args()

FIGURE_DIR = args.plot_dir
CLI_SYSTEMS = args.systems.split(",")

# Experiment configurations
BASELINE_BACKEND = "Cray MPICH"
OTHER_BACKENDS = ["RCCL", "Stream-Triggered"]

# Visual customizations
BACKEND_COLORS = {"Stream-Triggered": "tab:blue", "RCCL": "tab:red"}

MATRIX_MARKERS = {
    "audikw_1": "o",
    "Bump_2911": "v",
    "Cube_Coup_dt0": "^",
    "Flan_1565": "<",
    "Queen_4147": ">",
    "Serena": "8",
    "nd24k": "s",
    "ldoor": "p",
    "agg14m": "P",
    "guenda11m": "X",
}


if args.matrix_filter and args.matrix_filter == "all":
    MATRICES = []
elif args.matrix_filter:
    MATRICES = args.matrix_filter.split(",")
else:
    MATRICES = ["audikw_1", "Queen_4147", "Serena"]
print("Using filter:", MATRICES)


# ==========================================
# Helper filter to prepare data for plots
# ==========================================
def plot_data_prep(x_data, curr_system):
    # Merge X and Y data
    plot_data = pd.merge(
        df_solver, x_data, on=["system", "total_ranks", "Matrix"], how="inner"
    )
    # Filter for the plots
    plot_data = plot_data[plot_data["Backend"].isin(OTHER_BACKENDS)]
    plot_data = plot_data[plot_data["system"] == curr_system]

    return plot_data


# ==========================================
# Helper filter to save the plots
# ==========================================
def save_to_file(file_name_base, curr_system=""):
    plt.tight_layout()

    if curr_system:
        curr_system = f"{curr_system}-"
    output_file = (f"{curr_system}speedup-{file_name_base}.png").replace(" ", "_")
    plt.savefig(os.path.join(FIGURE_DIR, output_file), dpi=300, bbox_inches="tight")
    print(
        f"Plot successfully generated and saved to {os.path.join(FIGURE_DIR, output_file)}"
    )


# ==========================================
# Plot function
# ==========================================
def acg_plot(x_data, x_data_name, x_data_label, curr_system):

    plot_data = plot_data_prep(x_data, curr_system)

    plt.figure(figsize=(10, 6))

    ax = sns.lineplot(
        data=plot_data,
        x=x_data_name,
        y="Percent Speedup Improvement",
        hue="Backend",
        style="Matrix",
        palette=BACKEND_COLORS,
        markers=MATRIX_MARKERS,
        dashes=False,
        errorbar=("ci", 95),
    )

    plt.xscale("log", base=2)
    plt.grid()
    plt.axhline(0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    plt.xlabel(f"{x_data_label} [Log Scale]")
    plt.ylabel(f"Percent Change in Speedup vs {BASELINE_BACKEND}")

    plt.legend(title="Legend", bbox_to_anchor=(1.05, 1), loc="upper left")
    save_to_file(x_data_name, curr_system)


# ==========================================
# Side-by-side plots
# ==========================================
def acg_msg_size_comm_partner(
    x_data, x_data_name, x_data_label, x2_data, x2_data_name, x2_data_label, curr_system
):
    plot_data = plot_data_prep(x_data, curr_system)
    plot_data2 = plot_data_prep(x2_data, curr_system)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)

    sns.lineplot(
        data=plot_data,
        x=x_data_name,
        y="Percent Speedup Improvement",
        hue="Backend",
        style="Matrix",
        palette=BACKEND_COLORS,
        markers=MATRIX_MARKERS,
        dashes=False,
        errorbar=("ci", 95),
        ax=axes[0],
        legend=False,
    )

    sns.lineplot(
        data=plot_data2,
        x=x2_data_name,
        y="Percent Speedup Improvement",
        hue="Backend",
        style="Matrix",
        palette=BACKEND_COLORS,
        markers=MATRIX_MARKERS,
        dashes=False,
        errorbar=("ci", 95),
        ax=axes[1],
    )

    handles, labels = axes[1].get_legend_handles_labels()
    axes[1].get_legend().remove()

    axes[1].legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(1.05, 1.0),
        title="Legend",
    )

    for ax in axes:
        ax.set_xscale("log", base=2)
        ax.grid(True, linestyle="--", linewidth=1, alpha=0.5)
        ax.set_ylabel(f"Percent Change in Speedup vs {BASELINE_BACKEND}")

    axes[0].set_xlabel(x_data_label)
    axes[1].set_xlabel(x2_data_label)

    save_to_file(f"{x_data_name}-{x2_data_name}", curr_system)


# ==========================================
# DATA PROCESSING
# ==========================================

# 1. Read CSVs
MPI_CSV = os.path.join(args.csv_dir, "*/mpi_stats.csv")
SOLVER_CSV = os.path.join(args.csv_dir, "*/solver_times.csv")
all_files = glob.glob(SOLVER_CSV)
df_solver = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)
all_files = glob.glob(MPI_CSV)
df_mpi = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Clean up some of the fields:
df_solver = df_solver.rename(columns={"backend": "Backend", "matrix": "Matrix"})
df_mpi = df_mpi.rename(columns={"matrix": "Matrix"})

# Fix the names of the backends to be more readable
df_solver["Backend"] = df_solver["Backend"].replace(
    {"st": "Stream-Triggered", "rccl": "RCCL", "mpi": "Cray MPICH"}
)

# Calculate total ranks
df_solver["total_ranks"] = df_solver["nodes"] * df_solver["ppn"]
df_mpi["total_ranks"] = df_mpi["nodes"] * df_mpi["ppn"]

# Apply matrices filter
if MATRICES:
    df_mpi = df_mpi[df_mpi["Matrix"].isin(MATRICES)]
    df_solver = df_solver[df_solver["Matrix"].isin(MATRICES)]

# Process MPI Stats for X-axis (Average Message Size)
df_mpi["rank_avg_msg_size"] = df_mpi["bytes sent per iteration"] / df_mpi[
    "messages sent per iteration"
].replace(0, np.nan)

# For Plot 1
x_data_avg_msg_size = (
    df_mpi.groupby(["system", "total_ranks", "Matrix"])
    .agg(avg_msg_size=("rank_avg_msg_size", "mean"))
    .reset_index()
)


def get_value_avg_per_rank(column_name):
    return (
        # First, filter out 1 rank runs, as those don't send anything
        df_mpi[df_mpi["total_ranks"] > 1]
        # Then get average of all runs for a given rank
        .groupby(["system", "total_ranks", "Matrix", "rank"])[column_name]
        .mean()
        # Then do average across all ranks
        .groupby(level=["system", "total_ranks", "Matrix"])
        .mean()
        .reset_index()
    )


# For Plot 2
x_data_tbs = get_value_avg_per_rank("bytes sent per iteration")
# For Plot 3
x_data_msg_count = get_value_avg_per_rank("messages sent per iteration")


# Process Solver Times for Y-axis (User's Parallel Efficiency/Speedup)
# Create the pivot_df to find the 'min' runtime
pivot_df = (
    df_solver.groupby(["system", "Matrix", "total_ranks", "Backend"])["solver_time"]
    .agg(["min", "mean"])
    .reset_index()
    .set_index(["system", "Matrix", "total_ranks", "Backend"])
)

# Isolate baseline data to find the minimum ranks per problem
df_base = df_solver[df_solver["Backend"] == BASELINE_BACKEND]


def speedup_func(row):
    system = row["system"]
    matrix = row["Matrix"]

    # Dynamically find the smallest number of ranks for this system/matrix from the baseline
    mask = (df_base["system"] == system) & (df_base["Matrix"] == matrix)
    if not mask.any():
        return np.nan

    speedup_base = df_base[mask]["total_ranks"].min()

    try:
        base_rt = pivot_df.loc[(system, matrix, speedup_base, BASELINE_BACKEND), "min"]
        return (speedup_base * base_rt) / row["solver_time"]
    except KeyError:
        return np.nan


def relative_speedup_func(row):
    base_speedup = speedup_df.loc[
        (
            row["system"],
            row["Matrix"],
            row["nodes"],
            row["total_ranks"],
            BASELINE_BACKEND,
        ),
        "mean",
    ]
    return 100 * (row["speedup"] - base_speedup) / base_speedup


# Apply speedup function
df_solver["speedup"] = df_solver.apply(speedup_func, axis=1)

speedup_df = pd.pivot_table(
    df_solver,
    index=["system", "Matrix", "nodes", "total_ranks", "Backend"],
    values=["speedup"],
    aggfunc=["min", "mean", "std", "max"],
)
speedup_df.columns = speedup_df.columns.droplevel(1)
df_solver["Percent Speedup Improvement"] = df_solver.apply(
    relative_speedup_func, axis=1
)

# ==========================================
# PLOTTING
# ==========================================
for curr_system in CLI_SYSTEMS:
    acg_plot(
        x_data_avg_msg_size, "avg_msg_size", "Average Message Size (Bytes)", curr_system
    )
    acg_plot(
        x_data_tbs,
        "bytes sent per iteration",
        "Bytes Sent per Iteration (averaged across all ranks) (Bytes)",
        curr_system,
    )
    acg_plot(
        x_data_msg_count,
        "messages sent per iteration",
        "Messages Sent Per Iteration (averaged across all ranks)",
        curr_system,
    )
    acg_msg_size_comm_partner(
        x_data_avg_msg_size,
        "avg_msg_size",
        "Average Message Size (Bytes)",
        x_data_msg_count,
        "messages sent per iteration",
        "Messages Sent Per Iteration (averaged across all ranks)",
        curr_system,
    )
