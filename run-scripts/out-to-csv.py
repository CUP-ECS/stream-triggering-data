#!/usr/bin/env python3

from pathlib import Path

import argparse
import csv
import statistics

reset = "\033[0m"
blue  = "\033[94m"

def parse_directory(dir_to_parse, cluster, writer):
    for entry in dir_to_parse.iterdir():
        if entry.is_file():
            print(f"{blue}Found: {reset}{entry}")

            nodes = entry.name.split("-")[1]

            tests = []
            start_lines = []
            solve_lines = []
            with open(entry, 'r') as file:
                for line in file:
                    if "Solver creation time" in line:
                        start_lines.append(line.split(":")[1].strip())
                    elif "Solver solve time" in line:
                        solve_lines.append(line.split(":")[1].strip())
                    elif "Total Simulation Time:" in line:
                        num_cycles = line.split(":")[1].strip()
                    elif "Test:" in line:
                        tests.append(line.split(":")[1].strip())

            if len(tests) != len(start_lines) and len(start_lines) != len(solve_lines):
                print("Sizes not the same!")
                exit(1)
            
            lines_written = 0
            line_dictionary = {"system":cluster.lower(), "nodes":nodes, "cycles":num_cycles}
            for test_data, start_time, solve_time in zip(tests, start_lines, solve_lines):
                test_data = ( test_data.replace("MPI Advance", "MPIAdvance-CXI")
                                       .replace("Single ", "Single-")
                                       .replace("Double ", "Double-")
                                       .replace("grained ", "grained-")
                                       .replace("MPI ", "Cray-MPICH-CXI-GPU-Enabled ")
                                       .replace("MPIAdvance-CXI Single",
                                                "MPIAdvance-CXI-Single-Buffering Single")
                                       .replace("MPIAdvance-CXI Double",
                                                "MPIAdvance-CXI-Double-Buffering Double")
                            )

                backend, buffer_type, nodes, ppn, buff_size = test_data.split(" ")
                line_dictionary["ntasks"] = ppn
                line_dictionary["backend"] = backend
                if "Fine" in buffer_type:
                    line_dictionary["memory_type"] = "fine"
                else:
                    line_dictionary["memory_type"] = "coarse"
                if "Double" in buffer_type:
                    line_dictionary["send_type"] = "Ready Send"
                else:
                    line_dictionary["send_type"] = "Standard"
                line_dictionary["solver_creation"] = start_time
                line_dictionary["solver_time"] = solve_time
                line_dictionary["size"] = buff_size
                writer.writerow(line_dictionary)
                lines_written+=1
            print(f"{blue}Lines added: {reset}{lines_written}")

def main():
    # CSV fields
    fieldnames = ["nodes", "ntasks", "backend",
                    "solver_creation", "solver_time", "system",
                    "size", "memory_type", "send_type", "cycles"]

    dir_to_search = Path(".")

    for entry in dir_to_search.iterdir():
        if entry.is_dir():
            device = entry.name
            data_folder = entry/"outputs"
            if(data_folder.exists()):
                outfile = f"../data/{entry.name}/scaling-data.csv"
                print(f"{blue}Found: {reset}{data_folder} - {blue}Making: {reset}{outfile}")
                with open(outfile, 'a') as output:
                    writer=csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()

                    parse_directory(data_folder, device, writer)


if __name__ == "__main__":
    main()

