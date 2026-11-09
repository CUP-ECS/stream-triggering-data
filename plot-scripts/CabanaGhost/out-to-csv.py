#!/usr/bin/env python3
"""Turn CabanaGhost output files into a CabanaGhost CSV.

    out-to-csv.py <run dir or .out files...> <output.csv> [--system NAME]

Reads run-scripts/cabana-ghost-job.sh output. Columns:
    System,GPU,Backend,Buffering,Memory,Nodes,PPN,Size,Iters,SetupTime,SolveTime,Run
Backend is cxi (stream triggering) or mpi (Cray MPICH); Buffering sb (Send) or db (Rsend); Memory
coarse or fine; Size is gol's -n; SetupTime and SolveTime are gol's "Solver creation time" and
"Solver solve time" (seconds); Run is the output file's name without .out. Runs that failed or
never finished are reported and left out.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

FIELDS = ["System", "GPU", "Backend", "Buffering", "Memory", "Nodes", "PPN", "Size", "Iters",
          "SetupTime", "SolveTime", "Run"]


def timing(body, label):
    values = [line.split(":", 1)[1].strip() for line in body if line.startswith(label)]
    return values[0] if len(values) == 1 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="run directories or .out files, then the CSV to write")
    parser.add_argument("--system", choices=sorted(sd.GPU), help="default: from the file names")
    args = parser.parse_args()
    if len(args.inputs) < 2:
        parser.error("need at least one input and the output CSV")
    *inputs, output = args.inputs

    rows, failed = [], 0
    for path in sd.out_files(inputs):
        sd.log(f"reading {path}")
        system = args.system or sd.system_of(path)
        for fields, body, code in sd.runs(path):
            if len(fields) != 7:
                raise SystemExit(f"{path}: unexpected Test line: {' '.join(fields)}")
            backend, buffering, memory, nodes, ppn, size, iters = fields
            setup = timing(body, "Solver creation time:")
            solve = timing(body, "Solver solve time:")
            if code not in (0, None) or setup is None or solve is None:
                sd.warn(f"{path.name}: {' '.join(fields)} -- exit {code}, setup {setup}, solve {solve}: left out")
                failed += 1
                continue
            rows.append({"System": system, "GPU": sd.GPU[system], "Backend": backend,
                         "Buffering": buffering, "Memory": memory, "Nodes": nodes, "PPN": ppn,
                         "Size": size, "Iters": iters, "SetupTime": setup, "SolveTime": solve,
                         "Run": path.stem})
    sd.write_csv(output, FIELDS, rows)
    if failed:
        sd.warn(f"{failed} run(s) left out")


if __name__ == "__main__":
    main()
