# stream-triggering-data

Scripts and data for the experiments in the stream-triggering (ST) papers: the packing ping-pong
benchmark, CabanaGhost halo-exchange strong scaling, and aCG CG-solver strong scaling. The repository
only holds what new runs need. Older scripts and data (the SC and CLUSTER submissions, Tioga) are
in git history: `git log --diff-filter=D --name-only` lists what was removed, and
`git show a5ac4fd:<path>` brings back a file as it was before the 2026 clean-up.

Runs are normally driven from the ST-project-testing meta repository (`scripts/build.sh`,
`scripts/run.sh` and `scripts/collect.sh`), which calls everything below with its own `repos/`
checkouts. Everything here also works on its own.

## Layout

| Path | What it is |
|---|---|
| `systems/<system>.modules` | The software stack: one module list per system, loaded for every build and every job |
| `systems/<system>.sh` | Per-system settings (GPU architecture, compilers, libfabric, scheduler, install prefix) and the launch and submit functions. Tuolumne is tested. Frontier is a draft until Phase 5 |
| `systems/versions.sh` | Pinned third-party sources (Silo, Kokkos, aws-ofi-nccl) and where the ST repositories come from |
| `systems/common.sh` | Helpers shared by everything above (cloning, logging, manifests, dry runs) |
| `systems/metis-spack.yaml` | METIS for aCG on Tuolumne, through Spack |
| `build-scripts/build.sh` | Builds the stack into one prefix and writes `<prefix>/manifest.txt` |
| `run-scripts/submit.sh` | Submits one experiment (one job per node count per repeat) |
| `run-scripts/presets.sh` | What `smoke` and `full` mean for each experiment and system |
| `run-scripts/<experiment>-job.sh` | The batch job of each experiment |
| `plot-scripts/<Exp>/out-to-csv.py` | Run directory to CSV |
| `plot-scripts/<Exp>/*-analysis.py` | CSV to the paper's figures and tables. `PingPong/pingpong-compare.py` plots one set of runs against another |
| `data/<Exp>/<SYSTEM>/` | The CSVs, each with the build manifest and run info it came from |

## Build

```bash
build-scripts/build.sh -s tuolumne [-p prefix] [-g dir-with-the-ST-repos] [component...]
```
The components are `silo kokkos st cabana cabanaghost acg pingpong` (the default), plus `ofi-nccl`,
which is opt-in. Third-party sources are cloned under `<prefix>/src` at the pinned commits. Our own
repositories are built in place from `-g` (default `$HOME/git`), and missing ones are cloned. aCG
needs METIS (`METIS_DIR`, default `<prefix>/metis`; see `systems/metis-spack.yaml`).
`SD_DRY_RUN=1` prints every command instead of running it.

## Run, collect, plot

```bash
run-scripts/submit.sh -s tuolumne -x cabana-ghost -P smoke [-l label]
#   -> outputs/CabanaGhost/TUOLUMNE/<date>-smoke/{*.out, manifest.txt, run-info.txt, logs/}
python3 plot-scripts/CabanaGhost/out-to-csv.py outputs/CabanaGhost/TUOLUMNE/<label> data/CabanaGhost/TUOLUMNE/<label>.csv
python3 plot-scripts/CabanaGhost/scaling-analysis.py data/CabanaGhost/TUOLUMNE/<label>.csv --out-dir figures/
```
`outputs/` and `*.png` are gitignored. Commit the CSV together with the run's `manifest.txt` and
`run-info.txt`, renamed to `<label>.manifest.txt` and `<label>.run-info.txt` (the meta repo's
`scripts/collect.sh` does this), so every CSV can be traced to the commits and modules it was built
from. The parsers need only python3's standard library, so they can run on the cluster. The
analysis scripts need `plot-scripts/python-requirements.txt`.

Every job writes, for each run, a `Test: ...` line, the program's output, and then `Exit: <code>`.
The parsers report runs that failed or never finished and leave them out.

## CSV formats

All columns are PascalCase, lines end in LF, there's one file per batch of runs, and existing files
are never overwritten.

| Experiment | Columns |
|---|---|
| PingPong | `GPU,Backend,Buffering,IPC,Iters,Items,Time,Run` (Time: seconds for all round trips; Items: ints) |
| CabanaGhost | `System,GPU,Backend,Buffering,Memory,Nodes,PPN,Size,Iters,SetupTime,SolveTime,Run` |
| aCG times | `System,GPU,Backend,Nodes,PPN,Matrix,SolveTime,Run` |
| aCG MPI stats | `System,Nodes,PPN,Matrix,Rank,MsgsSentPerIter,MsgsRecvPerIter,BytesSentPerIter,BytesRecvPerIter,TotalBytesSent,TotalBytesRecv,Backend,Run` |

Backends: PingPong `cxi-coarse`, `cxi-fine`, `cxi-coarse-no-credit`, `mpi`, `ipc` (raw runs have
Buffering `raw`). CabanaGhost `cxi` or `mpi`, with Buffering `sb` (Send) or `db` (Rsend) and Memory
`coarse` or `fine`. aCG `mpi`, `mpi-no-ipc` (Cray MPICH with GPU IPC and the eager protocol off),
`st` and `rccl`.

## How the tables are computed

Speedup is against the **minimum** single-GPU Cray MPICH solve time. That's how the paper's Tables III
and IV were computed (they reproduce exactly from the 2026 data, `git show a5ac4fd:data/...`),
although its text says the mean (`--base-stat mean`). The tables print mean ± **95% CI**. The paper
printed the standard deviation, which is kept in `table3.csv`/`table4.csv`. For fine-grained memory
(Frontier), compare it once against coarse (`CabanaGhost/scaling-analysis.py --memory-check`), then
pool the two (`--pool-memory`, as the paper's Frontier rows did) or leave fine out.
