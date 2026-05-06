import argparse
import ast
import subprocess
import os
import sys
import json
import const

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
                # ast.get_source_segment is more reliable for end line across python versions
                # but end_lineno is simpler if python 3.8+ is guaranteed
                end_lineno = getattr(node, 'end_lineno', None)
                if end_lineno is None:
                    # Fallback for older python: just take the start line
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
        '-w',             # 匹配全词
        '-F',             # 固定字符串搜索
        '--json',         # 输出为 JSON 格式
        func_name,
        workspace_path
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("错误: 'rg' (ripgrep) 命令未找到。", file=sys.stderr)
        print("请确保 ripgrep 已安装并位于系统的 PATH 中。", file=sys.stderr)
        sys.exit(1)

    if result.returncode not in [0, 1]: # 0=matches, 1=no matches
        print(f"错误: ripgrep 执行失败: {result.stderr}", file=sys.stderr)
        return True # 默认视为已使用，避免误删

    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            match_data = json.loads(line)
            if match_data['type'] == 'match':
                match_path = os.path.abspath(match_data['data']['path']['text'])
                match_line = match_data['data']['line_number']
                
                # 检查引用是否在函数定义内部
                is_self_reference = (
                    match_path == target_file_abspath and
                    function_info['start_line'] <= match_line <= function_info['end_line']
                )
                
                if not is_self_reference:
                    # 找到了一个外部引用，可以立即确定函数是“已使用”的
                    return True
        except (json.JSONDecodeError, KeyError):
            # 忽略无法解析的行或格式不正确的数据
            continue
            
    # 遍历完所有匹配项，没有发现任何外部引用
    return False


def test_single_function(function_name, start_line, end_line):
    """
    提供一个独立的测试函数，用于检查单个函数是否未被使用。
    
    :param function_name: 要测试的函数名。
    :param start_line: 函数定义的起始行。
    :param end_line: 函数定义的结束行。
    :return: 如果函数未被使用，则返回 True，否则返回 False。
    """
    print(f"\n--- 单独测试函数: {function_name} ({start_line}-{end_line}) ---")
    
    # 构造测试用的 function_info
    func_info = {
        'name': function_name,
        'start_line': start_line,
        'end_line': end_line
    }
    
    # 获取与 main 函数中相同的路径配置
    _target_path = os.path.join(const.workspace, const.target_file)
    absolute_target_path = os.path.abspath(_target_path)
    
    # 调用核心逻辑
    is_used = find_references_outside_definition(func_info, const.workspace, absolute_target_path)
    
    # 返回 “not use” 的结果
    is_not_used = not is_used
    
    print(f"[*] 测试结果: 函数 '{function_name}' 是否未被使用? -> {is_not_used}")
    return is_not_used


def main():
    """
    主函数，用于编排整个扫描和分析过程。
    """

    # 根据 const.py 中的配置构造路径，并获取其绝对路径用于比较
    _target_path = os.path.join(const.workspace, const.target_file)
    absolute_target_path = os.path.abspath(_target_path)

    # 校验路径
    if not os.path.isfile(absolute_target_path):
        print(f"错误: 目标文件未找到 '{absolute_target_path}'", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(const.workspace):
        print(f"错误: 工作区目录未找到 '{const.workspace}'", file=sys.stderr)
        sys.exit(1)

    print(f"[*] 正在分析文件: {absolute_target_path}")
    print(f"[*] 正在搜索工作区: {const.workspace}")
    
    functions = extract_functions_from_file(absolute_target_path)
    if not functions:
        print("[*] 未在文件中找到任何函数定义。")
        return

    # 过滤掉 dunder 方法
    functions_to_check = [f for f in functions if not (f['name'].startswith('__') and f['name'].endswith('__'))]
    total_functions_to_check = len(functions_to_check)
    
    print(f"[*] 在 {os.path.basename(const.target_file)} 中找到 {len(functions)} 个函数。将检查 {total_functions_to_check} 个非特殊函数...")

    unused_functions = []
    for i, func_info in enumerate(functions_to_check):
        func_name = func_info['name']
        print(f"[*] 进度 {i+1}/{total_functions_to_check}: 正在检查 '{func_name}'...", end='\r', flush=True)
        
        if not find_references_outside_definition(func_info, const.workspace, absolute_target_path):
            unused_functions.append(func_name)
    
    print("\n" + "-" * 30) # 换行并打印分隔符
    if unused_functions:
        print(f"[+] 发现 {len(unused_functions)} 个未使用的函数:")
        for func_name in unused_functions:
            print(f"  - {func_name}")
    else:
        print("[*] 未发现未使用的函数。所有函数看起来都有外部引用。")

if __name__ == "__main__":
    main()

    # --- 测试单个函数的示例 ---
    # 取消下面的注释来测试一个特定的函数。
    # 请手动提供函数名、起始行和结束行。
    #
    # ret = test_single_function(
    #     function_name="recordStatisticsRecords",
    #     start_line=212,
    #     end_line=216
    # )
    # print(ret)
    # -------------------------
