import argparse
import re
from collections import Counter
from pathlib import Path

LOGIN_PATTERN = re.compile(r"onAccountCreated::\s+(\S+)")
LOGOUT_PATTERN = re.compile(r"onAccountDestroy\s+(\S+)")


def count_accounts(path: Path, pattern: re.Pattern[str]) -> Counter[str]:
    counts = Counter()
    with path.open("r", encoding="utf-8", errors="ignore") as log_file:
        for line in log_file:
            match = pattern.search(line)
            if match:
                counts[match.group(1)] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="统计账号登录次数和登出次数的差值")
    parser.add_argument("login_log", nargs="?", default="a.txt", help="登录日志文件")
    parser.add_argument("logout_log", nargs="?", default="b.txt", help="登出日志文件")
    parser.add_argument("--min-difference", type=int, default=2, help="最小登录登出差值")
    args = parser.parse_args()

    login_counts = count_accounts(Path(args.login_log), LOGIN_PATTERN)
    logout_counts = count_accounts(Path(args.logout_log), LOGOUT_PATTERN)
    accounts = sorted(set(login_counts) | set(logout_counts))
    suspicious = [
        (account, login_counts[account], logout_counts[account], login_counts[account] - logout_counts[account])
        for account in accounts
        if login_counts[account] - logout_counts[account] >= args.min_difference
    ]
    suspicious.sort(key=lambda item: (-item[3], item[0]))

    print(f"登录日志总数: {sum(login_counts.values())}")
    print(f"登出日志总数: {sum(logout_counts.values())}")
    print(f"异常账号数量: {len(suspicious)}")
    print("账号\t登录次数\t登出次数\t差值")
    for account, login_count, logout_count, difference in suspicious:
        print(f"{account}\t{login_count}\t{logout_count}\t{difference}")


if __name__ == "__main__":
    main()
