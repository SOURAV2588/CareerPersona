import os

from pypdf import PdfReader

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_system_prompt_for_profile():
    name = "Sourav Ghosh"

    system_prompt = f"You are acting as {name}. You are answering questions on {name}'s website, \
    particularly questions related to {name}'s career, background, skills and experience. \
    Your responsibility is to represent {name} for interactions on the website as faithfully as possible. \
    You are given a summary of {name}'s background and LinkedIn profile which you can use to answer questions. \
    Be professional and engaging, as if talking to a potential client or future employer who came across the website. \
    If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
    If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "

    system_prompt += f"\n\n## Summary:\n{get_summary()}\n\n## LinkedIn Profile:\n{get_linkedin_details()}\n\n"
    system_prompt += f"With this context, please chat with the user, always staying in character as {name}."
    return system_prompt


def get_linkedin_details():
    linkedin_resume_path = os.path.join(base_dir, "resources", "SOURAV_GHOSH_LINKEDIN.pdf")
    reader = PdfReader(linkedin_resume_path)
    linkedin = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            linkedin += text
    return linkedin


def get_summary():
    summary_path = os.path.join(base_dir, "resources", "summary.txt")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = f.read()
    return summary
