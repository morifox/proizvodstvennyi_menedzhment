import base64, io, json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
import app

class SmartFlowTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'test.sqlite3';app.init()
  self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def req(self,path,data=None):
  r=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(r) as x:return x.status,json.loads(x.read())
  except urllib.error.HTTPError as x:return x.code,json.loads(x.read())
 def upload(self,name='Счёт_104.txt'):
  data=(app.ROOT/'examples'/name).read_bytes();return self.req('/api/upload',{'name':name,'data':base64.b64encode(data).decode()})
 def test_workflow(self):
  code,d=self.upload();self.assertEqual(code,201);i=d['id'];f=self.req(f'/api/documents/{i}')[1]['fields'];self.assertEqual(f['amount'],'24500.00')
  self.assertEqual(self.req(f'/api/documents/{i}/approve',{})[0],400)
  self.assertEqual(self.req(f'/api/documents/{i}/submit',{'fields':f})[0],200)
  self.assertEqual(self.req(f'/api/documents/{i}')[1]['route'],'Бухгалтер')
  self.assertEqual(self.req(f'/api/documents/{i}/save',{'fields':f})[0],400)
  self.assertEqual(self.req(f'/api/documents/{i}/reject',{'reason':''})[0],400)
  self.assertEqual(self.req(f'/api/documents/{i}/reject',{'reason':'Исправить'})[0],200)
  self.req('/api/settings',{'threshold':'10000'})
  self.req(f'/api/documents/{i}/submit',{'fields':f});self.assertEqual(self.req(f'/api/documents/{i}')[1]['route'],'Руководитель')
  self.assertEqual(self.req(f'/api/documents/{i}/approve',{})[0],200)
  self.assertEqual(self.req(f'/api/documents/{i}')[1]['status'],'Согласован')
  app.init();self.assertEqual(len(self.req('/api/documents')[1]),1)
 def test_file_formats_and_duplicates(self):
  for ext in ['txt','pdf','docx']:
   code,d=self.upload('Счёт_104.'+ext);self.assertEqual(code,201,d)
   self.assertEqual(self.req('/api/documents/'+str(d['id']))[1]['fields']['number'],'104')
  self.assertEqual(self.upload()[0],409)
 def test_validation(self):
  for n in ['NaN','Infinity','0','-2','1.111']:
   with self.assertRaises(ValueError):app.money(n)
  with self.assertRaises(ValueError):app.validate({'number':'1','date':'31.02.2026','supplier':'A','inn':'7701234567','amount':'10'})
  self.assertEqual(self.req('/api/documents/999')[0],404)
 def test_threshold_and_export(self):
  _,d=self.upload();i=d['id'];f=self.req(f'/api/documents/{i}')[1]['fields'];f['amount']='50000';f['supplier']='=TEST'
  self.req(f'/api/documents/{i}/submit',{'fields':f});self.assertEqual(self.req(f'/api/documents/{i}')[1]['route'],'Бухгалтер')
  with urllib.request.urlopen(self.url+'/api/export') as r:self.assertIn("'=TEST",r.read().decode('utf-8-sig'))
if __name__=='__main__':unittest.main()
