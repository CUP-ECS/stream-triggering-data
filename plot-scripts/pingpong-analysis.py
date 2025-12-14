#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sbn
import glob

# Read the raw data into a Pandas Data Frame
all_files = glob.glob("../data/PingPong/*.csv")
df = pd.concat((pd.read_csv(f) for f in all_files), ignore_index=True)

# Filter out HIP runs (not used in paper)
df = df[df.Backend != "hip"]
# Filter out Fine grained memory (not used in paper)
df = df[df.Backend != "cxi-fine"]
# Filter out Cray MPICH single buffered (rsend) since not used in CabanaGhost
df = df.query("not (Backend == 'mpi' and Buffering == 'db')")

# Clean up names
df['Test_Type'] = df['Buffering'] + "_" + df['Backend']
df['Test_Type'] = df['Test_Type'].replace({
                                       "sb_cxi-coarse":"Stream-Triggered Send",
                                       "db_cxi-coarse":"Stream-Triggered Rsend",
                                       "sb_cxi-fine":"Stream-Triggered Send (fine)",
                                       "db_cxi-fine":"Stream-Triggered Rsend (fine)",
                                       "sb_mpi":"Cray MPICH Send",
                                       "db_mpi":"Cray MPICH Rsend"})

# Calculate true buffer size, bandwidth and latency
df['Buffer Size'] = df['Items'] * 4
df['Bandwidth'] = (df['Iters'] * 2 * df['Buffer Size']) / df['Time'] / 1073741824 
df['Latency'] = df['Time'] / df['Iters']

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

for key, group in df.groupby("GPU"):
    cray = group.query("Test_Type == 'Cray MPICH Send'")
    cray_l = cray.groupby(["Buffer Size"])["Latency"].mean()
    cray_b = cray.groupby(["Buffer Size"])["Bandwidth"].mean()

    send = group.query("Test_Type == 'Stream-Triggered Send'")
    send_l = send.groupby(["Buffer Size"])["Latency"].mean()
    send_b = send.groupby(["Buffer Size"])["Bandwidth"].mean()

    rsend = group.query("Test_Type == 'Stream-Triggered Rsend'")
    rsend_l = rsend.groupby(["Buffer Size"])["Latency"].mean()
    rsend_b = rsend.groupby(["Buffer Size"])["Bandwidth"].mean()

    print(key)
    # Difference to Cray for latency
    print(((send_l - cray_l) / cray_l) * 100)
    print(((rsend_l - cray_l) / cray_l) * 100)

    # Difference to Cray for bandwidth
    print(((send_b - cray_b) / cray_b) * 100)
    print(((rsend_b - cray_b) / cray_b) * 100)

# Colors to use
custom_palette = {"Cray MPICH Send": "tab:green",
                  "Stream-Triggered Send":"tab:blue",
                  "Stream-Triggered Rsend":"tab:orange"}
custom_order = ["Cray MPICH Send", "Stream-Triggered Rsend", "Stream-Triggered Send"]

for key, group in df.groupby("GPU"):
    # Less than 2^20
    latency_df=group[group['Buffer Size'] < 1048576]
    # Plot
    plt.figure(figsize=(6,4))
    sbn.lineplot(data=latency_df, x='Buffer Size',y='Latency', hue='Test_Type', style='Test_Type',
                 errorbar=("ci", 95), markers=True, palette=custom_palette, hue_order=custom_order)
    plt.xscale('log', base=2)
    plt.xlabel("Buffer Size (bytes)")
    plt.yscale('log', base=10)
    plt.ylabel("Latency (seconds)")
    plt.legend(title="Backend")
    plt.grid(which="both")
    plt.tight_layout()
    plt.savefig(f"pingpong-latency-logY-{key}.png")

    plt.figure(figsize=(6,3))
    sbn.lineplot(data=group, x='Buffer Size',y='Bandwidth', hue='Test_Type', style='Test_Type',
                 errorbar=("ci", 95), markers=True, palette=custom_palette, hue_order=custom_order)
    plt.xscale('log', base=2)
    plt.xlabel("Buffer Size (bytes)")
    plt.ylabel("Bandwidth (GB/second)")
    plt.legend(title="Backend")
    plt.xlim(right=2147483648)
    plt.grid()
    plt.tight_layout()
    plt.savefig(f"pingpong-bandwidth-linearY-{key}.png")

# latency_pivot_df = pd.pivot_table(df, 
#                      index = ["Test Type", "Buffer Size"],
#                      values = ["Latency"],
#                      aggfunc = ["min", "mean", "std"])
# latency_pivot_df.columns = latency_pivot_df.columns.droplevel(1)
# print(latency_pivot_df)
# bw_pivot_df = pd.pivot_table(df, 
#                      index = ["Test Type", "Buffer Size"],
#                      values = ["Bandwidth"],
#                      aggfunc = ["min", "mean", "std"])
# bw_pivot_df.columns = bw_pivot_df.columns.droplevel(1)
# print(bw_pivot_df)
