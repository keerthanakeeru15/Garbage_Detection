from PIL import Image
from detector import yolo_detect
import config

# Create a dummy image
dummy_img = Image.new('RGB', (100, 100), color = 'red')
dummy_img.save("temp_test.jpg")

print("Running yolo_detect...")
res = yolo_detect("temp_test.jpg", config.GEMINI_API_KEYS)
print("Result:", res)
