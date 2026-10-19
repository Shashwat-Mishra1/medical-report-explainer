import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# If you get a "model not found" error, pick a current free model
# from the Groq console and update this.
MODEL = "openai/gpt-oss-120b"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT = """You are a medical report explainer for people with no medical background.
Using ONLY the test data below, write a plain-language explanation.

Rules:
- Use simple words and short sentences.
- Do NOT diagnose any disease.
- Do NOT suggest medicines, supplements or doses.
- The "status" of each test is already decided. Do not change it or re-judge values.
- For anything not normal, say it is worth discussing with a doctor.
- If a status is critical_low or critical_high, say the person should see a doctor soon.

Return JSON only, in exactly this shape:
{{
  "summary": "2-3 sentence overall summary",
  "normal": [{{"test": "...", "meaning": "what this test measures, in one simple sentence"}}],
  "low": [{{"test": "...", "meaning": "...", "what_it_may_mean": "common general reasons, no diagnosis"}}],
  "high": [{{"test": "...", "meaning": "...", "what_it_may_mean": "common general reasons, no diagnosis"}}],
  "attention": [{{"test": "...", "why": "..."}}]
}}
Put critical values in "attention" as well as in "low" or "high".

TEST DATA:
{data}
"""


def explain_tests(tests: list[dict]) -> dict:
    data = json.dumps(tests, indent=2, ensure_ascii=False)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(data=data)}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)