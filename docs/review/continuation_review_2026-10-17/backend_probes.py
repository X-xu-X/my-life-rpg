"""Independent gap probes: temporary DB, synthetic users, no provider/SMTP calls."""
import os
os.environ.pop('TEST_PG_URL', None)
os.environ['DB_URL'] = 'sqlite://'
os.environ['DEEPSEEK_API_KEY'] = ''
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from tests.test_continuation import ContinuationTests
from app.models import User
from app.services import analysis_jobs
from app.services.time_service import utc_now

results = {}
t = ContinuationTests('runTest')
t.setUp()
try:
    registered = t.register('reviewer')
    t.configure_model()
    session = t.session()
    schedule = t.schedule(name='Known-plan')
    missed = t.write('/plan-schedules/' + str(schedule['id']) + '/occurrences/2026-10-16',
        {'outcome': 'missed', 'schedule_version': 1}, 0, 'PUT')
    assert missed.status_code == 200
    checklist = t.write('/life-checklists/2026-10-16',
        {'enabled': True, 'entries': {'diet-marker': 'recorded'}}, 0, 'PUT')
    assert checklist.status_code == 200
    event = t.client.post('/api/events', json={'record_kind': 'event', 'source': 'form',
        'content': 'new-event-after-session', 'occurred_on': '2026-10-16',
        'time_precision': 'date', 'client_request_id': str(uuid4())})
    assert event.status_code == 200
    captured = []
    def supplier(messages, **kwargs):
        captured.append(json.loads(messages[1]['content']))
        return {'questions': [], 'summary': 'Synthetic result', 'analysis': []}
    requested = t.write('/review-sessions/' + str(session['id']) + '/analyze', version=session['version'])
    assert requested.status_code == 200
    with patch('app.services.diary_review.llm_service.chat_json', side_effect=supplier):
        analysis_jobs.process(t.Session, analysis_jobs.claim(t.Session))
    assert len(captured) == 1
    context = json.dumps(captured[0])
    results['review_context'] = {'keys': list(captured[0]),
        'includes_plan': 'Known-plan' in context,
        'includes_checklist': 'diet-marker' in context,
        'includes_later_event': 'new-event-after-session' in context}
    assert not any(results['review_context'][key] for key in
        ('includes_plan', 'includes_checklist', 'includes_later_event'))

    unsupported = t.write('/plan-schedules', {'name': 'Linked plan', 'frequency': 'daily',
        'start': '2026-10-01', 'goal_id': 123})
    results['schedule_goal_link'] = {'status': unsupported.status_code,
        'reason': 'goal_id rejected as extra field'}
    assert unsupported.status_code == 422
    metric = t.client.get('/api/record-metrics').json()['metrics']['diary_content_days']
    results['current_streak'] = {'returned_keys': list(metric),
        'has_current_streak': any('current' in key for key in metric)}
    assert not results['current_streak']['has_current_streak']

    with t.Session() as db:
        user = db.get(User, registered['id'])
        user.email = 'reviewer@example.test'
        user.email_verified_at = utc_now()
        db.commit()
    sends = []
    def send(*args):
        sends.append(1)
        time.sleep(0.4)
    transport = SimpleNamespace(ready=True, send=send)
    timings = []
    responses = []
    with patch('app.services.mail_service.mailer', return_value=transport):
        for email in ('reviewer@example.test', 'missing@example.test'):
            started = time.perf_counter()
            response = t.client.post('/api/auth/email/recover-request', json={'email': email})
            timings.append(round(time.perf_counter() - started, 3))
            responses.append((response.status_code, response.json()))
    assert responses[0] == responses[1] and len(sends) == 1
    results['recovery_timing'] = {'same_http_response': True, 'smtp_mock_calls': len(sends),
        'known_email_seconds': timings[0], 'unknown_email_seconds': timings[1],
        'explanation': 'Only the known-account HTTP request waits for synchronous SMTP.'}

    t.login_owner()
    overview = t.client.get('/api/admin/overview').json()
    all_users = t.client.get('/api/admin/users').json()['items']
    filtered = t.client.get('/api/admin/users?search=does_not_exist&role=user&status=disabled').json()['items']
    results['admin_metadata'] = {'overview': overview,
        'ordinary_count': sum(row['role'] == 'user' for row in all_users),
        'management_count': sum(row['role'] == 'owner' for row in all_users),
        'filtered_count': len(filtered), 'all_count': len(all_users),
        'has_last_login': any('last_login' in key for row in all_users for key in row)}
    assert overview['users'] == len(all_users) == len(filtered) == 2
finally:
    t.tearDown()

output = Path(__file__).with_name('backend-probes.json')
output.write_text(json.dumps({'scope': 'Synthetic reproduction, not production validation',
    'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=True))
