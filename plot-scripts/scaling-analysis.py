#!/usr/bin/env python
# coding: utf-8

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

def make_speedup_plot(data, x, yscale, breakdown, extra=""):
    title = "Speedup by Backend and Problem Size"
    if breakdown != "System":
        title = title + "\non {row_name}" + " {col_name} " + breakdown
        kargs = {"row" : "System", "col" : breakdown}
        c = breakdown
        r = "System"
    else:
        title = title + "\non {col_name}"
        kargs = {"col" : "System"}
        
    speedup_plot = sbn.relplot(data=data, kind="line", x=x, y="Speedup", hue='Backend',
                               style="GB", errorbar=("ci", 68), markers=True, **kargs)
    speedup_plot.set_titles(title)
    for ax in speedup_plot.axes.flat:
        ax.grid(True, axis='both', ls=':')
        if yscale == 'log':
            ax.axline((0, 0), slope=1, color='k', ls='--')
    plt.xscale('log', base=2)
    if yscale == "log":
        plt.yscale('log', base=2)
    plt.savefig(f"Speedup-{x}-{breakdown}-{yscale}{extra}.png")

def make_percent_plot(data, x, breakdown, extra=""):
    ### Relative improvement in speedup by Problem Size
    mpiadvancedata = data[ data['Backend'].isin(["MPI Advance RSSend", "MPI Advance SSend"]) ]
    title = "Relative Speedup Improvement over Cray MPICH Send\nby Backend and Problem Size"
    if breakdown != "System":
        title = title + "on {row_name}" + " {col_name} " + breakdown
        kargs = {"row" : "System", "col" : breakdown}
        c = breakdown
        r = "System"
    else:
        title = title + "on {col_name}"
        kargs = {"col" : "System"}

    percent_plot = sbn.relplot(data=mpiadvancedata, kind="line", x=x, 
                               y="Percent Speedup Improvement", hue='Backend', style='GB',
                               errorbar=("ci", 68), markers=True, **kargs)
    percent_plot.set_titles(title)
    for ax in percent_plot.axes.flat:
        ax.grid(True, axis='both', ls=':')
    plt.xscale('log', base=2)
    plt.savefig(f"Percent-{x}-{breakdown}-linear{extra}.png")

def make_efficiency_plot(data, x, breakdown, extra=""):
    title = "Parallel Efficiency by Backend and Problem Size"
    if breakdown != "System":
        title = title + "\non {row_name}" + " {col_name} " + breakdown
        kargs = {"row" : "System", "col" : breakdown}
        c = breakdown
        r = "System"
    else:
        title = title + "\non {col_name}"
        kargs = {"col" : "System"}
        
    efficiency_plot = sbn.relplot(data=data, kind="line", x=x,
                                  y='Parallel Efficiency', hue='Backend', style='GB', 
                                  errorbar=("ci", 68), markers=True, **kargs)
    efficiency_plot.set_titles(title)
    efficiency_plot.set(ylim=(0.01, 1.05))
    for ax in efficiency_plot.axes.flat:
         ax.grid(True, axis='both', ls=':')
    plt.xscale('log', base=2)
    plt.savefig(f"Efficiency-{x}-{breakdown}-linear{extra}.png")


# Read the raw data into a Pandas Data Frame
all_files = glob.glob("../data/*/scaling-data*.csv")
df = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Fix the labels of the columns to be more readable
df = df.rename(columns={'nodes':'Nodes', 'ntasks':'PPN', 'ranks':'Ranks', 
          'solver_time':'Solve Time', 'solver_creation':'Startup Time',
          'size':'Size', 'system':'System', 'backend':'Backend', 'memory_type':'Memory Type'})

# Fix the names of the backends to be more readable
df['Backend'] = df['Backend'].replace({"MPIAdvance-CXI-Double-Buffering":"MPI Advance RSSend",
                                       "MPIAdvance-CXI-Single-Buffering":"MPI Advance SSend",
                                       "Cray-MPICH-CXI-GPU-Enabled":"Cray MPICH Send"})
# Fix the names of the backends to be more readable
df['System'] = df['System'].replace({"tioga":"Tioga",
                                     "tuolumne":"Tuolumne",
                                     "frontier":"Frontier"})


# Compute derived values to use to generate data to plot from measured terms
## The total number of MPI ranks used in a sample
df['GB'] = round(df['Size'] * df['Size'] * 8 / 10**9, 0)
df['Ranks'] = df['Nodes'] * df['PPN']
df['Edge Length'] = np.sqrt(df['Size']*df['Size']/df['Ranks']) * 8
df = df.sort_values(['Ranks','Nodes'])


## Compute speedup and parallel efficiency
### Aggregate the minimum, mean, and variance of the solver time using 
### a pivot table to calculate a base value to use for calculating speedup 
### calculations using a pivot table
pivot_df = pd.pivot_table(df, 
                     index = ["System", "GB", "Ranks", "Backend"],
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
    base_rt = pivot_df.loc[row['System'], row['GB'], speedup_base, "Cray MPICH Send"]["min"]
    return speedup_base * base_rt / row['Solve Time']

df['Speedup'] = df.apply(speedup_func, axis=1)
df['Parallel Efficiency'] = df['Speedup'] / df['Ranks']

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)
speedup_df = pd.pivot_table(df,
                     index = ["System", "GB", 'Nodes', 'Ranks', 'Backend'],
                     values = ["Speedup"],
                     aggfunc = ["min", "mean", "max"])
speedup_df.columns = speedup_df.columns.droplevel(1)
print("Summary of speedup statistics")
print(speedup_df)

def percent_func(row):
    base_speedup = speedup_df.loc[row['System'], row['GB'], row['Nodes'], row['Ranks'], "Cray MPICH Send"]["max"]
    return 100 * (row['Speedup'] - base_speedup) / base_speedup
df['Percent Speedup Improvement'] = df.apply(percent_func, axis=1)


# Now generate the actual plots we want using Seaborn

## Start by getting data frames wit the subsets of data we want.
speedupdata=df[  df['Backend'].isin(["MPI Advance RSSend","MPI Advance SSend","Cray MPICH Send"]) 
               & df['Memory Type'].isin(["coarse","fine"])
              ]
tuodata=speedupdata[ speedupdata['System'].isin(["Tuolumne"]) ]
frontierdata=speedupdata[ speedupdata['System'].isin(["Frontier"]) ]

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
print("Generating Tuolumne PPN breakdown")
make_speedup_plot(data=tuodata, x="Ranks", yscale="log", breakdown="PPN", extra="-Tuolumne")
make_speedup_plot(data=tuodata, x="Ranks", yscale="linear", breakdown="PPN", extra="-Tuolumne")
make_percent_plot(data=tuodata, x='Ranks', breakdown="PPN", extra="-Tuolumne")
make_efficiency_plot(data=tuodata, x='Ranks', breakdown="PPN", extra="-Tuolumne")

### Then Frontier
print("Generating Frontier PPN breakdown")
make_speedup_plot(data=frontierdata, x="Ranks", yscale="log", breakdown="PPN", extra="-Frontier")
make_speedup_plot(data=frontierdata, x="Ranks", yscale="linear", breakdown="PPN", extra="-Frontier")
make_percent_plot(data=frontierdata, x='Ranks', breakdown="PPN", extra="-Frontier")
make_efficiency_plot(data=frontierdata, x='Ranks', breakdown="PPN", extra="-Frontier")

## Break down speedup and efficiency by edge size
print("Generating Edge Length breakdown")
make_speedup_plot(data=speedupdata, x="Edge Length", yscale="log", breakdown="System")
make_speedup_plot(data=speedupdata, x="Edge Length", yscale="linear", breakdown="System")
make_percent_plot(data=speedupdata, x='Edge Length', breakdown="System")
make_efficiency_plot(data=speedupdata, x='Edge Length', breakdown="System")

make_percent_plot(data=tuodata, x="Edge Length", breakdown="PPN", extra="-Tuolumne")
make_percent_plot(data=frontierdata, x="Edge Length", breakdown="PPN", extra="-Frontier")

## Finally, look at the startup time for the different systems
startupdata=df[  df['Backend'].isin(["MPI Advance RSSend","MPI Advance SSend","Cray MPICH Send"]) 
               & df['Size'].isin([16384])
              ]
startup_plot = sbn.relplot(data=startupdata, kind='line', x='Ranks', 
                              y='Startup Time', hue='Backend', col='System',
                              errorbar=("ci", 68), markers=True)
startup_plot.set_titles("Startup Time for 2GB Problem by Backend\non {col_name}")
#startup_plot.set(ylim=(0.01, 1.05))
startup_plot.set(xlim=(0.8, 1100))
plt.xscale('log', base=2)
#plt.yscale('log', base=2)
plt.savefig("startup-size.png")
