"""Thin Gmail API wrapper used for all outbound mail.

Both immediate notifications (:mod:`services.tools`) and the daily digest
(:mod:`services.digest`) send through the single :data:`mail_util` instance
defined at the bottom of this module, rather than each constructing and
authenticating its own Gmail client.
"""

import base64
import os
from email.message import EmailMessage

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv(override=True)


class MailUtility:
    """Sends email through the Gmail API using a stored OAuth refresh token.

    Authentication is non-interactive: credentials are built from
    ``GMAIL_CLIENT_ID`` / ``GMAIL_CLIENT_SECRET`` / ``GMAIL_REFRESH_TOKEN``
    environment variables, with no access token stored and no login flow.
    The underlying Gmail service client is built lazily on first use of
    :attr:`service`, not at construction, so instantiating this class never
    requires valid credentials.
    """

    def __init__(self):
        """Initialize the instance with no Gmail service client built yet."""
        self._service = None

    @property
    def service(self):
        """The underlying Gmail API service client, built on first access.

        :return: A ``googleapiclient`` Gmail ``v1`` service resource.
        :rtype: googleapiclient.discovery.Resource
        """
        # Built on first use, not at construction, so importing/instantiating
        # this class never requires valid Gmail credentials or performs a
        # client build for a process that never ends up sending an email.
        if self._service is None:
            creds = self.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def send_email(self, subject, body):
        """Send a plain-text email to the configured recipient.

        :param subject: The email subject line.
        :type subject: str
        :param body: The plain-text email body.
        :type body: str
        :raises RuntimeError: If the ``GMAIL_RECIPIENT`` environment
            variable is not set.
        :return: None
        """
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
        """Build OAuth credentials from environment variables.

        :return: Credentials that refresh automatically via the stored
            refresh token; no access token is cached.
        :rtype: google.oauth2.credentials.Credentials
        """
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
