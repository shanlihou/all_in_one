import argparse
import ast
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from aliyun.log import LogClient, GetLogsRequest


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config.json')
KEYWORD = '_processNotifyOrder---------'
LOG_TIME_RE = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\d{1,3})\]')
DICT_RE = re.compile(r"_processNotifyOrder---------:\s*(\{.*\})\s*$", re.DOTALL)
BJ_TZ = timezone(timedelta(hours=8))


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


def parse_log_time(content):
    m = LOG_TIME_RE.search(content)
    if not m:
        return None
    dt_str, ms_str = m.group(1), m.group(2)
    try:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    ms = int(ms_str.ljust(3, '0')[:3])
    return dt.replace(microsecond=ms * 1000, tzinfo=BJ_TZ)


def parse_dict(content):
    m = DICT_RE.search(content)
    if not m:
        return None
    snippet = m.group(1)
    try:
        return ast.literal_eval(snippet)
    except (ValueError, SyntaxError):
        return None


def build_event(log_dt, data):
    sent_timestamp = int(log_dt.timestamp() * 1000)
    time_str = log_dt.strftime('%Y-%m-%d %H:%M:%S') + f'.{log_dt.microsecond // 1000:03d}'
    properties = {
        'order_id': data['outTradeNo'],
        'account_id': str(data['accountId']),
        'player_gbid': str(data['gbId']),
        'role_name': data['roleName'],
        'server_id': data['serverId'],
        'goods_id': data['itemId'],
        'stash_status': bool(data['addToSafe']),
        'create_time': data['createTime'],
        'pay_time': data['payTime'],
        'order_price': data['itemPrice'],
        'actual_pay_amount': data['actualAmount'],
        'game_id': 'fengyan',
    }
    return {
        'sent_timestamp': sent_timestamp,
        '#time': time_str,
        '#ip': '0.0.0.0',
        'properties': properties,
        '#account_id': str(data['gbId']),
        '#distinct_id': '',
        '#type': 'track',
        '#event_name': 'item_issuance',
    }


def main():
    parser = argparse.ArgumentParser(description='下载 _processNotifyOrder 日志并转换为事件 JSON')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='起始时间，例如 "2026-08-12 07:00:00"')
    parser.add_argument('--to', dest='to_time', required=True,
                        help='结束时间，例如 "2026-08-12 11:00:00"')
    parser.add_argument('--lines', type=int, default=100, help='每页拉取条数，默认 100')
    parser.add_argument('--out', dest='out_file', default='process_notify_orders.jsonl',
                        help='事件 JSON 输出文件 (jsonl)')
    parser.add_argument('--log-out', dest='log_file', default='process_notify_orders_logs.txt',
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

    raw_lines = []
    events = []
    total_logs = 0
    matched = 0

    try:
        for log in iter_logs(client, config['project'], config['logstore'],
                             from_ts, to_ts, query, args.lines):
            total_logs += 1
            content = dict(log.contents).get('content', '') or dict(log.contents).get('message', '')
            raw_lines.append(content)
            log_dt = parse_log_time(content)
            data = parse_dict(content)
            if log_dt is None or data is None:
                continue
            events.append(build_event(log_dt, data))
            matched += 1
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_lines))

    with open(args.out_file, 'w', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

    print(f"共拉取日志: {total_logs} 条，命中 _processNotifyOrder 字段: {matched} 条")
    print(f"原始日志已写入: {args.log_file}")
    print(f"事件 JSON 已写入: {args.out_file}")


if __name__ == '__main__':
    main()
