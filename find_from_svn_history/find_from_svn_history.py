import subprocess
import sys
import re
import json
import os

def load_config(config_path='config.json'):
    """加载配置文件"""
    if not os.path.exists(config_path):
        default_config = {
            "keyword": "TODO",
            "max_versions": 50,
            "svn_path": ""
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        print(f"已创建默认配置文件: {config_path}")
        return default_config

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_svn_command(cmd, cwd=None):
    """执行SVN命令并返回输出"""
    print(f"[DEBUG] 执行命令: {cmd}")
    print(f"[DEBUG] 工作目录: {cwd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, cwd=cwd)
        print(f"[DEBUG] 返回码: {result.returncode}")

        def decode_bytes(b):
            if not b:
                return ""
            try:
                return b.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return b.decode('gbk')
                except:
                    return b.decode('utf-8', errors='ignore')

        stdout = decode_bytes(result.stdout)
        stderr = decode_bytes(result.stderr)

        print(f"[DEBUG] stdout长度: {len(stdout)}")
        print(f"[DEBUG] stderr长度: {len(stderr)}")
        if stderr:
            print(f"[DEBUG] stderr内容: {stderr[:200]}")
        return stdout + stderr
    except Exception as e:
        print(f"[DEBUG] 异常: {e}")
        return str(e)

def get_svn_log(max_versions=100, cwd=None):
    """获取SVN log"""
    cmd = f'svn log -l {max_versions} -r HEAD:1'
    output = run_svn_command(cmd, cwd)
    print(f"[DEBUG] log输出长度: {len(output)}")
    print(f"[DEBUG] log输出前200字符: {output[:200]}")
    return parse_svn_log(output)

def parse_svn_log(log_output):
    """解析SVN log输出"""
    print(f"[DEBUG] 开始解析log输出，总长度: {len(log_output)}")

    if not log_output or not log_output.strip():
        print("[DEBUG] log输出为空")
        return []

    # 检查是否是SVN错误
    if 'not a working copy' in log_output.lower() or 'svn:' in log_output.lower():
        print(f"[DEBUG] SVN错误: {log_output[:300]}")
        return []

    entries = []
    current = None
    lines = log_output.split('\n')
    print(f"[DEBUG] log输出行数: {len(lines)}")

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # 检测到版本行: r124 | author | date | N lines
        if re.match(r'^r\d+', line):
            if current:
                entries.append(current)
                print(f"[DEBUG] 添加条目 r{current['revision']}")

            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                current = {
                    'revision': parts[0].strip().lstrip('r'),
                    'author': parts[1].strip(),
                    'date': parts[2].strip(),
                    'message': ''
                }
            i += 1
        # 跳过分隔线
        elif line.startswith('---'):
            i += 1
        # 收集消息内容
        elif current is not None:
            current['message'] += lines[i] + '\n'
            i += 1
        else:
            i += 1

    if current:
        entries.append(current)
        print(f"[DEBUG] 添加条目 r{current['revision']}")

    print(f"[DEBUG] 解析到 {len(entries)} 个log条目")
    if entries:
        print(f"[DEBUG] 第一个条目: {entries[0]}")

    return entries

def get_svn_diff(rev1, rev2, cwd=None):
    """获取两个版本之间的diff"""
    cmd = f'svn diff -r {rev1}:{rev2}'
    return run_svn_command(cmd, cwd)

def search_in_diff(diff_text, keyword):
    """在diff中搜索关键字"""
    lines = diff_text.split('\n')
    matches = []
    for i, line in enumerate(lines):
        if keyword in line:
            matches.append((i, line))
    return matches

def find_keyword_in_history(keyword, max_versions=50, cwd=None):
    """在历史版本中搜索关键字"""
    print(f"正在获取最近{max_versions}个版本的日志...")
    logs = get_svn_log(max_versions, cwd)

    if not logs:
        print("未找到SVN日志")
        return

    print(f"找到{len(logs)}个版本，开始搜索关键字: {keyword}")

    found_versions = []

    for i in range(len(logs) - 1):
        rev_current = logs[i]['revision']
        rev_prev = logs[i + 1]['revision']

        print(f"检查版本 r{rev_current} vs r{rev_prev}...")

        diff = get_svn_diff(rev_prev, rev_current, cwd)
        matches = search_in_diff(diff, keyword)

        if matches:
            print(f"\n找到匹配! 版本 r{rev_current}")
            print(f"提交信息: {logs[i]['message'].strip()}")
            print(f"作者: {logs[i]['author']}")
            print(f"日期: {logs[i]['date']}")
            print(f"匹配行数: {len(matches)}")
            for line_num, line in matches[:10]:
                print(f"  L{line_num}: {line}")
            if len(matches) > 10:
                print(f"  ... 还有{len(matches)-10}行匹配")
            print()

            found_versions.append({
                'revision': rev_current,
                'author': logs[i]['author'],
                'date': logs[i]['date'],
                'match_count': len(matches)
            })

    # 输出总结
    print("\n" + "="*60)
    print(f"搜索总结: 关键字 '{keyword}'")
    print("="*60)
    if found_versions:
        print(f"共在 {len(found_versions)} 个版本中找到匹配:")
        for v in found_versions:
            print(f"  r{v['revision']} - {v['date']} - {v['author']} ({v['match_count']} 处匹配)")
    else:
        print("未找到任何匹配")
    print("="*60)

if __name__ == '__main__':
    config = load_config()

    keyword = config.get('keyword', 'TODO')
    max_versions = config.get('max_versions', 50)
    cwd = config.get('svn_path', None) or None

    print(f"配置: 关键字={keyword}, 最大版本数={max_versions}, 路径={cwd or '当前目录'}")

    find_keyword_in_history(keyword, max_versions, cwd)
