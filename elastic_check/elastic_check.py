# -*- coding: utf-8 -*-
import json
import os
import sys
import base64
import time

try:
    import requests
except ImportError:
    sys.stderr.write('缺少依赖: requests, 请先 pip install requests\n')
    sys.exit(2)


EXPECTED_MAPPING_STR = """
{
  "settings": {
    "analysis": {
      "analyzer": {
        "ngram_analyzer": {
          "tokenizer": "ngram_tokenizer"
        }
      },
      "tokenizer": {
        "ngram_tokenizer": {
          "type": "ngram",
          "min_gram": 2,
          "max_gram": 3,
          "token_chars": ["letter", "digit"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "ngram_analyzer",
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      },
      "gbId": {
        "type": "long"
      }
    }
  }
}
"""


def _load_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if not os.path.isfile(cfg_path):
        sys.stderr.write('未找到配置文件: {}\n'.format(cfg_path))
        sys.exit(2)
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    return cfg, cfg_path


class ElasticChecker(object):
    STATUS_OK = 'OK'
    STATUS_FAIL = 'FAIL'
    STATUS_WARN = 'WARN'

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
        if self.user:
            userpass = '{}:{}'.format(self.user, self.password)
        else:
            userpass = self.password or ''
        if userpass:
            auth = base64.b64encode(userpass.encode('utf-8')).decode('utf-8')
            h['Authorization'] = 'Basic {}'.format(auth)
        if with_json:
            h['Content-Type'] = 'application/json'
        return h

    def _get(self, path):
        url = '{}{}'.format(self.base_url, path)
        try:
            r = requests.get(url, headers=self._headers(), timeout=self.timeout_sec)
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def _head(self, path):
        url = '{}{}'.format(self.base_url, path)
        try:
            r = requests.head(url, headers=self._headers(), timeout=self.timeout_sec)
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def _put(self, path, body):
        url = '{}{}'.format(self.base_url, path)
        try:
            r = requests.put(
                url,
                headers=self._headers(with_json=True),
                data=body if isinstance(body, bytes) else body.encode('utf-8'),
                timeout=self.timeout_sec,
            )
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def _post(self, path, body):
        url = '{}{}'.format(self.base_url, path)
        try:
            r = requests.post(
                url,
                headers=self._headers(with_json=True),
                data=body if isinstance(body, bytes) else body.encode('utf-8'),
                timeout=self.timeout_sec,
            )
            return r.status_code, r.text, None
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    def check_connectivity(self):
        code, body, err = self._get('/')
        if err is not None:
            return self.STATUS_FAIL, 'unreachable: {}'.format(err), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}'.format(code), body
        try:
            j = json.loads(body)
            info = 'cluster={}, version={}'.format(
                j.get('cluster_name', '?'),
                j.get('version', {}).get('number', '?'),
            )
        except Exception:
            info = body[:120]
        return self.STATUS_OK, info, None

    def check_auth(self):
        code, body, err = self._get('/_cluster/health')
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 200:
            return self.STATUS_OK, 'basic auth ok', None
        if code in (401, 403):
            return self.STATUS_FAIL, 'auth rejected (http {})'.format(code), body
        return self.STATUS_FAIL, 'http {}'.format(code), body

    def check_index_exists(self):
        code, body, err = self._head('/{}'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 200:
            return self.STATUS_OK, "index '{}' exists".format(self.index_name), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        return self.STATUS_FAIL, 'http {}'.format(code), body

    def ensure_index(self):
        code, _, err = self._head('/{}'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'head err: {}'.format(err), None
        if code == 200:
            return self.STATUS_OK, "index '{}' 已存在".format(self.index_name), None
        if code != 404:
            return self.STATUS_FAIL, "head http {}".format(code), None
        put_code, put_body, put_err = self._put(
            '/{}'.format(self.index_name), EXPECTED_MAPPING_STR,
        )
        if put_err is not None:
            return self.STATUS_FAIL, 'create err: {}'.format(put_err), None
        if put_code in (200, 201):
            try:
                j = json.loads(put_body)
                if j.get('acknowledged') is False:
                    return self.STATUS_FAIL, 'create not acknowledged: {}'.format(put_body)[:200], None
            except Exception:
                pass
            return self.STATUS_OK, "index '{}' 已创建".format(self.index_name), None
        if put_code == 400 and 'resource_already_exists_exception' in (put_body or ''):
            return self.STATUS_OK, "index '{}' 已存在(并发创建)".format(self.index_name), None
        return self.STATUS_FAIL, 'create http {}: {}'.format(put_code, (put_body or '')[:160]), None

    def check_index_health(self):
        code, body, err = self._get('/_cluster/health/{}'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}'.format(code), body
        try:
            j = json.loads(body)
            status = j.get('status', '?')
            active = j.get('active_shards', '?')
            primary = j.get('active_primary_shards', '?')
            unassigned = j.get('unassigned_shards', '?')
            info = 'status={}, active_shards={}, primary={}, unassigned={}'.format(
                status, active, primary, unassigned,
            )
            if status == 'red':
                return self.STATUS_FAIL, info, None
            if status == 'yellow':
                return self.STATUS_WARN, info, None
            return self.STATUS_OK, info, None
        except Exception as e:
            return self.STATUS_FAIL, 'parse err: {}'.format(e), body

    def check_index_stats(self):
        code, body, err = self._get('/{}/_stats'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}'.format(code), body
        try:
            j = json.loads(body)
            idx = j.get('_all', {}).get('total', {}).get('docs', {})
            store = j.get('_all', {}).get('total', {}).get('store', {})
            count = idx.get('count', '?')
            size_bytes = store.get('size_in_bytes', 0)
            if isinstance(size_bytes, (int, float)) and size_bytes:
                if size_bytes > 1024 * 1024:
                    size_str = '{:.2f}MB'.format(size_bytes / (1024.0 * 1024.0))
                elif size_bytes > 1024:
                    size_str = '{:.2f}KB'.format(size_bytes / 1024.0)
                else:
                    size_str = '{}B'.format(size_bytes)
            else:
                size_str = '?'
            info = 'docs={}, size={}'.format(count, size_str)
            return self.STATUS_OK, info, None
        except Exception as e:
            return self.STATUS_FAIL, 'parse err: {}'.format(e), body

    def check_index_mapping(self):
        code, body, err = self._get('/{}/_mapping'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}'.format(code), body
        try:
            actual = json.loads(body)
            expected = json.loads(EXPECTED_MAPPING_STR)
            exp_props = expected['mappings']['properties']
            actual_props = (
                actual.get(self.index_name, {})
                      .get('mappings', {})
                      .get('properties', {})
            )
            diffs = []
            for fname, fexp in exp_props.items():
                fact = actual_props.get(fname)
                if fact is None:
                    diffs.append("field '{}' missing".format(fname))
                    continue
                for k, v in fexp.items():
                    if k == 'fields':
                        fact_inner = fact.get('fields', {})
                        for ik, iv in v.items():
                            if fact_inner.get(ik, {}).get('type') != iv.get('type'):
                                diffs.append(
                                    "field '{}.{}.type' = {} (期望 {})".format(
                                        fname, ik, fact_inner.get(ik, {}).get('type'), iv.get('type'),
                                    )
                                )
                        continue
                    if k == 'analyzer':
                        if fact.get(k) != v:
                            diffs.append(
                                "field '{}.analyzer' = {} (期望 {})".format(fname, fact.get(k), v)
                            )
                        continue
                    if fact.get(k) != v:
                        diffs.append(
                            "field '{}.{}' = {} (期望 {})".format(fname, k, fact.get(k), v)
                        )
            extra = [k for k in actual_props.keys() if k not in exp_props]
            if extra:
                diffs.append('extra fields: {}'.format(extra))
            if not diffs:
                return self.STATUS_OK, 'mapping 与预期一致', None
            return self.STATUS_WARN, '{} 项差异: {}'.format(len(diffs), '; '.join(diffs)[:200]), None
        except Exception as e:
            return self.STATUS_FAIL, 'parse err: {}'.format(e), body

    def check_doc_count(self):
        code, body, err = self._get('/{}/_count'.format(self.index_name))
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}'.format(code), body
        try:
            j = json.loads(body)
            cnt = j.get('count', '?')
            return self.STATUS_OK, 'count={}'.format(cnt), None
        except Exception as e:
            return self.STATUS_FAIL, 'parse err: {}'.format(e), body

    def check_analyzer(self):
        sample = 'hello123'
        req_body = json.dumps({'analyzer': 'ngram_analyzer', 'text': sample})
        code, body, err = self._post(
            '/{}/_analyze'.format(self.index_name), req_body,
        )
        if err is not None:
            return self.STATUS_FAIL, 'err: {}'.format(err), None
        if code == 404:
            return self.STATUS_FAIL, "index '{}' missing (404)".format(self.index_name), None
        if code != 200:
            return self.STATUS_FAIL, 'http {}: {}'.format(code, body[:160]), None
        try:
            j = json.loads(body)
            tokens = [t.get('token', '') for t in j.get('tokens', [])]
        except Exception as e:
            return self.STATUS_FAIL, 'parse err: {}'.format(e), body
        if not tokens:
            return self.STATUS_FAIL, 'no tokens returned', None
        bad_len = [t for t in tokens if len(t) < 2 or len(t) > 3]
        bad_sub = [t for t in tokens if t and t not in sample]
        preview = ','.join(tokens[:10]) + ('...' if len(tokens) > 10 else '')
        info = 'tokens[{}]=[{}]'.format(len(tokens), preview)
        problems = []
        if bad_len:
            problems.append('长度越界: {}'.format(bad_len))
        if bad_sub:
            problems.append('非子串: {}'.format(bad_sub))
        if problems:
            return self.STATUS_WARN, info + ' | ' + '; '.join(problems), None
        return self.STATUS_OK, info, None

    @staticmethod
    def _fmt_bytes(n):
        try:
            n = int(n)
        except Exception:
            return str(n)
        if n >= 1024 * 1024:
            return '{:.2f}MB'.format(n / (1024.0 * 1024.0))
        if n >= 1024:
            return '{:.2f}KB'.format(n / 1024.0)
        return '{}B'.format(n)

    def cmd_list(self, include_system=False, filter_prefix=None):
        path = '/_cat/indices?format=json&bytes=b&h=health,status,index,uuid,docs.count,docs.deleted,store.size,pri,rep'
        code, body, err = self._get(path)
        if err is not None:
            print('[FAIL] list err: {}'.format(err))
            return 1
        if code != 200:
            print('[FAIL] list http {}: {}'.format(code, body[:200]))
            return 1
        try:
            rows = json.loads(body)
        except Exception as e:
            print('[FAIL] list parse err: {}'.format(e))
            return 1
        if not rows:
            print('(无索引)')
            return 0
        if not include_system:
            rows = [r for r in rows if not r.get('index', '').startswith('.')]
        if filter_prefix:
            rows = [r for r in rows if r.get('index', '').startswith(filter_prefix)]
        headers = [
            ('health', 6), ('status', 6), ('index', 32), ('pri', 3),
            ('rep', 3), ('docs', 12), ('deleted', 8), ('size', 10),
        ]
        print(' '.join(h.ljust(w) for h, w in headers))
        print('-' * sum(w + 1 for _, w in headers))
        for r in rows:
            cells = [
                r.get('health', '')[:6].ljust(6),
                r.get('status', '')[:6].ljust(6),
                r.get('index', '')[:32].ljust(32),
                str(r.get('pri', ''))[:3].ljust(3),
                str(r.get('rep', ''))[:3].ljust(3),
                str(r.get('docs.count', ''))[:12].ljust(12),
                str(r.get('docs.deleted', ''))[:8].ljust(8),
                self._fmt_bytes(r.get('store.size', ''))[:10].ljust(10),
            ]
            print(' '.join(cells))
        print('')
        print('共 {} 个索引'.format(len(rows)))
        return 0

    def cmd_inspect(self, index_name=None):
        target = index_name or self.index_name
        if not target:
            print('[FAIL] 未指定索引')
            return 1

        print('=== inspect: {} ==='.format(target))
        print('')

        # health
        code, body, err = self._get('/_cluster/health/{}'.format(target))
        if err is not None:
            print('[FAIL] health err: {}'.format(err))
            return 1
        if code == 404:
            print('[FAIL] index "{}" 不存在 (404)'.format(target))
            return 1
        if code != 200:
            print('[FAIL] health http {}: {}'.format(code, body[:160]))
            return 1
        try:
            j = json.loads(body)
            print('-- health --')
            print('  cluster            : {}'.format(j.get('cluster_name', '?')))
            print('  status             : {}'.format(j.get('status', '?')))
            print('  number_of_nodes    : {}'.format(j.get('number_of_nodes', '?')))
            print('  active_shards      : {}'.format(j.get('active_shards', '?')))
            print('  active_primary     : {}'.format(j.get('active_primary_shards', '?')))
            print('  unassigned_shards  : {}'.format(j.get('unassigned_shards', '?')))
            print('  relocating_shards  : {}'.format(j.get('relocating_shards', '?')))
            print('  initializing_shards: {}'.format(j.get('initializing_shards', '?')))
            print('')
        except Exception as e:
            print('[FAIL] health parse: {}'.format(e))
            return 1

        # settings
        code, body, err = self._get('/{}/_settings'.format(target))
        if code == 200:
            try:
                j = json.loads(body)
                idx = j.get(target, {}).get('settings', {}).get('index', {})
                print('-- settings.index --')
                for k in (
                    'number_of_shards', 'number_of_replicas',
                    'refresh_interval', 'creation_date', 'uuid', 'version',
                ):
                    if k in idx:
                        print('  {:<20}: {}'.format(k, idx[k]))
                analyzers = idx.get('analysis', {}).get('analyzer', {})
                tokenizers = idx.get('analysis', {}).get('tokenizer', {})
                if analyzers:
                    print('  -- analyzers --')
                    for an, cfg in analyzers.items():
                        print('    {:<20}: {}'.format(an, json.dumps(cfg, ensure_ascii=False)))
                if tokenizers:
                    print('  -- tokenizers --')
                    for tn, cfg in tokenizers.items():
                        print('    {:<20}: {}'.format(tn, json.dumps(cfg, ensure_ascii=False)))
                print('')
            except Exception as e:
                print('[WARN] settings parse: {}'.format(e))
        elif code != 404:
            print('[WARN] settings http {}'.format(code))

        # mappings
        code, body, err = self._get('/{}/_mapping'.format(target))
        if code == 200:
            try:
                j = json.loads(body)
                props = (
                    j.get(target, {})
                     .get('mappings', {})
                     .get('properties', {})
                )
                print('-- mappings --')
                if not props:
                    print('  (无字段)')
                for fname, fdef in props.items():
                    ftype = fdef.get('type', '?')
                    extra = ''
                    if 'analyzer' in fdef:
                        extra += ' analyzer={}'.format(fdef['analyzer'])
                    if 'fields' in fdef:
                        sub = ', '.join(
                            '{}:{}'.format(k, v.get('type', '?'))
                            for k, v in fdef['fields'].items()
                        )
                        extra += ' fields=[{}]'.format(sub)
                    print('  {:<20}: {}{}'.format(fname, ftype, extra))
                print('')
            except Exception as e:
                print('[WARN] mapping parse: {}'.format(e))
        elif code != 404:
            print('[WARN] mapping http {}'.format(code))

        # stats
        code, body, err = self._get('/{}/_stats'.format(target))
        if code == 200:
            try:
                j = json.loads(body)
                total = j.get('_all', {}).get('total', {})
                docs = total.get('docs', {})
                store = total.get('store', {})
                indexing = total.get('indexing', {})
                print('-- stats --')
                print('  docs.count         : {}'.format(docs.get('count', '?')))
                print('  docs.deleted       : {}'.format(docs.get('deleted', '?')))
                print('  store.size         : {}'.format(self._fmt_bytes(store.get('size_in_bytes', 0))))
                print('  store.throttle_time: {}ms'.format(store.get('throttle_time_in_millis', '?')))
                if indexing:
                    print('  indexing.index_total   : {}'.format(indexing.get('index_total', '?')))
                    print('  indexing.index_time_ms : {}'.format(indexing.get('index_time_in_millis', '?')))
                print('')
            except Exception as e:
                print('[WARN] stats parse: {}'.format(e))
        elif code != 404:
            print('[WARN] stats http {}'.format(code))

        # aliases
        code, body, err = self._get('/{}/_alias'.format(target))
        if code == 200:
            try:
                j = json.loads(body)
                aliases = j.get(target, {}).get('aliases', {})
                if aliases:
                    print('-- aliases --')
                    for a, cfg in aliases.items():
                        print('  {} -> {}'.format(a, json.dumps(cfg, ensure_ascii=False)))
                else:
                    print('-- aliases -- (无)')
                print('')
            except Exception:
                pass

        return 0


def _icon(status):
    return {
        ElasticChecker.STATUS_OK: '[OK]   ',
        ElasticChecker.STATUS_WARN: '[WARN] ',
        ElasticChecker.STATUS_FAIL: '[FAIL] ',
    }.get(status, '[?]    ')


def _print_header(cfg, cfg_path):
    print('== elastic_check ==')
    print('config  : {}'.format(cfg_path))
    print('target  : http://{}:{}/{}'.format(
        cfg.get('host', '127.0.0.1'),
        cfg.get('port', 9200),
        '{}_{}'.format(cfg.get('server_id', 1), cfg.get('index_suffix', 'friend_ik')),
    ))
    print('')


def run_check(checker):
    checks = [
        ('connectivity',   checker.check_connectivity),
        ('auth',           checker.check_auth),
        ('ensure_index',   checker.ensure_index),
        ('index_health',   checker.check_index_health),
        ('index_stats',    checker.check_index_stats),
        ('index_mapping',  checker.check_index_mapping),
        ('analyzer',       checker.check_analyzer),
        ('doc_count',      checker.check_doc_count),
    ]

    results = []
    t0 = time.time()
    for name, fn in checks:
        try:
            status, info, raw = fn()
        except Exception as e:
            status, info, raw = ElasticChecker.STATUS_FAIL, 'exception: {}'.format(e), None
        results.append((name, status, info))
        line = '{}{:<16} {}'.format(_icon(status), name, info)
        print(line)
        if status == ElasticChecker.STATUS_FAIL and name == 'connectivity':
            print('\n连不通, 后续检查终止')
            break
        if status == ElasticChecker.STATUS_FAIL and name == 'ensure_index':
            print("\n索引无法创建, 后续索引相关检查终止")
            break
    elapsed = time.time() - t0

    ok_cnt = sum(1 for _, s, _ in results if s == ElasticChecker.STATUS_OK)
    warn_cnt = sum(1 for _, s, _ in results if s == ElasticChecker.STATUS_WARN)
    fail_cnt = sum(1 for _, s, _ in results if s == ElasticChecker.STATUS_FAIL)

    print('')
    print('Summary: {} OK, {} WARN, {} FAIL  (elapsed {:.2f}s)'.format(
        ok_cnt, warn_cnt, fail_cnt, elapsed,
    ))
    return 1 if fail_cnt > 0 else 0


def _print_usage(prog):
    print('用法:')
    print('  {} [check]                        跑全部 check (默认)'.format(prog))
    print('  {} list [--all] [--prefix PREFIX]  列出所有索引'.format(prog))
    print('  {} inspect [INDEX]                查看索引详细信息 (默认: 配置中的索引)'.format(prog))
    print('')
    print('list 选项:')
    print('  --all                  包含系统索引 (默认隐藏 "." 开头的)')
    print('  --prefix PREFIX        只列出以 PREFIX 开头的索引')


def main():
    cfg, cfg_path = _load_config()
    checker = ElasticChecker(cfg)
    prog = 'elastic_check.py'

    args = sys.argv[1:]
    if not args or args[0] in ('check', '-h', '--help', 'help'):
        if args and args[0] in ('-h', '--help', 'help'):
            _print_usage(prog)
            sys.exit(0)
        _print_header(cfg, cfg_path)
        sys.exit(run_check(checker))

    if args[0] == 'list':
        include_system = '--all' in args
        prefix = None
        if '--prefix' in args:
            i = args.index('--prefix')
            if i + 1 < len(args):
                prefix = args[i + 1]
        _print_header(cfg, cfg_path)
        sys.exit(checker.cmd_list(include_system=include_system, filter_prefix=prefix))

    if args[0] == 'inspect':
        index_name = args[1] if len(args) > 1 else None
        _print_header(cfg, cfg_path)
        sys.exit(checker.cmd_inspect(index_name))

    _print_usage(prog)
    sys.exit(2)


if __name__ == '__main__':
    main()