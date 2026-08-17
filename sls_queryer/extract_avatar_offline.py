import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

from aliyun.log import LogClient, GetLogsRequest


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config.json')
OFFLINE_RE = re.compile(r'avatar offline\s+(\d+)')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_time(value, now):
    value = value.strip()
    if value.isdigit():
        return int(value)
    lower = value.lower()
    if lower.endswith('h'):
        return now - int(lower[:-1]) * 3600
    if lower.endswith('m'):
        return now - int(lower[:-1]) * 60
    if lower.endswith('d'):
        return now - int(lower[:-1]) * 86400
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return int(datetime.strptime(value, fmt).timestamp())
        except ValueError:
            continue
    raise ValueError(f'无法解析时间: {value}')


def fetch_logs(client, project, logstore, from_ts, to_ts, query, offset=0, lines=100):
    request = GetLogsRequest(project, logstore, from_ts, to_ts, '', query, lines, offset, False)
    return client.get_logs(request).get_logs()


def iter_logs(client, project, logstore, from_ts, to_ts, query, lines_per_page=100):
    offset = 0
    while True:
        logs = fetch_logs(client, project, logstore, from_ts, to_ts, query, offset, lines_per_page)
        if not logs:
            break
        for log in logs:
            yield log
        if len(logs) < lines_per_page:
            break
        offset += lines_per_page


def extract_offline_reason(content):
    if not content:
        return None
    m = OFFLINE_RE.search(content)
    return m.group(1) if m else None


def extract_hostname(contents):
    host = contents.get('__tag__:__hostname__', '') or ''
    if isinstance(host, bytes):
        host = host.decode('utf-8', errors='ignore')
    return host.strip() or 'unknown'


def main():
    parser = argparse.ArgumentParser(description='下载 avatar offline 日志并按服务器分别统计离线原因枚举值的出现次数')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='起始时间，例如 "2026-08-14 19:40:00"')
    parser.add_argument('--to', dest='to_time', required=True,
                        help='结束时间，例如 "2026-08-14 20:20:00"')
    parser.add_argument('--lines', type=int, default=100, help='每页拉取条数，默认 100')
    parser.add_argument('--out', dest='out_file', default='avatar_offline_count.txt',
                        help='统计结果输出文件 (tab 分隔)')
    parser.add_argument('--json-out', dest='json_file', default='avatar_offline_count.json',
                        help='统计结果输出文件 (json)')
    parser.add_argument('--log-out', dest='log_file', default='avatar_offline_logs.txt',
                        help='原始日志输出文件')
    args = parser.parse_args()

    config = load_config()
    client = LogClient(config['endpoint'], config['access_key_id'], config['access_key'])

    now = int(time.time())
    from_ts = parse_time(args.from_time, now)
    to_ts = parse_time(args.to_time, now)
    if from_ts >= to_ts:
        print('起始时间必须早于结束时间', file=sys.stderr)
        sys.exit(1)

    query = '"avatar offline" and zt'
    print(f"查询语句: {query}")
    print(f"查询区间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_ts))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_ts))}")

    raw_lines = []
    per_host = defaultdict(Counter)
    total_logs = 0
    matched = 0

    try:
        for log in iter_logs(client, config['project'], config['logstore'],
                             from_ts, to_ts, query, args.lines):
            total_logs += 1
            contents = dict(log.contents)
            content = contents.get('content', '') or contents.get('message', '')
            raw_lines.append(content)
            reason = extract_offline_reason(content)
            if reason is not None:
                matched += 1
                host = extract_hostname(contents)
                per_host[host][reason] += 1
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_lines))

    rows = []
    for host in sorted(per_host):
        items = sorted(per_host[host].items(), key=lambda kv: kv[1], reverse=True)
        for reason, count in items:
            rows.append((host, reason, count))

    with open(args.out_file, 'w', encoding='utf-8') as f:
        f.write("server\treason\tcount\n")
        for host, reason, count in rows:
            f.write(f"{host}\t{reason}\t{count}\n")

    grouped = {host: dict(counter) for host, counter in per_host.items()}
    with open(args.json_file, 'w', encoding='utf-8') as f:
        json.dump(grouped, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"共拉取日志: {total_logs} 条，命中 avatar offline 字段: {matched} 条")
    print(f"服务器数量: {len(per_host)}")
    print(f"原始日志已写入: {args.log_file}")
    print(f"统计结果已写入: {args.out_file} 和 {args.json_file}")
    print()
    for host in sorted(per_host):
        items = sorted(per_host[host].items(), key=lambda kv: kv[1], reverse=True)
        total = sum(c for _, c in items)
        print(f"[{host}] 合计 {total} 条")
        print(f"  {'reason':>10}  {'count':>8}")
        for reason, count in items:
            print(f"  {reason:>10}  {count:>8}")
        print()


if __name__ == '__main__':
    main()