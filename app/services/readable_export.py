"""User-selected readable exports; escaped offline HTML contains no scripts."""
import csv,html,io,json,re
from app.models import Event
from app.models.workflow import ReviewSession,ReviewTurn,ReviewAnalysis,DiaryRevision
from app.services.workflow_common import fields


def strip_questions(value):
    if isinstance(value,list):return [strip_questions(v) for v in value]
    if isinstance(value,dict):return {k:strip_questions(v) for k,v in value.items() if k not in ('turns','turns_snapshot','question','answer')}
    return value


def select(db,user,kind,start,end,deleted,history,questions,analysis):
    query=db.query(Event).filter_by(user_id=user.id)
    if not deleted:query=query.filter(Event.is_deleted.is_(False))
    if kind!='all':query=query.filter(Event.record_kind==kind) if kind!='legacy' else query.filter(Event.record_kind.is_(None))
    records=[]
    for event in query.order_by(Event.id).all():
        from app.services.time_service import local_day
        day=event.occurred_on or str(local_day(event.occurred_at or event.created_at,event.timezone_at_capture))
        if start and day<str(start) or end and day>str(end):continue
        row={'record':fields(event),'date':day,'sessions':[],'revisions':[]}
        if not questions:row['record'].get('params',{}).pop('_clarify_history',None)
        if questions:
            from app.models.full_system import FactNote
            row['supplements']=[fields(n) for n in db.query(FactNote).filter_by(user_id=user.id,event_id=event.id).order_by(FactNote.id).all() if history or n.event_version==event.content_version]
        sessions=db.query(ReviewSession).filter_by(user_id=user.id,diary_id=event.id).order_by(ReviewSession.id).all()
        if not history:sessions=[r for r in sessions if r.source_version==event.content_version]
        for session in sessions:
            row['sessions'].append({'session':fields(session),
                'turns':[fields(t) for t in db.query(ReviewTurn).filter_by(session_id=session.id).order_by(ReviewTurn.ordinal).all()] if questions else [],
                'analyses':[fields(a) for a in db.query(ReviewAnalysis).filter_by(session_id=session.id).order_by(ReviewAnalysis.id).all()] if analysis else []})
        for part in row['sessions']:
            if not history:part['analyses']=part['analyses'][-1:]
            if not questions:
                part['analyses']=strip_questions(part['analyses'])
        if history:row['revisions']=[fields(r) for r in db.query(DiaryRevision).filter_by(event_id=event.id).order_by(DiaryRevision.version).all()]
        if analysis:
            from app.models import AIJudgment,JudgmentLog
            judgments=db.query(AIJudgment).filter_by(event_id=event.id).order_by(AIJudgment.id).all()
            if not history:
                # Unknown legacy provenance cannot certify a current-version analysis.
                judgments=[j for j in judgments if j.status in ('pending','adjusted','confirmed') and any(s.get('id')==event.id and s.get('version')==event.content_version for s in (j.source_snapshot or []))]
                from app.models.workflow import FactSettlement
                latest={}
                for j in judgments:
                    booking=db.query(FactSettlement).filter_by(judgment_id=j.id).first()
                    latest[booking.fact_id if booking else 'unsettled']=j
                judgments=list(latest.values())
            row['judgments']=[{'judgment':fields(j),'logs':[fields(log) for log in db.query(JudgmentLog).filter_by(judgment_id=j.id).order_by(JudgmentLog.id).all()] if history else []} for j in judgments]
            from app.models.full_system import FactBundle,FactFragment
            groups=db.query(FactBundle).filter_by(user_id=user.id,event_id=event.id).order_by(FactBundle.id).all()
            if not history:groups=[g for g in groups if g.event_version==event.content_version][-1:]
            row['fact_bundles']=[fields(g) for g in groups]
            fragment_ids={i['fragment_id'] for g in groups for i in g.payload.get('items',[])}
            row['fact_fragments']=[fields(f) for f in db.query(FactFragment).filter_by(user_id=user.id,event_id=event.id).all() if history or f.id in fragment_ids]
        if not history:
            row['record'].get('params',{}).pop('_clarify_history',None)
            for fragment in row.get('fact_fragments',[]):fragment['history']=[]
        records.append(row)
    return records


def project_record_tables(tables,records,history):
    """The same selected rows drive both readable records and JSON attachments."""
    versions={r['record']['id']:r['record']['content_version'] for r in records}
    sessions=[s for r in records for s in r['sessions']]
    tables.update(events=[r['record'] for r in records],
        diary_revisions=[v for r in records for v in r['revisions']],
        review_sessions=[s['session'] for s in sessions],
        review_turns=[t for s in sessions for t in s['turns']],
        review_analyses=[a for s in sessions for a in s['analyses']],
        ai_judgments=[j['judgment'] for r in records for j in r.get('judgments',[])],
        judgment_logs=[log for r in records for j in r.get('judgments',[]) for log in j['logs']],
        fact_bundles=[b for r in records for b in r.get('fact_bundles',[])],
        fact_fragments=[f for r in records for f in r.get('fact_fragments',[])],
        fact_notes=[n for r in records for n in r.get('supplements',[])])
    if not history:
        # These are historical process traces, not the current selected analyses.
        tables['event_derivations']=[];tables['analysis_jobs']=[]
        for rows in tables.values():
            for row in rows:
                if 'history' in row:row['history']=[]
    else:
        for name in ('event_derivations','analysis_jobs'):
            tables[name]=[r for r in tables.get(name,[]) if r.get('event_id') in versions]
    return tables


def text_blocks(records,game=None):
    blocks=[('LifeXP 个人记录','可读导出，不承诺可直接导入恢复。未分类旧记录保持原身份。')]
    for row in records:
        e=row['record'];label={'event':'事件','diary':'晚间日记'}.get(e['record_kind'],'旧记录 · 未分类')
        blocks.append((f"{row['date']} · {label} · #{e['id']} · v{e['content_version']}",e['title']+'\n'+e['content']))
        blocks.append(('记录元数据',json.dumps({k:e[k] for k in ('source','timezone_at_capture','time_precision','created_at','saved_on','saved_timezone','is_deleted')},ensure_ascii=False,indent=2)))
        for rev in row['revisions']:blocks.append((f"原稿历史 v{rev['version']}",rev['content']))
        for note in row.get('supplements',[]):blocks.append((f"相关补充 #{note['id']} · 原文 v{note['event_version']}",json.dumps(note,ensure_ascii=False,indent=2)))
        for session in row['sessions']:
            s=session['session'];blocks.append((f"回顾会话 #{s['id']} · 来源 v{s['source_version']}",json.dumps(s['sources'],ensure_ascii=False,indent=2)))
            for turn in session['turns']:blocks.append((f"问题 #{turn['id']} · {turn['state']}",turn['question']+'\n对应回答：'+(turn['answer'] if turn['state']=='answered' else '已跳过' if turn['state']=='skipped' else '尚未回答')))
            for a in session['analyses']:blocks.append((f"回顾分析 #{a['id']} · 会话 v{a['session_version']}",json.dumps({'payload':a['payload'],'provenance':a['provenance']},ensure_ascii=False,indent=2)))
        for judgment in row.get('judgments',[]):blocks.append(('事件分析与审计',json.dumps(judgment,ensure_ascii=False,indent=2)))
        if row.get('fact_bundles'):blocks.append(('逐事实建议与确认历史',json.dumps({'bundles':row['fact_bundles'],'fragments':row['fact_fragments']},ensure_ascii=False,indent=2)))
    if game is not None:blocks.append(('本人游戏数据 · 全部日期',json.dumps(game,ensure_ascii=False,indent=2)))
    return blocks


def render(records,format,game=None):
    blocks=text_blocks(records,game)
    if format=='html':
        return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>LifeXP 个人记录</title><style>body{max-width:850px;margin:24px auto;padding:16px;font:17px/1.7 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-bottom:1px solid #ddd;padding:12px 0}</style><body>'+''.join('<section><h2>'+html.escape(title)+'</h2><pre>'+html.escape(text)+'</pre></section>' for title,text in blocks)+'</body></html>'
    if format=='markdown':
        output=[]
        for title,text in blocks:
            fence='`'*max(3,max((len(m[0]) for m in re.finditer(r'`+',text)),default=0)+1)
            output.append('## '+html.escape(title)+'\n\n'+fence+'text\n'+text+'\n'+fence+'\n')
        return '\n'.join(output)
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['id','kind','content_date','version','title','original','questions_answers_json','analyses_json','deleted','saved_on','saved_timezone','source','ai_permission','time_precision','created_at'])
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    for row in records:
        e=row['record'];writer.writerow([safe(v) for v in [e['id'],e['record_kind'] or 'legacy_unknown',row['date'],e['content_version'],e['title'],e['content'],json.dumps({'turns':[s['turns'] for s in row['sessions']],'supplements':row.get('supplements',[])},ensure_ascii=False),json.dumps({'reviews':[s['analyses'] for s in row['sessions']],'judgments':row.get('judgments',[]),'fact_bundles':row.get('fact_bundles',[]),'fact_fragments':row.get('fact_fragments',[])},ensure_ascii=False),e['is_deleted'],e['saved_on'] or '',e['saved_timezone'] or '',e['source'],e['ai_permission'],e['time_precision'] or '',e['created_at']]])
    return '\ufeff'+stream.getvalue()
