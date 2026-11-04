#!/usr/bin/env python3
# Compare two sets of PingPong runs (e.g. a library patch against develop) on one machine.
# Example (from this directory):
# python3 pingpong-compare.py --new ../../data/PingPong/TUOLUMNE/2026-10-16-patch1.csv --new-label patch1 \
#     --base ../../data/PingPong/TUOLUMNE/2026-10-15-develop.csv --base-label develop --stat both

from pathlib import Path

import argparse
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# Two-sided 95% Student t critical values, keyed by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
       10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 19: 2.093, 24: 2.064, 29: 2.045}

# (Backend, Buffering), label, color, marker
series = [
    (("cxi-coarse", "sb"), "Stream-Triggered Send", "#e8710a", "^"),
    (("cxi-coarse", "db"), "Stream-Triggered Rsend", "#e8710a", "s"),
    (("mpi", "sb"), "Cray MPICH Send", "#2ca02c", "^"),
    (("mpi", "db"), "Cray MPICH Rsend", "#2ca02c", "s"),
    (("ipc", "sb"), "Direct HIP IPC", "#1f6fde", "^"),
]

def parse_arguments():
    data = "../../data/PingPong/TUOLUMNE/"
    parser = argparse.ArgumentParser(description="Plot PingPong latency/bandwidth of one set of runs against another.")
    parser.add_argument("--new", default=data + "2026-10-16-patch1.csv", help="CSV of the runs being tested")
    parser.add_argument("--new-label", default="patch1")
    parser.add_argument("--base", default=data + "2026-10-15-develop.csv", help="CSV of the baseline runs")
    parser.add_argument("--base-label", default="develop")
    parser.add_argument("--stat", choices=["median", "mean", "both"], default="both",
                        help="median (IQR band) or mean (95%% CI band); both makes both sets of plots")
    parser.add_argument("--one-way", action="store_true",
                        help="One-way latency (half round trip) and GB/s, instead of round-trip latency and GiB/s")
    parser.add_argument("--max-latency-size", type=int, default=8 * 2**20,
                        help="Largest message size (bytes) on the latency plots")
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    return parser.parse_args()

def load(csv_file, one_way):
    df = pd.read_csv(csv_file)
    # Filter out raw (no stream-triggering library) and any special runs
    df = df[df.Buffering != "raw"]
    df = df[df.Backend != "cxi-coarse-no-credit"]
    df["Buffer Size"] = df["Items"] * 4
    # Bandwidth is bytes per one-way trip in both modes; only the unit changes
    df["Latency"] = df["Time"] / df["Iters"] * 1e6 / (2 if one_way else 1)
    df["Bandwidth"] = df["Iters"] * 2 * df["Buffer Size"] / df["Time"] / (1e9 if one_way else 2**30)
    return df

def summarize(df, metric, stat):
    """Per (Backend, Buffering, IPC, Buffer Size): centre, band low, band high, run count."""
    g = df.groupby(["Backend", "Buffering", "IPC", "Buffer Size"])[metric]
    if stat == "median":
        out = pd.DataFrame({"centre": g.median(), "lo": g.quantile(0.25), "hi": g.quantile(0.75), "n": g.size()})
    else:
        out = pd.DataFrame({"centre": g.mean(), "sd": g.std(), "n": g.size()})
        missing = set(out.n - 1) - T95.keys()
        if missing:
            raise ValueError(f"No t value for degrees of freedom {missing}; add it to T95")
        half = out.n.map(lambda n: T95[n - 1]) * out.sd / out.n ** 0.5
        out["lo"], out["hi"] = out.centre - half, out.centre + half
    return out.reset_index()

def fmt(b):
    for u, s in (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if b >= s:
            return f"{b // s} {u}"
    return f"{b} B"

def plot(sets, metric, stat, args, machine, fname):
    new_runs = sets[args.new_label][1]
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), sharey=True)
    for ax, loc, lt in zip(axes, ("ON-NODE", "OFF-NODE"), ("On-node", "Off-node")):
        for (backend, buffering), label, c, mk in series:
            for name, ls, fill, alpha in ((args.base_label, "--", "none", 0.55), (args.new_label, "-", c, 1.0)):
                s = sets[name][0]
                s = s[(s.Backend == backend) & (s.Buffering == buffering) & (s.IPC == loc)].sort_values("Buffer Size")
                if metric == "Latency":
                    s = s[s["Buffer Size"] <= args.max_latency_size]
                if s.empty:
                    continue
                if name == args.new_label:  # IQR (median) or 95% CI of the mean, across the new runs
                    ax.fill_between(s["Buffer Size"], s.lo, s.hi, color=c, alpha=0.18, lw=0)
                ax.plot(s["Buffer Size"], s.centre, ls=ls, color=c, marker=mk, mfc=fill, alpha=alpha, ms=5, lw=1.6)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        top = args.max_latency_size if metric == "Latency" else 2**30
        ticks = [2**e for e in range(5, 31, 2 if metric == "Latency" else 3) if 2**e <= top]
        ax.set_xticks(ticks, [fmt(x) for x in ticks], rotation=35, ha="right")
        ax.minorticks_off()
        ax.yaxis.set_minor_locator(matplotlib.ticker.LogLocator(subs="all"))
        ax.grid(True, which="major", color="#ddd")
        ax.grid(True, which="minor", axis="y", color="#f0f0f0")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_title(f"Standard - {lt}", fontsize=13)
        ax.set_xlabel("Message size")
    if metric == "Latency":
        axes[0].set_ylabel("One-way latency (µs, half round-trip)" if args.one_way else "Round-trip latency (µs)")
    else:
        axes[0].set_ylabel(f"Bandwidth ({'GB' if args.one_way else 'GiB'}/s, bytes / one-way latency)")
    handles = [Line2D([], [], color=c, marker=mk, label=label) for _, label, c, mk in series]
    band = "interquartile range" if stat == "median" else "95% CI of the mean"
    handles += [Line2D([], [], color="#444", ls="-", label=f"{args.new_label} (solid, filled)"),
                Line2D([], [], color="#888", ls="--", marker="o", mfc="none", label=f"{args.base_label} (dashed, hollow)"),
                Patch(color="#444", alpha=0.18, label=f"{args.new_label} {band} ({new_runs} runs)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=11)
    what = f"latency (up to {fmt(args.max_latency_size)})" if metric == "Latency" else "bandwidth"
    fig.suptitle(f"{machine} ping-pong {what} - {stat}s, {args.new_label} ({new_runs} runs) "
                 f"vs {args.base_label} ({sets[args.base_label][1]} runs)", fontsize=15)
    fig.tight_layout(rect=(0, 0.12, 1, 0.96))
    fig.savefig(args.out_dir / fname, dpi=150)
    plt.close(fig)

def main():
    args = parse_arguments()
    if args.new_label == args.base_label:
        raise SystemExit("--new-label and --base-label must differ")
    machine = Path(args.new).parent.name.capitalize()
    data = {args.new_label: load(args.new, args.one_way), args.base_label: load(args.base, args.one_way)}
    runs = {name: df.Run.nunique() if "Run" in df else "?" for name, df in data.items()}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for stat in (["median", "mean"] if args.stat == "both" else [args.stat]):
        suffix = "-mean" if stat == "mean" else ""
        for metric, kind in (("Latency", "latency"), ("Bandwidth", "bandwidth")):
            sets = {name: (summarize(df, metric, stat), runs[name]) for name, df in data.items()}
            plot(sets, metric, stat, args, machine, f"pingpong-compare-{kind}{suffix}-{args.new_label}.png")

if __name__ == "__main__":
    main()
