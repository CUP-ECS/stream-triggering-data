import argparse
import csv
import os
import re

def main():
    parser = argparse.ArgumentParser(description="Parse solver times from grep output.")
    parser.add_argument('--input', required=True, help='Input grep output file')
    parser.add_argument('--output', required=True, help='Output CSV file')
    parser.add_argument('--dates', type=str, help='Comma separated list of dates to use (format: "<month>-<day>"; default is to grab all)')
    parser.add_argument('--backends', type=str, help='Comma separated list of backends to use (mpi, st, rccl; default is all)')
    
    args = parser.parse_args()

    if(args.dates):
        valid_dates = [item.strip() for item in args.dates.split(',')]
        print("Grabing only these dates:", valid_dates)
    else:
        valid_dates = None

    if(args.backends):
        valid_backends = [item.strip() for item in args.backends.split(',')]
        print("Grabing only these backends:", valid_backends)
    else:
        valid_backends = None


    comm_to_backend = {
        "MPI for": "mpi",
        "alongside ST": "st",
        "RCCL": "rccl"
    }

    # Captures: 1=dir, 2=file, 3=rest_of_line
    line_pattern = re.compile(r'^(.+)/([^:]+):\s*(.*)$')
    
    # Captures just the solver time value
    solver_pattern = re.compile(r'(?:total\s+)?solver time:\s+([\d.]+)\s+seconds')

    # Dictionary to track the *current* active backend for a specific file
    current_backends = {}

    with open(args.output, 'w', newline='') as fout:
        writer = csv.writer(fout)
        writer.writerow(['system', 'nodes', 'ppn', 'matrix', 'backend', 'solver_time'])

        with open(args.input, 'r') as fin:
            for line in fin:
                match = line_pattern.search(line)
                if not match: continue
                
                full_path, file_name, content = match.groups()
                full_file_path = f"{full_path}/{file_name}"

                # -- STATE UPDATE: Check if this is a communication line --
                if "communication" in content:
                    found_backend = False
                    for key, backend_name in comm_to_backend.items():
                        if key in content:
                            current_backends[full_file_path] = backend_name
                            found_backend = True
                            break
                    
                    if not found_backend:
                        # Fallback if a communication line triggered but lacked a known keyword
                        current_backends[full_file_path] = "Unknown_Backend"
                    
                    continue # Move to the next line; nothing to write to CSV yet

                # -- ACTION: Check if this is a solver time line --
                solver_match = solver_pattern.search(content)
                if solver_match:
                    solver_time = solver_match.group(1)
                    
                    dir_name = os.path.basename(os.path.normpath(full_path))
                    system = dir_name.split('-')[0].capitalize()
                    date_str = "-".join(dir_name.split('-')[2:4])
                    day = dir_name.split('-')[3]

                    base = file_name.replace('.out', '')
                    try:
                        matrix, nodes, ppn = base.rsplit('_', 2)
                    except ValueError:
                        continue

                    # Retrieve the most recently seen backend for this file path
                    # Defaults to "No_Backend_Found" if a solver time appears before a communication line
                    backend = current_backends.get(full_file_path, "unknown")

                    ## Manual exclusion zone
                    # Semi-manual exclusions
                    if valid_backends and backend not in valid_backends:
                        print('Excluding (', system, nodes, ppn, matrix, backend, solver_time, backend, ') due to backend exclusion rule match')
                        continue

                    if valid_dates and date_str not in valid_dates:
                        print('Excluding (', system, nodes, ppn, matrix, backend, solver_time, date_str, ') due to date exclusion rule match')
                        continue

                    # For excluing rccl runs with bad data from the extra matricies
                    if backend == 'rccl' and day !='06' and system == 'Tuolumne' and ( matrix == 'guenda11m' or matrix == 'agg14m'):
                        print('Excluding (', system, nodes, ppn, matrix, backend, solver_time,') due to exclusion rule match')
                        continue

                    writer.writerow([system, nodes, ppn, matrix, backend, solver_time])

if __name__ == '__main__':
    main()