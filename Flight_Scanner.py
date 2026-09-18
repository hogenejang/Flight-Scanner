import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import math
import csv

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 화면 공간 최적화
st.markdown("""
<style>
    .block-container { padding: 0 !important; max-width: 100% !important; overflow: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    iframe { border: none !important; width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# 1. 전 세계 항공사 DB 백엔드 캐시
AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
@st.cache_data(ttl=86400)
def load_airlines():
    db = {}
    try:
        res = requests.get(AIRLINES_DATA_URL, timeout=5)
        if res.status_code == 200:
            reader = csv.reader(res.text.strip().splitlines())
            for row in reader:
                if len(row) >= 7:
                    icao = row[4].strip().upper()
                    if len(icao) == 3 and icao != "\\N":
                        db[icao] = row[1].strip()
    except Exception:
        pass
    return db

airlines_db = load_airlines()

# 2. 파이썬 백엔드 데이터 수집 (CORS 원천 차단)
def fetch_flight_data(lat, lon, source_pref):
    radius_nm = 100 # 약 180km 커버리지
    lat_diff = radius_nm / 60.0
    lon_diff = radius_nm / (60.0 * math.cos(math.radians(lat)))
    
    # [1순위] Flightradar24 (한국/인천공항 완벽 커버)
    if source_pref in ["Auto", "Flightradar24"]:
        url = f"https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds={lat+lat_diff:.3f},{lat-lat_diff:.3f},{lon-lon_diff:.3f},{lon+lon_diff:.3f}&faa=1&mlat=1&flarm=1&adsb=1&gnd=1&air=1&vehicles=0&estimated=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        try:
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                planes = []
                for k, v in data.items():
                    if k in ['full_count', 'version', 'stats']: 
                        continue
                    callsign = (v[13] or v[16] or v[0] or "Unknown").strip()
                    planes.append({
                        "hex": str(v[0]).upper(),
                        "lat": v[1],
                        "lon": v[2],
                        "track": v[3] or 0,
                        "alt": v[4] or 0,
                        "spd": v[5] or 0,
                        "type": v[8] or "N/A",
                        "callsign": callsign,
                        "airline": airlines_db.get(callsign[:3].upper(), "일반 / 개인 항공기")
                    })
                if planes or source_pref == "Flightradar24":
                    return planes, "Flightradar24"
        except Exception:
            pass

    # [2순위] Airplanes.live (오픈소스망 폴백)
    if source_pref in ["Auto", "Airplanes.live"]:
        url = f"https://api.airplanes.live/v2/point/{lat:.3f}/{lon:.3f}/{radius_nm}"
        try:
            res = requests.get(url, timeout=4)
            if res.status_code == 200:
                data = res.json()
                planes = []
                for v in data.get("ac", []):
                    callsign = v.get("flight", "Unknown").strip()
                    alt = v.get("alt_baro", 0)
                    if alt == "ground" or alt is None: 
                        alt = 0
                    planes.append({
                        "hex": v.get("hex", "").upper(),
                        "lat": v.get("lat"),
                        "lon": v.get("lon"),
                        "track": v.get("track", 0),
                        "alt": alt,
                        "spd": v.get("gs", 0),
                        "type": v.get("t", "N/A"),
                        "callsign": callsign,
                        "airline": airlines_db.get(callsign[:3].upper(), "일반 / 개인 항공기")
                    })
                return planes, "Airplanes.live"
        except Exception:
            pass

    return [], "서버 응답 없음"

# 3. 세션 상태 초기화
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.4600, 126.4400] # 인천공항

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("프리셋 버튼으로 스캔 위치를 즉시 이동할 수 있습니다.")
    
    source_option = st.selectbox(
        "항적 정보 소스 선택",
        options=["Auto", "Flightradar24", "Airplanes.live"]
    )
    
    st.markdown("### 📍 Location Presets")
    if st.button("🇰🇷 인천 국제공항", use_container_width=True):
        st.session_state.home_coords = [37.4600, 126.4400]
        st.rerun()
    if st.button("🗼 도쿄 하네다 공항", use_container_width=True):
        st.session_state.home_coords = [35.5494, 139.7798]
        st.rerun()
    if st.button("🗽 뉴욕 JFK 공항", use_container_width=True):
        st.session_state.home_coords = [40.6413, -73.7781]
        st.rerun()

# 4. Streamlit Fragment를 통한 부드러운 5초 부분 업데이트
@st.fragment(run_every="5s")
def render_live_radar():
    h_lat, h_lon = st.session_state.home_coords[0], st.session_state.home_coords[1]
    planes, source_name = fetch_flight_data(h_lat, h_lon, source_option)
    planes_json = json.dumps(planes)

    radar_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body, html {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: -apple-system, sans-serif; }}
            #map {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #e5e9ec; }}
            .top-hud {{ position: absolute; top: 12px; left: 12px; right: 12px; z-index: 1000; display: flex; justify-content: space-between; pointer-events: none; }}
            .hud-box {{ background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 13px; font-weight: bold; color: #2c3e50; pointer-events: auto; display: flex; align-items: center; gap: 8px; }}
            .bottom-hud {{ position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 480px; background: rgba(255, 255, 255, 0.96); border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.22); padding: 16px 20px; pointer-events: auto; display: flex; flex-direction: column; backdrop-filter: blur(8px); }}
            .plane-callsign {{ font-size: 24px; font-weight: 900; color: #e74c3c; line-height: 1; }}
            .plane-airline {{ font-size: 13px; color: #4a5568; margin-top: 6px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .grid-info {{ display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #edf2f7; padding-top: 10px; margin-top: 10px; }}
            .grid-val {{ font-size: 17px; font-weight: 800; color: #2d3748; margin-top: 2px; }}
            .grid-lbl {{ font-size: 11px; color: #a0aec0; text-transform: uppercase; font-weight: 700; }}
            .icon-wrapper {{ width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.4s linear; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div class="top-hud">
            <div class="hud-box" style="color: {'#2ecc71' if planes else '#e74c3c'};">
                📡 {len(planes)}대 추적 중 [{source_name}]
            </div>
            <div class="hud-box">
                <span style="color:#2ecc71;">● 수평</span>
                <span style="color:#f1c40f;">● 상승</span>
                <span style="color:#3498db;">● 하강</span>
            </div>
        </div>
        <div class="bottom-hud">
            <div class="plane-callsign" id="p-callsign">비행기를 선택하세요</div>
            <div class="plane-airline" id="p-airline">지도 위의 비행기 마커를 클릭하면 세부 정보가 표시됩니다.</div>
            <div class="grid-info">
                <div style="width: 33%;"><div class="grid-lbl">Altitude</div><div class="grid-val" id="p-alt">-</div></div>
                <div style="width: 33%;"><div class="grid-lbl">Speed</div><div class="grid-val" id="p-spd">-</div></div>
                <div style="width: 33%;"><div class="grid-lbl">Status</div><div class="grid-val" id="p-status">-</div></div>
            </div>
        </div>

        <script>
            const planes = {planes_json};
            const home = [{h_lat}, {h_lon}];

            const map = L.map('map', {{ center: home, zoom: 9, zoomControl: false }});
            L.control.zoom({{ position: 'bottomright' }}).addTo(map);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 18 }}).addTo(map);

            L.circle(home, {{ radius: 180000, color: '#2980b9', weight: 2, fillColor: '#3498db', fillOpacity: 0.04 }}).addTo(map);
            L.circleMarker(home, {{ radius: 6, color: '#c0392b', fillColor: '#ffffff', fillOpacity: 1, weight: 3 }}).addTo(map).bindTooltip("Home Point");

            function getIcon(heading, color) {{
                const html = `<div class="icon-wrapper" style="transform: rotate(${{heading}}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
                return L.divIcon({{ className: '', html: html, iconSize: [24,24], iconAnchor: [12,12] }});
            }}

            function updatePanel(p, statusTxt, color) {{
                document.getElementById('p-callsign').innerText = p.callsign;
                document.getElementById('p-callsign').style.color = color;
                document.getElementById('p-airline').innerText = (p.type !== 'N/A' ? p.type + ' | ' : '') + p.airline;
                document.getElementById('p-alt').innerText = `${{Math.round(p.alt).toLocaleString()}} ft`;
                document.getElementById('p-spd').innerText = `${{Math.round(p.spd)}} kts`;
                document.getElementById('p-status').innerText = statusTxt;
                document.getElementById('p-status').style.color = color;
            }}

            let nearestPlane = null;
            let minDist = 999999;

            planes.forEach(p => {{
                const dist = Math.hypot(p.lat - home[0], p.lon - home[1]);
                if (dist < minDist) {{
                    minDist = dist;
                    nearestPlane = p;
                }}

                const marker = L.marker([p.lat, p.lon], {{ icon: getIcon(p.track, '#2ecc71') }}).addTo(map);
                marker.bindTooltip(`<b>${{p.callsign}}</b><br>${{Math.round(p.alt)}} ft`, {{ direction: 'top' }});
                marker.on('click', () => updatePanel(p, "Tracking", "#2ecc71"));
            }});

            // 가장 가까운 기체를 하단 패널에 자동 표시
            if (nearestPlane) {{
                updatePanel(nearestPlane, "Tracking", "#2ecc71");
            }} else {{
                document.getElementById('p-callsign').innerText = "기체 없음";
                document.getElementById('p-airline').innerText = "현재 탐지 반경 내에 비행 중인 항공기가 없습니다.";
            }}
        </script>
    </body>
    </html>
    """

    components.html(radar_html, height=850, scrolling=False)

render_live_radar()
