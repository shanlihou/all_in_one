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


class ElasticSearcher(object):

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

    def search_by_name(self, index, role_name, size=50):
        query = {
            'query': {
                'bool': {
                    'should': [
                        {
                            'match': {
                                'name': {
                                    'query': role_name,
                                    'operator': 'and',
                                }
                            }
                        },
                        {
                            'match': {
                                'name.raw': {
                                    'query': role_name,
                                    'operator': 'and',
                                }
                            }
                        },
                    ]
                }
            },
            'size': size,
        }
        body_str = json.dumps(query, ensure_ascii=False)
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
    print('用法: {} NAME [--index NAME] [--size N]'.format(prog))
    print('  复刻线上 reqSearchAvatarName 的 bool.should 查询:')
    print('    match name      (operator=and, ngram 分析器)')
    print('    match name.raw  (operator=and, keyword)')


def main():
    cfg, cfg_path = load_config()
    searcher = ElasticSearcher(cfg)
    prog = 'elastic_search_user.py'

    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help', 'help'):
        _print_usage(prog)
        sys.exit(0 if args else 2)

    role_name = args[0]
    index = searcher.index_name
    size = 50

    i = 1
    while i < len(args):
        a = args[i]
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
                size = int(args[i])
            except ValueError:
                sys.stderr.write('--size 必须是整数\n')
                sys.exit(2)
            if size < 1 or size > 10000:
                sys.stderr.write('--size 必须在 1..10000 之间\n')
                sys.exit(2)
        else:
            sys.stderr.write('未知参数: {}\n'.format(a))
            _print_usage(prog)
            sys.exit(2)
        i += 1

    print('config  : {}'.format(cfg_path))
    print('index   : {}'.format(index))
    print('query   : "{}" (size={})'.format(role_name, size))
    print('')

    j, err = searcher.search_by_name(index, role_name, size=size)
    if err is not None:
        print('[FAIL] {}'.format(err))
        sys.exit(1)

    total_obj = j.get('hits', {}).get('total', {})
    if isinstance(total_obj, dict):
        total = total_obj.get('value', '?')
        relation = total_obj.get('relation', '?')
    else:
        total = total_obj
        relation = '?'
    took = j.get('took', '?')

    hits = j.get('hits', {}).get('hits', [])
    print('total   : {} ({})  took={}ms'.format(total, relation, took))
    print('')

    if not hits:
        print('(无匹配)')
        sys.exit(0)

    name_w = max(8, min(40, max(
        (len(h.get('_source', {}).get('name', '') or '') for h in hits),
        default=8,
    )))
    score_w = 7
    id_w = 20
    gb_w = 14

    print('{} {} {} {}'.format(
        'score'.ljust(score_w),
        'id'.ljust(id_w),
        'gbId'.ljust(gb_w),
        'name'.ljust(name_w),
    ))
    print('-' * (score_w + id_w + gb_w + name_w + 3))
    for h in hits:
        src = h.get('_source', {})
        score = h.get('_score')
        score_s = '{:.3f}'.format(score) if isinstance(score, (int, float)) else str(score or '')
        print('{} {} {} {}'.format(
            score_s[:score_w].ljust(score_w),
            str(h.get('_id', ''))[:id_w].ljust(id_w),
            str(src.get('gbId', ''))[:gb_w].ljust(gb_w),
            (src.get('name', '') or '')[:name_w].ljust(name_w),
        ))
    print('')
    print('命中 {} 条'.format(len(hits)))


if __name__ == '__main__':
    main()