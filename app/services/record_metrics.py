"""Separate named date metrics; candidates never become rewards implicitly."""
from datetime import timedelta,date
from app.models import Event
from app.services.time_service import local_day


def metrics(db,user):
    rows=db.query(Event).filter_by(user_id=user.id,is_deleted=False).all()
    result={'policy_version':'candidate-date-v1','reward_policy':'unconfigured','metrics':{},'legacy_unclassified':sum(r.record_kind is None for r in rows)}
    for kind in ('event','diary'):
        selected=[r for r in rows if r.record_kind==kind]
        for basis in ('content','saved'):
            values={r.occurred_on or str(local_day(r.occurred_at,r.timezone_at_capture)) for r in selected} if basis=='content' else {str(local_day(r.created_at,user.timezone)) for r in selected}
            ordered=sorted(date.fromisoformat(d) for d in values);longest=run=0;last=None
            for d in ordered:run=run+1 if last and d-last==timedelta(days=1) else 1;longest=max(longest,run);last=d
            result['metrics'][f'{kind}_{basis}_days']={'count':len(values),'longest_contiguous_days':longest,'dates':sorted(values),'event_ids':[r.id for r in selected]}
    return result
