import re
from collections import defaultdict
from const import LOG_FILE_PATH

def parse_logs():
    # 使用 defaultdict(int) 方便计数，不存在的键默认值为 0
    counts = defaultdict(int)
    
    # 定义正则表达式匹配 "doAddBuff" 及其后的数字
    # \s+ 匹配一个或多个空格
    # (\d+) 捕获组，提取数字部分
    pattern = re.compile(r'doAddBuff\s+(\d+)')

    try:
        with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    number = match.group(1)
                    counts[number] += 1
        
        # 打印统计结果
        print(f"解析完成，路径: {LOG_FILE_PATH}")
        print("-" * 30)
        # 按出现次数降序排列，次数相同时按数字升序排列
        sorted_counts = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        for num, count in sorted_counts:
            print(f"数字 {num}: 出现 {count} 次")
            
    except FileNotFoundError:
        print(f"错误: 找不到文件 {LOG_FILE_PATH}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    parse_logs()
