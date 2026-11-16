"""HTTP-level acceptance checks for S-11; synthetic identities and temporary storage."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from server import Catalogue, handler


class CatalogueAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'test.sqlite3'
        self.model = Catalogue(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.model))
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def api(self, path, method='GET', payload=None, token='catalogue-admin-demo'):
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        data = None if payload is None else json.dumps(payload).encode()
        try:
            response = urlopen(Request(self.base + path, data=data, headers=headers, method=method), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response)

    def resource(self, code='A-103', kind='room'):
        return {'code': code, 'name': 'Навчальний ресурс', 'kind': kind, 'status': 'available'}

    def test_ac1_admin_creates_both_types_and_values_persist(self):
        for code, kind in [('A-103', 'room'), ('P-002', 'equipment')]:
            self.assertEqual(self.api('/api/resources', 'POST', self.resource(code, kind))[0], 201)
        reopened = Catalogue(self.db)
        actual = {r['code']: r for r in reopened.resources()}
        self.assertEqual(actual['A-103']['kind'], 'room')
        self.assertEqual(actual['P-002']['kind'], 'equipment')
        self.assertEqual(actual['A-103']['status'], 'available')

    def test_ac1_duplicate_is_rejected_after_code_normalization(self):
        self.assertEqual(self.api('/api/resources', 'POST', self.resource())[0], 201)
        self.assertEqual(self.api('/api/resources', 'POST', self.resource(' a-103 '))[0], 409)

    def test_ac1_invalid_availability_does_not_create_resource(self):
        item = self.resource(); item['status'] = 'probably'
        self.assertEqual(self.api('/api/resources', 'POST', item)[0], 400)
        self.assertNotIn('A-103', [r['code'] for r in self.model.resources()])

    def test_ac2_requester_cannot_create_or_modify_via_direct_http(self):
        before = self.model.resources(True)
        self.assertEqual(self.api('/api/resources', 'POST', self.resource(), token='catalogue-requester-demo')[0], 403)
        self.assertEqual(self.api('/api/resources/A-101', 'PUT', {'archived': True}, token='catalogue-requester-demo')[0], 403)
        self.assertEqual(self.model.resources(True), before)

    def test_ac2_unknown_identity_cannot_read_or_write(self):
        self.assertEqual(self.api('/api/resources', token='unknown')[0], 401)
        self.assertEqual(self.api('/api/resources', 'POST', self.resource(), token='unknown')[0], 401)

    def test_ac3_archived_resource_hidden_and_historical_code_unchanged(self):
        self.assertEqual(self.api('/api/resources/A-099', 'PUT', {'archived': False})[0], 200)
        history_before = self.model.history()
        self.assertEqual(self.api('/api/resources/A-099', 'PUT', {'archived': True})[0], 200)
        _, data = self.api('/api/resources', token='catalogue-requester-demo')
        self.assertNotIn('A-099', [r['code'] for r in data['resources']])
        self.assertEqual(self.model.history(), history_before)
        self.assertEqual(history_before[0]['resource_code'], 'A-099')
        self.assertIn('A-099', [r['code'] for r in self.model.resources(True)])

    def test_ac3_requester_cannot_bypass_archive_filter(self):
        self.assertEqual(self.api('/api/resources?include_archived=1', token='catalogue-requester-demo')[0], 403)

    def test_code_change_and_string_boolean_rejected(self):
        self.assertEqual(self.api('/api/resources/A-101', 'PUT', {'code': 'A-NEW'})[0], 400)
        self.assertEqual(self.api('/api/resources/A-101', 'PUT', {'archived': 'false'})[0], 400)

    def test_missing_resource_returns_not_found(self):
        self.assertEqual(self.api('/api/resources/A-404', 'PUT', {'archived': True})[0], 404)

    def test_page_served_with_explicit_teaching_scope(self):
        with urlopen(self.base, timeout=3) as response:
            html = response.read().decode()
        self.assertIn('навчальний каталог', html)
        self.assertIn('академічний IdP', html)


if __name__ == '__main__':
    unittest.main()
