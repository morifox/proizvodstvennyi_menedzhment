"""SmartFlow: local, single-user invoice workflow prototype."""
import base64, csv, hashlib, io, json, os, re, sqlite3, sys, zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('SMARTFLOW_DB', ROOT / 'data.sqlite3'))

def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, filename TEXT, digest TEXT UNIQUE, source TEXT, fields TEXT, status TEXT, route TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, doc_id INTEGER, time TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, threshold TEXT);
INSERT OR IGNORE INTO settings VALUES(1,'50000');''')

def event(c,i,msg): c.execute('INSERT INTO events(doc_id,time,message) VALUES(?,?,?)',(i,datetime.now().isoformat(timespec='seconds'),msg))
def money(v):
 try:
  n=Decimal(str(v).replace(' ','').replace('\xa0','').replace(',','.'))
  if not n.is_finite() or n<=0 or n>Decimal('999999999999') or n.as_tuple().exponent < -2: raise ValueError()
  return format(n,'.2f')
 except (InvalidOperation,ValueError): raise ValueError('Сумма должна быть положительным числом, не более 2 знаков после запятой.')
def extract(name,data):
 ext=Path(name).suffix.lower()
 if ext=='.txt':
  try: text=data.decode('utf-8-sig')
  except UnicodeDecodeError: raise ValueError('Сохраните TXT в кодировке UTF-8.')
 elif ext=='.pdf':
  import fitz
  with fitz.open(stream=data,filetype='pdf') as p:
   if p.needs_pass: raise ValueError('PDF защищён паролем.')
   if len(p)>30: raise ValueError('Не более 30 страниц PDF.')
   text='\n'.join(page.get_text() for page in p)
 elif ext=='.docx':
  from docx import Document
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   if sum(i.file_size for i in z.infolist())>30_000_000: raise ValueError('Слишком большой DOCX после распаковки.')
  d=Document(io.BytesIO(data));text='\n'.join([p.text for p in d.paragraphs]+[' '.join(cell.text for cell in row.cells) for t in d.tables for row in t.rows])
 else: raise ValueError('Поддерживаются TXT, DOCX и PDF с текстовым слоем.')
 if len(text.strip())<10: raise ValueError('Нет доступного текста. Для сканов нужен OCR — он не входит в MVP.')
 if len(text)>100000: raise ValueError('Документ содержит слишком много текста.')
 def match(pattern):
  m=re.search(pattern,text,re.I|re.M);return m.group(1).strip() if m else ''
 fields={'number':match(r'сч[её]т(?:\s+на\s+оплату)?\s*[№#]\s*([^\s,]+)'), 'date':match(r'(?:от|дата\s*:?)\s*(\d{2}\.\d{2}\.\d{4})'), 'supplier':match(r'^(?:поставщик|исполнитель)\s*:\s*(.+)$'), 'inn':match(r'ИНН\s*:?\s*(\d{10,12})\b'), 'amount':match(r'(?:итого\s+к\s+оплате|всего\s+к\s+оплате|итого|сумма)\s*:?\s*([\d][\d \xa0]*(?:[.,]\d{1,2})?)')}
 try: fields['amount']=money(fields['amount'])
 except ValueError: fields['amount']=''
 return text,fields

def validate(f):
 f={k:str(f.get(k,'')).strip() for k in ['number','date','supplier','inn','amount']}
 if any(not v for v in f.values()): raise ValueError('Заполните все пять реквизитов.')
 if any(len(v)>250 for v in f.values()): raise ValueError('Реквизит слишком длинный.')
 if not re.fullmatch(r'\d{10}|\d{12}',f['inn']): raise ValueError('ИНН должен содержать 10 или 12 цифр.')
 try: datetime.strptime(f['date'],'%d.%m.%Y')
 except ValueError: raise ValueError('Дата должна существовать и иметь формат ДД.ММ.ГГГГ.')
 f['amount']=money(f['amount']);return f

def pack(row):
 d=dict(row);d['fields']=json.loads(d['fields']);return d

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def send(self,status,body,kind='application/json; charset=utf-8'):
  if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
  elif isinstance(body,str): body=body.encode()
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=self.path.split('?')[0]
  with conn() as c:
   if path=='/api/documents': return self.send(200,[pack(r) for r in c.execute('SELECT * FROM documents ORDER BY id DESC')])
   if re.fullmatch(r'/api/documents/\d+',path):
    i=int(path.rsplit('/',1)[1]);r=c.execute('SELECT * FROM documents WHERE id=?',(i,)).fetchone()
    if not r:return self.send(404,{'error':'Документ не найден.'})
    d=pack(r);d['events']=[dict(e) for e in c.execute('SELECT time,message FROM events WHERE doc_id=? ORDER BY id',(i,))];return self.send(200,d)
   if path=='/api/settings': return self.send(200,dict(c.execute('SELECT threshold FROM settings').fetchone()))
   if path=='/api/export':
    s=io.StringIO();w=csv.writer(s,delimiter=';');w.writerow(['ID','Файл','Номер','Дата','Поставщик','ИНН','Сумма, RUB','Статус','Согласующий'])
    def safe(x):
     x=str(x);return "'"+x if x.lstrip().startswith(('=','+','-','@')) else x
    for r in c.execute('SELECT * FROM documents ORDER BY id'):
     d=pack(r);f=d['fields'];w.writerow([safe(x) for x in [d['id'],d['filename'],f['number'],f['date'],f['supplier'],f['inn'],f['amount'],d['status'],d['route']]])
    return self.send(200,'\ufeff'+s.getvalue(),'text/csv; charset=utf-8')
  files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
  if path in files:
   p=ROOT/'static'/files[path];return self.send(200,p.read_bytes(),{'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[p.suffix])
  self.send(404,{'error':'Не найдено.'})
 def do_POST(self):
  # Local app: reject cross-site browser requests.
  if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.send(403,{'error':'Запрос с другого сайта запрещён.'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length<=0 or length>7_000_000: raise ValueError('Размер запроса превышает лимит.')
   if 'application/json' not in self.headers.get('Content-Type',''): raise ValueError('Ожидается JSON.')
   b=json.loads(self.rfile.read(length))
   with conn() as c:
    if self.path=='/api/upload':
     name=Path(str(b['name']).replace('\\','/')).name[:200];data=base64.b64decode(b['data'],validate=True)
     if len(data)>5_000_000:raise ValueError('Файл должен быть не больше 5 МБ.')
     digest=hashlib.sha256(data).hexdigest();old=c.execute('SELECT id FROM documents WHERE digest=?',(digest,)).fetchone()
     if old:return self.send(409,{'error':'Этот файл уже загружен. Откройте его в реестре.','id':old['id']})
     try:text,f=extract(name,data)
     except ValueError:raise
     except Exception:raise ValueError('Не удалось прочитать файл. Проверьте его формат и содержимое.')
     i=c.execute('INSERT INTO documents(filename,digest,source,fields,status,route,created) VALUES(?,?,?,?,?,?,?)',(name,digest,text,json.dumps(f,ensure_ascii=False),'Проверка','—',datetime.now().isoformat(timespec='seconds'))).lastrowid
     event(c,i,'Загружен документ. Извлечение по правилам; требуется проверка реквизитов.');c.commit();return self.send(201,{'id':i})
    if self.path=='/api/settings':
     n=money(b['threshold']);c.execute('UPDATE settings SET threshold=?',(n,));c.commit();return self.send(200,{'threshold':n})
    m=re.fullmatch(r'/api/documents/(\d+)/(save|submit|approve|reject)',self.path)
    if not m:return self.send(404,{'error':'Не найдено.'})
    i=int(m[1]);action=m[2];r=c.execute('SELECT * FROM documents WHERE id=?',(i,)).fetchone()
    if not r:return self.send(404,{'error':'Документ не найден.'})
    if action in ['save','submit']:
     if r['status'] not in ['Проверка','Возвращён']:raise ValueError('Редактирование доступно до отправки на согласование.')
     f=validate(b.get('fields',{}));status=r['status'];route='—'
     if action=='submit':
      status='На согласовании';limit=Decimal(c.execute('SELECT threshold FROM settings').fetchone()[0]);route='Руководитель' if Decimal(f['amount'])>limit else 'Бухгалтер'
     c.execute('UPDATE documents SET fields=?,status=?,route=? WHERE id=?',(json.dumps(f,ensure_ascii=False),status,route,i));event(c,i,'Реквизиты сохранены.' if action=='save' else 'Направлен на согласование: '+route+'.')
    else:
     if r['status']!='На согласовании':raise ValueError('Документ не находится на согласовании.')
     reason=str(b.get('reason','')).strip()
     if action=='reject' and not reason:raise ValueError('Укажите причину возврата.')
     if len(reason)>1000:raise ValueError('Комментарий не более 1000 символов.')
     c.execute('UPDATE documents SET status=? WHERE id=?',('Согласован' if action=='approve' else 'Возвращён',i));event(c,i,('Согласован: '+r['route']+'.' if action=='approve' else 'Возвращён: '+reason))
    c.commit();return self.send(200,{'ok':True})
  except (ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e) or 'Некорректный запрос.'})
  except Exception:self.send(500,{'error':'Внутренняя ошибка. Проверьте журнал сервера.'});import traceback;traceback.print_exc()

if __name__=='__main__':
 init();port=int(os.environ.get('PORT','8000'));print(f'SmartFlow: http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
