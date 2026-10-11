"""Generate the actual route surface; policy is explicit, transitive locking needs review."""
import inspect
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.routing import APIRoute
from app.main import app


def inventory():
    rows=[]
    effective=[]
    for route in app.routes:
        if isinstance(route,APIRoute):effective.append(route)
        elif hasattr(route,'effective_route_contexts'):
            effective.extend(context for context in route.effective_route_contexts() if isinstance(context.original_route,APIRoute))
    for route in effective:
        source=inspect.getsource(route.endpoint)
        family=route.path.split('/')[2] if route.path.startswith('/api/') else 'internal'
        for method in sorted(route.methods):
            rows.append({'method':method,'path':route.path,'endpoint':route.endpoint.__module__+'.'+route.endpoint.__name__,
                'family':family,'business_write':method not in ('GET','HEAD','OPTIONS') and family!='auth',
                'authentication':'internal health/proxy block' if family in ('health','ready') else (
                    'auth entry Origin/throttle' if family=='auth' else 'current_user + owner-scoped Session'),
                'direct_profile_lock':'lock_profile(' in source,'direct_receipt':'receipts.' in source,
                'direct_version_guard':'expected_version' in source,'direct_commit':'db.commit()' in source,
                'source':str(Path(inspect.getfile(route.endpoint)).relative_to(Path.cwd())).replace('\\','/'),
                'review_note':'Direct flags exclude service-layer behavior; see BUSINESS_WRITE_POLICY_2026-10-10.md'})
    return rows


if __name__=='__main__':
    output=json.dumps(inventory(),ensure_ascii=False,indent=2)
    if len(sys.argv)==2:Path(sys.argv[1]).write_text(output,encoding='utf-8')
    else:print(output)
