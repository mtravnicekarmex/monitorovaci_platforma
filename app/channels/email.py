import ssl
from email.message import EmailMessage
import os
import re
import smtplib
import threading
import time
from decouple import config


_OUTLOOK_SMTP_LOCK = threading.Lock()
_OUTLOOK_SMTP_MAX_ATTEMPTS = 3
_OUTLOOK_SMTP_RETRY_DELAY_SECONDS = 5
_OUTLOOK_SMTP_TRANSIENT_CODES = {421, 432, 451, 452}




def send_email_gmail(email_receiver, subject, body, file_path=None, is_html=True):
    """ Send email with attachment"""
    email_sender = config('A_EMAIL')
    email_password = config('A_APP')

    # Add SSL for security
    context = ssl.create_default_context()

    msg = EmailMessage()
    msg['From'] = email_sender
    msg['To'] = email_receiver
    msg['Subject'] = subject

    if is_html:
        msg.add_alternative(body, subtype='html')
    else:
        msg.set_content(body)


    # Attach attachment file if provided
    if file_path:
        with open(file_path, 'rb') as file:
            msg.add_attachment(file.read(),
                              maintype='application',
                              subtype='octet-stream',
                              filename=os.path.basename(file_path))


    # Log in and send the email
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(email_sender, email_password)
        smtp.sendmail(email_sender, email_receiver, msg.as_string())



# send_email(email_receiver='travnicek.michal5@gmail.com', subject=subject, body=body, file_path=None)




def _html_to_plain_text(body: str) -> str:
    """Provide a simple plain-text fallback for HTML emails."""
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    return text.strip()


def _is_transient_outlook_smtp_error(exc: BaseException) -> bool:
    if not isinstance(exc, smtplib.SMTPResponseException):
        return False
    return int(exc.smtp_code) in _OUTLOOK_SMTP_TRANSIENT_CODES


def _send_outlook_message_once(email_sender: str, email_password: str, msg: EmailMessage, context: ssl.SSLContext) -> None:
    with smtplib.SMTP('smtp.office365.com', 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(email_sender, email_password)
        smtp.send_message(msg)


def send_email_outlook(email_receiver, subject, body, sender_alias=None, file_path=None, is_html=False, attachments=None):
    """ Send email with attachment"""
    email_sender = config('O_EMAIL')
    email_password = config('O_APP')

    # Add SSL for security
    context = ssl.create_default_context()

    msg = EmailMessage()
    if sender_alias:
        msg['From'] = sender_alias
    else:
        msg['From'] = email_sender

    msg['To'] = email_receiver
    msg['Subject'] = subject

    if is_html:
        msg.set_content(_html_to_plain_text(body))
        msg.add_alternative(body, subtype='html')
    else:
        msg.set_content(body)

    # Attach attachment file if provided
    if file_path:
        with open(file_path, 'rb') as file:
            msg.add_attachment(file.read(),
                              maintype='application',
                              subtype='octet-stream',
                              filename=os.path.basename(file_path))

    if attachments:
        for filename, content, maintype, subtype in attachments:
            msg.add_attachment(
                content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
                disposition='attachment',
            )

    with _OUTLOOK_SMTP_LOCK:
        for attempt in range(1, _OUTLOOK_SMTP_MAX_ATTEMPTS + 1):
            try:
                _send_outlook_message_once(email_sender, email_password, msg, context)
                return
            except Exception as exc:
                if attempt >= _OUTLOOK_SMTP_MAX_ATTEMPTS or not _is_transient_outlook_smtp_error(exc):
                    raise
                time.sleep(_OUTLOOK_SMTP_RETRY_DELAY_SECONDS * attempt)



# send_email_outlook(email_receiver='m.travnicek.armex@gmail.com', subject='subject', body='body', sender_alias=config('ALIAS_ALARM'), file_path=None)

