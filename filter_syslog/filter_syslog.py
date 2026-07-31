import json
from datetime import datetime
from pathlib import Path

LOG_FILE_PATH = "/var/log/fengyan.log"
CONFIG_FILE_PATH = Path(__file__).with_name("config.json")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def load_time_range():
    with CONFIG_FILE_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    start_time = datetime.strptime(config["start_time"], TIME_FORMAT)
    end_time = datetime.strptime(config["end_time"], TIME_FORMAT)
    if start_time > end_time:
        raise ValueError("start_time 不能晚于 end_time")
    return start_time, end_time


def count_unique_login_accounts(start_time, end_time):
    accounts = set()
    invalid_lines = 0

    with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get("#event_name") != "Server_Login":
                    continue

                event_time = datetime.strptime(record["#time"], TIME_FORMAT)
                if not start_time <= event_time <= end_time:
                    continue

                account_id = record.get("properties", {}).get("account_id")
                if account_id is not None and str(account_id).strip():
                    accounts.add(str(account_id))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                invalid_lines += 1

    return len(accounts), invalid_lines


def main():
    try:
        start_time, end_time = load_time_range()
        account_count, invalid_lines = count_unique_login_accounts(start_time, end_time)
        print(f"不重复登录账号总数: {account_count}")
        if invalid_lines:
            print(f"跳过格式错误的日志行数: {invalid_lines}")
    except FileNotFoundError as e:
        print(f"错误: 找不到文件 {e.filename}")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        print(f"配置错误: {e}")
    except OSError as e:
        print(f"读取文件失败: {e}")


if __name__ == "__main__":
    main()
