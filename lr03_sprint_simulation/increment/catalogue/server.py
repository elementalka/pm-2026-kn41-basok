"""S-11 local teaching increment; fixture identities, never a production IdP."""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, parse_qs, unquote

HERE = Path(__file__).resolve().parent
FIXTURES = json.loads((HERE / 'fixtures.json').read_text(encoding='utf-8'))


def validate(payload, code=None):
    if not isinstance(payload, dict):
        raise ValueError('JSON object required')
    allowed = {'code', 'name', 'kind', 'status', 'archived'}
    if set(payload) - allowed:
        raise ValueError('Unknown fields')
    if code is None:
        if not all(k in payload for k in ('code', 'name', 'kind', 'status')):
            raise ValueError('code/name/kind/status required')
    for key in ('code', 'name', 'kind', 'status'):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            raise ValueError(key + ' must be non-empty text')
    result = {k: v.strip() if isinstance(v, str) else v for k, v in payload.items()}
    if 'code' in result:
        result['code'] = result['code'].upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,31}', result['code']):
            raise ValueError('Invalid resource code')
        if code is not None and result['code'] != code:
            raise ValueError('Resource code is immutable')
    if 'name' in result and len(result['name']) > 160:
        raise ValueError('Name exceeds 160 characters')
    if 'kind' in result and result['kind'] not in ('room', 'equipment'):
        raise ValueError('kind must be room or equipment')
    if 'status' in result and result['status'] not in ('available', 'unavailable'):
        raise ValueError('status must be available or unavailable')
    if 'archived' in result and not isinstance(result['archived'], bool):
        raise ValueError('archived must be boolean')
    return result


class Catalogue:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS resources (
                    code TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                    status TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS history (
                    request_id TEXT PRIMARY KEY,
                    resource_code TEXT NOT NULL REFERENCES resources(code),
                    status TEXT NOT NULL);
            ''')
            if not db.execute('SELECT count(*) FROM resources').fetchone()[0]:
                for r in FIXTURES['resources']:
                    db.execute('INSERT INTO resources VALUES (?,?,?,?,?)',
                               (r['code'], r['name'], r['kind'], r['status'], r['archived']))
                for r in FIXTURES['historical_requests']:
                    db.execute('INSERT INTO history VALUES (?,?,?)',
                               (r['request_id'], r['resource_code'], r['status']))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def resources(self, include_archived=False):
        with self.connect() as db:
            where = '' if include_archived else 'WHERE archived=0'
            return [dict(r) for r in db.execute('SELECT * FROM resources ' + where + ' ORDER BY code')]

    def create(self, payload):
        r = validate(payload)
        with self.connect() as db:
            db.execute('INSERT INTO resources VALUES (?,?,?,?,?)',
                       (r['code'], r['name'], r['kind'], r['status'], r.get('archived', False)))
        return r

    def update(self, code, payload):
        r = validate(payload, code)
        with self.connect() as db:
            old = db.execute('SELECT * FROM resources WHERE code=?', (code,)).fetchone()
            if old is None:
                return None
            values = dict(old)
            values.update(r)
            db.execute('UPDATE resources SET name=?,kind=?,status=?,archived=? WHERE code=?',
                       (values['name'], values['kind'], values['status'], values['archived'], code))
        return values

    def history(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM history ORDER BY request_id')]


def handler(catalogue):
    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data):
            raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def dispatch(self, method):
            path = urlsplit(self.path)
            if method == 'GET' and path.path == '/':
                raw = (HERE / 'index.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            authorization = self.headers.get('Authorization', '')
            token = authorization[7:] if authorization.startswith('Bearer ') else ''
            role = FIXTURES['identities'].get(token)
            if role is None:
                self.respond(401, {'error': 'Unknown fixture identity'})
                return
            if method in ('POST', 'PUT') and role != 'admin':
                self.respond(403, {'error': 'Requester cannot edit the catalogue'})
                return
            try:
                if method == 'GET' and path.path == '/api/resources':
                    archived = parse_qs(path.query).get('include_archived') == ['1']
                    if archived and role != 'admin':
                        self.respond(403, {'error': 'Archive listing requires admin'})
                        return
                    self.respond(200, {'resources': catalogue.resources(archived)})
                    return
                if method == 'GET' and path.path == '/api/history':
                    self.respond(200, {'requests': catalogue.history()})
                    return
                if method in ('POST', 'PUT'):
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536:
                        raise ValueError('Body size must be 1..65536 bytes')
                    payload = json.loads(self.rfile.read(size))
                    if method == 'POST' and path.path == '/api/resources':
                        self.respond(201, {'resource': catalogue.create(payload)})
                        return
                    if method == 'PUT' and path.path.startswith('/api/resources/'):
                        code = unquote(path.path.removeprefix('/api/resources/')).strip().upper()
                        result = catalogue.update(code, payload)
                        self.respond(200 if result else 404, {'resource': result})
                        return
                self.respond(404, {'error': 'Not found'})
            except sqlite3.IntegrityError:
                self.respond(409, {'error': 'Resource code already exists'})
            except (ValueError, UnicodeDecodeError) as exc:
                self.respond(400, {'error': str(exc)})

        def do_GET(self): self.dispatch('GET')
        def do_POST(self): self.dispatch('POST')
        def do_PUT(self): self.dispatch('PUT')
    return API


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8731)
    parser.add_argument('--db', type=Path, default=HERE / 'catalogue.sqlite3')
    args = parser.parse_args()
    httpd = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Catalogue(args.db)))
    print('Teaching fixture catalogue: http://127.0.0.1:' + str(args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
