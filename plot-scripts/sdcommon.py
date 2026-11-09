"""Helpers shared by the out-to-csv and analysis scripts.

Every run script writes its output the same way: a "Test: ..." line naming one run, that run's
output, then (since the 2026 rewrite) "Exit: <code>". Lines starting with "#" are headers. Older
outputs have no Exit lines; a run then ends at the next Test line or the end of the file.
"""

import csv
import math
import sys
from pathlib import Path

BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"

GPU = {"tuolumne": "MI300", "frontier": "MI250"}


def log(msg):
    print(f"{BLUE}{msg}{RESET}", file=sys.stderr)


def warn(msg):
    print(f"{RED}warning:{RESET} {msg}", file=sys.stderr)


def out_files(paths):
    """The .out files in the given run directories (or the files themselves), sorted."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(p.glob("*.out")))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"{p}: no such file or directory")
    if not files:
        raise SystemExit(f"no .out files in {', '.join(map(str, paths))}")
    return files


def system_of(path):
    """tuolumne / frontier, from an output file's name (TUOLUMNE-2N-r1.out, tuolumne-10-16-....out)."""
    name = Path(path).name.upper()
    for system in GPU:
        if name.startswith(system.upper()) or name.startswith(system[:3].upper() + "-"):
            return system
    raise ValueError(f"can't tell the system from {Path(path).name}: pass --system")


def runs(path):
    """Yield (test_fields, body_lines, exit_code) for each run in an output file.

    exit_code is an int, or None when the file has no Exit line for the run (an older output,
    or a job that was killed mid-run).
    """
    fields, body = None, []
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("Test:"):
                if fields is not None:
                    yield fields, body, None
                fields, body = line.split()[1:], []
            elif line.startswith("Exit:") and fields is not None:
                yield fields, body, int(line.split()[1])
                fields, body = None, []
            elif fields is not None and not line.startswith("#"):
                body.append(line)
    if fields is not None:
        yield fields, body, None


def number(text):
    """A float from output that may carry thousands separators (aCG prints with %')."""
    return float(text.replace(",", ""))


def write_csv(path, fieldnames, rows):
    """Write a new CSV with LF line endings; never overwrite one."""
    path = Path(path)
    if path.exists():
        raise SystemExit(f"{path} already exists: not overwriting it")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    log(f"wrote {len(rows)} rows to {path}")


def ci95(values):
    """Half-width of the two-sided 95% Student-t confidence interval of the mean."""
    from scipy import stats  # only the analysis scripts need scipy; the parsers run on clusters

    n = len(values)
    if n < 2:
        return math.nan
    return stats.t.ppf(0.975, n - 1) * values.std(ddof=1) / math.sqrt(n)


def add_speedup(df, problem, baseline, stat):
    """Add Speedup and Parallel Efficiency columns, against the single-GPU run of one baseline.

    problem: columns that name one strong-scaling problem (e.g. ["System", "Size"]).
    baseline: the Label whose 1-rank solve time is the reference.
    stat: "min" or "mean". The paper's Tables III and IV were computed against the minimum
    single-GPU time (checked against the 2026 data in data/ before it was deleted), although its
    text says the mean; "min" reproduces the tables.
    Returns the per-problem baseline times (mean and min, for the record) as well.
    """
    base_rows = df[(df.Label == baseline) & (df.Ranks == 1)]
    base = base_rows.groupby(problem)["SolveTime"].agg(stat).rename("BaseTime")
    record = base_rows.groupby(problem)["SolveTime"].agg(["mean", "min", "size"])
    missing = df[problem].drop_duplicates().merge(base.reset_index(), how="left")
    missing = missing[missing.BaseTime.isna()]
    if not missing.empty:
        raise SystemExit("no single-GPU " + baseline + " run for:\n" + missing[problem].to_string(index=False))
    df = df.merge(base.reset_index(), on=problem)
    df["Speedup"] = df.BaseTime / df.SolveTime
    df["Parallel Efficiency"] = df.Speedup / df.Ranks
    return df, record


def add_percent_improvement(df, problem, baseline):
    """Percent Improvement: each run's speedup against the baseline's mean speedup on the same
    nodes and ranks (the paper's Figs. 6, 7, 9, 10, 11)."""
    keys = problem + ["Nodes", "Ranks"]
    ref = (df[df.Label == baseline].groupby(keys)["Speedup"].mean()
           .rename("BaselineSpeedup").reset_index())
    df = df.merge(ref, on=keys, how="left")
    df["Percent Improvement"] = 100 * (df.Speedup - df.BaselineSpeedup) / df.BaselineSpeedup
    return df


def best_mean_speedup(df, group):
    """Per group: the nodes/ranks with the highest mean speedup, that mean, its 95% CI half-width
    (the "±" the tables print), its standard deviation (the paper's "±") and the number of runs
    (Tables III, IV)."""
    per = (df.groupby(group + ["Nodes", "Ranks"])["Speedup"]
           .agg(Mean="mean", SD="std", CI95=ci95, Runs="size").reset_index())
    best = per.loc[per.groupby(group)["Mean"].idxmax()]
    return best.reset_index(drop=True)
