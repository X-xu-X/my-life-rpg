from pathlib import Path
import subprocess
HERE = Path(__file__).resolve().parent
html = (HERE/'template.html').read_text(encoding='utf-8')
css = '\n'.join((HERE/p).read_text(encoding='utf-8') for p in ['core.css','full.css'])
js = '\n'.join((HERE/p).read_text(encoding='utf-8') for p in ['core.js','system.js','journal.js','account.js','admin.js','review-v2.js','boot.js'])
subprocess.run(['node','--check','-'],input=js,text=True,encoding='utf-8',check=True)
(HERE/'index.html').write_text(html.replace('/* STYLE */',css).replace('/* SCRIPT */',js),encoding='utf-8')
prefix=(HERE.parent/'lifexp-context-preview-2026-10-17/check-preview.mjs').read_text(encoding='utf-8').split('  const shots=[];')[0]
prefix=prefix.replace('errors.push(message.params.exceptionDetails.text)', 'errors.push(message.params.exceptionDetails.exception?.description||message.params.exceptionDetails.text)')
(HERE/'check-preview.mjs').write_text(prefix+(HERE/'checks.js').read_text(encoding='utf-8').replace('  /* REVIEW_CHECKS */',(HERE/'review-checks.js').read_text(encoding='utf-8')),encoding='utf-8')
print('Built unified standalone demo: '+str(HERE/'index.html'))
