"""Reviewed annual display data. Importing a calendar NEVER creates gift eligibility."""
from datetime import date,timedelta
from app.models.daily_use import OfficialCalendar

SOURCE='https://www.gov.cn/zhengce/content/202511/content_7047090.htm'
MIRROR='https://www.beijing.gov.cn/zhengce/zhengcefagui/202511/t20251104_4258873.html'
STATUTE='https://www.gov.cn/zhengce/content/202411/content_6986380.htm'


def bundled_2026():
    breaks=[]
    for name,start,end in [('元旦','01-01','01-03'),('春节','02-15','02-23'),('清明节','04-04','04-06'),('劳动节','05-01','05-05'),('端午节','06-19','06-21'),('中秋节','09-25','09-27'),('国庆节','10-01','10-07')]:
        current=date.fromisoformat('2026-'+start);stop=date.fromisoformat('2026-'+end)
        while current<=stop:breaks.append({'date':str(current),'name':name});current+=timedelta(days=1)
    statutory=[]
    for name,days in [('元旦',['01-01']),('春节',['02-16','02-17','02-18','02-19']),('清明节',['04-05']),('劳动节',['05-01','05-02']),('端午节',['06-19']),('中秋节',['09-25']),('国庆节',['10-01','10-02','10-03'])]:
        statutory.extend({'date':'2026-'+d,'name':name} for d in days)
    return {'statutory':statutory,'breaks':breaks,'working_days':['2026-'+d for d in ['01-04','02-14','02-28','05-09','09-20','10-10']]}


def read(db,year):
    row=db.query(OfficialCalendar).filter_by(year=year).first()
    if row:return {'year':row.year,'version':row.version,'source_url':row.source_url,'status':row.status,'data':row.data,'persisted':True}
    if year==2026:return {'year':year,'version':1,'source_url':SOURCE,'verification_url':MIRROR,'statute_url':STATUTE,'verified_on':'2026-10-21','status':'bundled_verified','data':bundled_2026(),'persisted':False}
    return {'year':year,'version':0,'status':'missing','message':'此年度官方日历尚未核对，不套用往年安排。','data':{'statutory':[],'breaks':[],'working_days':[]}}
