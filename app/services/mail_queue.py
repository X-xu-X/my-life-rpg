"""Durable recovery delivery; retry after crash without persisting cleartext tokens.

Delivery is at least once; a retry reuses the same single-use token. Logs only codes.
Unknown recipients go through the same acceptance and worker queue.
"""
import secrets
from datetime import timedelta
from sqlalchemy import or_,and_
from app.models import User
from app.models.accounts import MailDelivery,EmailToken
from app.services import credentials,auth_service as auth,mail_service
from app.services.time_service import utc_now


def deliver_one(factory):
    now=utc_now();lease=secrets.token_hex(24)
    with factory() as db:
        row=db.query(MailDelivery).filter(MailDelivery.state.in_(('queued','retry','sending')),
            MailDelivery.next_attempt<=now).order_by(MailDelivery.id).with_for_update(skip_locked=True).first()
        if not row:return False
        if row.expires_at<=now or row.attempts>=6:
            row.state='expired';row.encrypted_key=None;db.commit();return True
        claimed=db.query(MailDelivery).filter_by(id=row.id,state=row.state,attempts=row.attempts).update(
            {MailDelivery.state:'sending',MailDelivery.lease_token:lease,MailDelivery.attempts:row.attempts+1,
             MailDelivery.next_attempt:now+timedelta(seconds=60)},synchronize_session=False)
        if claimed!=1:db.rollback();return False
        db.expire(row)
        user=db.query(User).filter_by(email=row.email,status='active').first()
        if not user or not user.email_verified_at:
            row.state='discarded';row.encrypted_key=None;db.commit();return True
        token_row=db.get(EmailToken,row.token_id) if row.token_id else None
        if token_row and (token_row.consumed_at or token_row.credentials_version!=user.credentials_version or token_row.email!=user.email):
            row.state='discarded';row.encrypted_key=None;db.commit();return True
        if not token_row:
            token=secrets.token_urlsafe(40);key_id,keys=credentials.keyring()
            token_row=EmailToken(user_id=user.id,email=row.email,purpose='recover',token_hash=auth.digest(token),
                credentials_version=user.credentials_version,expires_at=row.expires_at)
            db.add(token_row);db.flush();row.token_id=token_row.id
            row.key_id=key_id;row.encrypted_key=keys[key_id].encrypt(token.encode()).decode()
        else:token=credentials.decrypt(row)
        identity,email=row.id,row.email;db.commit()
    # No transaction held across SMTP; lease lasts longer than the transport timeout.
    error=None
    try:mail_service.mailer().send(email,'recover',token)
    except Exception:error='DELIVERY_UNCONFIRMED'
    with factory() as db:
        row=db.query(MailDelivery).filter_by(id=identity,state='sending',lease_token=lease).with_for_update().first()
        if not row:return True
        row.state='retry' if error else 'sent';row.error_code=error;row.lease_token=None
        row.next_attempt=utc_now()+timedelta(seconds=min(600,15*2**row.attempts))
        if not error:row.encrypted_key=None
        db.commit()
    return True
