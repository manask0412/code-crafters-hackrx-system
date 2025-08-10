import httpx
import re
# --- City to multiple landmarks mapping ---
city_to_landmarks = {
    # Indian Cities
    "Delhi": ["Gateway of India"],
    "Mumbai": ["India Gate", "Space Needle"],
    "Chennai": ["Charminar"],
    "Hyderabad": ["Marina Beach", "Taj Mahal"],
    "Ahmedabad": ["Howrah Bridge"],
    "Mysuru": ["Golconda Fort"],
    "Kochi": ["Qutub Minar"],
    "Pune": ["Meenakshi Temple", "Golden Temple"],
    "Nagpur": ["Lotus Temple"],
    "Chandigarh": ["Mysore Palace"],
    "Kerala": ["Rock Garden"],
    "Bhopal": ["Victoria Memorial"],
    "Varanasi": ["Vidhana Soudha"],
    "Jaisalmer": ["Sun Temple"],

    # International Cities
    "New York": ["Eiffel Tower"],
    "London": ["Statue of Liberty", "Sydney Opera House"],
    "Tokyo": ["Big Ben"],
    "Beijing": ["Colosseum"],
    "Bangkok": ["Christ the Redeemer"],
    "Toronto": ["Burj Khalifa"],
    "Dubai": ["CN Tower"],
    "Amsterdam": ["Petronas Towers"],
    "Cairo": ["Leaning Tower of Pisa"],
    "San Francisco": ["Mount Fuji"],
    "Berlin": ["Niagara Falls"],
    "Barcelona": ["Louvre Museum"],
    "Moscow": ["Stonehenge"],
    "Seoul": ["Sagrada Familia", "Times Square"],
    "Cape Town": ["Acropolis"],
    "Istanbul": ["Big Ben"],
    "Riyadh": ["Machu Picchu"],
    "Paris": ["Taj Mahal"],
    "Singapore": ["Christchurch Cathedral"],
    "Jakarta": ["The Shard"],
    "Vienna": ["Blue Mosque"],
    "Kathmandu": ["Neuschwanstein Castle"],
    "Los Angeles": ["Buckingham Palace"],
    "Dubai Airport": ["Moai Statues"]
}

landmark_to_endpoint = {
    "Gateway of India":    "getFirstCityFlightNumber",
    "Taj Mahal":           "getSecondCityFlightNumber",
    "Eiffel Tower":        "getThirdCityFlightNumber",
    "Big Ben":             "getFourthCityFlightNumber",
}
DEFAULT_ENDPOINT = "getFifthCityFlightNumber"

# Async flight-lookup helper (minimal)
async def run_flight_lookup():
    """
    Runs the 1) myFavouriteCity -> map -> endpoint -> flightNumber flow (async httpx).
    Returns (city, landmark, endpoint_key, flight_number).
    Raises on failure.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1) fetch favourite city
        r = await client.get("https://register.hackrx.in/submissions/myFavouriteCity")
        r.raise_for_status()
        payload = r.json()
        city = payload.get("data", {}).get("city")
        if not city:
            raise RuntimeError("API did not return a city name")

        # 2) get all landmarks for the city
        landmarks = city_to_landmarks.get(city)
        if not landmarks:
            raise KeyError(f"Unknown city '{city}' — please update the mapping.")

        # 3) choose endpoint key
        #endpoint_key = landmark_to_endpoint.get(landmark, DEFAULT_ENDPOINT)
        endpoint_key = DEFAULT_ENDPOINT
        for lm in landmarks:
            if lm in landmark_to_endpoint:
                endpoint_key = landmark_to_endpoint[lm]
                break  # first special match is enough

        # 4) fetch flight number
        r2 = await client.get(f"https://register.hackrx.in/teams/public/flights/{endpoint_key}")
        r2.raise_for_status()
        payload2 = r2.json()
        flight = payload2.get("data", {}).get("flightNumber")
        message = payload2.get("message", "")
        if not flight:
            raise RuntimeError(f"No flightNumber in response from {endpoint_key}")
        # Get first word from message (destination)
        destination = message.split()[0] if message else None

        return flight, destination
    
async def fetch_secret_token(url: str) -> str:
    """
    Fetch the given URL and extract the secret token from the HTML.
    Looks for <div id="token">TOKEN</div> pattern.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        html_text = r.text

    match = re.search(r'<div id="token">([\w\d]+)</div>', html_text)
    if not match:
        raise RuntimeError("Token not found in page HTML")
    return match.group(1)