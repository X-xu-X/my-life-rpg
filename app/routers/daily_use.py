from datetime import date,timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,Goal
from app.models.daily_use import PersonalInformation,ExperiencePreference,ReturnCheckin,ImportantDay,OfficialCalendar
from app.models.full_system import PersonalPhase
from app.services.personal_context import USES
from app.services.workflow_common import WriteIn,begin,finish,fields,version,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now,local_day

router=APIRouter()
Hint=Literal['record-help','plans-help','rewards-help','growth-help','daily-reflection','questionnaire-help']
Use=Literal['judge','review','report','pricing']


class InformationEntry(BaseModel):
    id:UUID
    text:str=Field(min_length=1,max_length=4000)
    uses:list[Use]=Field(default_factory=list,max_length=4)


class InformationIn(WriteIn):
    entries:list[InformationEntry]=Field(default_factory=list,max_length=30)


@router.get('/personal-information')
def information(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=db.query(PersonalInformation).filter_by(user_id=user.id).first()
    return {'data':fields(row) if row else None,'uses':USES}


@router.put('/personal-information')
def save_information(body:InformationIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'personal-information',body)
    if prior is not None:return prior
    row=db.query(PersonalInformation).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if len({e.id for e in body.entries})!=len(body.entries):raise HTTPException(422,'信息身份不能重复。')
    if not row:row=PersonalInformation(user_id=user.id,version=0);db.add(row)
    old={e['id']:e for e in row.entries or []}
    row.entries=[dict(e.model_dump(mode='json'),updated_at=old[str(e.id)]['updated_at'] if str(e.id) in old and old[str(e.id)]['text']==e.text and old[str(e.id)]['uses']==e.uses else utc_now().isoformat(),source='self_report') for e in body.entries]
    row.version+=1;db.flush();return finish(db,user,'personal-information',body,fp,row,fields(row))


class PreferenceIn(WriteIn):
    suppressed:list[Hint]=Field(default_factory=list,max_length=6)
    return_disabled:bool=False


@router.get('/experience-preferences')
def preferences(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=db.query(ExperiencePreference).filter_by(user_id=user.id).first()
    return fields(row) if row else {'version':0,'suppressed':[],'return_disabled':False}


@router.put('/experience-preferences')
def save_preferences(body:PreferenceIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'experience-preferences',body)
    if prior is not None:return prior
    row=db.query(ExperiencePreference).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:row=ExperiencePreference(user_id=user.id,version=0);db.add(row)
    row.suppressed=list(dict.fromkeys(body.suppressed));row.return_disabled=body.return_disabled;row.version+=1
    db.flush();return finish(db,user,'experience-preferences',body,fp,row,fields(row))


RETURN_QUESTIONS=[{'id':k,'text':v} for k,v in [('changes','离开这段时间，有什么愿意告诉自己的变化？'),('direction','现在最想推进或暂时放下什么？'),('energy','近期精力与可支配时间怎么样？'),('rewards','最近想怎样休息或犒赏自己？')]]


class Answer(BaseModel):
    state:Literal['answered','skipped']
    value:str=Field('',max_length=2000)


class ReturnIn(WriteIn):
    answers:dict[str,Answer]=Field(default_factory=dict,max_length=4)
    uses:list[Use]=Field(default_factory=list,max_length=4)


class CompleteReturnIn(WriteIn):
    skip:bool=False
    stop_reminding:bool=False


@router.get('/return-checkin')
def read_return(db:Session=Depends(get_db)):
    from app.routers.phase import read
    user=get_or_create_default_user(db);row=db.query(ReturnCheckin).filter_by(user_id=user.id).first()
    return {'draft':fields(row) if row else None,'questions':RETURN_QUESTIONS,'eligible':read(db)['return_prompt']}


@router.put('/return-checkin')
def save_return(body:ReturnIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'return-draft',body)
    if prior is not None:return prior
    if not set(body.answers)<={q['id'] for q in RETURN_QUESTIONS}:raise HTTPException(422,'未知近况问题。')
    row=db.query(ReturnCheckin).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:row=ReturnCheckin(user_id=user.id,version=0);db.add(row)
    row.answers={k:{'state':v.state,'value':v.value if v.state=='answered' else ''} for k,v in body.answers.items()}
    row.uses=body.uses;row.state='draft';row.version+=1;db.flush()
    return finish(db,user,'return-draft',body,fp,row,fields(row))


@router.post('/return-checkin/complete')
def complete_return(body:CompleteReturnIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'return-complete',body)
    if prior is not None:return prior
    row=db.query(ReturnCheckin).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:row=ReturnCheckin(user_id=user.id,version=0,answers={},uses=[],history=[]);db.add(row)
    if not body.skip and (set(row.answers)!={q['id'] for q in RETURN_QUESTIONS} or any(v['state']=='answered' and not v['value'].strip() for v in row.answers.values())):raise HTTPException(422,'请回答或跳过每个问题。')
    row.state='skipped' if body.skip else 'completed';row.version+=1
    row.history=[*row.history,{'at':utc_now().isoformat(),'state':row.state,'questions':RETURN_QUESTIONS,'answers':row.answers,'uses':row.uses}]
    phase=db.query(PersonalPhase).filter_by(user_id=user.id).first()
    if not phase:phase=PersonalPhase(user_id=user.id,version=0,payload={},history=[]);db.add(phase)
    phase.return_cooldown_until=utc_now()+timedelta(days=30);phase.version+=1
    if body.stop_reminding:
        pref=db.query(ExperiencePreference).filter_by(user_id=user.id).first()
        if not pref:pref=ExperiencePreference(user_id=user.id,version=0);db.add(pref)
        pref.return_disabled=True;pref.version+=1
    db.flush();return finish(db,user,'return-complete',body,fp,row,fields(row))


class DayIn(WriteIn):
    name:str=Field(min_length=1,max_length=120)
    month:int=Field(ge=1,le=12,strict=True)
    day:int=Field(ge=1,le=31,strict=True)
    year:int|None=Field(None,ge=1900,le=2200,strict=True)
    annual:bool=True
    remind_days:int=Field(3,ge=0,le=30,strict=True)
    enabled:bool=True
    @model_validator(mode='after')
    def valid(self):
        if not self.annual and self.year is None:raise ValueError('一次日期需完整年份。')
        date(self.year if not self.annual else 2000,self.month,self.day)
        return self


@router.get('/important-days')
def days(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[fields(r) for r in db.query(ImportantDay).filter_by(user_id=user.id).order_by(ImportantDay.month,ImportantDay.day).all()]}


@router.post('/important-days')
@router.put('/important-days/{day_id}')
def save_day(body:DayIn,day_id:int|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'important-day:{day_id or "create"}';fp,prior=begin(db,user,op,body,create=day_id is None)
    if prior is not None:return prior
    row=get_owned(db,ImportantDay,day_id) if day_id else None
    if row:version(row,body.expected_version)
    else:row=ImportantDay(user_id=user.id,version=0);db.add(row)
    for key,value in body.model_dump(exclude={'request_key','expected_version'}).items():setattr(row,key,value)
    row.version+=1;db.flush();return finish(db,user,op,body,fp,row,fields(row))


def upcoming(db,user,today):
    result=[]
    for row in db.query(ImportantDay).filter_by(user_id=user.id,enabled=True).all():
        candidates=[]
        for year in (today.year,today.year+1) if row.annual else (row.year,):
            try:target=date(year,row.month,row.day)
            except ValueError:continue  # Feb 29 stays Feb 29, never silently moved.
            if 0<=(target-today).days<=row.remind_days:candidates.append(target)
        if candidates:result.append({'id':row.id,'name':row.name,'date':str(min(candidates)),'days_left':(min(candidates)-today).days,'source':'personal'})
    for goal in db.query(Goal).filter_by(user_id=user.id,status='active').all():
        if goal.deadline:
            target=goal.deadline.date() if hasattr(goal.deadline,'date') else goal.deadline
            if 0<=(target-today).days<=7:result.append({'id':goal.id,'name':goal.description,'date':str(target),'days_left':(target-today).days,'source':'goal'})
    return sorted(result,key=lambda r:r['date'])[:5]


@router.get('/daily-prompts')
def prompts(db:Session=Depends(get_db)):
    from app.routers.phase import read
    user=get_or_create_default_user(db);today=local_day(utc_now(),user.timezone);pref=db.query(ExperiencePreference).filter_by(user_id=user.id).first()
    count=db.query(Event).filter(Event.user_id==user.id,Event.is_deleted.is_(False),Event.record_kind.in_(('event','diary')),Event.saved_on>=str(today-timedelta(days=14))).count()
    already_today=db.query(Event.id).filter_by(user_id=user.id,is_deleted=False,record_kind='diary',occurred_on=str(today)).first()
    reflection=count>=3 and not already_today and not read(db)['return_prompt'] and not (pref and ('daily-reflection' in pref.suppressed or pref.review_snoozed_until and pref.review_snoozed_until>utc_now()))
    from app.services.official_calendar import read as calendar
    annual=calendar(db,today.year)
    return {'important_days':upcoming(db,user,today),'reflection':'今天有没有一个想记住的小细节？也可以先跳过。' if reflection else None,
        'calendar':{**annual,'data':None},'today_calendar':{'statutory':[r for r in annual['data']['statutory'] if r['date']==str(today)],
            'breaks':[r for r in annual['data']['breaks'] if r['date']==str(today)],'working_day':str(today) in annual['data']['working_days']}}


@router.post('/daily-prompts/snooze')
def snooze(body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'reflection-snooze',body)
    if prior is not None:return prior
    row=db.query(ExperiencePreference).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:row=ExperiencePreference(user_id=user.id,version=0);db.add(row)
    row.review_snoozed_until=utc_now()+timedelta(days=7);row.version+=1;db.flush()
    return finish(db,user,'reflection-snooze',body,fp,row,fields(row))


@router.get('/calendar')
def calendar(year:int|None=None,db:Session=Depends(get_db)):
    from app.services.official_calendar import read
    user=get_or_create_default_user(db)
    return read(db,year or local_day(utc_now(),user.timezone).year)


class CalendarIn(WriteIn):
    source_url:str=Field(max_length=1000)
    data:dict
    reason:str=Field(min_length=1,max_length=2000)


from app.routers.admin import require_owner


@router.post('/admin/calendars/{year}')
def import_calendar(year:int,body:CalendarIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    from urllib.parse import urlsplit
    from app.routers.admin import audit
    parsed=urlsplit(body.source_url);host=parsed.hostname or ''
    if not 1900<=year<=2200:raise HTTPException(422,'日历年份范围1900～2200。')
    if parsed.scheme!='https' or not (host=='gov.cn' or host.endswith('.gov.cn')) or parsed.username or parsed.password:raise HTTPException(422,'请使用官方政府HTTPS来源链接。')
    data=body.data
    try:
        if set(data)!={'statutory','breaks','working_days'}:raise ValueError()
        for kind,rows in data.items():
            if not isinstance(rows,list) or len(rows)>366:raise ValueError()
            seen=set()
            for row in rows:
                value=row if kind=='working_days' else row['date']
                parsed_day=date.fromisoformat(value)
                if str(parsed_day)!=value or parsed_day.year!=year or value in seen:raise ValueError()
                if kind!='working_days' and (not isinstance(row.get('name'),str) or not 1<=len(row['name'])<=120):raise ValueError()
                seen.add(value)
        if set(data['working_days']) & {r['date'] for r in data['breaks']}:raise ValueError()
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'年度日历内容或日期无效，请核对去重与假期/工作日冲突。') from None
    op=f'calendar-import:{year}';fp,prior=begin(db,owner,op,body)
    if prior is not None:return prior
    row=db.query(OfficialCalendar).filter_by(year=year).first();version(row,body.expected_version)
    if not row:row=OfficialCalendar(year=year,version=0);db.add(row)
    row.source_url=body.source_url;row.data=data;row.status='verified';row.version+=1;db.flush()
    audit(db,owner,'calendar-import',str(year),body.reason,row.version)
    return finish(db,owner,op,body,fp,row,fields(row))
