import csv
import const

def strip_and_sort_log():
    try:
        data = []
        # 1. 读取并收集数据
        with open(const.INPUT_FILE, mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            
            # 校验字段是否存在
            if 'content' not in reader.fieldnames or const.TIME_COLUMN not in reader.fieldnames:
                print(f"错误: 在文件 {const.INPUT_FILE} 中未找到必要列 (content 或 {const.TIME_COLUMN})。")
                return

            for row in reader:
                time_val = row.get(const.TIME_COLUMN, '')
                content = row.get('content', '')
                if content:
                    # 存入元组，方便后续根据时间排序
                    data.append((time_val, content))
        
        # 2. 排序 (默认按时间字段字符串/数值升序)
        # 如果时间字段是 Unix 时间戳，直接按字符串或转换为 float 排序即可
        data.sort(key=lambda x: x[0])

        # 3. 输出排序后的内容
        with open(const.OUTPUT_FILE, mode='w', encoding='utf-8') as outfile:
            for time_val, content in data:
                # 按照 "时间 content" 的格式输出，或者根据需求仅输出 content
                outfile.write(f"[{time_val}] {content}\n")
            
            print(f"处理并排序完成！共处理 {len(data)} 条日志，已保存到 {const.OUTPUT_FILE}。")

    except FileNotFoundError:
        print(f"错误: 找不到文件 {const.INPUT_FILE}。")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    strip_and_sort_log()
