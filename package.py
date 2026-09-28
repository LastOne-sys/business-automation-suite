"""Build independently installable, credential-free product archives."""
from pathlib import Path
import zipfile
from core.store import PROJECTS

ROOT = Path(__file__).resolve().parent
for key, meta in PROJECTS.items():
    folder = ROOT / 'projects' / key
    folder.mkdir(parents=True, exist_ok=True)
    launcher = f"import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[2]))\nfrom core.server import run\nif __name__ == '__main__': run('{key}')\n"
    (folder/'run.py').write_text(launcher, encoding='utf-8')
    for name, flag in [('START',''),('DEMO',' --demo')]:
        command = f'@echo off\r\ncd /d "%~dp0..\\.."\r\nif not exist ".venv\\Scripts\\python.exe" (\r\n  echo Run install.ps1 in the main folder first.\r\n  pause\r\n  exit /b 1\r\n)\r\n".venv\\Scripts\\python.exe" run.py --project {key}{flag}\r\npause\r\n'
        (folder/(name+'.cmd')).write_text(command, encoding='ascii', newline='')
    base_readme = (ROOT/'README.md').read_text(encoding='utf-8')
    base_readme = base_readme.replace('Open one of the four folders under `projects` and double-click', 'In this extracted folder double-click')
    readme = f"# {meta['name']}\n\n{meta['tagline']}\n\nThis archive contains one independently installable application. The shared reference below describes the complete product family.\n\n" + base_readme
    readme += f"\n## This product\n\nRun `python run.py` or `python run.py --demo`. URL: http://127.0.0.1:{meta['port']}. Data: `data/{key}` (demo: `data/{key}-demo`).\n"
    (folder/'README.md').write_text(readme, encoding='utf-8')
    dest = ROOT/'dist'/f"{meta['name']}-1.0.zip"
    dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for sub in ('core','web'):
            for p in (ROOT/sub).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:
                    z.write(p,str(p.relative_to(ROOT)))
        z.write(ROOT/'tests'/'test_business.py','tests/test_business.py')
        if (ROOT/'examples').exists():
            for p in (ROOT/'examples').iterdir():
                if p.is_file():z.write(p,'examples/'+p.name)
        for name in ('requirements.txt','install.ps1','.gitignore','HANDOVER-RU.md','MARKET-RESEARCH.md'):
            z.write(ROOT/name,name)
        if (ROOT/'VERIFICATION.md').exists():z.write(ROOT/'VERIFICATION.md','VERIFICATION.md')
        z.writestr('README.md',readme)
        z.writestr('run.py',f"from core.server import run\nif __name__ == '__main__': run('{key}')\n")
        for name, flag in [('START',''),('DEMO',' --demo')]:
            z.writestr(name+'.cmd',f'@echo off\r\ncd /d "%~dp0"\r\nif not exist ".venv\\Scripts\\python.exe" (\r\n echo Run install.ps1 first.\r\n pause\r\n exit /b 1\r\n)\r\n".venv\\Scripts\\python.exe" run.py{flag}\r\npause\r\n')
    print(meta['name'],dest.stat().st_size,'bytes')
