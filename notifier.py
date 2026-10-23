import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import requests

def send_email(sender, pwd, receiver, subject, message, image_path):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = receiver
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        if image_path:
            with open(image_path, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-Disposition', 'attachment', filename=image_path.split('/')[-1])
                msg.attach(img)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except:
        return False

def send_sms(account_sid, auth_token, from_num, to_num, message):
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "From": from_num,
            "To": to_num,
            "Body": message
        }
        response = requests.post(url, auth=(account_sid, auth_token), data=data)
        if response.status_code in [200, 201]:
            return True
        else:
            print(f"Twilio SMS Error: HTTP {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Twilio SMS Exception: {e}")
        return False
