import json
from google import genai
from PIL import Image

_CURRENT_KEY_INDEX = 0

def yolo_detect(image_path, api_keys):
    global _CURRENT_KEY_INDEX
    if not api_keys:
        return None
        
    prompt = """
    Detect if there is littering or garbage in this image.
    Return strictly JSON:
    {
      "littering": true or false,
      "confidence": float between 0.0 and 1.0,
      "description": "short explanation"
    }
    """
    
    num_keys = len(api_keys)
    attempts = 0
    
    while attempts < num_keys:
        key = api_keys[_CURRENT_KEY_INDEX].strip()
        _CURRENT_KEY_INDEX = (_CURRENT_KEY_INDEX + 1) % num_keys  # Round Robin: always advance
        attempts += 1
        
        if not key:
            continue
            
        try:
            client = genai.Client(api_key=key)
            img = Image.open(image_path)
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=[img, prompt],
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            data = json.loads(text.strip())
            return data
        except Exception as e:
            print(f"Error with API key {key[:5]}... : {e}")
            # If it fails, the loop continues and tries the next key
            continue
            
    return None
