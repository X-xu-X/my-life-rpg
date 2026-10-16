from app.models.accounts import SitePolicy
DEFAULT={'site_name':'LifeXP','description':'个人记录与成长','registration':'invite','email_required':False,'password_sessions':'all'}


def read(db):
    row=db.get(SitePolicy,1)
    return {**DEFAULT,**(row.payload if row else {}),'version':row.version if row else 0}
