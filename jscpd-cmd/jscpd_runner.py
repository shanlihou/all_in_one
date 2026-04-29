import json
import subprocess
import os
import html

def generate_html_report(report_data, output_path):
    """Generates a simple, styled HTML report from the filtered jscpd data."""
    duplicates = report_data.get('duplicates', [])
    statistics = report_data.get('statistics', {})
    total = statistics.get('total', {})
    
    # Calculate filtered stats
    filtered_lines = sum(d['lines'] for d in duplicates)
    filtered_count = len(duplicates)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>jscpd Cross-File Duplicate Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }}
        h1, h2 {{ color: #2c3e50; }}
        .summary {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }}
        .duplicate-block {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; border-left: 5px solid #e74c3c; }}
        .file-info {{ font-weight: bold; margin-bottom: 10px; display: flex; justify-content: space-between; }}
        .file-path {{ color: #2980b9; }}
        pre {{ background: #2d3436; color: #dfe6e9; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 14px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 15px; }}
        .stat-item {{ background: #ecf0f1; padding: 10px; border-radius: 4px; text-align: center; }}
        .stat-value {{ display: block; font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .stat-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
        .no-duplicates {{ text-align: center; padding: 40px; background: #fff; border-radius: 8px; color: #7f8c8d; }}
    </style>
</head>
<body>
    <h1>jscpd Detection Report</h1>
    
    <div class="summary">
        <h2>Summary (Cross-File Only)</h2>
        <div class="stats-grid">
            <div class="stat-item">
                <span class="stat-value">{total.get('lines', 0)}</span>
                <span class="stat-label">Total Lines Scanned</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{filtered_lines}</span>
                <span class="stat-label">Duplicated Lines</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{filtered_count}</span>
                <span class="stat-label">Duplicate Blocks</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{total.get('percentage', 0)}%</span>
                <span class="stat-label">Total Duplication %</span>
            </div>
        </div>
    </div>

    <h2>Duplicates Details</h2>
    """

    if not duplicates:
        html_content += '<div class="no-duplicates"><h3>No cross-file duplicates found.</h3></div>'
    else:
        for i, dup in enumerate(duplicates):
            f1 = dup['firstFile']
            f2 = dup['secondFile']
            # Escape code fragment for HTML
            fragment = html.escape(dup.get('fragment', 'Code fragment not available'))
            
            html_content += f"""
    <div class="duplicate-block">
        <div class="file-info">
            <span>#{i+1} - {dup['lines']} lines ({dup['tokens']} tokens)</span>
        </div>
        <div class="file-info">
            <span class="file-path">{f1['name']}</span>
            <span>Lines {f1['start']}-{f1['end']}</span>
        </div>
        <div class="file-info">
            <span class="file-path">{f2['name']}</span>
            <span>Lines {f2['start']}-{f2['end']}</span>
        </div>
        <pre><code>{fragment}</code></pre>
    </div>
    """

    html_content += """
</body>
</html>
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

def run_jscpd(config_path='config.json'):
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)

    base_dirs = config.get('base_dirs', [])
    asset_path = config.get('asset_path', '')
    output_dir = config.get('output_dir', '.jscpd-temp')
    min_lines = config.get('min_lines', 1)
    max_lines = config.get('max_lines', 99999)
    min_tokens = config.get('min_tokens', 30)
    max_size = config.get('max_size', '50mb')

    if not base_dirs or not asset_path:
        print("Error: base_dirs or asset_path not specified in config.")
        return

    file1 = os.path.join(base_dirs[0], asset_path)
    file2 = os.path.join(base_dirs[1], asset_path)

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
            
            # Save filtered JSON
            filtered_report_path = os.path.join(output_dir, 'filtered-report.json')
            with open(filtered_report_path, 'w') as wf:
                json.dump(report_data, wf, indent=2)

            # Generate HTML Report
            html_report_path = os.path.join(output_dir, 'report.html')
            generate_html_report(report_data, html_report_path)

            # Basic summary output
            statistics = report_data.get('statistics', {})
            total = statistics.get('total', {})
            
            print("\n--- Detection Summary (Filtered: Cross-file only) ---")
            print(f"Total lines in both files: {total.get('lines')}")
            print(f"Cross-file duplicated lines: {filtered_duplicated_lines}")
            print(f"Original duplicated lines (including self): {total.get('duplicatedLines')}")
            
            if filtered_duplicates:
                print(f"\nFound {len(filtered_duplicates)} cross-file duplicate blocks.")
                print(f"HTML report saved to: {html_report_path}")
                print(f"Filtered JSON saved to: {filtered_report_path}")
            else:
                print("\nNo cross-file duplicates found.")
        else:
            print(f"Report not found at {report_path}. stdout might contain info.")
            print(result.stdout)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    run_jscpd()
