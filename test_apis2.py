import requests
import json

GEMINI_API_KEY = "AQ.Ab8RN6IFPd7wYj6-q98dV0HBsEpA7_d3O-wnX8ITfzegQ7-wGw"
GROQ_API_KEY = "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"
OPENROUTER_API_KEY = "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"

def get_gemini_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        models = [m['name'] for m in res.json().get('models', [])]
        return ", ".join(models)
    return f"Error {res.status_code}: {res.text[:100]}"

def get_groq_models():
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        models = [m['id'] for m in res.json().get('data', [])]
        return ", ".join(models)
    return str(res.status_code)

def get_openrouter_models():
    url = "https://openrouter.ai/api/v1/models"
    res = requests.get(url)
    if res.status_code == 200:
        models = [m['id'] for m in res.json().get('data', []) if "free" in m['id'].lower()]
        return ", ".join(models[:15])
    return str(res.status_code)

with open("available_models.txt", "w", encoding="utf-8") as f:
    f.write("Gemini: " + get_gemini_models() + "\n")
    f.write("Groq: " + get_groq_models() + "\n")
    f.write("OpenRouter: " + get_openrouter_models() + "\n")
