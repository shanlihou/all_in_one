import time
import json
import smtplib
import hashlib
import re
from email.mime.text import MIMEText
from aliyun.log import LogClient, GetLogsRequest

# 用于存储已发送日志数据的 MD5 值，防止重复发送
sent_log_hashes = set()

# 从 .config.json 里面读出来
with open('.config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

endpoint = config.get('endpoint')
access_key_id = config.get('access_key_id')
access_key = config.get('access_key')
project = config.get('project')
logstore = config.get('logstore')
email_config = config.get('email', {})

client = LogClient(endpoint, access_key_id, access_key)

def get_md5(text):
    """计算字符串的 MD5 值"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def extract_teleporter_data(content):
    """从日志内容中提取 _doRandomTeleporter 后面的数据"""
    # 匹配 _doRandomTeleporter: 后面紧跟的 {} 及其内容
    match = re.search(r'_doRandomTeleporter:\s*(\{.*?\})', content)
    if match:
        return match.group(1)
    return None

def send_email(content):
    """发送邮件提醒"""
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = email_config.get('subject', 'SLS Alert')
        msg['From'] = email_config.get('sender')
        msg['To'] = email_config.get('receiver')

        server = smtplib.SMTP_SSL(email_config.get('smtp_server'), email_config.get('smtp_port'))
        server.login(email_config.get('sender'), email_config.get('password'))
        server.sendmail(email_config.get('sender'), [email_config.get('receiver')], msg.as_string())
        server.quit()
        print(f"[{time.strftime('%H:%M:%S')}] 邮件发送成功")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 邮件发送失败: {e}")

def run_query():
    """执行 SLS 查询逻辑"""
    to_time = int(time.time())
    from_time = to_time - 60  # 查询最近一分钟的数据

    request = GetLogsRequest(
        project,
        logstore,
        from_time,
        to_time,
        '',
        '_doRandomTeleporter',
        100,
        0,
        False
    )

    try:
        response = client.get_logs(request)
        logs = response.get_logs()
        
        new_entries = []
        for log in logs:
            contents_dict = dict(log.contents)
            # 优先从 content 字段找，找不到从 message 找
            content_str = contents_dict.get('content', '') or contents_dict.get('message', '')
            
            # 提取目标数据
            data_str = extract_teleporter_data(content_str)
            if data_str:
                # 计算 MD5 并去重
                data_hash = get_md5(data_str)
                if data_hash not in sent_log_hashes:
                    sent_log_hashes.add(data_hash)
                    new_entries.append(content_str)
        
        if new_entries:
            print(f"[{time.strftime('%H:%M:%S')}] 发现 {len(new_entries)} 条新数据，准备发送邮件...")
            email_body = "查询到以下新增日志数据：\n\n" + "\n\n".join(new_entries)
            send_email(email_body)
            
            # 限制内存占用，只保留最近的 1000 条 hash
            if len(sent_log_hashes) > 1000:
                sent_log_hashes.clear()
        else:
            # print(f"[{time.strftime('%H:%M:%S')}] 无新增数据")
            pass
            
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 查询失败: {e}")

if __name__ == "__main__":
    print(f"开始监控 SLS 日志（频率：5秒，关键字：_doRandomTeleporter）...")
    while True:
        run_query()
        time.sleep(5)
