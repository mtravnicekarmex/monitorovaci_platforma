import ssl
from email.message import EmailMessage
import os
import smtplib
from decouple import config




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




def send_email_outlook(email_receiver, subject, body, sender_alias=None, file_path=None, is_html=False):
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
    with smtplib.SMTP('smtp.office365.com', 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(email_sender, email_password)
        smtp.send_message(msg)



# send_email_outlook(email_receiver='m.travnicek.armex@gmail.com', subject='subject', body='body', sender_alias=config('ALIAS_ALARM'), file_path=None)

