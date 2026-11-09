#!/usr/bin/env python3
"""Packing ping-pong latency and bandwidth: the paper's Fig. 5, from a PingPong CSV.

    pingpong-analysis.py <csv> [--placement OFF-NODE|ON-NODE|both] [--with-mpi-rsend] [--out-dir DIR]

Each trial (one Run) measured one time per size and test; latency is that time over its
iterations (a round trip), bandwidth bytes moved over time. Lines are the mean over trials with
its 95% Student-t confidence interval, as the paper plots them. The paper's Fig. 5 is OFF-NODE
(two nodes), with Cray MPICH Send against stream-triggered Send and Rsend; raw (no packing
kernel) and no-credit runs are left out. Also prints the latency difference from Cray MPICH Send
per size, to set against the paper's "12-39% (Send) and 12-49% (Rsend) lower, 32 B to 512 KB".
Replaces pingpong-analysis.py and pingpong-analysis2.py.
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

CRAY = "Cray MPICH Send"
SERIES = {("mpi", "sb"): (CRAY, "tab:green", "o"),
          ("mpi", "db"): ("Cray MPICH Rsend", "tab:olive", "s"),
          ("cxi-coarse", "sb"): ("Stream-Triggered Send", "tab:blue", "^"),
          ("cxi-coarse", "db"): ("Stream-Triggered Rsend", "tab:orange", "v"),
          ("ipc", "sb"): ("Direct HIP IPC", "tab:purple", "d")}


def fmt(b):
    for unit, scale in (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if b >= scale:
            return f"{b // scale} {unit}"
    return f"{b} B"


def summarize(df, metric):
    g = df.groupby(["Label", "IPC", "Bytes"])[metric]
    out = pd.DataFrame({"Mean": g.mean(), "CI95": g.agg(sd.ci95), "Trials": g.size()}).reset_index()
    return out


def plot(summary, metric, ylabel, placements, out, max_bytes=None):
    fig, axes = plt.subplots(1, len(placements), figsize=(7 * len(placements), 4.5), squeeze=False)
    for ax, placement in zip(axes[0], placements):
        for label, color, marker in SERIES.values():
            s = summary[(summary.Label == label) & (summary.IPC == placement)].sort_values("Bytes")
            if max_bytes:
                s = s[s.Bytes <= max_bytes]
            if s.empty:
                continue
            ax.plot(s.Bytes, s.Mean, color=color, marker=marker, ms=4, label=label)
            ax.fill_between(s.Bytes, s.Mean - s.CI95, s.Mean + s.CI95, color=color, alpha=0.2, lw=0)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ticks = [b for b in sorted(summary.Bytes.unique())[::3] if not max_bytes or b <= max_bytes]
        ax.set_xticks(ticks, [fmt(b) for b in ticks], rotation=35, ha="right")
        ax.minorticks_off()
        ax.yaxis.set_major_locator(LogLocator(subs=(1, 2, 5)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.grid(True, ls=":")
        ax.set_title(placement.lower())
        ax.set_xlabel("Message size")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    sd.log(f"wrote {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv")
    parser.add_argument("--placement", choices=["OFF-NODE", "ON-NODE", "both"], default="OFF-NODE")
    parser.add_argument("--with-mpi-rsend", action="store_true", help="also plot Cray MPICH Rsend")
    parser.add_argument("--max-latency-size", type=int, default=2**20,
                        help="largest message (bytes) on the latency plot (default 1 MiB)")
    parser.add_argument("--out-dir", type=Path, default=Path("figures/PingPong"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    if "IPC" not in df:  # the SC-paper CSVs predate the column; those runs were all off-node
        sd.warn(f"{args.csv} has no IPC column: taking every row as OFF-NODE")
        df["IPC"] = "OFF-NODE"
    df = df[[(b, s) in SERIES for b, s in zip(df.Backend, df.Buffering)]].copy()
    if not args.with_mpi_rsend:
        df = df[~((df.Backend == "mpi") & (df.Buffering == "db"))]
    df["Label"] = [SERIES[(b, s)][0] for b, s in zip(df.Backend, df.Buffering)]
    df["Bytes"] = df.Items * 4
    df["Latency"] = df.Time / df.Iters * 1e6
    df["Bandwidth"] = df.Iters * 2 * df.Bytes / df.Time / 2**30
    placements = ["ON-NODE", "OFF-NODE"] if args.placement == "both" else [args.placement]

    stem = Path(args.csv).stem
    for gpu, gdf in df.groupby("GPU"):
        lat = summarize(gdf, "Latency")
        bw = summarize(gdf, "Bandwidth")
        plot(lat, "Latency", "Round-trip latency (µs)", placements,
             args.out_dir / f"pingpong-latency-{gpu}-{stem}.png", args.max_latency_size)
        plot(bw, "Bandwidth", "Bandwidth (GiB/s)", placements,
             args.out_dir / f"pingpong-bandwidth-{gpu}-{stem}.png")

        for placement in placements:
            table = lat[lat.IPC == placement].pivot(index="Bytes", columns="Label", values="Mean")
            if CRAY not in table:
                continue
            print(f"\n{gpu} {placement}: latency difference from {CRAY} (%; negative is faster)")
            diff = table.drop(columns=CRAY).sub(table[CRAY], axis=0).div(table[CRAY], axis=0) * 100
            diff.index = [fmt(b) for b in diff.index]
            print(diff.round(1).to_string())


if __name__ == "__main__":
    main()
