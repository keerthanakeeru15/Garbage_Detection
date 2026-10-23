import requests

def get_location_ip():
    try:
        resp = requests.get("http://ip-api.com/json/").json()
        return resp.get("lat"), resp.get("lon"), resp.get("city"), resp.get("regionName")
    except:
        return None, None, None, None

def get_area_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {"User-Agent": "YOLOGarbageDetector/1.0 (contact@example.com)"}
        resp = requests.get(url, headers=headers).json()
        addr = resp.get("address", {})
        area = addr.get("suburb") or addr.get("neighbourhood") or addr.get("village") or addr.get("county")
        city = addr.get("city") or addr.get("town")
        state = addr.get("state")
        country = addr.get("country")
        return area, city, state, country
    except:
        return None, None, None, None

def get_full_location():
    lat, lon, city, state = get_location_ip()
    if lat and lon:
        area, c, s, country = get_area_name(lat, lon)
        return {
            "lat": lat,
            "lon": lon,
            "area": area,
            "city": city or c,
            "state": state or s,
            "country": country
        }
    return None
