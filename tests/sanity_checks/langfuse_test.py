"""Manual connectivity check for Langfuse — not a pytest test module.

Run directly (``python -m services.langfuse_test`` or similar) to confirm
Langfuse credentials and connectivity work: it emits one traced generation
and flushes it, then prints a link to the dashboard to confirm the trace
arrived.
"""

import os

from dotenv import load_dotenv
from langfuse import Langfuse, observe, get_client

load_dotenv(override=True)
# langfuse = Langfuse(
#     public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
#     secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
#     base_url=os.getenv("LANGFUSE_BASE_URL")
# )


def verify_connection():
    """Emit one traced generation, flush it, and print confirmation.

    :return: None
    """
    test_generation()

    client = get_client()
    client.flush()

    print("Langfuse client initialized successfully.")
    print("Check dashboard at https://dashboard.langfuse.com/")

@observe
def test_generation():
    """Traced no-op generation used to exercise the Langfuse pipeline.

    :return: A fixed greeting string.
    :rtype: str
    """
    return "Hello World from Langfuse"

if __name__ == "__main__":
    verify_connection()