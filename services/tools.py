import datetime

from langfuse import observe

from services.mail_utility import MailUtility
from services.question_store import store_question

mail_util = MailUtility()


@observe()
def record_user_details(email, name="Name not provided", notes="not provided"):
    today = datetime.datetime.now().strftime("%d %b %Y")
    subject = f"Career Persona — interest received [{today}]"

    mail_util.send_email(subject,
                         f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}


@observe()
def record_unknown_question(question):
    store_question(f"Recording unknown question: {question}")
    return {"recorded": "ok"}


record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "input_schema": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address of this user"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            }
            ,
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [record_user_details_json, record_unknown_question_json]
