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
    test_generation()

    client = get_client()
    client.flush()

    print("Langfuse client initialized successfully.")
    print("Check dashboard at https://dashboard.langfuse.com/")

@observe
def test_generation():
    return "Hello World from Langfuse"

if __name__ == "__main__":
    verify_connection()