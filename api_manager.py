from google import genai

class APIManager:
    def __init__(self, api_keys):
        self.keys = [k.strip() for k in api_keys if k.strip()]
        self.current_key_index = 0

    def get_client(self):
        if not self.keys:
            return None
        key = self.keys[self.current_key_index]
        return genai.Client(api_key=key)

    def switch_key(self):
        if not self.keys:
            return False
            
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        return True
