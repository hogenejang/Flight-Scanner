import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import csv
import os

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 모바일 화면 공간 최적화 (여백 제거)
st.markdown("""
<style>
    .block-container { padding: 0 !important; max-width: 100% !important; overflow: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    iframe { border: none !important; width: 100% !important; }
</style>
""", unsafe_allow_html=True)

AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
LOCAL_AIRLINE_FILE = "airlines_db.dat"

# 항공사 데이터베이스 로드
@st.cache_data(ttl=86400)
def get_airlines_json():
    data_text = ""
    if os.path.exists(LOCAL_AIRLINE_FILE):
        try:
            with open(LOCAL_AIRLINE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                data_text = f.read()
        except:
            pass

    if not data_text:
        try:
            res = requests.get(AIRLINES_DATA_URL, timeout=10)
            if res.status_code == 200:
                data_text = res.text
                with open(LOCAL_AIRLINE_FILE, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(data_text)
        except:
            pass

    db = {}
    if data_text:
        reader = csv.reader(data_text.strip().splitlines())
        for row in reader:
            if len(row) >= 7:
                name = row[1].strip()
                icao = row[4].strip().upper()
                if len(icao) == 3 and icao != "\\N":
                    db[icao] = name
    return json.dumps(db)

airlines_json_str = get_airlines_json()

# 세션 상태 초기화 (사이드바 제어용)
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.5665, 126.9780] # 기본값: 서울

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 아무 곳이나 더블클릭하면 100km 스캔 위치가 즉시 이동합니다.")
    
    st.markdown("### 🧪 Coverage Test (커버리지 테스트)")
    st.write("한국에 비행기가 안 뜰 경우 아래 버튼을 눌러 테스트해보세요.")
    
    if st.button("🗼 테스트: 도쿄 하네다 공항", use_container_width=True):
        st.session_state.home_coords = [35.5494, 139.7798]
        st.rerun()
        
    if st.button("🗽 테스트: 뉴욕 JFK 공항", use_container_width=True):
        st.session_state.home_coords = [40.6413, -73.7781]
        st.rerun()
        
    if st.button("🏠 내 위치로 복귀 (서울)", use_container_width=True):
        st.session_state.home_coords = [37.5665, 126.9780]
        st.rerun()

# 파이썬 변수를 JS로 주입
init_lat = st.session_state.home_coords[0]
init_lon = st.session_state.home_coords[1]

# 무깜빡임 실시간 레이더 HTML/JS 엔진
radar_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ height: calc(100vh - 86px); width: 100%; background: #e5e9ec; }}
        .header-bar {{
            height: 36px; background: #1e272c; color: #ecf0f1; padding: 0 12px;
            display: flex; justify-content: space-between; align-items: center; font-size: 12px;
        }}
        .legend-item {{ display: inline-flex; align-items: center; margin-left: 8px; }}
        .legend-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }}
        .telemetry-bar {{
            height: 50px; background: #ffffff; border-top: 1px solid #dcdde1; padding: 4px 12px;
            display: flex; align-items: center; gap: 8px; overflow-x: auto; font-size: 12px; white-space: nowrap;
        }}
        .badge {{ background: #f1f2f6; padding: 4px 8px; border-radius: 4px; color: #2f3542; border: 1px solid #e4e7eb; display: inline-block; }}
        .badge b {{ color: #1e272c; }}
        .icon-wrapper {{
            width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 3px rgba(0,0,0,0.6)); transition: transform 0.4s linear;
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <span>🎯 <b>Double-click/Tap map</b> to set Home point</span>
        <div>
            <span class="legend-item"><span class="legend-dot" style="background:#2ecc71;"></span>Level</span>
            <span class="legend-item"><span class="legend-dot" style="background:#f1c40f;"></span>Climb</span>
            <span class="legend-item"><span class="legend-dot" style="background:#3498db;"></span>Desc</span>
        </div>
    </div>

    <div id="map"></div>

    <div class="telemetry-bar">
        <span class="badge">📡 API: <b id="tel-count" style="color:#e67e22;">Initializing...</b></span>
        <span class="badge">Plane: <b id="tel-callsign">Click a plane</b></span>
        <span class="badge">Airline: <b id="tel-airline">-</b></span>
        <span class="badge">Alt: <b id="tel-alt">-</b></span>
        <span class="badge">Speed: <b id="tel-spd">-</b></span>
        <span class="badge">Status: <b id="tel-status">-</b></span>
    </div>

    <script>
        const airlinesDB = {airlines_json_str};
        
        let homeLat = {init_lat};
        let homeLon = {init_lon};

        const map = L.map('map', {{
            center: [homeLat, homeLon],
            zoom: 9,
            zoomControl: false,
            doubleClickZoom: false 
        }});
        L.control.zoom({{ position: 'topright' }}).addTo(map);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 18,
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        let radarCircle = L.circle([homeLat, homeLon], {{
            radius: 100000,
            color: '#2980b9',
            weight: 2,
            fillColor: '#3498db',
            fillOpacity: 0.05
        }}).addTo(map);

        let homeMarker = L.circleMarker([homeLat, homeLon], {{
            radius: 6,
            color: '#c0392b',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 3
        }}).addTo(map).bindTooltip("Home Point");

        let flightHistory = {{}};
        let markers = {{}};
        let polylines = {{}};
        let selectedIcao = null;

        function getTriangleIcon(heading, color) {{
            const deg = heading || 0;
            const html = `
            <div class="icon-wrapper" style="transform: rotate(${{deg}}deg);">
                <svg width="20" height="20" viewBox="0 0 20 20">
                    <polygon points="10,1 2,19 10,14 18,19" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" />
                </svg>
            </div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [20, 20], iconAnchor: [10, 10] }});
        }}

        function checkStatus(hist) {{
            if (hist.length < 2) return {{ color: '#2ecc71', text: 'Level / Cruise' }};
            const p0 = hist[Math.max(0, hist.length - 4)];
            const p1 = hist[hist.length - 1];
            const dt = (p1.time - p0.time) / 1000;
            if (dt <= 0) return {{ color: '#2ecc71', text: 'Level / Cruise' }};
            const vsFpm = ((p1.alt - p0.alt) / dt) * 60;
            if (vsFpm > 150) return {{ color: '#f1c40f', text: `Climb (+${{Math.round(vsFpm)}})` }};
            if (vsFpm < -150) return {{ color: '#3498db', text: `Desc (${{Math.round(vsFpm)}})` }};
            return {{ color: '#2ecc71', text: 'Level / Cruise' }};
        }}

        // 3중 우회 Fetch 로직
        async function fetchFlightData() {{
            const radiusNm = 54;
            const lat = homeLat.toFixed(4);
            const lon = homeLon.toFixed(4);
            
            const endpoints = [
                `https://opendata.adsb.fi/api/v3/lat/${{lat}}/lon/${{lon}}/dist/${{radiusNm}}`,
                `https://api.adsb.lol/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`,
                `https://api.allorigins.win/raw?url=` + encodeURIComponent(`https://opendata.adsb.fi/api/v3/lat/${{lat}}/lon/${{lon}}/dist/${{radiusNm}}`)
            ];

            let data = null;
            let success = false;
            document.getElementById('tel-count').innerText = "Fetching...";
            document.getElementById('tel-count').style.color = "#f39c12";

            for (let url of endpoints) {{
                try {{
                    const res = await fetch(url, {{ cache: 'no-store' }});
                    if (res.ok) {{
                        const resData = await res.json();
                        if (resData && resData.ac !== undefined) {{
                            data = resData;
                            success = true;
                            break; 
                        }}
                    }}
                }} catch (e) {{ console.log("Fetch failed:", url); }}
            }}

            if (!success) {{
                document.getElementById('tel-count').innerText = "API Blocked / Server Down";
                document.getElementById('tel-count').style.color = "#e74c3c";
                return;
            }}

            const planes = data.ac || [];
            
            if (planes.length === 0) {{
                document.getElementById('tel-count').innerText = "0 planes (No traffic)";
                document.getElementById('tel-count').style.color = "#7f8c8d";
            }} else {{
                document.getElementById('tel-count').innerText = `${{planes.length}} planes OK`;
                document.getElementById('tel-count').style.color = "#2ecc71";
            }}

            const now = Date.now();
            const currentIcaos = new Set();

            planes.forEach(ac => {{
                const icao = ac.hex ? ac.hex.trim().toUpperCase() : null;
                const callsign = ac.flight ? ac.flight.trim() : null;
                if (!icao || ac.lat == null || ac.lon == null || !callsign) return;

                currentIcaos.add(icao);
                const alt = (ac.alt_baro === "ground" || ac.alt_baro == null) ? 0 : ac.alt_baro;
                const spd = ac.gs || 0;
                const heading = ac.track || 0;

                let airlineName = "Unknown Airline";
                if (callsign.length >= 3) {{
                    const prefix = callsign.substring(0, 3).toUpperCase();
                    if (airlinesDB[prefix]) airlineName = airlinesDB[prefix];
                }}

                if (!flightHistory[icao]) {{
                    flightHistory[icao] = [];
                    if (alt > 0 && spd > 100) {{
                        const rad = heading * Math.PI / 180;
                        const backRad = (rad + Math.PI) % (2 * Math.PI);
                        [30, 15].forEach(pastSec => {{
                            const distKm = (spd * pastSec / 3600.0) * 1.852;
                            const d = distKm / 6371.0;
                            const pLat = Math.asin(Math.sin(ac.lat * Math.PI / 180) * Math.cos(d) +
                                         Math.cos(ac.lat * Math.PI / 180) * Math.sin(d) * Math.cos(backRad));
                            const pLon = (ac.lon * Math.PI / 180) + Math.atan2(
                                Math.sin(backRad) * Math.sin(d) * Math.cos(ac.lat * Math.PI / 180),
                                Math.cos(d) - Math.sin(ac.lat * Math.PI / 180) * Math.sin(pLat)
                            );
                            flightHistory[icao].push({{ lat: pLat * 180 / Math.PI, lon: pLon * 180 / Math.PI, alt: alt, time: now - (pastSec * 1000) }});
                        }});
                    }}
                }}

                flightHistory[icao].push({{
                    lat: ac.lat, lon: ac.lon, alt: alt, spd: spd,
                    heading: heading, callsign: callsign, airline: airlineName, time: now
                }});

                flightHistory[icao] = flightHistory[icao].filter(p => now - p.time <= 900000);
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = checkStatus(hist);

                const newIcon = getTriangleIcon(heading, status.color);
                if (markers[icao]) {{
                    markers[icao].setLatLng([ac.lat, ac.lon]);
                    markers[icao].setIcon(newIcon);
                }} else {{
                    const m = L.marker([ac.lat, ac.lon], {{ icon: newIcon }}).addTo(map);
                    m.bindTooltip(`${{callsign}} (${{alt.toLocaleString()}} ft)`, {{ direction: 'top' }});
                    m.on('click', () => {{
                        selectedIcao = icao;
                        showTelemetry(hist[hist.length - 1], status.text);
                    }});
                    markers[icao] = m;
                }}

                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: status.color }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{ color: status.color, weight: 2.5, opacity: 0.8 }}).addTo(map);
                }}

                if (selectedIcao === icao) {{ showTelemetry(hist[hist.length - 1], status.text); }}
            }});

            Object.keys(markers).forEach(icao => {{
                if (!currentIcaos.has(icao)) {{
                    map.removeLayer(markers[icao]);
                    map.removeLayer(polylines[icao]);
                    delete markers[icao];
                    delete polylines[icao];
                    delete flightHistory[icao];
                }}
            }});
        }}

        function showTelemetry(latest, statusText) {{
            document.getElementById('tel-callsign').innerText = latest.callsign;
            document.getElementById('tel-airline').innerText = latest.airline;
            document.getElementById('tel-alt').innerText = `${{latest.alt.toLocaleString()}} ft`;
            document.getElementById('tel-spd').innerText = `${{Math.round(latest.spd)}} kts`;
            document.getElementById('tel-status').innerText = statusText;
        }}

        function relocateHomePoint(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {{}}; polylines = {{}}; flightHistory = {{}}; selectedIcao = null;
            document.getElementById('tel-callsign').innerText = 'Scanning new area...';
            fetchFlightData();
        }}

        map.on('dblclick', function(e) {{ relocateHomePoint(e.latlng.lat, e.latlng.lng); }});
        
        let lastTouchTime = 0;
        map.on('click', function(e) {{
            const currentTime = new Date().getTime();
            if (currentTime - lastTouchTime < 300 && currentTime - lastTouchTime > 0) {{
                relocateHomePoint(e.latlng.lat, e.latlng.lng);
            }}
            lastTouchTime = currentTime;
        }});

        fetchFlightData();
        setInterval(fetchFlightData, 8000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=800, scrolling=False)
