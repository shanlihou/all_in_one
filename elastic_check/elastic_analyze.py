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


class ElasticAnalyzer(object):

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

    def analyze(self, index, text, analyzer=None, field=None, tokenizer=None,
                filters=None):
        body = {'text': text}
        if analyzer:
            body['analyzer'] = analyzer
        if field:
            body['field'] = field
        if tokenizer:
            body['tokenizer'] = tokenizer
        if filters:
            body['filter'] = filters
        body_str = json.dumps(body, ensure_ascii=False)
        code, resp, err = self._post('/{}/_analyze'.format(index), body_str)
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

    def match_query(self, index, field, text, operator='and', size=5):
        body = {
            'query': {
                'match': {
                    field: {
                        'query': text,
                        'operator': operator,
                    }
                }
            },
            'size': size,
        }
        body_str = json.dumps(body, ensure_ascii=False)
        code, resp, err = self._post('/{}/_search'.format(index), body_str)
        if err is not None:
            return None, 'err: {}'.format(err)
        if code != 200:
            return None, 'http {}: {}'.format(code, (resp or '')[:200])
        try:
            return json.loads(resp), None
        except Exception as e:
            return None, 'parse: {}'.format(e)

    def explain(self, index, field, text):
        body = {
            'query': {
                'match': {
                    field: {
                        'query': text,
                        'operator': 'and',
                    }
                }
            },
        }
        body_str = json.dumps(body, ensure_ascii=False)
        code, resp, err = self._post('/{}/_validate/query?explain=true'.format(index), body_str)
        if err is not None:
            return None, 'err: {}'.format(err)
        if code != 200:
            return None, 'http {}: {}'.format(code, (resp or '')[:200])
        try:
            return json.loads(resp), None
        except Exception as e:
            return None, 'parse: {}'.format(e)


def _print_usage(prog):
    print('用法:')
    print('  {} TEXT                              用 ngram_analyzer 分词 (默认)'.format(prog))
    print('  {} TEXT --field name                 按字段分词 (查询时实际用的方式)'.format(prog))
    print('  {} TEXT --analyzer NAME              指定 analyzer'.format(prog))
    print('  {} TEXT --all                        一次性对比 ngram / field / standard'.format(prog))
    print('  {} TEXT --match                      跑一遍 match query, 看实际命中'.format(prog))
    print('  {} TEXT --explain                    打印 _validate/query?explain 的解析'.format(prog))


def _print_tokens(title, j):
    if j is None:
        print('  (无响应)')
        return
    detail = j.get('detail', {})
    tokens = j.get('tokens', [])
    print('-- {} --'.format(title))
    if detail:
        print('  analyzer : {}'.format(detail.get('analyzer', '?')))
        print('  tokenizer: {}'.format(detail.get('tokenizer', '?')))
    if not tokens:
        print('  (0 tokens)')
        return
    print('  {} tokens:'.format(len(tokens)))
    print('  {:<22} {:<4} {:<6} {:<6} {:<14}'.format(
        'token', 'pos', 'start', 'end', 'type',
    ))
    print('  ' + '-' * 56)
    for t in tokens:
        tok = (t.get('token') or '').replace('\n', '\\n')
        print('  {:<22} {:<4} {:<6} {:<6} {:<14}'.format(
            tok[:22],
            str(t.get('position', ''))[:4],
            str(t.get('start_offset', ''))[:6],
            str(t.get('end_offset', ''))[:6],
            (t.get('type', '') or '')[:14],
        ))


def main():
    cfg, cfg_path = load_config()
    az = ElasticAnalyzer(cfg)
    prog = 'elastic_analyze.py'

    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help', 'help'):
        _print_usage(prog)
        sys.exit(0 if args else 2)

    text = args[0]
    index = az.index_name
    analyzer = 'ngram_analyzer'
    field = None
    do_match = False
    do_explain = False
    do_all = False

    i = 1
    while i < len(args):
        a = args[i]
        if a == '--index':
            i += 1
            if i >= len(args):
                sys.stderr.write('--index 需要一个参数\n')
                sys.exit(2)
            index = args[i]
        elif a == '--field':
            i += 1
            if i >= len(args):
                sys.stderr.write('--field 需要一个参数\n')
                sys.exit(2)
            field = args[i]
            analyzer = None
        elif a == '--analyzer':
            i += 1
            if i >= len(args):
                sys.stderr.write('--analyzer 需要一个参数\n')
                sys.exit(2)
            analyzer = args[i]
            field = None
        elif a == '--match':
            do_match = True
        elif a == '--explain':
            do_explain = True
        elif a == '--all':
            do_all = True
            do_match = True
        else:
            sys.stderr.write('未知参数: {}\n'.format(a))
            _print_usage(prog)
            sys.exit(2)
        i += 1

    print('config  : {}'.format(cfg_path))
    print('index   : {}'.format(index))
    print('text    : "{}"'.format(text))
    print('')

    def _analyze_one(label, **kw):
        j, err = az.analyze(index, text, **kw)
        if err is not None:
            print('[FAIL] {}: {}'.format(label, err))
            return None
        _print_tokens(label, j)
        print('')
        return j

    if do_all:
        _analyze_one('ngram_analyzer', analyzer='ngram_analyzer')
        _analyze_one('field=name', field='name')
        _analyze_one('standard', analyzer='standard')
        match_field = 'name'
        match_op = 'and'
    else:
        if field:
            _analyze_one('field={}'.format(field), field=field)
            match_field = field
        else:
            _analyze_one('analyzer={}'.format(analyzer), analyzer=analyzer)
            match_field = 'name'
        match_op = 'and'

    if do_match:
        j, err = az.match_query(index, match_field, text, operator=match_op, size=5)
        if err is not None:
            print('[FAIL] match query: {}'.format(err))
        else:
            total = j.get('hits', {}).get('total', {})
            if isinstance(total, dict):
                total_v = total.get('value', '?')
            else:
                total_v = total
            hits = j.get('hits', {}).get('hits', [])
            print('-- match query (field={}, op={}) --'.format(match_field, match_op))
            print('  total hits: {}'.format(total_v))
            if hits:
                for h in hits:
                    src = h.get('_source', {})
                    score = h.get('_score')
                    score_s = '{:.3f}'.format(score) if isinstance(score, (int, float)) else '-'
                    print('  [{}] id={} name={!r} gbId={}'.format(
                        score_s,
                        h.get('_id'),
                        src.get('name', ''),
                        src.get('gbId'),
                    ))
            else:
                print('  (0 matches)')
            print('')

    if do_explain:
        j, err = az.explain(index, match_field, text)
        if err is not None:
            print('[FAIL] explain: {}'.format(err))
        else:
            print('-- _validate/query?explain --')
            print(json.dumps(j, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()