import config
from google import genai
client = genai.Client(api_key=config.GEMINI_API_KEYS[0])
for model in client.models.list():
    print(model.name)
