import requests

URL = "https://api.dashboard.kontaktmarkazi.uz/v1/operators"

def fetch_operator_snapshot():
    try:
        response = requests.get(URL, timeout=2)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {"data": {"agents": []}}