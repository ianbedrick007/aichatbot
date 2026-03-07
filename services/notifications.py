import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

from jinja2 import Template


load_dotenv()


def send_email(receiver: str, subject: str, content: str, html_content: str = None):
    """
    Sends an email notification using SMTP.
    Expects environment variables for SMTP configuration.
    """
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "ianquaynor4@gmail.com"
    sender_password = "qnzg slej texf frdp"

    if not sender_email or not sender_password:
        print("Email notification skipped: Credentials not configured.")
        return False

    msg = MIMEMultipart("alternative")
    msg['From'] = f"OmniLabs"
    msg['To'] = receiver
    msg['Subject'] = subject

    msg.attach(MIMEText(content, 'plain'))
    if html_content:
        msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


with open("../templates/email.html", "r") as t:
    mail_content = Template(t.read())

html = mail_content.render(
    subject="Brand new",
    content="Please login to your account.",
    year=2026,
    action_url="https://omnialabsgh.com/dashboard"
)

send_email("ianquaynor@outlook.com", "Brand new", "Please login to your account.",
           html_content=html)
