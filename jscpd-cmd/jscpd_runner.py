import json
import subprocess
import os
import sys

def run_jscpd(config_path='config.json'):
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)

    file1 = config.get('file1')
    file2 = config.get('file2')
    output_dir = config.get('output_dir', '.jscpd-temp')
    min_lines = config.get('min_lines', 1)
    max_lines = config.get('max_lines', 99999)
    min_tokens = config.get('min_tokens', 30)
    max_size = config.get('max_size', '50mb')

    if not file1 or not file2:
        print("Error: file1 or file2 not specified in config.")
        return

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Construct the jscpd command
    command = [
        "jscpd",
        "--reporters", "json",
        "--output", output_dir,
        "--min-lines", str(min_lines),
        "--max-lines", str(max_lines),
        "--min-tokens", str(min_tokens),
        "--max-size", max_size,
        file1, file2
    ]

    print(f"Executing: {' '.join(command)}")

    try:
        # Run the command
        result = subprocess.run(command, capture_output=True, text=True)
        
        # jscpd might exit with non-zero if duplicates are found, so we don't necessarily check check=True
        # but we should check if the command itself failed to execute.
        if result.returncode != 0 and not result.stdout and result.stderr:
            print(f"Error executing jscpd: {result.stderr}")
            return

        # Path to the JSON report
        report_path = os.path.join(output_dir, 'jscpd-report.json')
        
        if os.path.exists(report_path):
            with open(report_path, 'r') as rf:
                report_data = json.load(rf)
                
            duplicates = report_data.get('duplicates', [])
            
            # Filter duplicates to only include those between different files
            filtered_duplicates = []
            for dup in duplicates:
                file1_name = os.path.normpath(dup['firstFile']['name'])
                file2_name = os.path.normpath(dup['secondFile']['name'])
                if file1_name != file2_name:
                    filtered_duplicates.append(dup)

            # Update report data with filtered duplicates
            report_data['duplicates'] = filtered_duplicates
            
            # Recalculate basic statistics for filtered duplicates
            filtered_duplicated_lines = sum(d['lines'] for d in filtered_duplicates)
            
            filtered_report_path = os.path.join(output_dir, 'filtered-report.json')
            with open(filtered_report_path, 'w') as wf:
                json.dump(report_data, wf, indent=2)

            # Basic summary output
            statistics = report_data.get('statistics', {})
            total = statistics.get('total', {})
            
            print("\n--- Detection Summary (Filtered: Cross-file only) ---")
            print(f"Total lines in both files: {total.get('lines')}")
            print(f"Cross-file duplicated lines: {filtered_duplicated_lines}")
            print(f"Original duplicated lines (including self): {total.get('duplicatedLines')}")
            
            if filtered_duplicates:
                print(f"\nFound {len(filtered_duplicates)} cross-file duplicate blocks.")
                print(f"Filtered report saved to: {filtered_report_path}")
            else:
                print("\nNo cross-file duplicates found.")
        else:
            print(f"Report not found at {report_path}. stdout might contain info.")
            print(result.stdout)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    run_jscpd()
