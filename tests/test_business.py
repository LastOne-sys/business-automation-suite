import csv
import io
import json
import tempfile
import threading
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from core.domain import Invalid, quote_lines, support_answer, safe_csv, calendar_file
from core.store import Store
from core.server import Server


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def store(self, name):
        return Store(name, Path(self.tmp.name) / name)

    def invoice(self, **changes):
        fields = dict(Vendor='Acme', Invoice='A-1', Date='2026-09-28', Due='2026-10-28', Net='100', Tax='20', Total='120', Currency='EUR')
        fields.update(changes)
        return {'text': '\n'.join(f'{k}: {v}' for k,v in fields.items())}

    def booking(self, store):
        day = datetime.now(timezone.utc).date() + timedelta(days=1)
        while day.weekday() > 4:
            day += timedelta(days=1)
        slots = store.slots(day.isoformat(), 'Консультация', 'Специалист 1')
        return dict(customer='Customer', email='person@example.com', service='Консультация', resource='Специалист 1', start=slots[0]['value'], consent=True)

    def test_quote_decimal_and_discount(self):
        s=self.store('quote');s.save_catalog({'csv':'sku,name,price\nA,Product,0.10'})
        s.create_quote({'customer':'Buyer','email':'b@example.com','lines':'A,3','discount':'10'})
        self.assertEqual(s.records()[0]['total'],'0.27')

    def test_quote_unknown_blocks_approval(self):
        s=self.store('quote');r=s.create_quote({'customer':'Buyer','email':'b@example.com','lines':'MISSING,3'})
        with self.assertRaises(Invalid):s.action(r['id'],'approve',{})
        self.assertEqual(len(list(csv.reader(io.StringIO(s.export().decode('utf-8-sig'))))),1)

    def test_quote_price_snapshot(self):
        s=self.store('quote');s.save_catalog({'csv':'sku,name,price\nA,One,10'})
        s.create_quote({'customer':'Buyer','email':'b@example.com','lines':'A,2'})
        s.save_catalog({'csv':'sku,name,price\nA,One,100'})
        self.assertEqual(s.records()[0]['total'],'20.00')

    def test_catalog_atomic_on_duplicate(self):
        s=self.store('quote');s.save_catalog({'csv':'sku,name,price\nA,One,10'})
        with self.assertRaises(Invalid):s.save_catalog({'csv':'sku,name,price\nB,Two,10\nB,Three,12'})
        self.assertIn('A',s.catalog())

    def test_invalid_quantity_and_money(self):
        for q in ['NaN','-1','0','Infinity','100001']:
            with self.assertRaises(Invalid):quote_lines('A,'+q,{'A':{'name':'One','price':'10'}})

    def test_invoice_exact_duplicate(self):
        s=self.store('invoice');a=s.create_invoice(self.invoice());b=s.create_invoice(self.invoice())
        self.assertEqual(a['id'],b['id']);self.assertTrue(b['duplicate']);self.assertEqual(len(s.records()),1)

    def test_invoice_number_duplicate(self):
        s=self.store('invoice');s.create_invoice(self.invoice())
        with self.assertRaises(Invalid):s.create_invoice(self.invoice(Total='999'))

    def test_invoice_invalid_totals_not_exported(self):
        s=self.store('invoice');r=s.create_invoice(self.invoice(Total='130'))
        with self.assertRaises(Invalid):s.action(r['id'],'approve',{})
        self.assertNotIn('Acme',s.export().decode())

    def test_invoice_precision_not_silently_rounded(self):
        s=self.store('invoice');r=s.create_invoice(self.invoice(Net='100.001',Total='120.001'))
        with self.assertRaises(Invalid):s.action(r['id'],'approve',{})

    def test_booking_resources_configurable(self):
        s=self.store('booking');settings=s.setting('business')
        s.configure({**settings,'resources':'Team A\nTeam B','services':'Assessment,90'})
        self.assertEqual(s.setting('business')['services'],{'Assessment':90})

    def test_catalog_currency_not_relabelled(self):
        s=self.store('quote');s.save_catalog({'csv':'sku,name,price\nA,Item,10'})
        with self.assertRaises(Invalid):s.configure({'name':'Shop','currency':'USD'})

    def test_invoice_correction_reapproval(self):
        s=self.store('invoice');r=s.create_invoice(self.invoice());s.action(r['id'],'approve',{})
        fields=s.records()[0]['fields'];fields['total']='140';s.save_invoice(r['id'],fields)
        self.assertEqual(s.records()[0]['status'],'review');self.assertNotIn('Acme',s.export().decode())

    def test_paid_invoice_immutable(self):
        s=self.store('invoice');r=s.create_invoice(self.invoice());s.action(r['id'],'approve',{});s.action(r['id'],'paid',{})
        with self.assertRaises(Invalid):s.save_invoice(r['id'],s.records()[0]['fields'])

    def test_persistence_after_restart(self):
        s=self.store('invoice');s.create_invoice(self.invoice());self.assertEqual(len(self.store('invoice').records()),1)

    def test_support_known_source(self):
        s=self.store('support');s.save_article({'title':'Доставка','keywords':'доставка сроки','body':'Три дня.'})
        answer=s.ask({'question':'Доставка','customer':'A','email':'a@example.com'})
        self.assertEqual(answer['answer'],'Три дня.');self.assertEqual(answer['source']['title'],'Доставка')

    def test_support_no_fabrication(self):
        self.assertEqual(support_answer('What is my bank balance?',[])['status'],'needs_agent')

    def test_support_ambiguous_escalates(self):
        a=[{'id':'1','title':'Shipping','keywords':'delivery','body':'A'}, {'id':'2','title':'Shipping','keywords':'delivery','body':'B'}]
        self.assertEqual(support_answer('Shipping',a)['status'],'needs_agent')

    def test_support_no_close_without_reply(self):
        s=self.store('support');r=s.ask({'question':'Help','customer':'A','email':'a@example.com'})
        with self.assertRaises(Invalid):s.action(r['id'],'close',{})
        s.action(r['id'],'reply',{'reply':'We will help.'});s.action(r['id'],'close',{})
        self.assertEqual(s.records()[0]['status'],'closed')

    def test_booking_concurrent_conflict(self):
        s=self.store('booking');body=self.booking(s)
        def create(_):
            try:s.book(body);return True
            except Invalid:return False
        with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(create,range(6)))
        self.assertEqual(sum(results),1)

    def test_booking_overlap_different_duration(self):
        s=self.store('booking');body=self.booking(s);body['service']='Расширенная встреча';s.book(body)
        body['start']=(datetime.fromisoformat(body['start'])+timedelta(minutes=30)).isoformat()
        body['service']='Консультация'
        with self.assertRaises(Invalid):s.book(body)

    def test_booking_cancel_releases_slot(self):
        s=self.store('booking');body=self.booking(s);r=s.book(body);s.cancel(token=r['cancel_token']);s.book(body)
        self.assertEqual(len(s.bookings()),2)

    def test_booking_consent_required(self):
        s=self.store('booking');body=self.booking(s);body['consent']=False
        with self.assertRaises(Invalid):s.book(body)

    def test_reminders_idempotent_and_cancelled(self):
        s=self.store('booking');r=s.book(self.booking(s))
        with s.db() as db:
            db.execute('UPDATE appointments SET start=?,end=? WHERE id=?',
                ((datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                 (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),r['id']))
        self.assertEqual(s.prepare_reminders()['created'],1)
        self.assertEqual(s.prepare_reminders()['created'],0)
        s.cancel(rid=r['id'])
        self.assertEqual(s.dashboard()['reminders'][0]['status'],'cancelled')

    def test_backup_restores_records(self):
        import sqlite3
        s=self.store('invoice');s.create_invoice(self.invoice())
        backup=Path(self.tmp.name)/'backup.sqlite3'
        with s.db() as db, closing(sqlite3.connect(backup)) as target:db.backup(target)
        with closing(sqlite3.connect(backup)) as restored:
            self.assertEqual(restored.execute("SELECT count(*) FROM records WHERE kind='invoice'").fetchone()[0],1)

    def test_calendar_injection_escaped(self):
        s=self.store('booking');s.book(self.booking(s));row=s.bookings()[0];row['service']='Test\nEND:VEVENT'
        out=calendar_file(row,'Office').decode();self.assertEqual(out.count('\r\nEND:VEVENT'),1)

    def test_csv_formula_protection(self):
        out=safe_csv([['=HYPERLINK("bad")',' +cmd','normal']]).decode('utf-8-sig')
        row=next(csv.reader(io.StringIO(out)));self.assertTrue(row[0].startswith("'"));self.assertTrue(row[1].startswith("'"))

    def test_password_change_revokes_sessions(self):
        s=self.store('quote');pwd=(s.directory/'FIRST-LOGIN.txt').read_text().splitlines()[1];token=s.login(pwd)
        self.assertTrue(s.authorized(token));s.change_password(pwd,'NewStrongPassword123');self.assertFalse(s.authorized(token));self.assertFalse((s.directory/'FIRST-LOGIN.txt').exists())

    def test_seed_does_not_overwrite(self):
        s=self.store('invoice');s.seed();s.seed();self.assertEqual(len(s.records()),2)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store('support',self.tmp.name)
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        hdr={'Content-Type':'application/json','X-Requested-With':'BusinessDesk',**(headers or {})}
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=hdr)
        try:
            with urlopen(req) as r:return r.status,r.read(),r.headers
        except HTTPError as e:return e.code,e.read(),e.headers

    def test_private_data_requires_auth(self):
        self.assertEqual(self.request('/api/dashboard')[0],401)
        self.assertEqual(self.request('/api/export')[0],401)

    def test_cross_origin_write_rejected(self):
        self.assertEqual(self.request('/api/login',{'password':'x'},{'Origin':'https://evil.example'})[0],403)

    def test_dns_rebinding_rejected(self):
        self.assertEqual(self.request('/api/info',headers={'Host':'evil.example'})[0],403)

    def test_login_cookie_and_logout(self):
        password=(self.store.directory/'FIRST-LOGIN.txt').read_text().splitlines()[1]
        status,_,headers=self.request('/api/login',{'password':password});self.assertEqual(status,200)
        self.assertIn('HttpOnly',headers['Set-Cookie']);cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/dashboard',headers={'Cookie':cookie})[0],200)
        self.request('/api/logout',{},headers={'Cookie':cookie})
        self.assertEqual(self.request('/api/dashboard',headers={'Cookie':cookie})[0],401)

    def test_public_ask_stores_without_exposing_private_data(self):
        status,body,_=self.request('/api/public/ask',{'customer':'Visitor','email':'v@example.com','question':'Hello','consent':True})
        self.assertEqual(status,200);self.assertNotIn(b'v@example.com',body);self.assertEqual(len(self.store.records()),1)

    def test_login_rate_limit(self):
        for _ in range(8):self.request('/api/login',{'password':'bad'})
        self.assertEqual(self.request('/api/login',{'password':'bad'})[0],429)


if __name__=='__main__':unittest.main()
