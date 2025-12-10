#!/usr/bin/env python
# coding: utf-8

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

def make_speedup_plot(data, x, yscale, breakdown, style="Problem Size (GB)", hue="Backend", extra=""):
    
    kargs = {"hue" : hue}
    if style != "":
        kargs["style"] = style

    if breakdown != "System":
        title = "{row_name}" + " {col_name} " + breakdown
        kargs["row"] = "System"
        kargs["col"] = breakdown
    else:
        title = "{col_name}"
        kargs["col"] = "System"
        
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
    kargs = {"hue": "Backend"}
    if style != "":
        kargs["style"] = style

    if breakdown != "System":
        title = "{row_name}" + " {col_name} " + breakdown
        kargs["row"] = "System"
        kargs["col"] = breakdown
    else:
        title = "{col_name}"
        kargs["col"] = "System"
        
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
    kargs = {"hue": "Backend"}
    if style != "":
        kargs["style"] = style

    if breakdown != "System":
        title = "{row_name}" + " {col_name} " + breakdown
        kargs["row"] = "System"
        kargs["col"] = breakdown
    else:
        title = "{col_name}"
        kargs["col"] = "System"
        
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
print("Summary of basic data statistics")
print(pivot_df)

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

def relative_speedup_func(row):
    base_speedup = speedup_df.loc[row['System'], row['Problem Size (GB)'], row['Nodes'], row['Ranks'], "Cray MPICH Send"]["max"]
    return 100 * (row['Speedup'] - base_speedup) / base_speedup

def relative_efficiency_func(row):
    base_efficiency = speedup_df.loc[row['System'], row['Problem Size (GB)'], row['Nodes'], row['Ranks'], "Cray MPICH Send"]["max"] / row['Ranks']
    return 100 * (row['Efficiency'] - base_efficiency) / base_efficiency

df['Percent Speedup Improvement'] = df.apply(relative_speedup_func, axis=1)
df['Percent Efficiency Improvement'] = df.apply(relative_speedup_func, axis=1)


# Now generate the actual plots we want using Seaborn

## Start by getting data frames wit the subsets of data we want.
mpiadvancedata=df[  df['Backend'].isin([
    "MPI Advance RSSend",
    "MPI Advance SSend",
    "MPI Advance RSend", 
    "MPI Advance Send", 
    "Cray MPICH Send"]) 
               & df['Memory Type'].isin(["coarse","fine"])
              ]

## First, let;s compare RSSend, RSend, SSend, and Send on the two systems
## to see if there's a reason to prefer one to the other
make_speedup_plot(data=mpiadvancedata, x="Ranks", yscale="log", breakdown="System", extra="-Full")
make_speedup_plot(data=mpiadvancedata, x="Ranks", yscale="linear", breakdown="System", extra="-Full")
make_percent_plot(data=mpiadvancedata, x='Ranks', breakdown="System", extra="-Full")
make_efficiency_plot(data=mpiadvancedata, x='Ranks', breakdown="System", extra="-Full")

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
make_speedup_plot(data=frontierdata, x="Ranks", yscale="log", breakdown="Backend", hue="Memory Type", extra="-Frontier")
make_speedup_plot(data=frontierdata, x="Ranks", yscale="linear", breakdown="Backend", hue="Memory Type", extra="-Frontier")

## So now we know what we have - 10 data points at each sample since we treat
## coarse and fine the same. Generate the main speedup analyses.

## As first plots, we want speedup, efficiency and percent improvement
## broken down by Problem Size

### For Speedup, we use both log and linear scales.
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
make_percent_plot(data=frontierdata, x='Edge Length', breakdown="System", extra="-Frontier")

## Finally, look at the startup time for the different systems
startupdata=df[  df['Backend'].isin([
    #"MPI Advance RSSend",
    #"MPI Advance SSend",
    "MPI Advance RSend",
    "MPI Advance Send",
    "Cray MPICH Send"]) 
               & df['Size'].isin([16384])
              ]
startup_plot = sbn.relplot(data=startupdata, kind='line', x='Ranks', 
                              y='Startup Time', hue='Backend', col='System',
                              errorbar=("ci", 95), 
                              markers=True)
startup_plot.set_titles("Startup Time for 2GB Problem on {col_name}")
#startup_plot.set(ylim=(0.01, 1.05))
startup_plot.set(xlim=(0.8, 1100))
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

