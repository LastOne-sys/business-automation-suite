import json
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen

root=Path(__file__).resolve().parents[1]
results=[]
for project,name in [('quote','QuoteDesk'),('invoice','InvoiceDesk'),('support','SupportDesk'),('booking','BookDesk')]:
    with tempfile.TemporaryDirectory() as temp:
        with zipfile.ZipFile(root/'dist'/f'{name}-1.0.zip') as archive:
            assert not any('FIRST-LOGIN' in n or n.endswith('.sqlite3') or n.startswith('data/') for n in archive.namelist())
            archive.extractall(temp)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        proc=subprocess.Popen([sys.executable,'run.py','--port',str(port)],cwd=temp,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            result=None
            for _ in range(50):
                if proc.poll() is not None:raise RuntimeError(proc.stderr.read().decode(errors='replace'))
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/info',timeout=1) as response:result=json.load(response)
                    break
                except OSError:time.sleep(.1)
            assert result and result['project']==project,(project,result)
            assert not result['settings']['demo']
            with urlopen(f'http://127.0.0.1:{port}/',timeout=1) as response:assert b'app.js' in response.read()
            assert (Path(temp)/'data'/project/'FIRST-LOGIN.txt').exists()
            results.append(name+': standalone archive starts, empty workspace, generated private password, no packaged secrets')
        finally:
            proc.terminate();proc.wait(timeout=5);proc.stderr.close()
print('\n'.join(results))
(root/'archive-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
