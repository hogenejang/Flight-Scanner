import streamlit as st
import streamlit.components.v1 as components
import requests
import tempfile
import math
import csv
import os
import time

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

# 1. 전 세계 항공사 DB 파이썬 백엔드 로드
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
    except: pass
    return db

airlines_db = load_airlines()

# 2. 파이썬 백엔드 데이터 수집 엔진 (브라우저 CORS 완벽 우회)
def fetch_flight_data(lat, lon, source_pref):
    radius_nm = 100 # 반경 확대 (약 180km)
    lat_diff = radius_nm / 60.0
    lon_diff = radius_nm / (60.0 * math.cos(math.radians(lat)))
    
    # [1순위] Flightradar24 (한국 커버리지 가장 완벽)
    if source_pref in ["Auto", "Flightradar24"]:
        url = f"https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds={lat+lat_diff:.3f},{lat-lat_diff:.3f},{lon-lon_diff:.3f},{lon+lon_diff:.3f}&faa=1&mlat=1&flarm=1&adsb=1&gnd=1&air=1&vehicles=0&estimated=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                planes = []
                for k, v in data.items():
                    if k in ['full_count', 'version', 'stats']: continue
                    callsign = (v[13] or v[16] or v[0] or "Unknown").strip()
                    planes.append({
                        "hex": str(v[0]).upper(), "lat": v[1], "lon": v[2], "track": v[3],
                        "alt": v[4], "spd": v[5], "type": v[8] or "N/A", "callsign": callsign,
                        "airline": airlines_db.get(callsign[:3].upper(), "일반 / 개인 항공기")
                    })
                if planes or source_pref == "Flightradar24":
                    return planes, "Flightradar24"
        except: pass

    # [2순위] Airplanes.live (오픈소스망 폴백)
    if source_pref in ["Auto", "Airplanes.live"]:
        url = f"https://api.airplanes.live/v2/point/{lat:.3f}/{lon:.3f}/{radius_nm}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                planes = []
                for v in data.get("ac", []):
                    callsign = v.get("flight", "Unknown").strip()
                    alt = v.get("alt_baro", 0)
                    if alt == "ground": alt = 0
                    planes.append({
                        "hex": v.get("hex", "").upper(), "lat": v.get("lat"), "lon": v.get("lon"),
                        "track": v.get("track", 0), "alt": alt, "spd": v.get("gs", 0),
                        "type": v.get("t", "N/A"), "callsign": callsign,
                        "airline": airlines_db.get(callsign[:3].upper(), "일반 / 개인 항공기")
                    })
                return planes, "Airplanes.live"
        except: pass

    return [], "No Data (서버 에러)"

# 3. Streamlit 세션 및 사이드바 설정
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.4600, 126.4400] # 인천공항

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 아무 곳이나 더블클릭하면 스캔 위치가 파이썬으로 전송되어 즉시 이동합니다.")
    
    source_option = st.selectbox(
        "항적 정보 소스 선택",
        options=["Auto", "Flightradar24", "Airplanes.live"]
    )
    
    st.markdown("### 📍 Location Presets")
    if st.button("🇰🇷 인천 국제공항", use_container_width=True):
        st.session_state.home_coords = [37.4600, 126.4400]
    if st.button("🗼 도쿄 하네다 공항", use_container_width=True):
        st.session_state.home_coords = [35.5494, 139.7798]
    if st.button("🗽 뉴욕 JFK 공항", use_container_width=True):
        st.session_state.home_coords = [40.6413, -73.7781]

# 4. 화면 깜빡임이 없는 커스텀 컴포넌트 HTML 정의
html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: -apple-system, sans-serif; }
        #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #e5e9ec; }
        .top-hud { position: absolute; top: 12px; left: 12px; z-index: 1000; pointer-events: none; }
        .hud-box { background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 13px; font-weight: bold; color: #2c3e50; pointer-events: auto; }
        .bottom-hud { position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 480px; background: rgba(255, 255, 255, 0.96); border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.22); padding: 16px 20px; pointer-events: auto; display: flex; flex-direction: column; backdrop-filter: blur(8px); }
        .plane-callsign { font-size: 24px; font-weight: 900; color: #e74c3c; line-height: 1; }
        .plane-airline { font-size: 14px; color: #4a5568; margin-top: 6px; font-weight: 600; }
        .grid-info { display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #edf2f7; padding-top: 10px; margin-top: 12px; }
        .grid-val { font-size: 18px; font-weight: 800; color: #2d3748; margin-top: 2px; }
        .grid-lbl { font-size: 11px; color: #a0aec0; text-transform: uppercase; font-weight: 700; }
        .icon-wrapper { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.5s ease-out; }
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="top-hud">
        <div class="hud-box" id="status-box">📡 파이썬 엔진 연결 중...</div>
    </div>
    <div class="bottom-hud">
        <div class="plane-callsign" id="p-callsign">탐색 중...</div>
        <div class="plane-airline" id="p-airline">파이썬 서버에서 기체 정보를 분석합니다.</div>
        <div class="grid-info">
            <div style="width: 33%;"><div class="grid-lbl">Altitude</div><div class="grid-val" id="p-alt">-</div></div>
            <div style="width: 33%;"><div class="grid-lbl">Speed</div><div class="grid-val" id="p-spd">-</div></div>
            <div style="width: 33%;"><div class="grid-lbl">Status</div><div class="grid-val" id="p-status">-</div></div>
        </div>
    </div>

    <script>
        let map = L.map('map', { zoomControl: false, doubleClickZoom: false });
        L.control.zoom({ position: 'bottomright' }).addTo(map);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18 }).addTo(map);

        let radarCircle = L.circle([0,0], { radius: 180000, color: '#2980b9', weight: 2, fillColor: '#3498db', fillOpacity: 0.04 }).addTo(map);
        let homeMarker = L.circleMarker([0,0], { radius: 6, color: '#c0392b', fillColor: '#ffffff', fillOpacity: 1, weight: 3 }).addTo(map);

        let markers = {};
        let polylines = {};
        let flightHistory = {};
        let selectedIcao = null;
        let isInitialized = false;

        function sendMessageToStreamlit(type, data) {
            window.parent.postMessage({ isStreamlitMessage: true, type: type, ...data }, '*');
        }

        function getIcon(heading, color) {
            const html = `<div class="icon-wrapper" style="transform: rotate(${heading}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${color}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
            return L.divIcon({ className: '', html: html, iconSize: [24,24], iconAnchor: [12,12] });
        }

        // 파이썬으로부터 데이터 실시간 수신 (화면 깜빡임 없음)
        window.addEventListener('message', function(event) {
            if (event.data.type === 'streamlit:render') {
                const args = event.data.args;
                if (!args) return;

                const planes = args.planes || [];
                const homeCoords = args.home_coords;
                
                sendMessageToStreamlit('setFrameHeight', {height: 850}); // 프레임 고정

                if (!isInitialized) {
                    map.setView(homeCoords, 9);
                    isInitialized = true;
                }
                radarCircle.setLatLng(homeCoords);
                homeMarker.setLatLng(homeCoords);

                document.getElementById('status-box').innerText = `📡 ${planes.length}대 추적 중 [${args.source}]`;
                document.getElementById('status-box').style.color = planes.length > 0 ? "#2ecc71" : "#e74c3c";

                const now = Date.now();
                const currentIcaos = new Set();
                let nearestIcao = null;
                let minDist = 999999;

                planes.forEach(p => {
                    const icao = p.hex;
                    currentIcaos.add(icao);

                    const dist = Math.hypot(p.lat - homeCoords[0], p.lon - homeCoords[1]);
                    if (dist < minDist) { minDist = dist; nearestIcao = icao; }

                    if (!flightHistory[icao]) flightHistory[icao] = [];
                    flightHistory[icao].push({ ...p, time: now });
                    flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 900000);
                    const hist = flightHistory[icao];

                    let color = '#2ecc71'; let statusTxt = 'Level';
                    if (hist.length >= 2) {
                        const p0 = hist[Math.max(0, hist.length-4)];
                        const dt = (p.time - p0.time)/1000;
                        if (dt > 0) {
                            const vs = ((p.alt - p0.alt)/dt)*60;
                            if (vs > 150) { color = '#f1c40f'; statusTxt = 'Climb'; }
                            else if (vs < -150) { color = '#3498db'; statusTxt = 'Desc'; }
                        }
                    }

                    const newIcon = getIcon(p.track, color);
                    if (markers[icao]) {
                        markers[icao].setLatLng([p.lat, p.lon]);
                        markers[icao].setIcon(newIcon);
                    } else {
                        const m = L.marker([p.lat, p.lon], {icon: newIcon}).addTo(map);
                        m.bindTooltip(`<b>${p.callsign}</b><br>${p.alt} ft`, {direction: 'top'});
                        m.on('click', () => { selectedIcao = icao; updatePanel(p, statusTxt, color); });
                        markers[icao] = m;
                    }

                    const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                    if (polylines[icao]) {
                        polylines[icao].setLatLngs(latlngs);
                        polylines[icao].setStyle({color: color});
                    } else {
                        polylines[icao] = L.polyline(latlngs, {color: color, weight: 3}).addTo(map);
                    }
                });

                Object.keys(markers).forEach(icao => {
                    if (!currentIcaos.has(icao)) {
                        map.removeLayer(markers[icao]);
                        map.removeLayer(polylines[icao]);
                        delete markers[icao]; delete polylines[icao]; delete flightHistory[icao];
                        if (selectedIcao === icao) selectedIcao = null;
                    }
                });

                if (!selectedIcao || !flightHistory[selectedIcao]) selectedIcao = nearestIcao;
                if (selectedIcao && flightHistory[selectedIcao]) {
                    const latest = flightHistory[selectedIcao][flightHistory[selectedIcao].length-1];
                    updatePanel(latest, "Tracking", "#2ecc71");
                }
            }
        });

        function updatePanel(p, statusTxt, color) {
            document.getElementById('p-callsign').innerText = p.callsign;
            document.getElementById('p-callsign').style.color = color;
            document.getElementById('p-airline').innerText = p.type + " | " + p.airline;
            document.getElementById('p-alt').innerText = `${Math.round(p.alt)} ft`;
            document.getElementById('p-spd').innerText = `${Math.round(p.spd)} kts`;
            document.getElementById('p-status').innerText = statusTxt;
            document.getElementById('p-status').style.color = color;
        }

        // 파이썬 백엔드로 더블클릭 좌표 전송
        map.on('dblclick', function(e) {
            sendMessageToStreamlit('streamlit:setComponentValue', {value: {lat: e.latlng.lat, lng: e.latlng.lng}});
        });

        window.parent.postMessage({isStreamlitMessage: true, type: 'streamlit:componentReady'}, '*');
    </script>
</body>
</html>
"""

# 5. 커스텀 컴포넌트 즉석 빌드
component_dir = os.path.join(tempfile.gettempdir(), "radar_engine")
if not os.path.exists(component_dir):
    os.makedirs(component_dir)
with open(os.path.join(component_dir, "index.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

radar_component = components.declare_component("radar_component", path=component_dir)

# 6. 파이썬에서 데이터 Fetch 후 컴포넌트로 주입
h_lat, h_lon = st.session_state.home_coords[0], st.session_state.home_coords[1]
planes_data, source_name = fetch_flight_data(h_lat, h_lon, source_option)

click_data = radar_component(
    planes=planes_data, 
    home_coords=[h_lat, h_lon], 
    source=source_name, 
    key="radar_widget"
)

# 더블클릭 이벤트 발생 시 파이썬 변수 업데이트 후 즉시 렌더링
if click_data and click_data != st.session_state.get('last_click'):
    st.session_state.last_click = click_data
    st.session_state.home_coords = [click_data['lat'], click_data['lng']]
    st.rerun()

# 7. 백그라운드 자동 루프 (6초 간격 파이썬 통신)
time.sleep(6)
st.rerun()
