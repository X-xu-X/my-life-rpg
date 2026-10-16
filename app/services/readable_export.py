"""User-selected readable exports; escaped offline HTML contains no scripts."""
import csv,html,io,json,re
from app.models import Event
from app.models.workflow import ReviewSession,ReviewTurn,ReviewAnalysis,DiaryRevision
from app.services.workflow_common import fields


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
        sessions=db.query(ReviewSession).filter_by(user_id=user.id,diary_id=event.id).order_by(ReviewSession.id).all()
        if not history:sessions=[r for r in sessions if r.source_version==event.content_version]
        for session in sessions:
            row['sessions'].append({'session':fields(session),
                'turns':[fields(t) for t in db.query(ReviewTurn).filter_by(session_id=session.id).order_by(ReviewTurn.ordinal).all()] if questions else [],
                'analyses':[fields(a) for a in db.query(ReviewAnalysis).filter_by(session_id=session.id).order_by(ReviewAnalysis.id).all()] if analysis else []})
        for part in row['sessions']:
            if not history:part['analyses']=part['analyses'][-1:]
            if not questions:
                for item in part['analyses']:item['payload'].pop('turns_snapshot',None)
        if history:row['revisions']=[fields(r) for r in db.query(DiaryRevision).filter_by(event_id=event.id).order_by(DiaryRevision.version).all()]
        if analysis:
            from app.models import AIJudgment,JudgmentLog
            row['judgments']=[{'judgment':fields(j),'logs':[fields(log) for log in db.query(JudgmentLog).filter_by(judgment_id=j.id).order_by(JudgmentLog.id).all()] if history else []} for j in db.query(AIJudgment).filter_by(event_id=event.id).order_by(AIJudgment.id).all()]
        records.append(row)
    return records


def text_blocks(records,game=None):
    blocks=[('LifeXP 个人记录','可读导出，不承诺可直接导入恢复。未分类旧记录保持原身份。')]
    for row in records:
        e=row['record'];label={'event':'事件','diary':'晚间日记'}.get(e['record_kind'],'旧记录 · 未分类')
        blocks.append((f"{row['date']} · {label} · #{e['id']} · v{e['content_version']}",e['title']+'\n'+e['content']))
        blocks.append(('记录元数据',json.dumps({k:e[k] for k in ('source','timezone_at_capture','time_precision','created_at','is_deleted')},ensure_ascii=False,indent=2)))
        for rev in row['revisions']:blocks.append((f"原稿历史 v{rev['version']}",rev['content']))
        for session in row['sessions']:
            s=session['session'];blocks.append((f"回顾会话 #{s['id']} · 来源 v{s['source_version']}",json.dumps(s['sources'],ensure_ascii=False,indent=2)))
            for turn in session['turns']:blocks.append((f"问题 #{turn['id']} · {turn['state']}",turn['question']+'\n对应回答：'+(turn['answer'] if turn['state']=='answered' else '已跳过' if turn['state']=='skipped' else '尚未回答')))
            for a in session['analyses']:blocks.append((f"回顾分析 #{a['id']} · 会话 v{a['session_version']}",json.dumps({'payload':a['payload'],'provenance':a['provenance']},ensure_ascii=False,indent=2)))
        for judgment in row.get('judgments',[]):blocks.append(('事件分析与审计',json.dumps(judgment,ensure_ascii=False,indent=2)))
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
    writer.writerow(['id','kind','content_date','version','title','original','questions_answers_json','analyses_json','deleted'])
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    for row in records:
        e=row['record'];writer.writerow([safe(v) for v in [e['id'],e['record_kind'] or 'legacy_unknown',row['date'],e['content_version'],e['title'],e['content'],json.dumps([s['turns'] for s in row['sessions']],ensure_ascii=False),json.dumps([s['analyses'] for s in row['sessions']],ensure_ascii=False),e['is_deleted']]])
    return '\ufeff'+stream.getvalue()
