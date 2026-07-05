import requests
import json

GEMINI_API_KEY = "AQ.Ab8RN6IFPd7wYj6-q98dV0HBsEpA7_d3O-wnX8ITfzegQ7-wGw"
GROQ_API_KEY = "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"
OPENROUTER_API_KEY = "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"

def test_gemini(model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": "hi"}]}]})
    return f"{model}: {res.status_code} - {res.text[:50]}"

def test_groq(model):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    res = requests.post(url, headers=headers, json={"model": model, "messages": [{"role": "user", "content": "hi"}]})
    return f"{model}: {res.status_code} - {res.text[:50]}"

def test_openrouter(model):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    res = requests.post(url, headers=headers, json={"model": model, "messages": [{"role": "user", "content": "hi"}]})
    return f"{model}: {res.status_code} - {res.text[:50]}"

with open("api_test_results.txt", "w", encoding="utf-8") as f:
    f.write(test_gemini("gemini-1.5-flash-latest") + "\n")
    f.write(test_gemini("gemini-1.5-flash") + "\n")
    f.write(test_gemini("gemini-1.5-pro-latest") + "\n")
    f.write(test_gemini("gemini-1.0-pro") + "\n")
    f.write(test_gemini("gemini-pro") + "\n")
    f.write(test_groq("llama3-8b-8192") + "\n")
    f.write(test_groq("llama3-70b-8192") + "\n")
    f.write(test_groq("gemma-7b-it") + "\n")
    f.write(test_openrouter("huggingfaceh4/zephyr-7b-beta:free") + "\n")
    f.write(test_openrouter("meta-llama/llama-3-8b-instruct:free") + "\n")
