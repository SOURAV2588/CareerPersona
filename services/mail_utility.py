import base64
import os
from email.message import EmailMessage

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv(override=True)


class MailUtility:

    def __init__(self):
        creds = self.get_credentials()
        self.service = build("gmail", "v1", credentials=creds)

    def send_email(self, body):
        message = EmailMessage()
        message["To"] = "souravghosh358@gmail.com"
        message["Subject"] = "Question from CareerPersona"
        message.set_content(body)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print("Sent message id:", sent["id"])

    @staticmethod
    def get_credentials():
        return Credentials(
            token=None,  # no access token stored; refreshed automatically
            refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
            client_id=os.getenv("GMAIL_CLIENT_ID"),
            client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )
