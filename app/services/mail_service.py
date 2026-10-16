"""Configured SMTP delivery or explicit unavailability; test outbox is injectable only."""
import smtplib,secrets,re
from email.message import EmailMessage
from pathlib import Path
from fastapi import HTTPException
from app.config import settings


def normalize(value):
    value=value.strip().lower()
    if len(value)>254 or not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}',value):raise HTTPException(422,'邮箱格式无效。')
    return value


class DisabledMailer:
    ready=False
    def send(self,*args):raise HTTPException(503,'邮件服务未配置，未发送邮件；原恢复码继续可用。')


class TestMailer:
    ready=True
    def __init__(self):self.outbox=[]
    def send(self,email,purpose,token):self.outbox.append({'email':email,'purpose':purpose,'token':token})


class SMTPMailer:
    ready=True
    def send(self,email,purpose,token):
        message=EmailMessage();message['From']=settings.mail_from;message['To']=email;message['Subject']='LifeXP 账号验证'
        message.set_content(f'用途：{purpose}。请在 LifeXP 账号安全页输入一次性验证码：\n{token}\n有效期 30 分钟。若非本人操作请忽略。')
        try:
            with smtplib.SMTP_SSL(settings.mail_host,settings.mail_port,timeout=15) as smtp:
                smtp.login(settings.mail_username,settings.mail_password or Path(settings.mail_password_file).read_text(encoding='utf-8').strip());smtp.send_message(message)
        except Exception:raise HTTPException(503,'邮件投递结果无法确认，请稍后检查收件箱；未报告发送成功。') from None


def mailer():
    return SMTPMailer() if all((settings.mail_host,settings.mail_from,settings.mail_username,(settings.mail_password or settings.mail_password_file and Path(settings.mail_password_file).is_file()))) else DisabledMailer()
