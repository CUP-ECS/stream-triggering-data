#!/usr/bin/env python3
"""CabanaGhost strong scaling: the paper's Figs. 6, 7 and 9 and Table III, from CabanaGhost CSVs.

    scaling-analysis.py <csv...> [--out-dir DIR] [--base-stat min|mean] [--edge-ppn 1,2]
                        [--with-fine | --pool-memory | --memory-check]

Takes any number of CSVs from CabanaGhost/out-to-csv.py, from one system or several. Speedup is
against the single-GPU Cray MPICH solve time of the same system and problem size: its minimum by
default, which is what the paper's Table III used (its text says the mean; --base-stat mean). The
table's "±" is the 95% Student-t confidence interval of the mean (the paper printed the standard
deviation; table3.csv has both). Percent improvement compares each run's speedup with the mean Cray
MPICH speedup on the same nodes and ranks.

Fine-grained memory (decided 2026-11-09): check once whether it differs from coarse
(--memory-check), then pool the two (--pool-memory), as the paper's Frontier rows of Table III did.
By default fine-grained runs are left out; --with-fine plots them as their own lines.

Writes PNGs and table3.csv to --out-dir, and prints the single-GPU baselines and Table III.
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sbn  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

CRAY = "Cray MPICH Send"
LABELS = {("mpi", "sb"): CRAY, ("cxi", "db"): "Stream-Triggered Rsend", ("cxi", "sb"): "Stream-Triggered Send"}
PALETTE = {CRAY: "tab:green", "Stream-Triggered Rsend": "tab:orange", "Stream-Triggered Send": "tab:blue",
           "Stream-Triggered Rsend (fine)": "tab:red", "Stream-Triggered Send (fine)": "tab:purple"}
PROBLEM = ["System", "Problem Size (GB)"]


def load(paths, with_fine, pool_memory):
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    if not (with_fine or pool_memory):
        df = df[df.Memory == "coarse"]
    df["Label"] = [LABELS[(b, s)] + (" (fine)" if m == "fine" and not pool_memory else "")
                   for b, s, m in zip(df.Backend, df.Buffering, df.Memory)]
    df["System"] = df.System.str.capitalize()
    df["Problem Size (GB)"] = (df.Size ** 2 * 8 / 1e9).round().astype(int)
    df["Ranks"] = df.Nodes * df.PPN
    df["GPUs per Node"] = df.PPN
    # Mean halo edge per rank, in bytes (8 bytes per cell), as the older scripts computed it
    df["Edge Length"] = np.sqrt(df.Size ** 2 / df.Ranks) * 8
    return df


def memory_check(paths):
    """Coarse against fine-grained memory, per ST variant and configuration: mean solve times,
    the difference, and whether their 95% CIs overlap. Answers whether the two can be pooled."""
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    df = df[df.Backend == "cxi"]
    keys = ["System", "Size", "Buffering", "Nodes", "PPN"]
    g = df.groupby(keys + ["Memory"])["SolveTime"].agg(Mean="mean", CI95=sd.ci95, Runs="size").unstack("Memory")
    if "fine" not in g.columns.get_level_values(1) or "coarse" not in g.columns.get_level_values(1):
        raise SystemExit("--memory-check needs both coarse- and fine-grained-memory ST runs")
    g = g.dropna()
    c, f = g.xs("coarse", axis=1, level=1), g.xs("fine", axis=1, level=1)
    out = pd.DataFrame({"Coarse": c.Mean, "Fine": f.Mean, "Fine vs coarse %": 100 * (f.Mean - c.Mean) / c.Mean,
                        "CIs overlap": (c.Mean - c.CI95 <= f.Mean + f.CI95) & (f.Mean - f.CI95 <= c.Mean + c.CI95),
                        "Runs": c.Runs.astype(int).astype(str) + "/" + f.Runs.astype(int).astype(str)})
    pd.set_option("display.max_rows", None)
    print("Coarse- vs fine-grained-memory ST solve time (s), per configuration")
    print(out.round(3).to_string())
    split = (~out["CIs overlap"]).sum()
    print(f"\n{split} of {len(out)} configurations have non-overlapping 95% CIs; "
          f"median difference {out['Fine vs coarse %'].median():+.2f}%, range "
          f"{out['Fine vs coarse %'].min():+.2f}% to {out['Fine vs coarse %'].max():+.2f}%")


def lineplot(data, x, y, out, title, hue="Label", style="Problem Size (GB)", logy=False, ideal=False,
             xlabel=None):
    if data.empty:
        sd.warn(f"no data for {out.name}")
        return
    fig, ax = plt.subplots(figsize=(6.5, 4))
    order = [label for label in PALETTE if label in set(data[hue])]
    sbn.lineplot(data=data, x=x, y=y, hue=hue, hue_order=order, palette=PALETTE, style=style,
                 markers=True, errorbar=("ci", 95), ax=ax)
    ax.set_xscale("log", base=2)
    if logy:
        ax.set_yscale("log", base=2)
    if ideal:
        top = data[x].max()
        ax.plot([1, top], [1, top], "k--", lw=1, label="Ideal")
    if y == "Percent Improvement":
        ax.axhline(0, color="k", lw=0.8)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(True, ls=":")
    sbn.move_legend(ax, "upper left", bbox_to_anchor=(1.02, 1), frameon=False)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    sd.log(f"wrote {out}")


def speedup_by_ppn(data, out, title):
    """Speedup by total ranks, one panel per GPUs-per-node count, log-log with ideal scaling: the
    old scripts' "Speedup-Ranks-GPUs per Node-log-<System>" figure."""
    if data.empty:
        sd.warn(f"no data for {out.name}")
        return
    order = [label for label in PALETTE if label in set(data.Label)]
    grid = sbn.relplot(data=data, kind="line", x="Ranks", y="Speedup", col="GPUs per Node",
                       hue="Label", hue_order=order, palette=PALETTE, style="Problem Size (GB)",
                       markers=True, errorbar=("ci", 95), height=3.5, aspect=1.25)
    top = data.Ranks.max()
    for ax in grid.axes.flat:
        ax.set_xscale("log", base=2)
        ax.set_yscale("log", base=2)
        ax.plot([1, top], [1, top], "k--", lw=1)
        ax.grid(True, ls=":")
    grid.set_titles("{col_name} GPUs per Node")
    grid.figure.suptitle(title, y=1.02)
    grid.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(grid.figure)
    sd.log(f"wrote {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csvs", nargs="+")
    parser.add_argument("--out-dir", type=Path, default=Path("figures/CabanaGhost"))
    parser.add_argument("--base-stat", choices=["min", "mean"], default="min")
    parser.add_argument("--edge-ppn", default="1,2",
                        help="GPUs per node in the edge-length plot (Fig. 9 used 1 and 2 on Tuolumne)")
    parser.add_argument("--with-fine", action="store_true", help="plot fine-grained-memory runs as their own lines")
    parser.add_argument("--pool-memory", action="store_true",
                        help="count fine-grained-memory runs with the coarse ones (the paper's Frontier Table III rows)")
    parser.add_argument("--memory-check", action="store_true",
                        help="only compare coarse- and fine-grained-memory ST solve times, then stop")
    args = parser.parse_args()
    if args.memory_check:
        memory_check(args.csvs)
        return
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = load(args.csvs, args.with_fine, args.pool_memory)
    df, base = sd.add_speedup(df, PROBLEM, CRAY, args.base_stat)
    df = sd.add_percent_improvement(df, PROBLEM, CRAY)

    print(f"Single-GPU {CRAY} solve time (seconds; speedup uses the {args.base_stat}) -- the paper's text "
          "(means): Frontier 90.90 (30 GB) / 6.030 (2 GB), Tuolumne 43.18 / 3.023 (the 2026 data: 3.203)")
    print(base.to_string(), "\n")

    table = sd.best_mean_speedup(df, PROBLEM + ["Label"])
    print("Table III: best mean speedup ± 95% CI half-width [standard deviation], nodes/ranks")
    for _, r in table.iterrows():
        print(f"  {r.System:9} {r['Problem Size (GB)']:>3} GB  {r.Label:24} {r.Mean:8.2f} ± {r.CI95:5.2f}"
              f" [{r.SD:5.2f}]  {r.Nodes}/{r.Ranks}  ({r.Runs} runs)")
    out = args.out_dir / "table3.csv"
    table.to_csv(out, index=False, lineterminator="\n")
    sd.log(f"wrote {out}")

    edge_ppn = [int(p) for p in args.edge_ppn.split(",")]
    for system, sdf in df.groupby("System"):
        st = sdf[sdf.Label != CRAY]
        # Figs. 6 (Frontier) and 7 (Tuolumne)
        lineplot(st, "Ranks", "Percent Improvement", args.out_dir / f"percent-improvement-ranks-{system}.png",
                 f"{system}: speedup vs {CRAY}, by total ranks")
        # Fig. 9
        lineplot(st[st.PPN.isin(edge_ppn)], "Edge Length", "Percent Improvement",
                 args.out_dir / f"percent-improvement-edge-{system}.png",
                 f"{system}: improvement by mean halo edge length ({args.edge_ppn} GPUs/node)",
                 xlabel="Mean halo edge length (bytes)")
        lineplot(sdf, "Ranks", "Speedup", args.out_dir / f"speedup-ranks-{system}.png",
                 f"{system}: strong-scaling speedup", logy=True, ideal=True)
        speedup_by_ppn(sdf, args.out_dir / f"speedup-ranks-ppn-{system}.png",
                       f"{system}: strong-scaling speedup by GPUs per node")
        lineplot(sdf, "Ranks", "Parallel Efficiency", args.out_dir / f"efficiency-ranks-{system}.png",
                 f"{system}: parallel efficiency")
        lineplot(sdf, "Ranks", "Percent Improvement", args.out_dir / f"percent-improvement-ppn-{system}.png",
                 f"{system}: improvement by GPUs per node", style="GPUs per Node")
        lineplot(sdf[sdf["Problem Size (GB)"] == sdf["Problem Size (GB)"].min()], "Ranks", "SetupTime",
                 args.out_dir / f"setup-time-ranks-{system}.png", f"{system}: setup time, smallest problem")


if __name__ == "__main__":
    main()
