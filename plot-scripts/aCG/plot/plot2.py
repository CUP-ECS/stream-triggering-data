#!/usr/bin/env python
# coding: utf-8

import argparse
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

parser = argparse.ArgumentParser(
    description="Create plots comparing MPI, ST, and RCCL backends in aCG"
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
parser.add_argument(
    "--baseline-backend", help="Choose the baseline backend to compare against."
)
args = parser.parse_args()

# Pandas printing options:
pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.width", 100)

FIGURE_DIR = args.plot_dir
CLI_SYSTEMS = args.systems.split(",")

palette = {
    "Cray MPICH": "tab:green",
    "Stream-Triggered": "tab:blue",
    "RCCL": "tab:red",
    "Cray MPICH 2": "tab:purple",
    "audikw_1": "tab:blue",
    "Bump_2911": "tab:green",
    "Cube_Coup_dt0": "tab:orange",
    "Flan_1565": "tab:red",
    "Queen_4147": "tab:purple",
    "Serena": "tab:gray",
    "nd24k": "tab:cyan",
    "ldoor": "tab:olive",
    "agg14m": "tab:blue",
    "guenda11m": "tab:green",
}

system_order = ["Frontier", "Tuolumne"]
full_backend_order = ["Cray MPICH", "Cray MPICH 2", "Stream-Triggered", "RCCL"]

if args.baseline_backend:
    BASELINE_BACKEND = args.baseline_backend
else:
    BASELINE_BACKEND = "Cray MPICH"

if args.matrix_filter and args.matrix_filter == "all":
    matrix_filter = []
    matrix_order = [
        "audikw_1",
        "Bump_2911",
        "Cube_Coup_dt0",
        "Flan_1565",
        "Queen_4147",
        "Serena",
        "nd24k",
        "ldoor",
        "agg14m",
        "guenda11m",
    ]
elif args.matrix_filter:
    matrix_filter = args.matrix_filter.split(",")
    matrix_order = args.matrix_filter.split(",")
else:
    matrix_filter = ["audikw_1", "Queen_4147", "Serena"]
    matrix_order = ["audikw_1", "Queen_4147", "Serena"]
print("Using filter:", matrix_filter)


def setup_kargs_and_title(k, breakdown, hue, style):
    k["height"] = 3.5
    k["aspect"] = 1.25
    if hue != "":
        k["hue"] = hue
        k["palette"] = palette
    if style != "":
        k["style"] = style

    if breakdown == "System":
        k["col_order"] = system_order
        k["col"] = "System"
        title = "{col_name}"
    elif breakdown != "":
        title = "{row_name}" + " {col_name} " + breakdown
        k["row"] = "System"
        k["col"] = breakdown
    else:
        title = ""

    if hue == "Backend":
        k["hue_order"] = full_backend_order
    elif hue == "Matrix":
        k["hue_order"] = matrix_filter

    return title


def make_runtime_plot(
    data, x, yscale, breakdown, style="Problem Size (GB)", hue="Backend", extra=""
):
    kargs = {}
    title = setup_kargs_and_title(kargs, breakdown, hue, style)

    runtime_plot = sbn.relplot(
        data=data,
        kind="line",
        x=x,
        y="Solve Time",
        errorbar=("ci", 95),
        markers=True,
        **kargs,
    )
    runtime_plot.set_titles(title)
    for ax in runtime_plot.axes.ravel():
        ax.grid(True, axis="both", ls=":")
    plt.xscale("log", base=2)
    if yscale == "log":
        plt.yscale("log", base=10)
    filepath = os.path.join(FIGURE_DIR, f"Runtime-{x}-{breakdown}-{yscale}{extra}.png")
    plt.savefig(filepath)
    plt.close()


def get_max_speedup(data):
    # Get averages first
    avg_df = (
        data.groupby(["System", "Matrix", "GPUs per Node", "Ranks", "Backend"])["Speedup"]
        .agg(['mean', 'std'])
        .reset_index()
    )

    result_indices = avg_df.groupby(["Backend", "Matrix"])["mean"].idxmax()
    final_df = avg_df.loc[result_indices]
    print(final_df)


def get_1_node_runs(data):
    # Get averages first
    avg_df = (
        data.groupby(["System", "Matrix", "Ranks", "Backend"])["Solve Time"]
        .agg(['mean', 'std'])
        .reset_index()
    )

    final_df = avg_df[avg_df["Ranks"] == 1]
    print(final_df)


def make_speedup_plot(
    data,
    x,
    yscale,
    breakdown="",
    style="Matrix",
    hue="Backend",
    extra="",
    print_data=False,
):
    kargs = {}

    title = setup_kargs_and_title(kargs, breakdown, hue, style)

    if print_data:
        pd.set_option("display.width", 200)
        print(data)

    speedup_plot = sbn.relplot(
        data=data,
        kind="line",
        x=x,
        y="Speedup",
        errorbar=("ci", 95),
        markers=True,
        **kargs,
    )
    speedup_plot.set_titles(title)
    for ax in speedup_plot.axes.ravel():
        ax.grid(True, axis="both", ls=":")
        if yscale == "log":
            ax.axline((0, 0), slope=1, color="k", ls="--")
    plt.xscale("log", base=2)
    if yscale == "log":
        plt.yscale("log", base=2)
    filepath = os.path.join(FIGURE_DIR, f"Speedup-{x}-{breakdown}-{yscale}{extra}.png")
    plt.savefig(filepath)
    plt.close()


def make_percent_plot(
    data, x, breakdown="", y="Speedup", style="Backend", invertx=False, extra=""
):
    ### Relative improvement in speedup by Problem Size
    kargs = {}

    mpiadvancedata = data[data["Backend"].isin(["Stream-Triggered", "RCCL"])]

    title = setup_kargs_and_title(kargs, breakdown, "Matrix", style)

    percent_plot = sbn.relplot(
        data=mpiadvancedata,
        kind="line",
        x=x,
        y=f"Percent {y} Improvement",
        errorbar=("ci", 95),
        markers=True,
        **kargs,
    )
    percent_plot.set_titles(title)
    plt.xscale("log", base=2)
    for ax in percent_plot.axes.ravel():
        ax.grid(True, axis="both", ls=":")
        if invertx:
            ax.invert_xaxis()

    filepath = os.path.join(
        FIGURE_DIR, f"Percent-{y}-{x}-{breakdown}-linear{extra}.png"
    )
    plt.savefig(filepath)
    plt.close()


# Read the raw data into a Pandas Data Frame
all_files = [
    file
    for d in CLI_SYSTEMS
    for file in glob.glob(os.path.join(args.csv_dir, d.upper(), "solver_times*.csv"))
]
df = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Fix the labels of the columns to be more readable
df = df.rename(
    columns={
        "nodes": "Nodes",
        "ppn": "GPUs per Node",
        "solver_time": "Solve Time",
        "system": "System",
        "backend": "Backend",
        "date": "Date",
        "matrix": "Matrix",
    }
)

# Filter out irrelevant matrices
if matrix_filter:
    df = df[df["Matrix"].isin(matrix_filter)]

# Fix the names of the backends to be more readable
df["Backend"] = df["Backend"].replace(
    {
        "st": "Stream-Triggered",
        "rccl": "RCCL",
        "mpi": "Cray MPICH",
        "mpi-no-ipc": "Cray MPICH 2",
    }
)

# Compute derived values to use to generate data to plot from measured terms
## The total number of MPI ranks used in a sample
df["Ranks"] = df["Nodes"] * df["GPUs per Node"]
df = df.sort_values(["Ranks", "Nodes"])

## Compute speedup and parallel efficiency
### Aggregate the minimum, mean, and variance of the solver time using
### a pivot table to calculate a base value to use for calculating speedup
### calculations using a pivot table
pivot_df = pd.pivot_table(
    df,
    index=["System", "Matrix", "Ranks", "Backend"],
    values=["Solve Time"],
    aggfunc=["min", "mean", "std"],
)
pivot_df.columns = pivot_df.columns.droplevel(1)

### Now compute the speedup, parallel efficiency with the baseline as the best runtime
### from an execution on the smallest number of ranks in the data set for a given problem
### from the original Cray backend
speedup_base = 1


def speedup_func(row):
    base_rt = pivot_df.loc[
        row["System"], row["Matrix"], speedup_base, BASELINE_BACKEND
    ]["min"]
    return speedup_base * base_rt / row["Solve Time"]


df["Speedup"] = df.apply(speedup_func, axis=1)

# Now summarize/compute averages by node/rank combination
speedup_df = pd.pivot_table(
    df,
    index=["System", "Matrix", "Nodes", "Ranks", "Backend"],
    values=["Speedup"],
    aggfunc=["min", "mean", "std", "max"],
)
speedup_df.columns = speedup_df.columns.droplevel(1)


# # Calculate speedup and efficiency on a node/rank basis compared to the
# # identical node/rank configuration.
def relative_speedup_func(row):
    base_speedup = speedup_df.loc[
        row["System"], row["Matrix"], row["Nodes"], row["Ranks"], BASELINE_BACKEND
    ]["mean"]
    return 100 * (row["Speedup"] - base_speedup) / base_speedup


df["Percent Speedup Improvement"] = df.apply(relative_speedup_func, axis=1)

speedupdata = df[
    df["Backend"].isin(["Stream-Triggered", "RCCL", "Cray MPICH", "Cray MPICH 2"])
]

for graph_system in CLI_SYSTEMS:
    graph_system = graph_system.capitalize()
    system_data = speedupdata[speedupdata["System"].isin([graph_system])]
    system_name = f"-{graph_system}"

    make_speedup_plot(
        data=system_data,
        x="Ranks",
        yscale="log",
        extra=system_name,
        print_data=False,
    )
    make_speedup_plot(data=system_data, x="Ranks", yscale="linear", extra=system_name)
    make_percent_plot(data=system_data, x="Ranks", extra=system_name)

    # Print out max speedup for each system
    get_max_speedup(system_data)
    # Print out solver times for each system 1 GPU runs
    get_1_node_runs(system_data)

    make_speedup_plot(
        data=system_data,
        x="Ranks",
        yscale="log",
        breakdown="GPUs per Node",
        extra=system_name,
    )
    make_speedup_plot(
        data=system_data,
        x="Ranks",
        yscale="linear",
        breakdown="GPUs per Node",
        extra=system_name,
    )
    make_percent_plot(
        data=system_data, x="Ranks", breakdown="GPUs per Node", extra=system_name
    )
