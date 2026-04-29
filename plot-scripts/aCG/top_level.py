import argparse
import subprocess
import os

## Example usages:
# For parsing only:
# python3 top_level.py --parse --input-dir=${HOME}/git/aCG/run/outputs --csv-dir=../../data/aCG/
# For plotting only:
# python3 top_level.py --plot --csv-dir=../../data/aCG/ --plot-dir=figs --matrix-filter=Serena,Bump_2911,Queen_4147,audikw_1


def main():
    ### Define parameters script can accept
    parser = argparse.ArgumentParser(
        description="Run greps, generate CSVs from MPI logs, and/or plot them."
    )

    parser.add_argument(
        "--parse",
        action="store_true",
        help="Toggle to parse input files and create CSV files.",
    )
    parser.add_argument(
        "--plot", action="store_true", help="Toggle to create plots from CSV files."
    )

    parser.add_argument(
        "--input-dir",
        help="Directory containing the MPI output folders. (Required if --parse)",
    )
    parser.add_argument(
        "--csv-dir",
        help="Directory to save/read the CSV files. (Required if --parse or --plot)",
    )
    parser.add_argument(
        "--plot-dir", help="Directory to save the resulting plots. (Required if --plot)"
    )

    parser.add_argument(
        "--matrix-filter",
        help="Comma separated list of matrices to show in plots. Does nothing if --plot is not used.",
    )
    args = parser.parse_args()

    ###  Validate input options
    # Ensure the user selects at least one action
    if not args.parse and not args.plot:
        parser.error("No action requested. Please specify --parse, --plot, or both.")

    # Validate --parse requirements
    if args.parse:
        if not args.input_dir or not args.csv_dir:
            parser.error("--parse requires both --input-dir and --csv-dir.")

    # Validate --plot requirements
    if args.plot:
        if not args.csv_dir or not args.plot_dir:
            parser.error("--plot requires both --csv-dir and --plot-dir.")

    ### Run code for parsing output files and creating CSVs
    if args.parse:
        os.makedirs(args.csv_dir, exist_ok=True)

        # Figure out system
        cluster_name = os.getenv("LCSCHEDCLUSTER") or os.getenv("LMOD_SYSTEM_NAME")

        if not cluster_name:
            raise RuntimeError(
                "Unable to determine cluster from environment variables, stopping."
            )

        cluster_name = cluster_name.upper()

        # Make directory for files
        directory_location = os.path.join(args.csv_dir, cluster_name)
        subprocess.run(["mkdir", "-p", directory_location])

        # Temporary files for grep routing
        stats_grep_out = os.path.join(directory_location, "temp_stats.txt")
        times_grep_out = os.path.join(directory_location, "temp_times.txt")

        # Final outputs
        stats_csv = os.path.join(directory_location, "mpi_stats.csv")
        times_csv = os.path.join(directory_location, "solver_times.csv")

        print(f"Running grep for MPI statistics in {args.input_dir}...")
        with open(stats_grep_out, "w") as f:
            subprocess.run(
                ["grep", "-r", "-E", "sends|receives", args.input_dir], stdout=f
            )

        print(f"Running grep for solver times in {args.input_dir}...")
        with open(times_grep_out, "w") as f:
            subprocess.run(
                ["grep", "-r", "-E", "communication|solver time: ", args.input_dir],
                stdout=f,
            )

        print("Parsing statistics to CSV...")
        subprocess.run(
            [
                "python3",
                "parse/parse_stats.py",
                "--input",
                stats_grep_out,
                "--output",
                stats_csv,
            ]
        )

        print("Parsing solver times to CSV...")
        subprocess.run(
            [
                "python3",
                "parse/parse_times.py",
                "--input",
                times_grep_out,
                "--output",
                times_csv,
            ]
        )

        # Clean up intermediate text files
        if os.path.exists(stats_grep_out):
            os.remove(stats_grep_out)
        if os.path.exists(times_grep_out):
            os.remove(times_grep_out)

        print(f"Done! CSV files saved in {os.path.abspath(directory_location)}:")
        print(f"  - {os.path.basename(stats_csv)}")
        print(f"  - {os.path.basename(times_csv)}")

    ### Run code for creating plots
    if args.plot:
        ## Check if matrix selection present:
        if args.matrix_filter:
            matrix_flag = f"{args.matrix_filter}"
        else:
            matrix_flag = "all"

        ## Figure out which systems have data present:
        unique_prefixes = set()
        for filename in os.listdir(args.csv_dir):
            # Check if it's a file to avoid accidentally splitting directory names
            if os.path.isdir(os.path.join(args.csv_dir, filename)):
                a_part = filename.capitalize()
                unique_prefixes.add(a_part)
        comma_separated_systems = ",".join(sorted(unique_prefixes))
        print(f"Creating plots for {comma_separated_systems}...")
        os.makedirs(args.plot_dir, exist_ok=True)
        subprocess.run(
            [
                "python3",
                "plot/plots.py",
                "--csv-dir",
                args.csv_dir,
                "--plot-dir",
                args.plot_dir,
                "--systems",
                comma_separated_systems,
                "--matrix-filter",
                matrix_flag,
            ]
        )
        subprocess.run(
            [
                "python3",
                "plot/plot2.py",
                "--csv-dir",
                args.csv_dir,
                "--plot-dir",
                args.plot_dir,
                "--systems",
                comma_separated_systems,
                "--matrix-filter",
                matrix_flag,
            ]
        )
        print(f"Done! Plots saved in {os.path.abspath(args.plot_dir)}")


if __name__ == "__main__":
    main()
