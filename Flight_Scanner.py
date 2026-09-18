import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import time
import math
import csv
import os

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 여백 최적화
st.markdown("""
<style>
    .block-container { padding: 0.5rem 1rem 1rem 1rem !important; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
LOCAL_AIRLINE_FILE = "airlines_db.dat"
MAX_HISTORY_SEC = 900
MAX_HISTORY_POINTS = 120

# 1. 항공사 DB 로드
@st.cache_data(ttl=86400)
def load_global_airlines():
    data_text = ""
    if os.path.exists(LOCAL_AIRLINE_FILE):
        try:
            with open(LOCAL_AIRLINE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                data_text = f.read()
        except Exception:
            pass

    if not data_text:
        try:
            res = requests.get(AIRLINES_DATA_URL, timeout=8)
            if res.status_code == 200:
                data_text = res.text
                with open(LOCAL_AIRLINE_FILE, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(data_text)
        except Exception:
            pass

    db = {}
    if data_text:
        reader = csv.reader(data_text.strip().splitlines())
        for row in reader:
            if len(row) >= 7:
                name = row[1].strip()
                icao = row[4].strip().upper()
                country = row[6].strip()
                if len(icao) == 3 and icao != "\\N":
                    db[icao] = {"name": name, "country": country}
    return db

airlines_db = load_global_airlines()

def get_airline_info(callsign):
    if not callsign or len(callsign) < 3:
        return "Private / General", "N/A"
    code = callsign[:3].upper()
    if code in airlines_db:
        return airlines_db[code]["name"], airlines_db[code]["country"]
    return "Unknown Airline", "Unknown"

# 세션 상태 초기화
if "flight_history" not in st.session_state:
    st.session_state.flight_history = {}
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.5665, 126.9780]

with st.sidebar:
    st.header("⚙️ Radar Settings")
    lat_in = st.number_input("Home Latitude", value=float(st.session_state.home_coords[0]), format="%.4f")
    lon_in = st.number_input("Home Longitude", value=float(st.session_state.home_coords[1]), format="%.4f")
    
    if st.button("📍 Set Coordinates", use_container_width=True):
        st.session_state.home_coords = [lat_in, lon_in]
        st.session_state.flight_history.clear()
        st.rerun()

    display_limit_min = st.select_slider("Track Line Length (Min)", options=[1, 3, 5, 10, 15], value=5)
    display_limit_sec = display_limit_min * 60

# 2. 파이썬 백엔드에서 실시간 데이터 수집 (CORS 문제 원천 차단)
def fetch_live_data(lat, lon):
    radius_nm = 54
    url = f"https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{radius_nm}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get('ac', [])
    except Exception:
        pass
    return []

def get_flight_status(hist):
    if len(hist) < 2:
        return "#2ecc71", "Level / Cruise"
    p0 = hist[max(0, len(hist) - 4)]
    p1 = hist[-1]
    dt = p1['time'] - p0['time']
    if dt <= 0:
        return "#2ecc71", "Level / Cruise"
    vs_fpm = ((p1['alt'] - p0['alt']) / dt) * 60.0
    if vs_fpm > 150:
        return "#f1c40f", f"Climbing (+{vs_fpm:.0f} fpm)"
    elif vs_fpm < -150:
        return "#3498db", f"Descending ({vs_fpm:.0f} fpm)"
    return "#2ecc71", "Level / Cruise"

# 데이터 갱신 및 가상 꼬리선 보간
now = time.time()
raw_ac = fetch_live_data(st.session_state.home_coords[0], st.session_state.home_coords[1])

for ac in raw_ac:
    icao = ac.get('hex', '').strip().upper()
    callsign = ac.get('flight', '').strip()
    lat, lon = ac.get('lat'), ac.get('lon')

    if not icao or lat is None or lon is None or not callsign:
        continue

    alt = 0 if (ac.get('alt_baro') == "ground" or ac.get('alt_baro') is None) else ac.get('alt_baro')
    spd = ac.get('gs', 0.0) or 0.0
    heading = ac.get('track', 0.0) or 0.0
    ac_type = ac.get('t', 'Unknown')
    airline_name, airline_country = get_airline_info(callsign)

    # 30초 이전 가상 꼬리선
    if icao not in st.session_state.flight_history:
        st.session_state.flight_history[icao] = []
        if alt > 0 and spd > 100:
            rad = math.radians(heading)
            back_rad = (rad + math.pi) % (2 * math.pi)
            for past_sec in [30, 15]:
                dist_km = (spd * past_sec / 3600.0) * 1.852
                d = dist_km / 6371.0
                p_lat = math.asin(math.sin(math.radians(lat)) * math.cos(d) +
                                  math.cos(math.radians(lat)) * math.sin(d) * math.cos(back_rad))
                p_lon = math.radians(lon) + math.atan2(
                    math.sin(back_rad) * math.sin(d) * math.cos(math.radians(lat)),
                    math.cos(d) - math.sin(math.radians(lat)) * math.sin(p_lat)
                )
                st.session_state.flight_history[icao].append({
                    'time': now - past_sec, 'lat': math.degrees(p_lat), 'lon': math.degrees(p_lon),
                    'alt': alt, 'spd': spd
                })

    st.session_state.flight_history[icao].append({
        'time': now, 'lat': lat, 'lon': lon, 'alt': alt,
        'spd': spd, 'heading': heading, 'callsign': callsign,
        'type': ac_type, 'airline': airline_name, 'country': airline_country
    })

# 슬라이딩 윈도우 보존
for icao in list(st.session_state.flight_history.keys()):
    st.session_state.flight_history[icao] = [
        p for p in st.session_state.flight_history[icao] if now - p['time'] <= MAX_HISTORY_SEC
    ]
    if len(st.session_state.flight_history[icao]) > MAX_HISTORY_POINTS:
        st.session_state.flight_history[icao] = st.session_state.flight_history[icao][-MAX_HISTORY_POINTS:]
    if not st.session_state.flight_history[icao]:
        del st.session_state.flight_history[icao]

# 3. 프론트엔드로 전달할 JSON 페이로드 생성
planes_payload = []
for icao, hist in st.session_state.flight_history.items():
    if not hist:
        continue
    latest = hist[-1]
    color_hex, status_txt = get_flight_status(hist)
    path_coords = [[round(p['lat'], 4), round(p['lon'], 4)] for p in hist if now - p['time'] <= display_limit_sec]
    
    planes_payload.append({
        "icao": icao,
        "callsign": latest['callsign'],
        "lat": latest['lat'],
        "lon": latest['lon'],
        "heading": latest.get('heading', 0),
        "alt": latest['alt'],
        "spd": round(latest['spd']),
        "type": latest.get('type', 'Unknown'),
        "airline": latest.get('airline', 'N/A'),
        "color": color_hex,
        "status": status_txt,
        "path": path_coords
    })

payload_json = json.dumps({
    "home": st.session_state.home_coords,
    "planes": planes_payload
})

# 4. 지도 엔진 (Leaflet 기반 무깜빡임 단일 렌더러)
map_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; width: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ height: calc(100vh - 110px); min-height: 520px; width: 100%; }}
        .header-bar {{
            background: #2c3e50; color: white; padding: 8px 12px;
            display: flex; justify-content: space-between; align-items: center; font-size: 13px;
        }}
        .legend-item {{ display: inline-flex; align-items: center; margin-right: 8px; }}
        .legend-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 4px; }}
        .telemetry-bar {{
            background: #ffffff; border-top: 1px solid #e0e0e0; padding: 8px 12px;
            display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; align-items: center;
        }}
        .badge {{ background: #f1f2f6; padding: 3px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="header-bar">
        <span>🎯 100km Coverage Radar (Planes: {len(planes_payload)})</span>
        <div>
            <span class="legend-item"><span class="legend-dot" style="background:#2ecc71;"></span>Level</span>
            <span class="legend-item"><span class="legend-dot" style="background:#f1c40f;"></span>Climb</span>
            <span class="legend-item"><span class="legend-dot" style="background:#3498db;"></span>Desc</span>
        </div>
    </div>

    <div id="map"></div>

    <div class="telemetry-bar">
        <span><b>Selected:</b> <span id="tel-callsign">Click any plane</span></span>
        <span class="badge">Airline: <b id="tel-airline">-</b></span>
        <span class="badge">Model: <b id="tel-type">-</b></span>
        <span class="badge">Alt: <b id="tel-alt">-</b></span>
        <span class="badge">Speed: <b id="tel-spd">-</b></span>
        <span class="badge">Status: <b id="tel-status">-</b></span>
    </div>

    <script>
        const initialData = {payload_json};
        const homeCoords = initialData.home;

        // 지도 생성
        const map = L.map('map', {{
            center: homeCoords,
            zoom: 9,
            zoomControl: false
        }});
        L.control.zoom({{ position: 'topright' }}).addTo(map);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 18,
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        // 100km 원형 경계선 및 홈 마커
        L.circle(homeCoords, {{
            radius: 100000,
            color: '#2980b9',
            weight: 2,
            fillColor: '#3498db',
            fillOpacity: 0.05
        }}).addTo(map);

        L.circleMarker(homeCoords, {{
            radius: 7,
            color: '#e74c3c',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 3
        }}).addTo(map).bindTooltip("Home Point");

        // 세모 모양 SVG 생성기
        function makeTriangle(angle, color) {{
            const deg = angle || 0;
            const svg = `<svg width="20" height="20" viewBox="0 0 20 20" style="transform: rotate(${{deg}}deg);">
                <polygon points="10,2 2,18 10,14 18,18" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" />
            </svg>`;
            return L.divIcon({{
                className: '',
                html: svg,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            }});
        }}

        // 비행기 및 항적 렌더링
        initialData.planes.forEach(plane => {{
            // 마커
            const marker = L.marker([plane.lat, plane.lon], {{
                icon: makeTriangle(plane.heading, plane.color)
            }}).addTo(map);

            marker.bindTooltip(`${{plane.callsign}} (${{plane.alt.toLocaleString()}} ft)`, {{ direction: 'top' }});
            marker.on('click', () => {{
                document.getElementById('tel-callsign').innerText = plane.callsign;
                document.getElementById('tel-airline').innerText = plane.airline;
                document.getElementById('tel-type').innerText = plane.type;
                document.getElementById('tel-alt').innerText = plane.alt.toLocaleString() + ' ft';
                document.getElementById('tel-spd').innerText = plane.spd + ' kts';
                document.getElementById('tel-status').innerText = plane.status;
            }});

            // 꼬리선
            if (plane.path && plane.path.length > 1) {{
                L.polyline(plane.path, {{
                    color: plane.color,
                    weight: 2.5,
                    opacity: 0.8
                }}).addTo(map);
            }}
        }});
    </script>
</body>
</html>
"""

components.html(map_html, height=660, scrolling=False)

# 8초 주기 자동 갱신 트리거
time.sleep(8)
st.rerun()
