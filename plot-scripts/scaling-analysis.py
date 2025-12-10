#!/usr/bin/env python
# coding: utf-8

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

palette = {
    'Cray MPICH Send': 'tab:green',
    'MPI Advance RSend': 'tab:red',
    'MPI Advance RSSend': 'tab:orange',
    'MPI Advance Send': 'tab:blue',
    'MPI Advance SSend': 'tab:purple'
}

system_order = ["Frontier", "Tuolumne"]
full_backend_order = ["Cray MPICH Send", "MPI Advance RSend", "MPI Advance RSSend", "MPI Advance Send", "MPI Advance SSend"]

def setup_kargs_and_title(k, breakdown, hue, style):
    k["palette"] = palette

    if hue != "":
        k["hue"] = hue
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

    return title

def make_runtime_plot(data, x, yscale, breakdown, style="Problem Size (GB)", hue="Backend", extra=""):
    kargs = {}
    title = setup_kargs_and_title(kargs, breakdown, hue, style)
 
    runtime_plot = sbn.relplot(data=data, kind="line", x=x, y="Solve Time", 
                               errorbar=("ci", 95), 
                               markers=True, **kargs)
    runtime_plot.set_titles(title)
    for ax in runtime_plot.axes.ravel():
        ax.grid(True, axis='both', ls=':')
    plt.xscale('log', base=2)
    if yscale == 'log':
        plt.yscale('log', base=10)
    plt.savefig(f"Runtime-{x}-{breakdown}-{yscale}{extra}.png")
    plt.close()

def make_speedup_plot(data, x, yscale, breakdown, style="Problem Size (GB)", hue="Backend", extra=""):
    kargs = {}
    title = setup_kargs_and_title(kargs, breakdown, hue, style)

    speedup_plot = sbn.relplot(data=data, kind="line", x=x, y="Speedup", 
                               errorbar=("ci", 95), 
                               markers=True, **kargs)
    speedup_plot.set_titles(title)
    for ax in speedup_plot.axes.ravel():
        ax.grid(True, axis='both', ls=':')
        if yscale == 'log':
            ax.axline((0, 0), slope=1, color='k', ls='--')
    plt.xscale('log', base=2)
    if yscale == 'log':
        plt.yscale('log', base=2)
    plt.savefig(f"Speedup-{x}-{breakdown}-{yscale}{extra}.png")
    plt.close()

def make_percent_plot(data, x, breakdown, y="Speedup", style="Problem Size (GB)", invertx=False, extra=""):
    ### Relative improvement in speedup by Problem Size
    mpiadvancedata = data[ data['Backend'].isin([
        "MPI Advance RSSend", 
        "MPI Advance SSend", 
        "MPI Advance RSend", 
        "MPI Advance Send"]) ]
    kargs = {}
    title = setup_kargs_and_title(kargs, breakdown, "Backend", style)
        
    percent_plot = sbn.relplot(data=mpiadvancedata, kind="line", x=x, 
                               y=f"Percent {y} Improvement",
                               errorbar=("ci", 95),
                               markers=True, **kargs)
    percent_plot.set_titles(title)
    plt.xscale('log', base=2)
    for ax in percent_plot.axes.ravel():
        ax.grid(True, axis='both', ls=':')
        if invertx:
            ax.invert_xaxis()
    plt.savefig(f"Percent-{y}-{x}-{breakdown}-linear{extra}.png")
    plt.close()

def make_efficiency_plot(data, x, breakdown, style="Problem Size (GB)", extra=""):
    kargs = {}
    title = setup_kargs_and_title(kargs, breakdown, "Backend", style)
        
    efficiency_plot = sbn.relplot(data=data, kind="line", x=x, y='Parallel Efficiency', 
                                  errorbar=("ci", 95), 
                                  markers=True, **kargs)
    efficiency_plot.set_titles(title)
    efficiency_plot.set(ylim=(0.01, 1.05))
    plt.xscale('log', base=2)
    for ax in efficiency_plot.axes.ravel():
        ax.grid(True, axis='both', ls=':')
    plt.savefig(f"Efficiency-{x}-{breakdown}-linear{extra}.png")
    plt.close()


# Read the raw data into a Pandas Data Frame
all_files = glob.glob("../data/*/scaling-data*.csv")
df = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Fix the labels of the columns to be more readable
df = df.rename(columns={'nodes':'Nodes', 'ntasks':'PPN', 'ranks':'Ranks', 
          'solver_time':'Solve Time', 'solver_creation':'Startup Time',
          'size':'Size', 'system':'System', 'backend':'Backend', 'memory_type':'Memory Type'})

# Fix the names of the backends to be more readable
df['Backend'] = df['Backend'].replace({
                                       "MPIAdvance-CXI-Double-Buffering":"MPI Advance RSSend",
                                       "MPIAdvance-CXI-Single-Buffering":"MPI Advance SSend",
                                       "MPIAdvance-CXI-Double-Buffering2":"MPI Advance RSend",
                                       "MPIAdvance-CXI-Single-Buffering2":"MPI Advance Send",
                                       "Cray-MPICH-CXI-GPU-Enabled":"Cray MPICH Send"})
# Fix the names of the backends to be more readable
df['System'] = df['System'].replace({"tioga":"Tioga",
                                     "tuolumne":"Tuolumne",
                                     "frontier":"Frontier"})


# Compute derived values to use to generate data to plot from measured terms
## The total number of MPI ranks used in a sample
df['Problem Size (GB)'] = round(df['Size'] * df['Size'] * 8 / 10**9, 0)
df['Ranks'] = df['Nodes'] * df['PPN']
df['Edge Length'] = np.sqrt(df['Size']*df['Size']/df['Ranks']) * 8
df = df.sort_values(['Ranks','Nodes'])


## Compute speedup and parallel efficiency
### Aggregate the minimum, mean, and variance of the solver time using 
### a pivot table to calculate a base value to use for calculating speedup 
### calculations using a pivot table
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)
pivot_df = pd.pivot_table(df, 
                     index = ["System", "Problem Size (GB)", "Ranks", "Backend"],
                     values = ["Solve Time"],
                     aggfunc = ["min", "mean", "std"])
pivot_df.columns = pivot_df.columns.droplevel(1)

### Now compute the speedup, parallel efficiency with the baseline as the best runtime 
### from an execution on the smallest number of ranks in the data set for a given problem 
### from the original Cray backend
speedup_base = 1;
def speedup_func(row):
    base_rt = pivot_df.loc[row['System'], row['Problem Size (GB)'], speedup_base, "Cray MPICH Send"]["min"]
    return speedup_base * base_rt / row['Solve Time']

df['Speedup'] = df.apply(speedup_func, axis=1)
df['Parallel Efficiency'] = df['Speedup'] / df['Ranks']

speedup_df = pd.pivot_table(df,
                     index = ["System", "Problem Size (GB)", 'Nodes', 'Ranks', 'Backend'],
                     values = ["Speedup"],
                     aggfunc = ["min", "mean", "max"])
speedup_df.columns = speedup_df.columns.droplevel(1)
print("Summary of basic speedups")
print(speedup_df)

def relative_speedup_func(row):
    base_speedup = speedup_df.loc[row['System'], row['Problem Size (GB)'], row['Nodes'], row['Ranks'], "Cray MPICH Send"]["max"]
    return 100 * (row['Speedup'] - base_speedup) / base_speedup

def relative_efficiency_func(row):
    base_efficiency = speedup_df.loc[row['System'], row['Problem Size (GB)'], row['Nodes'], row['Ranks'], "Cray MPICH Send"]["max"] / row['Ranks']
    return 100 * (row['Efficiency'] - base_efficiency) / base_efficiency

df['Percent Speedup Improvement'] = df.apply(relative_speedup_func, axis=1)
df['Percent Efficiency Improvement'] = df.apply(relative_speedup_func, axis=1)


# Initial pathfinding analyses. Commented out as we don't use this data in
# the main paper, but included here for reference.

## First, let;s compare RSSend, RSend, SSend, and Send on the two systems
## to see if there's a reason to prefer one to the other
mpiadvancedata=df[  df['Backend'].isin([
    "MPI Advance RSSend",
    "MPI Advance SSend",
    "MPI Advance RSend", 
    "MPI Advance Send", 
    "Cray MPICH Send"]) 
               & df['Memory Type'].isin(["coarse","fine"])
              ]

# make_speedup_plot(data=mpiadvancedata, x="Ranks", yscale="log", breakdown="System", extra="-Full")
# make_speedup_plot(data=mpiadvancedata, x="Ranks", yscale="linear", breakdown="System", extra="-Full")
# make_percent_plot(data=mpiadvancedata, x='Ranks', breakdown="System", extra="-Full")
# make_efficiency_plot(data=mpiadvancedata, x='Ranks', breakdown="System", extra="-Full")

## This data shows no consistent reason to prefer one to the other, so we
## focus on rsend and send as it provides more semantic flexibility and more
## balanced resource iusage between sends and receives
speedupdata=df[  df['Backend'].isin([
    "MPI Advance RSend", 
    "MPI Advance Send", 
    "Cray MPICH Send"]) 
               & df['Memory Type'].isin(["coarse","fine"])
              ]
tuodata=speedupdata[ speedupdata['System'].isin(["Tuolumne"]) ]
frontierdata=speedupdata[ speedupdata['System'].isin(["Frontier"]) ]

## Next, look and see if there's a perfomrance difference between 
## coarse and fine memory on Frontier - if there's no difference, we 
## treat the data points as the same
# make_speedup_plot(data=frontierdata, x="Ranks", yscale="log", breakdown="Backend", hue="Memory Type", extra="-Frontier")
# make_speedup_plot(data=frontierdata, x="Ranks", yscale="linear", breakdown="Backend", hue="Memory Type", extra="-Frontier")
# make_speedup_plot(data=tuodata, x="Ranks", yscale="log", breakdown="Backend", hue="Memory Type", extra="-Tuolumne")
# make_speedup_plot(data=tuodata, x="Ranks", yscale="linear", breakdown="Backend", hue="Memory Type", extra="-Tuolumne")

## No real difference between memory type, so use both coarse and fine data as
## measureing the same thing. As a result, we now have 10 data points at each sample 

# Generate the main analyses that we'll use inthe paper.

## Start with actual runtime, not speedup so that people can see actual
## runtimes, not just relative numbers.
make_runtime_plot(data=speedupdata, x="Ranks", yscale="log", breakdown="System")

## Now that we have that, focus on speedup, efficiency and percent improvement
## broken down by Problem Size. For speedup, we use both log and linear scales
## so that we can see magnitude of difference at scale (linear) and detilas of
## tradeoffs on the small problems.
make_speedup_plot(data=speedupdata, x="Ranks", yscale="log", breakdown="System")
make_speedup_plot(data=speedupdata, x="Ranks", yscale="linear", breakdown="System")
make_percent_plot(data=speedupdata, x='Ranks', breakdown="System")
make_efficiency_plot(data=speedupdata, x='Ranks', breakdown="System")

## On tuolumne (but not Frontier), the speedup for Cray MPICH is highly dependent on PPN 
## Break these down separately by system since they have different PPNs they can support

### First Tuolumne
trimmeddata = tuodata[tuodata['PPN'].isin([2,4])]
make_speedup_plot(data=trimmeddata, x="Ranks", yscale="log", breakdown="PPN", extra="-Tuolumne")
make_speedup_plot(data=trimmeddata, x="Ranks", yscale="linear", breakdown="PPN", extra="-Tuolumne")
make_percent_plot(data=trimmeddata, x='Ranks', breakdown="PPN", extra="-Tuolumne")
make_efficiency_plot(data=trimmeddata, x='Ranks', breakdown="PPN", extra="-Tuolumne")

### Then Frontier
trimmeddata = frontierdata[frontierdata['PPN'].isin([4,8])]
make_speedup_plot(data=trimmeddata, x="Ranks", yscale="log", breakdown="PPN", extra="-Frontier")
make_speedup_plot(data=trimmeddata, x="Ranks", yscale="linear", breakdown="PPN", extra="-Frontier")
make_percent_plot(data=trimmeddata, x='Ranks', breakdown="PPN", extra="-Frontier")
make_efficiency_plot(data=trimmeddata, x='Ranks', breakdown="PPN", extra="-Frontier")

## To understand where the performance impacts are most significant, 
## we look at percent improvement by edge length, limited to Frontier 
## data where the data is most stable. This shows that the main advantage
## is on mid-sized messages. For largemewssages, both systems are bandwidth-bound.
## For small messages, Cray can leverage unexpected message hardware that
## our GPU implementation does not.
make_percent_plot(data=frontierdata, x='Edge Length', breakdown="", extra="-Frontier")

## Finally, look at the startup time for the different systems
startupdata=df[  df['Backend'].isin([
    "MPI Advance RSend",
    "MPI Advance Send",
    "Cray MPICH Send"]) 
               & df['Size'].isin([16384])
              ]
kargs={}
setup_kargs_and_title(kargs, "System", "Backend", "")
startup_plot = sbn.relplot(data=startupdata, kind='line', x='Ranks', 
                              y='Startup Time', errorbar=("ci", 95), 
                              markers=True, **kargs)
startup_plot.set_titles("Startup Time for 2GB Problem Size on {col_name}")
#startup_plot.set(ylim=(0.01, 1.05))
plt.xscale('log', base=2)
#plt.yscale('log', base=2)
plt.savefig("startup-size.png")
plt.close()

# Abandoned analyses below.
## Analyze data from frontier by memory type to see if coarse versus fine grain memory made
## a difference. It did not, so we're not showing these graphs.

## Edge length sorted speedup and efficiency data - didn't really add that much since
## the differenc data sets have different baseline amounts of parallelism
#make_speedup_plot(data=tuodata, x='Edge Length', yscale="linear", breakdown="System", extra="-Tuolumne")
#make_speedup_plot(data=tuodata, x='Edge Length', yscale="log", breakdown="System", extra="-Tuolumne")
#make_efficiency_plot(data=tuodata, x='Edge Length', breakdown="System", extra="-Tuolumne")
#make_percent_plot(data=tuodata, x="Edge Length", breakdown="System", extra="-Tuolumne")

#make_speedup_plot(data=frontierdata, x='Edge Length', yscale="linear", breakdown="System", extra="-Frontier")
#make_speedup_plot(data=frontierdata, x='Edge Length', yscale="log", breakdown="System", extra="-Frontier")
#make_efficiency_plot(data=frontierdata, x='Edge Length', breakdown="System", extra="-Frontier")
#make_percent_plot(data=frontierdata, x="Edge Length", breakdown="System", extra="-Frontier")

## Attempt to aggregate parallel efficiency data together across multiple data sets to 
## correct for the problems above. Data is not normal or well aligned, so this didn't really 
## make sense in retrospeect.
# make_efficiency_plot(data=speedupdata, x='Edge Length', style="", breakdown="System")
# make_percent_plot(data=speedupdata, x='Edge Length', y="Efficiency", style="", breakdown="System")

