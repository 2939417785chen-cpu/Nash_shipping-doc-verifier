import os
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Read the key from .env in the repo folder (never print the key itself)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
key = os.getenv("GEMINI_API_KEY")
if not key:
    raise SystemExit("GEMINI_API_KEY not found. Check your .env file")

client = genai.Client(api_key=key)
PROMPT = "Reply with only the word: ready"


def newest_flash_model(names):
    """Pick the highest-version plain flash model, e.g. models/gemini-3.6-flash"""
    best = None
    for name in names:
        match = re.fullmatch(r"models/gemini-(\d+(?:\.\d+)*)-flash", name)
        if match:
            version = tuple(int(x) for x in match.group(1).split("."))
            if best is None or version > best[0]:
                best = (version, name)
    return best[1] if best else None


try:
    usable = [m.name for m in client.models.list()
              if "generateContent" in (m.supported_actions or [])]
except Exception as e:
    raise SystemExit(f"Could not list models: {type(e).__name__}: {str(e)[:200]}")

print("models that support generateContent:", len(usable))
print("flash models:", sorted(n for n in usable if "flash" in n))

name = os.getenv("GEMINI_MODEL") or newest_flash_model(usable)
if not name:
    raise SystemExit("No plain flash model found for this key")
model = name.replace("models/", "")
print("using model:", model)


def via_interactions():
    interaction = client.interactions.create(model=model, input=PROMPT)
    return interaction.output_text


def via_generate_content():
    response = client.models.generate_content(model=model, contents=PROMPT)
    return response.text


# Try both ways, so we know which one to use in the real code
for label, call in (("Interactions API", via_interactions),
                    ("generate_content", via_generate_content)):
    try:
        print(f"{label}: ok ->", call().strip())
    except Exception as e:
        print(f"{label}: failed ->", type(e).__name__, str(e)[:200])
