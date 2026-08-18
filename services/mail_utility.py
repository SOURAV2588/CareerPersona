import base64
import os
from email.message import EmailMessage

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv(override=True)


class MailUtility:

    def __init__(self):
        self._service = None

    @property
    def service(self):
        # Built on first use, not at construction, so importing/instantiating
        # this class never requires valid Gmail credentials or performs a
        # client build for a process that never ends up sending an email.
        if self._service is None:
            creds = self.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def send_email(self, subject, body):
        recipient = os.getenv("GMAIL_RECIPIENT")
        if not recipient:
            raise RuntimeError("GMAIL_RECIPIENT environment variable is not set")

        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = subject
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


# Single shared instance: both services.tools (immediate notifications) and
# services.digest (the daily digest) send through this one lazily-built
# client instead of each constructing and authenticating their own.
mail_util = MailUtility()
