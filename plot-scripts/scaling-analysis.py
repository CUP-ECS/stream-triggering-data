#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

# Read the raw data into a Pandas Data Frame
all_files = glob.glob("../data/TUOLUMNE/scaling-data-*.csv")
df = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Fix the labels of the columns to be more readable
df = df.rename(columns={'nodes':'Nodes', 'ntasks':'PPN', 'ranks':'Ranks', 
          'solver_time':'Solve Time', 'solver_creation':'Startup Time',
          'size':'Size', 'system':'System', 'backend':'Backend', 'memory_type':'Memory Type'})

# Fix the names of the backends to be more readable
df['Backend'] = df['Backend'].replace({"MPIAdvance-CXI-Double-Buffering":"MPI Advance RSend",
                                       "MPIAdvance-CXI-Single-Buffering":"MPI Advance Send",
                                       "Cray-MPICH-CXI-GPU-Enabled":"Cray MPICH",
                                       "Cray-MPICH-CXI-GPU-Disabled":"Cray MPICH No GPU IPC"})
# Fix the names of the backends to be more readable
df['System'] = df['System'].replace({"tioga":"Tioga",
                                     "tuolumne":"Tuolumne",
                                     "frontier":"Frontier"})


# Compute derived values to use to generate data to plot from measured terms
## The total number of MPI ranks used in a sample
df['GB'] = round(df['Size'] * df['Size'] * 8 / 2**30, 0)
df['Ranks'] = df['Nodes'] * df['PPN']
df = df.sort_values(['Ranks','Nodes'])


## Compute speedup and parallel efficiency
### Aggregate the minimum, mean, and variance of the solver time using 
### a pivot table to calculate a base value to use for calculating speedup 
### calculations using a pivot table
pivot_df = pd.pivot_table(df, 
                     index = ["System", "GB", "Ranks"],
                     values = ["Solve Time"],
                     aggfunc = ["min", "mean", "std"])
pivot_df.columns = pivot_df.columns.droplevel(1)
print("Summary of basic data statistics")
print(pivot_df)

### Now compute the speedup and parallel efficiency the best runtime from an execution on
### the smallest number of ranks in the data set for a given problem from the original 
### Cray backend
speedup_base = 1;
def speedup_func(row):
    base_rt = pivot_df.loc[row['System'], row['GB'], speedup_base]["min"]
    return speedup_base * base_rt / row['Solve Time']
df['Speedup'] = df.apply(speedup_func, axis=1)
df['Parallel Efficiency'] = df['Speedup'] / df['Ranks']


# Now generate the actual plots using Seaborn
speedupdata=df[  df['Backend'].isin(["MPI Advance RSend","MPI Advance Send","Cray MPICH","Cray MPICH No GPU IPC"]) 
               & df['Memory Type'].isin(["coarse","fine"])
               & df['Size'].isin([16384,61440,90112,92160])
              ]

# Speedup broken down by Problem Size
speedup_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                           y='Speedup', hue='Backend', row='System', 
                           style='GB',
                           errorbar=("ci", 68), markers=True)
speedup_plot.set_titles("Speedup by Backend and Problem Size\non {row_name}")
speedup_plot.set(ylim=(0.8, 1050))
speedup_plot.set(xlim=(0.8, 1050))
for ax in speedup_plot.axes.flat:
    ax.axline((0, 0), slope=1, color='k', ls='--')
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("speedup-size.png")

efficiency_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                              y='Parallel Efficiency', hue='Backend', row='System', 
                              style='GB', 
                              errorbar=("ci", 68), markers=True)
efficiency_plot.set_titles("Parallel Efficiency by Backend and Problem Size\non {row_name}")
efficiency_plot.set(ylim=(0.01, 1.05))
efficiency_plot.set(xlim=(0.8, 1050))
for ax in efficiency_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
#plt.yscale('log', base=2)
plt.savefig("efficiency-size.png")

# Speedup broken down by Problem Size and PPN
speedup_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                           y='Speedup', hue='Backend', row='System', 
                           col='PPN', style='GB',
                           errorbar=("ci", 68), markers=True)
speedup_plot.set_titles("Speedup by Backend and PPN\non {row_name} {col_name} PPN")
speedup_plot.set(ylim=(0.8, 1050))
speedup_plot.set(xlim=(0.8, 1050))
for ax in speedup_plot.axes.flat:
    ax.axline((0, 0), slope=1, color='k', ls='--')
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("speedup-ppn.png")

efficiency_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                              y='Parallel Efficiency', hue='Backend', row='System', 
                              col='PPN', style='GB',
                              errorbar=("ci", 68), markers=True)
efficiency_plot.set_titles("Parallel Efficiency by Backend and PPN Size\non {row_name} {col_name} PPN")
efficiency_plot.set(ylim=(0.01, 1.05))
efficiency_plot.set(xlim=(0.8, 1050))
for ax in efficiency_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("efficiency-ppn.png")

startup_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                              y='Startup Time', hue='Backend', row='System', 
                              style='GB', 
                              errorbar=("ci", 68), markers=True)
startup_plot.set_titles("Startup Time by Backend and Problem Size\non {row_name}")
#startup_plot.set(ylim=(0.01, 1.05))
startup_plot.set(xlim=(0.8, 1050))
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("startup-size.png")

