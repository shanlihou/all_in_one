# -*- coding: utf-8 -*-
import json
import os
import sys
import base64

try:
    import requests
except ImportError:
    sys.stderr.write('缺少依赖: requests, 请先 pip install requests\n')
    sys.exit(2)


def load_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if not os.path.isfile(cfg_path):
        sys.stderr.write('未找到配置文件: {}\n'.format(cfg_path))
        sys.exit(2)
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    return cfg, cfg_path


class ElasticReader(object):

    def __init__(self, cfg):
        self.host = cfg.get('host', '127.0.0.1')
        self.port = int(cfg.get('port', 9200))
        self.user = cfg.get('user', '')
        self.password = cfg.get('password', '')
        self.server_id = cfg.get('server_id', 1)
        self.index_suffix = cfg.get('index_suffix', 'friend_ik')
        self.timeout_sec = int(cfg.get('timeout_sec', 5))
        self.index_name = '{}_{}'.format(self.server_id, self.index_suffix)
        self.base_url = 'http://{}:{}'.format(self.host, self.port)

    def _headers(self, with_json=False):
        h = {}
        userpass = '{}:{}'.format(self.user, self.password) if self.user else (self.password or '')
        if userpass:
            auth = base64.b64encode(userpass.encode('utf-8')).decode('utf-8')
            h['Authorization'] = 'Basic {}'.format(auth)
        if with_json:
            h['Content-Type'] = 'application/json'
        return h

    def _get(self, path):
        try:
            r = requests.get(self.base_url + path, headers=self._headers(), timeout=self.timeout_sec)
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def _post(self, path, body):
        try:
            r = requests.post(
                self.base_url + path,
                headers=self._headers(with_json=True),
                data=body if isinstance(body, bytes) else body.encode('utf-8'),
                timeout=self.timeout_sec,
            )
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def get_count(self, index):
        code, body, err = self._get('/{}/_count'.format(index))
        if err is not None:
            return None, str(err)
        if code == 404:
            return None, "index '{}' 不存在 (404)".format(index)
        if code != 200:
            return None, 'http {}: {}'.format(code, body[:160])
        try:
            return json.loads(body).get('count'), None
        except Exception as e:
            return None, 'parse: {}'.format(e)

    def list_all_users(self, index, page_size=1000, name_filter=None):
        if name_filter:
            query = {'match': {'name': {'query': name_filter, 'operator': 'and'}}}
        else:
            query = {'match_all': {}}
        sort = [{'gbId': 'asc'}]
        results = []
        search_after = None
        while True:
            body = {
                'size': page_size,
                'sort': sort,
                'query': query,
                'track_total_hits': False,
            }
            if search_after is not None:
                body['search_after'] = search_after
            j, err = self._do_search(index, body)
            if err:
                return results, err
            hits = j.get('hits', {}).get('hits', [])
            if not hits:
                break
            for h in hits:
                src = h.get('_source', {})
                results.append({
                    'id': h.get('_id'),
                    'name': src.get('name', ''),
                    'gbId': src.get('gbId'),
                })
            if len(hits) < page_size:
                break
            last_sort = hits[-1].get('sort')
            if not last_sort:
                break
            search_after = last_sort
        return results, None

    def _do_search(self, index, body):
        body_str = json.dumps(body, ensure_ascii=False)
        code, resp, err = self._post('/{}/_search'.format(index), body_str)
        if err is not None:
            return None, 'err: {}'.format(err)
        if code == 404:
            return None, "index '{}' 不存在 (404)".format(index)
        if code != 200:
            return None, 'http {}: {}'.format(code, (resp or '')[:200])
        try:
            return json.loads(resp), None
        except Exception as e:
            return None, 'parse: {}'.format(e)


def _print_usage(prog):
    print('用法: {} [--index NAME] [--size N] [--filter SUBSTR]'.format(prog))
    print('  默认从 config.json 读取 server_id + index_suffix 拼索引名')
    print('  --index NAME     覆盖索引名')
    print('  --size N         每页文档数 (默认 1000, 上限 10000)')
    print('  --filter SUBSTR  按 name 子串过滤 (使用 name 字段的 ngram 分析器)')


def main():
    cfg, cfg_path = load_config()
    reader = ElasticReader(cfg)
    prog = 'elastic_read_users.py'

    args = sys.argv[1:]
    index = reader.index_name
    page_size = 1000
    name_filter = None

    i = 0
    while i < len(args):
        a = args[i]
        if a in ('-h', '--help', 'help'):
            _print_usage(prog)
            sys.exit(0)
        if a == '--index':
            i += 1
            if i >= len(args):
                sys.stderr.write('--index 需要一个参数\n')
                sys.exit(2)
            index = args[i]
        elif a == '--size':
            i += 1
            if i >= len(args):
                sys.stderr.write('--size 需要一个参数\n')
                sys.exit(2)
            try:
                page_size = int(args[i])
            except ValueError:
                sys.stderr.write('--size 必须是整数\n')
                sys.exit(2)
            if page_size < 1 or page_size > 10000:
                sys.stderr.write('--size 必须在 1..10000 之间\n')
                sys.exit(2)
        elif a == '--filter':
            i += 1
            if i >= len(args):
                sys.stderr.write('--filter 需要一个参数\n')
                sys.exit(2)
            name_filter = args[i]
        else:
            sys.stderr.write('未知参数: {}\n'.format(a))
            _print_usage(prog)
            sys.exit(2)
        i += 1

    print('config  : {}'.format(cfg_path))
    print('index   : {}'.format(index))
    if name_filter:
        print('filter  : {}'.format(name_filter))
    print('')

    total, err = reader.get_count(index)
    if err is not None:
        print('[FAIL] count 失败: {}'.format(err))
        sys.exit(1)
    print('total   : {}'.format(total))
    print('')

    users, err = reader.list_all_users(index, page_size=page_size, name_filter=name_filter)
    if err is not None:
        print('[FAIL] 读取失败: {}'.format(err))
        sys.exit(1)
    if not users:
        print('(无数据)')
        sys.exit(0)

    name_w = max(8, min(40, max((len(u['name']) for u in users), default=8)))
    id_w = 20
    gb_w = 14
    print('{} {} {}'.format('id'.ljust(id_w), 'gbId'.ljust(gb_w), 'name'.ljust(name_w)))
    print('-' * (id_w + gb_w + name_w + 2))
    for u in users:
        print('{} {} {}'.format(
            str(u['id'])[:id_w].ljust(id_w),
            str(u['gbId'])[:gb_w].ljust(gb_w),
            u['name'][:name_w].ljust(name_w),
        ))
    print('')
    print('列出 {} 条'.format(len(users)))


if __name__ == '__main__':
    main()