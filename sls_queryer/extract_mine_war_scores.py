import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

from aliyun.log import LogClient, GetLogsRequest


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config.json')
KEYWORD = 'MineWarMapVal.addMineWarScoreVal'
PLAYER_RE = re.compile(r'playerGbId=(\d+)')
TOTAL_RE = re.compile(r'totalScore=(\d+)')


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


def extract_player_total(content):
    if not content:
        return None, None
    player_m = PLAYER_RE.search(content)
    total_m = TOTAL_RE.search(content)
    if not player_m or not total_m:
        return None, None
    return player_m.group(1), int(total_m.group(1))


def main():
    parser = argparse.ArgumentParser(description='下载 MineWarMapVal.addMineWarScoreVal 日志并按 playerGbId 取最大 totalScore')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='起始时间，例如 "2026-07-30 13:25:00"')
    parser.add_argument('--to', dest='to_time', required=True,
                        help='结束时间，例如 "2026-07-30 13:40:00"')
    parser.add_argument('--lines', type=int, default=100, help='每页拉取条数，默认 100')
    parser.add_argument('--out', dest='out_file', default='mine_war_max_scores.txt',
                        help='playerGbId -> max totalScore 输出文件')
    parser.add_argument('--log-out', dest='log_file', default='mine_war_logs.txt',
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

    query = KEYWORD
    print(f"查询语句: {query}")
    print(f"查询区间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_ts))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_ts))}")

    max_scores = {}
    raw_lines = []
    total_logs = 0
    matched = 0

    try:
        for log in iter_logs(client, config['project'], config['logstore'],
                             from_ts, to_ts, query, args.lines):
            total_logs += 1
            content = dict(log.contents).get('content', '') or dict(log.contents).get('message', '')
            raw_lines.append(content)
            player, total = extract_player_total(content)
            if player is None:
                continue
            matched += 1
            if total > max_scores.get(player, -1):
                max_scores[player] = total
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_lines))

    with open(args.out_file, 'w', encoding='utf-8') as f:
        f.write("playerGbId\tmaxTotalScore\n")
        for player in sorted(max_scores):
            f.write(f"{player}\t{max_scores[player]}\n")

    with open(args.out_file + '.json', 'w', encoding='utf-8') as f:
        json.dump(max_scores, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"共拉取日志: {total_logs} 条，命中 playerGbId/totalScore: {matched} 条")
    print(f"去重后 playerGbId 数量: {len(max_scores)}")
    print(f"原始日志已写入: {args.log_file}")
    print(f"统计结果已写入: {args.out_file} 和 {args.out_file}.json")
    print()
    print(f"{'playerGbId':>22}  {'maxTotalScore':>14}")
    for player in sorted(max_scores):
        print(f"{player:>22}  {max_scores[player]:>14}")


if __name__ == '__main__':
    main()