import json
from google import genai
import config

client = genai.Client(api_key=config.GEMINI_API_KEYS[0])
models = client.models.list()
for model in models:
    print(model.name)
