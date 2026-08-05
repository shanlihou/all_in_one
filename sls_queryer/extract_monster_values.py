import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

from aliyun.log import LogClient, GetLogsRequest


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config.json')


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


def build_value_extractor(keyword):
    pattern = re.compile(
        rf'\bon\s+create\s+{re.escape(keyword)}\s+(\d+)\b'
    )
    def extract(content):
        if not content:
            return None
        m = pattern.search(content)
        return m.group(1) if m else None
    return extract


def main():
    parser = argparse.ArgumentParser(description='下载 Monster on create 日志并统计数值出现次数')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='起始时间，例如 "2026-07-30 13:25:00"')
    parser.add_argument('--to', dest='to_time', required=True,
                        help='结束时间，例如 "2026-07-30 13:40:00"')
    parser.add_argument('--keyword', default='40020441',
                        help='on create 后的关键字，默认 40020441')
    parser.add_argument('--divisor', type=float, default=1000.0,
                        help='提取数值要除以的因子，默认 1000')
    parser.add_argument('--lines', type=int, default=100, help='每页拉取条数，默认 100')
    parser.add_argument('--out', dest='out_file', default='monster_values_count.txt',
                        help='统计结果输出文件')
    parser.add_argument('--log-out', dest='log_file', default='monster_logs.txt',
                        help='原始日志输出文件')
    parser.add_argument('--top', type=int, default=0,
                        help='只打印前 N 条统计结果，0 表示全部')
    args = parser.parse_args()

    config = load_config()
    client = LogClient(config['endpoint'], config['access_key_id'], config['access_key'])

    now = int(time.time())
    from_ts = parse_time(args.from_time, now)
    to_ts = parse_time(args.to_time, now)
    if from_ts >= to_ts:
        print('起始时间必须早于结束时间', file=sys.stderr)
        sys.exit(1)

    query = f'"on create" and {args.keyword} and Monster'
    print(f"查询语句: {query}")
    print(f"查询区间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_ts))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_ts))}")

    extract_value = build_value_extractor(args.keyword)
    raw_lines = []
    counter = Counter()
    total_logs = 0
    matched = 0

    try:
        for log in iter_logs(client, config['project'], config['logstore'],
                             from_ts, to_ts, query, args.lines):
            total_logs += 1
            content = dict(log.contents).get('content', '') or dict(log.contents).get('message', '')
            raw_lines.append(content)
            value = extract_value(content)
            if value is not None:
                matched += 1
                try:
                    divided = int(value) / args.divisor if args.divisor else int(value)
                except ValueError:
                    continue
                counter[divided] += 1
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_lines))

    items = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    if args.top > 0:
        items = items[:args.top]

    with open(args.out_file, 'w', encoding='utf-8') as f:
        f.write(f"value\tcount\n")
        for value, count in items:
            f.write(f"{value}\t{count}\n")

    print(f"共拉取日志: {total_logs} 条，命中数值字段: {matched} 条")
    print(f"去重后数值数量: {len(counter)}")
    print(f"原始日志已写入: {args.log_file}")
    print(f"统计结果已写入: {args.out_file}")
    print()
    print(f"{'value':>20}  {'count':>8}")
    for value, count in items:
        print(f"{value:>20}  {count:>8}")


if __name__ == '__main__':
    main()
