"""Shared pytest setup.

Several modules under test read credentials from the environment at *import
time* (``services.mail_utility`` calls ``load_dotenv(override=True)``, and
``services.tools`` builds a module-level ``MailUtility()`` singleton as soon
as it is imported). To keep the suite hermetic — importable with no ``.env``
file present, and incapable of making a real network call even if a real
``.env`` happens to be sitting in the working directory — this module:

1. Seeds dummy credential env vars before anything else is imported.
2. Patches ``googleapiclient.discovery.build`` for the whole session so no
   Gmail API client construction ever touches the network.

Both of these must happen at *module import time* (not inside a fixture),
because pytest imports ``conftest.py`` before it collects/imports any test
module that in turn imports ``services.tools`` / ``services.mail_utility``.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("GMAIL_CLIENT_ID", "test-client-id")
os.environ.setdefault("GMAIL_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GMAIL_REFRESH_TOKEN", "test-refresh-token")
os.environ.setdefault("GMAIL_RECIPIENT", "test-recipient@example.com")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

# A fresh MagicMock per call (rather than one shared instance) so that
# call-count assertions in one test can never be polluted by another
# MailUtility instance constructed elsewhere in the suite.
_build_patcher = patch("googleapiclient.discovery.build", side_effect=lambda *a, **kw: MagicMock())
_build_patcher.start()
