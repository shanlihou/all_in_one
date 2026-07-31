import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

from aliyun.log import LogClient, GetLogsRequest


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config.json')
AVATAR_RE = re.compile(r'Avatar\(\d+-(\d+)\)')


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
            dt = datetime.strptime(value, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise ValueError(f'无法解析时间: {value}')


def fetch_logs(client, project, logstore, from_ts, to_ts, offset=0, lines=100):
    request = GetLogsRequest(
        project,
        logstore,
        from_ts,
        to_ts,
        '',
        'onCellAppDeath and Avatar',
        lines,
        offset,
        False,
    )
    response = client.get_logs(request)
    return response.get_logs()


def iter_logs(client, project, logstore, from_ts, to_ts, lines_per_page=100):
    offset = 0
    while True:
        logs = fetch_logs(client, project, logstore, from_ts, to_ts, offset, lines_per_page)
        if not logs:
            break
        for log in logs:
            yield log
        if len(logs) < lines_per_page:
            break
        offset += lines_per_page


def extract_avatar(content):
    if not content:
        return None
    match = AVATAR_RE.search(content)
    return match.group(1) if match else None


def main():
    parser = argparse.ArgumentParser(description='下载 onCellAppDeath 日志并提取唯一 Avatar ID')
    parser.add_argument('--from', dest='from_time', default='24h',
                        help='起始时间，Unix 时间戳或相对值，例如 1700000000 / 24h / 30m / 7d')
    parser.add_argument('--to', dest='to_time', default='now',
                        help='结束时间，Unix 时间戳或相对值，默认 now')
    parser.add_argument('--out', dest='out_file', default='onCellAppDeath_avatars.txt',
                        help='去重后的 Avatar ID 输出文件')
    parser.add_argument('--log-out', dest='log_file', default='onCellAppDeath_logs.txt',
                        help='原始日志输出文件')
    parser.add_argument('--lines', type=int, default=100, help='每页拉取条数，默认 100')
    parser.add_argument('--stdout', action='store_true', help='将去重结果输出到 stdout')
    args = parser.parse_args()

    config = load_config()
    client = LogClient(config['endpoint'], config['access_key_id'], config['access_key'])

    now = int(time.time())
    to_ts = parse_time(args.to_time, now) if args.to_time != 'now' else now
    from_ts = parse_time(args.from_time, now)

    if from_ts >= to_ts:
        print('起始时间必须早于结束时间', file=sys.stderr)
        sys.exit(1)

    print(f"查询区间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_ts))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_ts))}")

    avatars = set()
    raw_lines = []
    total_logs = 0
    matched = 0

    try:
        for log in iter_logs(client, config['project'], config['logstore'],
                             from_ts, to_ts, args.lines):
            total_logs += 1
            content = dict(log.contents).get('content', '') or dict(log.contents).get('message', '')
            raw_lines.append(content)
            avatar = extract_avatar(content)
            if avatar:
                avatars.add(avatar)
                matched += 1
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_lines))

    with open(args.out_file, 'w', encoding='utf-8') as f:
        for avatar in sorted(avatars):
            f.write(avatar + '\n')

    print(f"共拉取日志: {total_logs} 条，包含 Avatar 字段: {matched} 条")
    print(f"去重后 Avatar ID 数量: {len(avatars)}")
    print(f"原始日志已写入: {args.log_file}")
    print(f"去重结果已写入: {args.out_file}")

    if args.stdout:
        for avatar in sorted(avatars):
            print(avatar)


if __name__ == '__main__':
    main()
