from pathlib import Path

HERE = Path(__file__).resolve().parent
html = (HERE / 'template.html').read_text(encoding='utf-8')
html = html.replace('/* STYLE */', (HERE / 'style.css').read_text(encoding='utf-8'))
html = html.replace('/* SCRIPT */', (HERE / 'app.js').read_text(encoding='utf-8'))
(HERE / 'index.html').write_text(html, encoding='utf-8')
print('Built local standalone preview: ' + str(HERE / 'index.html'))

base = (HERE.parent / 'lifexp-complete-preview-2026-10-16/check-preview.mjs').read_text(encoding='utf-8')
checks = (HERE / 'checks.js').read_text(encoding='utf-8')
checks = checks.replace("  await check('initial standalone", (HERE / 'revision-checks.js').read_text(encoding='utf-8') + "\n  await check('initial standalone", 1)
(HERE / 'check-preview.mjs').write_text(base[:base.index("  await send('Page.enable')")] + checks, encoding='utf-8')
