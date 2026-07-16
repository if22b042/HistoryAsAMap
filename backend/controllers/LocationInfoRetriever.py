import requests

def reverse_geocode(lat, lon):
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json"
            },
            headers={"User-Agent": "YourApp/1.0"}  # Required by Nominatim
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("address", {}).get("country")
    except Exception as e:
        print("Reverse geocoding error:", e)

    return None


def check_on_water(lat, lon):
    try:
        response = requests.get(f"https://api.onwater.io/api/v1/results/{lat},{lon}")

        if response.status_code == 200:
            data = response.json()
            return data.get("water", False)
    except Exception as e:
        print("Water API error:", e)

    return False


