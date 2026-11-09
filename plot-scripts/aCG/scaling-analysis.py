#!/usr/bin/env python3
"""aCG strong scaling: the paper's Figs. 8, 10 and 11 and Table IV, from aCG CSVs.

    scaling-analysis.py --times <csv...> [--stats <csv...>] [--out-dir DIR] [--base-stat mean|min]
                        [--matrices A,B,...]

Takes the solver-time (and, for Fig. 10, MPI-statistics) CSVs from aCG/out-to-csv.py. Replaces the
old top_level.py --plot and plot/{plots,plot2}.py. Speedup is against the single-GPU Cray MPICH
(mpi) solve time of the same system and matrix: its minimum by default, which is what the paper's
Table IV used (its text quotes the means; --base-stat mean). The table's "±" is the 95%
Student-t confidence interval of the mean (the paper printed the standard deviation; table4.csv
has both). Percent improvement compares a run's speedup
with a baseline backend's mean speedup on the same nodes and ranks: Cray MPICH for Fig. 10, Cray
MPICH with IPC and eager off (mpi-no-ipc) for Fig. 11.

Writes PNGs and table4.csv to --out-dir, and prints the single-GPU baselines and Table IV.
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sbn  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

LABELS = {"mpi": "Cray MPICH", "mpi-no-ipc": "Cray MPICH (no IPC/eager)", "st": "Stream Send",
          "rccl": "RCCL"}
PALETTE = {"Cray MPICH": "tab:green", "Cray MPICH (no IPC/eager)": "tab:olive", "Stream Send": "tab:blue",
           "RCCL": "tab:red"}
PROBLEM = ["System", "Matrix"]


def load_times(paths, matrices):
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    if matrices:
        df = df[df.Matrix.isin(matrices)]
    unknown = set(df.Backend) - set(LABELS)
    if unknown:
        raise SystemExit(f"unknown backends {sorted(unknown)} (known: {', '.join(LABELS)})")
    df["Label"] = df.Backend.map(LABELS)
    df["System"] = df.System.str.capitalize()
    df["Ranks"] = df.Nodes * df.PPN
    df["GPUs per Node"] = df.PPN
    return df


def mean_message_size(paths, matrices):
    """Per system, nodes, PPN and matrix: the mean over ranks of bytes per message sent (one
    iteration), the x axis of Fig. 10. Ranks that send nothing are left out."""
    st = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    if matrices:
        st = st[st.Matrix.isin(matrices)]
    st["System"] = st.System.str.capitalize()
    st = st[(st.Nodes * st.PPN > 1) & (st.MsgsSentPerIter > 0)]
    st["MsgSize"] = st.BytesSentPerIter / st.MsgsSentPerIter
    # every backend's run of a configuration reports the same pattern; average them per rank first
    per_rank = st.groupby(["System", "Nodes", "PPN", "Matrix", "Rank"])["MsgSize"].mean()
    return per_rank.groupby(level=["System", "Nodes", "PPN", "Matrix"]).mean().rename(
        "Mean Message Size (bytes)").reset_index()


def facet(data, x, y, out, title, col="Matrix", style=None, logx=True, logy=False, ideal=False):
    if data.empty:
        sd.warn(f"no data for {out.name}")
        return
    order = [label for label in PALETTE if label in set(data.Label)]
    g = sbn.relplot(data=data, kind="line", x=x, y=y, col=col, col_wrap=min(4, data[col].nunique()),
                    hue="Label", hue_order=order, palette=PALETTE, style=style, markers=True,
                    errorbar=("ci", 95), height=3.2, aspect=1.1, facet_kws={"sharey": False})
    for ax in g.axes.ravel():
        if logx:
            ax.set_xscale("log", base=2)
        if logy:
            ax.set_yscale("log", base=2)
        if ideal:
            ax.plot([1, data[x].max()], [1, data[x].max()], "k--", lw=1)
        if y == "Percent Improvement":
            ax.axhline(0, color="k", lw=0.8)
        ax.grid(True, ls=":")
    g.figure.suptitle(title, y=1.02)
    g.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(g.figure)
    sd.log(f"wrote {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--times", nargs="+", required=True, help="solver-time CSVs")
    parser.add_argument("--stats", nargs="+", default=[], help="MPI-statistics CSVs (for Fig. 10)")
    parser.add_argument("--out-dir", type=Path, default=Path("figures/aCG"))
    parser.add_argument("--base-stat", choices=["min", "mean"], default="min")
    parser.add_argument("--matrices", help="comma-separated matrices to keep (default: all)")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    matrices = args.matrices.split(",") if args.matrices else None

    df = load_times(args.times, matrices)
    df, base = sd.add_speedup(df, PROBLEM, LABELS["mpi"], args.base_stat)

    print(f"Single-GPU Cray MPICH solve time (seconds; speedup uses the {args.base_stat}) -- the paper's "
          "text (means, Tuolumne): Queen_4147 58.55, Bump_2911 23.09, audikw_1 2.661, Serena 1.742")
    print(base.to_string(), "\n")

    table = sd.best_mean_speedup(df, PROBLEM + ["Label"])
    print("Table IV: best mean speedup ± 95% CI half-width [standard deviation], nodes/ranks")
    for _, r in table.iterrows():
        print(f"  {r.System:9} {r.Matrix:12} {r.Label:26} {r.Mean:7.3f} ± {r.CI95:6.3f}"
              f" [{r.SD:6.3f}]  {r.Nodes}/{r.Ranks}  ({r.Runs} runs)")
    out = args.out_dir / "table4.csv"
    table.to_csv(out, index=False, lineterminator="\n")
    sd.log(f"wrote {out}")

    for system, sdf in df.groupby("System"):
        main_backends = sdf[sdf.Backend.isin(["mpi", "st", "rccl"])]
        # Fig. 8
        facet(main_backends, "Ranks", "Speedup", args.out_dir / f"speedup-ranks-{system}.png",
              f"{system}: aCG strong-scaling speedup", logy=True, ideal=True)
        # Fig. 10
        if args.stats:
            sizes = mean_message_size(args.stats, matrices)
            vs_cray = sd.add_percent_improvement(main_backends, PROBLEM, LABELS["mpi"])
            vs_cray = vs_cray.merge(sizes, on=["System", "Nodes", "PPN", "Matrix"])
            facet(vs_cray[vs_cray.Backend != "mpi"], "Mean Message Size (bytes)", "Percent Improvement",
                  args.out_dir / f"percent-improvement-msgsize-{system}.png",
                  f"{system}: speedup vs Cray MPICH, by mean message size", col="System")
        # Fig. 11
        ablation = sdf[sdf.Backend.isin(["mpi-no-ipc", "st"])]
        if (ablation.Backend == "mpi-no-ipc").any():
            ablation = sd.add_percent_improvement(ablation, PROBLEM, LABELS["mpi-no-ipc"])
            facet(ablation[ablation.Backend == "st"], "Ranks", "Percent Improvement",
                  args.out_dir / f"percent-improvement-no-ipc-{system}.png",
                  f"{system}: Stream Send vs Cray MPICH without IPC and eager", style="GPUs per Node")
        else:
            sd.warn(f"{system}: no mpi-no-ipc runs, so no Fig. 11")


if __name__ == "__main__":
    main()
