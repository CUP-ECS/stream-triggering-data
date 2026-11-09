#!/usr/bin/env python3
"""Turn aCG output files into the aCG solver-time and MPI-statistics CSVs.

    out-to-csv.py <run dir or .out files...> --times <times.csv> --stats <stats.csv> [--system NAME]

Reads run-scripts/acg-job.sh output (replaces the old top_level.py --parse and parse/*.py). Columns:
    times: System,GPU,Backend,Nodes,PPN,Matrix,SolveTime,Run
    stats: System,Nodes,PPN,Matrix,Rank,MsgsSentPerIter,MsgsRecvPerIter,BytesSentPerIter,
           BytesRecvPerIter,TotalBytesSent,TotalBytesRecv,Backend,Run
Backend is mpi, mpi-no-ipc, st or rccl; SolveTime is aCG's "total solver time" (seconds); Run is
the output file's name without .out. Runs that failed or never finished are reported and left out.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

TIME_FIELDS = ["System", "GPU", "Backend", "Nodes", "PPN", "Matrix", "SolveTime", "Run"]
STAT_FIELDS = ["System", "Nodes", "PPN", "Matrix", "Rank", "MsgsSentPerIter", "MsgsRecvPerIter",
               "BytesSentPerIter", "BytesRecvPerIter", "TotalBytesSent", "TotalBytesRecv",
               "Backend", "Run"]

SOLVER_TIME = re.compile(r"total solver time:\s+([\d.,]+)\s+seconds")
# "rank  3 sends 1,234 B 56 B/it in 78 msg 9 msg/it max 10 B/msg" (and "receives")
STAT = re.compile(r"rank\s+(\d+)\s+(sends|receives)\s+([\d,]+)\s+B\s+([\d,]+)\s+B/it.*?\s([\d,]+)\s+msg/it")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="run directories or .out files")
    parser.add_argument("--times", required=True, help="solver-time CSV to write")
    parser.add_argument("--stats", required=True, help="MPI-statistics CSV to write")
    parser.add_argument("--system", choices=sorted(sd.GPU), help="default: from the file names")
    args = parser.parse_args()
    for out in (args.times, args.stats):
        if Path(out).exists():
            raise SystemExit(f"{out} already exists: not overwriting it")

    times, stats, failed = [], [], 0
    for path in sd.out_files(args.inputs):
        sd.log(f"reading {path}")
        system = args.system or sd.system_of(path)
        for fields, body, code in sd.runs(path):
            if len(fields) != 4:
                raise SystemExit(f"{path}: unexpected Test line: {' '.join(fields)}")
            backend, nodes, ppn, matrix = fields
            solve = [m.group(1) for m in map(SOLVER_TIME.search, body) if m]
            if code not in (0, None) or not solve:
                sd.warn(f"{path.name}: {' '.join(fields)} -- exit {code}, no solver time: left out")
                failed += 1
                continue
            if len(solve) > 1:
                sd.warn(f"{path.name}: {' '.join(fields)} -- {len(solve)} solver times, using the first")
            times.append({"System": system, "GPU": sd.GPU[system], "Backend": backend,
                          "Nodes": nodes, "PPN": ppn, "Matrix": matrix,
                          "SolveTime": sd.number(solve[0]), "Run": path.stem})
            per_rank = {}
            for m in filter(None, map(STAT.search, body)):
                rank, action, total, per_it, msgs = m.groups()
                row = per_rank.setdefault(rank, {
                    "System": system, "Nodes": nodes, "PPN": ppn, "Matrix": matrix, "Rank": rank,
                    "Backend": backend, "Run": path.stem})
                key = "Sent" if action == "sends" else "Recv"
                row[f"Msgs{key}PerIter"] = int(sd.number(msgs))
                row[f"Bytes{key}PerIter"] = int(sd.number(per_it))
                row[f"TotalBytes{key}"] = int(sd.number(total))
            stats.extend(per_rank.values())
    sd.write_csv(args.times, TIME_FIELDS, times)
    sd.write_csv(args.stats, STAT_FIELDS, stats)
    if failed:
        sd.warn(f"{failed} run(s) left out")


if __name__ == "__main__":
    main()
