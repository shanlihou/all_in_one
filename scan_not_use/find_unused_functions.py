import argparse
import ast
import subprocess
import os
import sys
import json
import const
from pathlib import Path

def extract_functions_from_file(file_path):
    """
    解析一个 Python 文件，并返回其中定义的所有函数信息的列表。
    每个函数信息是一个包含名称、起始行和结束行号的字典。

    :param file_path: 要解析的 Python 文件的路径。
    :return: 一个包含函数信息的字典列表。
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    functions = []
    try:
        tree = ast.parse(content, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                end_lineno = getattr(node, 'end_lineno', None)
                if end_lineno is None:
                    end_lineno = node.lineno

                functions.append({
                    'name': node.name,
                    'start_line': node.lineno,
                    'end_line': end_lineno
                })
    except SyntaxError as e:
        print(f"错误: 解析文件时发生语法错误 '{file_path}': {e}", file=sys.stderr)

    return functions

def find_references_outside_definition(function_info, workspace_path, target_file_abspath):
    """
    使用 ripgrep (rg) 查找函数的引用，并过滤掉函数定义内部的自引用。

    :param function_info: 包含函数名称、起始行和结束行的字典。
    :param workspace_path: 要搜索的工作区目录。
    :param target_file_abspath: 被分析文件的绝对路径，用于比较。
    :return: 如果找到任何外部引用，则返回 True，否则返回 False。
    """
    func_name = function_info['name']
    command = [
        'rg',
        '-w',
        '-F',
        '--json',
        func_name,
        workspace_path
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("错误: 'rg' (ripgrep) 命令未找到。", file=sys.stderr)
        print("请确保 ripgrep 已安装并位于系统的 PATH 中。", file=sys.stderr)
        sys.exit(1)

    if result.returncode not in [0, 1]:
        print(f"错误: ripgrep 执行失败: {result.stderr}", file=sys.stderr)
        return True

    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            match_data = json.loads(line)
            if match_data['type'] == 'match':
                match_path = os.path.abspath(match_data['data']['path']['text'])
                match_line = match_data['data']['line_number']

                is_self_reference = (
                    match_path == target_file_abspath and
                    function_info['start_line'] <= match_line <= function_info['end_line']
                )

                if not is_self_reference:
                    return True
        except (json.JSONDecodeError, KeyError):
            continue

    return False


def get_all_py_files(workspace_path, max_depth=2):
    """
    从 workspace 递归遍历，获取深度在 max_depth 之内的所有 py 文件。

    :param workspace_path: 工作区目录路径。
    :param max_depth: 最大目录深度（相对于 workspace 根目录）。
    :return: py 文件路径列表。
    """
    py_files = []
    workspace_path = Path(workspace_path)

    for py_file in workspace_path.rglob('*.py'):
        try:
            relative_path = py_file.relative_to(workspace_path)
            if len(relative_path.parts) <= max_depth:
                py_files.append(py_file)
        except ValueError:
            continue

    return py_files


def main():
    """
    主函数，用于编排整个扫描和分析过程。
    """
    workspace = const.workspace

    if not os.path.isdir(workspace):
        print(f"错误: 工作区目录未找到 '{workspace}'", file=sys.stderr)
        sys.exit(1)

    print(f"[*] 工作区: {workspace}")

    py_files = get_all_py_files(workspace, max_depth=2)
    total_files = len(py_files)
    print(f"[*] 找到 {total_files} 个 Python 文件\n")

    all_unused = {}
    for idx, py_file in enumerate(py_files):
        absolute_target_path = str(py_file)
        print(f"[*] [{idx+1}/{total_files}] 正在分析文件: {absolute_target_path}")

        functions = extract_functions_from_file(absolute_target_path)
        if not functions:
            continue

        functions_to_check = [f for f in functions if not (f['name'].startswith('__') and f['name'].endswith('__'))]
        if not functions_to_check:
            continue

        print(f"[*] 在 {py_file.name} 中找到 {len(functions)} 个函数，将检查 {len(functions_to_check)} 个非特殊函数...")

        unused_functions = []
        for func_info in functions_to_check:
            func_name = func_info['name']
            if not find_references_outside_definition(func_info, workspace, absolute_target_path):
                unused_functions.append(func_name)

        if unused_functions:
            all_unused[str(py_file)] = unused_functions
            print(f"[+] 发现 {len(unused_functions)} 个未使用的函数: {unused_functions}")
        else:
            print(f"[*] {py_file.name} 中所有函数都有外部引用")

    print("\n" + "=" * 50)
    if all_unused:
        total_unused = sum(len(v) for v in all_unused.values())
        print(f"[+] 共发现 {total_unused} 个未使用的函数，分布在 {len(all_unused)} 个文件中:")
        for file_path, funcs in all_unused.items():
            rel_path = Path(file_path).relative_to(workspace)
            print(f"\n  [{rel_path}]")
            for func_name in funcs:
                print(f"    - {func_name}")
    else:
        print("[*] 未发现未使用的函数。所有函数看起来都有外部引用。")

if __name__ == "__main__":
    main()
