"""Local demonstration launcher; separate synthetic databases, no external sends."""
import subprocess
import sys
import json
import socket
from pathlib import Path
from core.store import PROJECTS

root=Path(__file__).resolve().parent
(root/'data').mkdir(exist_ok=True)
processes={}
for project in PROJECTS:
    with socket.socket() as check:
        if check.connect_ex(('127.0.0.1', PROJECTS[project]['port'])) == 0:
            print(project, 'already has a listener; not starting another copy')
            continue
    log=open(root/'data'/f'{project}.log','a',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,str(root/'run.py'),'--project',project,'--demo'],cwd=root,
                          stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    processes[project]=proc.pid
    log.close()
(root/'data'/'demo-processes.json').write_text(json.dumps(processes),encoding='utf-8')
print('Started four demo processes:', ', '.join(PROJECTS))
