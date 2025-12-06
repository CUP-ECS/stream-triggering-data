#!/usr/bin/env python
# coding: utf-8

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

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
speedup_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                           y='Speedup', hue='Backend', col='System', 
                           style='GB',
                           errorbar=("ci", 68), markers=True)
speedup_plot.set_titles("Speedup by Backend and Problem Size\non {col_name}")
speedup_plot.set(xlim=(0.8, 8300))
#### First a linear scale with a perfect speedup refernece line showing the differences
#### across the range but deemphasizeing hte big differences at the larger sizes
plt.xscale('log', base=2)
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.savefig("speedup-size-linear.png")

#### Then a log scale which shows the big differences at the end but compresses
#### out the small differences at the start and on the small problem.
plt.xscale('linear')
plt.yscale('linear')
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
    ax.axline((0, 0), slope=1, color='k', ls='--')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("speedup-size-log.png")


### Relative improvement in speedup by Problem Size
mpiadvancedata = speedupdata[ speedupdata['Backend'].isin(["MPI Advance RSSend", "MPI Advance SSend"]) ]
percent_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
                           y='Percent Speedup Improvement', hue='Backend', col='System', 
                           style='GB',
                           errorbar=("ci", 68), markers=True)
percent_plot.set_titles("Relative Speedup Improvement over Cray MPICH Send\nby Backend and Problem Size on {col_name}")
percent_plot.set(xlim=(0.8, 8300))
for ax in percent_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("percent-size-linear.png")

### Parallel efficiency 
efficiency_plot = sbn.relplot(data=speedupdata, kind='line', x='Ranks', 
                              y='Parallel Efficiency', hue='Backend', col='System', 
                              style='GB', 
                              errorbar=("ci", 68), markers=True)
efficiency_plot.set_titles("Parallel Efficiency by Backend and Problem Size\non {col_name}")
efficiency_plot.set(xlim=(0.8, 8300))
efficiency_plot.set(ylim=(0.01, 1.05))
for ax in efficiency_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("efficiency-size-linear.png")

## On tuolumne (but not Frontier), the speedup for Cray MPICH is highly dependent on PPN 
## Break these down separately.

### First Tuolumne
speedup_plot = sbn.relplot(data=tuodata, kind='line', x='Ranks', 
                           y='Speedup', hue='Backend', row='System', 
                           col='PPN', style='GB',
                           errorbar=("ci", 68), markers=True)
speedup_plot.set_titles("Speedup by Backend and Problem Size\non {row_name} {col_name} PPN")
#### First a linear scale with a perfect speedup refernece line showing the differences
#### across the range but deemphasizeing hte big differences at the larger sizes
plt.xscale('log', base=2)
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.savefig("speedup-ppn-tuo-linear.png")

#### Then a log scale which shows the big differences at the end but compresses
#### out the small differences at the start and on the small problem.
plt.xscale('linear')
plt.yscale('linear')
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
    ax.axline((0, 0), slope=1, color='k', ls='--')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("speedup-ppn-tuo-log.png")

efficiency_plot = sbn.relplot(data=tuodata, kind='line', x='Ranks', 
                              y='Parallel Efficiency', hue='Backend', row='System', 
                              col='PPN', style='GB',
                              errorbar=("ci", 68), markers=True)
efficiency_plot.set_titles("Parallel Efficiency by Backend and Problem Size\non {row_name} {col_name} PPN")
efficiency_plot.set(ylim=(0.01, 1.05))
for ax in efficiency_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("efficiency-ppn-tuo-linear.png")

mpiadvancedata = tuodata[ tuodata['Backend'].isin(["MPI Advance RSSend", "MPI Advance SSend"]) ]
percent_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
                           y='Percent Speedup Improvement', hue='Backend', row='System', 
                           col='PPN', style='GB',
                           errorbar=("ci", 68), markers=True)
percent_plot.set_titles("Relative Speedup Improvement over Cray MPICH Send\nby Backend and Problem Size on {row_name} {col_name} PPN")
for ax in percent_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("percent-ppn-tuo-linear.png")


### Then Frontier
speedup_plot = sbn.relplot(data=frontierdata, kind='line', x='Ranks', 
                           y='Speedup', hue='Backend', row='System', 
                           col='PPN', style='GB',
                           errorbar=("ci", 68), markers=True)
speedup_plot.set_titles("Speedup by Backend and Problem Size\non {row_name} {col_name} PPN")
#### First a linear scale with a perfect speedup refernece line showing the differences
#### across the range but deemphasizeing hte big differences at the larger sizes
plt.xscale('log', base=2)
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.savefig("speedup-ppn-frontier-linear.png")

#### Then a log scale which shows the big differences at the end but compresses
#### out the small differences at the start and on the small problem.
plt.xscale('linear')
plt.yscale('linear')
for ax in speedup_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
    ax.axline((0, 0), slope=1, color='k', ls='--')
plt.xscale('log', base=2)
plt.yscale('log', base=2)
plt.savefig("speedup-ppn-frontier-log.png")

efficiency_plot = sbn.relplot(data=frontierdata, kind='line', x='Ranks', 
                              y='Parallel Efficiency', hue='Backend', row='System', 
                              col='PPN', style='GB',
                              errorbar=("ci", 68), markers=True)
efficiency_plot.set_titles("Parallel Efficiency by Backend and Problem Size\non {row_name} {col_name} PPN")
efficiency_plot.set(ylim=(0.01, 1.05))
for ax in efficiency_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("efficiency-ppn-frontier-linear.png")

mpiadvancedata = frontierdata[ frontierdata['Backend'].isin(["MPI Advance RSSend", "MPI Advance SSend"]) ]
percent_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
                           y='Percent Speedup Improvement', hue='Backend', row='System', 
                           col='PPN', style='GB',
                           errorbar=("ci", 68), markers=True)
percent_plot.set_titles("Relative Speedup Improvement over Cray MPICH Send\nby Backend and Problem Size on {row_name} {col_name} PPN")
for ax in percent_plot.axes.flat:
    ax.grid(True, axis='both', ls=':')
plt.xscale('log', base=2)
plt.savefig("percent-ppn-frontier-linear.png")

## On Frontier (but not Tuolumne), we can use fine versus coarse grain memory to
## reduce triggering time. See if it makes a difference. It doesn't, so we aren't
## generating these plots right now.

#### mpiadvancedata = speedupdata[ speedupdata['Backend'].isin(["MPI Advance RSSend", "MPI Advance SSend"]) ]
#### speedup_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
####                            y='Speedup', hue='Memory Type', col='System', 
####                            style='GB',
####                            errorbar=("ci", 68), markers=True)
#### speedup_plot.set_titles("Speedup by Memory Type and Problem Size\non {col_name}")
#### speedup_plot.set(xlim=(0.8, 8300))
#### for ax in speedup_plot.axes.flat:
####     ax.grid(True, axis='both', ls=':')
#### plt.xscale('log', base=2)
#### plt.savefig("speedup-memory-linear.png")
#### 
#### efficiency_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
####                               y='Parallel Efficiency', hue='Memory Type', col='System', 
####                               style='GB',
####                               errorbar=("ci", 68), markers=True)
#### efficiency_plot.set_titles("Parallel Efficiency by Memory Type and Problem Size\non {col_name}")
#### efficiency_plot.set(ylim=(0.01, 1.05))
#### for ax in efficiency_plot.axes.flat:
####     ax.grid(True, axis='both', ls=':')
#### plt.xscale('log', base=2)
#### plt.savefig("efficiency-memory-linear.png")
#### 
#### percent_plot = sbn.relplot(data=mpiadvancedata, kind='line', x='Ranks', 
####                            y='Percent Speedup Improvement', hue='Memory Type', col='System', 
####                            style='GB',
####                            errorbar=("ci", 68), markers=True)
#### percent_plot.set_titles("Relative Speedup Improvement over Cray MPICH Send\nby Memory Type and Problem Size on {col_name}")
#### percent_plot.set(xlim=(0.8, 8300))
#### for ax in percent_plot.axes.flat:
####     ax.grid(True, axis='both', ls=':')
#### plt.xscale('log', base=2)
#### plt.savefig("percent-memory-linear.png")

## Finally, look at the startup time for the different systems
startupdata=df[  df['Backend'].isin(["MPI Advance RSSend","MPI Advance SSend","Cray MPICH Send"]) 
               & df['Memory Type'].isin(["coarse"])
              ]
startup_plot = sbn.relplot(data=startupdata, kind='line', x='Ranks', 
                              y='Startup Time', hue='Backend', col='System',
                              errorbar=("ci", 68), markers=True)
startup_plot.set_titles("Startup Time by Backend\non {col_name}")
#startup_plot.set(ylim=(0.01, 1.05))
startup_plot.set(xlim=(0.8, 1100))
plt.xscale('log', base=2)
#plt.yscale('log', base=2)
plt.savefig("startup-size.png")
