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

# 화면 최적화 (모바일/PC 스크롤바 방지 및 여백 제거)
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

@st.cache_data(ttl=86400)
def get_airlines_json():
    data_text = ""
    if os.path.exists(LOCAL_AIRLINE_FILE):
        try:
            with open(LOCAL_AIRLINE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                data_text = f.read()
        except: pass

    if not data_text:
        try:
            res = requests.get(AIRLINES_DATA_URL, timeout=10)
            if res.status_code == 200:
                data_text = res.text
                with open(LOCAL_AIRLINE_FILE, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(data_text)
        except: pass

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

if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.4600, 126.4400] # 인천공항

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 아무 곳이나 더블클릭하면 150km 스캔 위치가 즉시 이동합니다.")
    
    st.markdown("### 📍 Location Presets")
    st.write("한국 외 지역 테스트 이동")
    if st.button("🇰🇷 인천 국제공항", use_container_width=True):
        st.session_state.home_coords = [37.4600, 126.4400]
        st.rerun()
    if st.button("🗼 도쿄 하네다 공항", use_container_width=True):
        st.session_state.home_coords = [35.5494, 139.7798]
        st.rerun()
    if st.button("🗽 뉴욕 JFK 공항", use_container_width=True):
        st.session_state.home_coords = [40.6413, -73.7781]
        st.rerun()

init_lat = st.session_state.home_coords[0]
init_lon = st.session_state.home_coords[1]

# 강력한 4중 우회 프록시 엔진 및 에러 로깅 UI 탑재
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
        #map {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; z-index: 1; background: #e5e9ec; }}
        
        .top-hud {{
            position: absolute; top: 12px; left: 12px; right: 12px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: flex-start; pointer-events: none; flex-wrap: wrap; gap: 10px;
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 13px; font-weight: bold; color: #2c3e50;
            pointer-events: auto; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(0,0,0,0.1);
        }}
        
        .bottom-hud {{
            position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%); z-index: 1000;
            width: 90%; max-width: 480px; background: rgba(255, 255, 255, 0.96); border-radius: 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.22); padding: 16px 20px; pointer-events: auto;
            display: flex; flex-direction: column; border: 1px solid rgba(0,0,0,0.06); backdrop-filter: blur(8px);
        }}
        .plane-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }}
        .plane-callsign {{ font-size: 24px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .plane-type {{ font-size: 13px; font-weight: bold; color: #7f8c8d; background: #edf2f7; padding: 3px 8px; border-radius: 4px; }}
        .plane-airline {{ font-size: 12px; color: #4a5568; margin-bottom: 12px; font-weight: 600; line-height: 1.4; }}
        
        .grid-info {{ display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #edf2f7; padding-top: 10px; }}
        .grid-item {{ display: flex; flex-direction: column; width: 33%; }}
        .grid-val {{ font-size: 18px; font-weight: 800; color: #2d3748; margin-top: 2px; }}
        .grid-lbl {{ font-size: 11px; color: #a0aec0; text-transform: uppercase; font-weight: 700; }}
        
        .icon-wrapper {{
            width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.5s ease-out;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="top-hud">
        <div class="hud-box" id="status-box">📡 스캔 준비 중...</div>
        <div class="hud-box">
            <span style="color:#2ecc71;">● 수평</span>
            <span style="color:#f1c40f;">● 상승</span>
            <span style="color:#3498db;">● 하강</span>
        </div>
    </div>

    <div class="bottom-hud" id="telemetry-card">
        <div class="plane-header">
            <span class="plane-callsign" id="p-callsign">탐색 중...</span>
            <span class="plane-type" id="p-type">-</span>
        </div>
        <!-- 진단 및 정보 표시 겸용 텍스트 -->
        <div class="plane-airline" id="p-airline" style="color:#3498db;">데이터 수집망 4곳 접속 시도 중...</div>
        <div class="grid-info">
            <div class="grid-item">
                <span class="grid-lbl">Altitude</span>
                <span class="grid-val" id="p-alt">-</span>
            </div>
            <div class="grid-item">
                <span class="grid-lbl">Speed</span>
                <span class="grid-val" id="p-spd">-</span>
            </div>
            <div class="grid-item">
                <span class="grid-lbl">Status</span>
                <span class="grid-val" id="p-status" style="font-size:16px;">-</span>
            </div>
        </div>
    </div>

    <script>
        const airlinesDB = {airlines_json_str};
        let homeLat = {init_lat};
        let homeLon = {init_lon};

        const map = L.map('map', {{ center: [homeLat, homeLon], zoom: 9, zoomControl: false, doubleClickZoom: false }});
        L.control.zoom({{ position: 'bottomright' }}).addTo(map);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 18, attribution: '© OSM' }}).addTo(map);

        let radarCircle = L.circle([homeLat, homeLon], {{ radius: 150000, color: '#2980b9', weight: 2, fillColor: '#3498db', fillOpacity: 0.04 }}).addTo(map);
        let homeMarker = L.circleMarker([homeLat, homeLon], {{ radius: 6, color: '#c0392b', fillColor: '#ffffff', fillOpacity: 1, weight: 3 }}).addTo(map).bindTooltip("Home Point (150km)");

        let flightHistory = {{}};
        let markers = {{}};
        let polylines = {{}};
        let selectedIcao = null;

        function getTriangleIcon(heading, color) {{
            const deg = heading || 0;
            const html = `<div class="icon-wrapper" style="transform: rotate(${{deg}}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [24, 24], iconAnchor: [12, 12] }});
        }}

        function checkStatus(hist) {{
            if (hist.length < 2) return {{ color: '#2ecc71', text: 'Level' }};
            const p0 = hist[Math.max(0, hist.length - 4)];
            const p1 = hist[hist.length - 1];
            const dt = (p1.time - p0.time) / 1000;
            if (dt <= 0) return {{ color: '#2ecc71', text: 'Level' }};
            const vsFpm = ((p1.alt - p0.alt) / dt) * 60;
            if (vsFpm > 150) return {{ color: '#f1c40f', text: 'Climb' }};
            if (vsFpm < -150) return {{ color: '#3498db', text: 'Desc' }};
            return {{ color: '#2ecc71', text: 'Level' }};
        }}

        // 4중 하이브리드 엔진 (자동 폴백)
        async function fetchFlightData() {{
            document.getElementById('status-box').innerText = "📡 데이터 스캔 중...";
            document.getElementById('status-box').style.color = "#f39c12";
            document.getElementById('p-airline').innerText = "데이터 수집망 4곳 통신 시도 중...";
            document.getElementById('p-airline').style.color = "#3498db";

            const lat = homeLat.toFixed(3);
            const lon = homeLon.toFixed(3);
            const radiusNm = 80;
            
            const radiusLat = 1.35; const radiusLon = 1.7;
            const minLat = (homeLat - radiusLat).toFixed(3);
            const maxLat = (homeLat + radiusLat).toFixed(3);
            const minLon = (homeLon - radiusLon).toFixed(3);
            const maxLon = (homeLon + radiusLon).toFixed(3);
            
            const fr24Url = `https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds=${{maxLat}},${{minLat}},${{minLon}},${{maxLon}}&faa=1&mlat=1&flarm=1&adsb=1&gnd=1&air=1&vehicles=0&estimated=1`;

            // 접속을 시도할 4개의 강력한 라우트 정의
            const endpoints = [
                {{ name: "ADSB.one", url: `https://api.adsb.one/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`, type: 'v2' }},
                {{ name: "Airplanes.live", url: `https://api.airplanes.live/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`, type: 'v2' }},
                {{ name: "FR24(Proxy1)", url: `https://api.allorigins.win/get?url=${{encodeURIComponent(fr24Url)}}`, type: 'fr24_allorigins' }},
                {{ name: "FR24(Proxy2)", url: `https://api.codetabs.com/v1/proxy?quest=${{encodeURIComponent(fr24Url)}}`, type: 'fr24_raw' }}
            ];
            
            let planes = [];
            let sourceNetwork = "";
            let logMsg = "";
            
            for (let ep of endpoints) {{
                try {{
                    const res = await fetch(ep.url, {{ cache: 'no-store' }});
                    if (!res.ok) {{
                        logMsg += `[${{ep.name}} HTTP ${{res.status}}] `;
                        continue;
                    }}
                    
                    if (ep.type === 'v2') {{
                        const json = await res.json();
                        if (json && json.ac && json.ac.length > 0) {{
                            planes = json.ac; sourceNetwork = ep.name; break;
                        }} else {{ logMsg += `[${{ep.name}} 0대] `; }}
                    }} 
                    else if (ep.type === 'fr24_allorigins') {{
                        const json = await res.json();
                        if (json.contents) {{
                            const frData = JSON.parse(json.contents);
                            let arr = [];
                            for (let key in frData) {{
                                if (['full_count', 'version', 'stats'].includes(key)) continue;
                                let p = frData[key];
                                arr.push({{ hex: p[0], lat: p[1], lon: p[2], track: p[3], alt_baro: p[4], gs: p[5], t: p[8], flight: p[13] || p[16] || p[0] }});
                            }}
                            if (arr.length > 0) {{ planes = arr; sourceNetwork = "FR24"; break; }}
                            else {{ logMsg += `[FR24 0대] `; }}
                        }} else {{ logMsg += `[FR24 Proxy Empty] `; }}
                    }} 
                    else if (ep.type === 'fr24_raw') {{
                        const frData = await res.json();
                        let arr = [];
                        for (let key in frData) {{
                            if (['full_count', 'version', 'stats'].includes(key)) continue;
                            let p = frData[key];
                            arr.push({{ hex: p[0], lat: p[1], lon: p[2], track: p[3], alt_baro: p[4], gs: p[5], t: p[8], flight: p[13] || p[16] || p[0] }});
                        }}
                        if (arr.length > 0) {{ planes = arr; sourceNetwork = "FR24"; break; }}
                        else {{ logMsg += `[FR24 Proxy2 0대] `; }}
                    }}
                }} catch (e) {{
                    logMsg += `[${{ep.name}} CORS/Network Err] `;
                }}
            }}

            // 4개 망이 전부 실패하거나 진짜 0대인 경우 에러 상세 출력
            if (planes.length === 0) {{
                document.getElementById('status-box').innerText = "📡 0대 (통신 장애 또는 기체 없음)";
                document.getElementById('status-box').style.color = "#e74c3c";
                document.getElementById('p-callsign').innerText = "결과 없음";
                document.getElementById('p-airline').style.color = "#c0392b";
                document.getElementById('p-airline').innerText = "상세 진단 로그: " + logMsg;
                return;
            }}

            document.getElementById('status-box').innerText = "📡 " + planes.length + "대 추적 중 [" + sourceNetwork + "]";
            document.getElementById('status-box').style.color = "#2ecc71";
            document.getElementById('p-airline').style.color = "#4a5568";

            const now = Date.now();
            const currentIcaos = new Set();
            let nearestIcao = null;
            let minDistance = 999999;

            planes.forEach(ac => {{
                const icao = ac.hex ? ac.hex.trim().toUpperCase() : null;
                const callsign = ac.flight ? ac.flight.trim() : null;
                if (!icao || ac.lat == null || ac.lon == null || !callsign) return;

                currentIcaos.add(icao);
                const dist = Math.hypot(ac.lat - homeLat, ac.lon - homeLon);
                if (dist < minDistance) {{ minDistance = dist; nearestIcao = icao; }}

                const alt = (ac.alt_baro === "ground" || ac.alt_baro == null) ? 0 : ac.alt_baro;
                const spd = ac.gs || 0;
                const heading = ac.track || 0;
                const typeCode = ac.t || "N/A";

                let airlineName = "일반 / 개인 / 군용기";
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
                            const pLat = Math.asin(Math.sin(ac.lat * Math.PI / 180) * Math.cos(d) + Math.cos(ac.lat * Math.PI / 180) * Math.sin(d) * Math.cos(backRad));
                            const pLon = (ac.lon * Math.PI / 180) + Math.atan2(Math.sin(backRad) * Math.sin(d) * Math.cos(ac.lat * Math.PI / 180), Math.cos(d) - Math.sin(ac.lat * Math.PI / 180) * Math.sin(pLat));
                            flightHistory[icao].push({{ lat: pLat * 180 / Math.PI, lon: pLon * 180 / Math.PI, alt: alt, time: now - (pastSec * 1000) }});
                        }});
                    }}
                }}

                flightHistory[icao].push({{ lat: ac.lat, lon: ac.lon, alt: alt, spd: spd, heading: heading, callsign: callsign, airline: airlineName, type: typeCode, time: now }});
                flightHistory[icao] = flightHistory[icao].filter(p => now - p.time <= 900000); // 15분
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = checkStatus(hist);
                const newIcon = getTriangleIcon(heading, status.color);

                if (markers[icao]) {{
                    markers[icao].setLatLng([ac.lat, ac.lon]);
                    markers[icao].setIcon(newIcon);
                }} else {{
                    const m = L.marker([ac.lat, ac.lon], {{ icon: newIcon }}).addTo(map);
                    m.bindTooltip(`<b>${{callsign}}</b><br>${{Math.round(alt)}} ft`, {{ direction: 'top' }});
                    m.on('click', () => {{ selectedIcao = icao; updatePanel(hist[hist.length - 1], status.text, status.color, sourceNetwork); }});
                    markers[icao] = m;
                }}

                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: status.color }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{ color: status.color, weight: 3, opacity: 0.7 }}).addTo(map);
                }}
            }});

            Object.keys(markers).forEach(icao => {{
                if (!currentIcaos.has(icao)) {{
                    map.removeLayer(markers[icao]);
                    map.removeLayer(polylines[icao]);
                    delete markers[icao];
                    delete polylines[icao];
                    delete flightHistory[icao];
                    if (selectedIcao === icao) selectedIcao = null;
                }}
            }});

            if (planes.length > 0 && (!selectedIcao || !flightHistory[selectedIcao])) {{
                selectedIcao = nearestIcao;
            }}
            
            if (selectedIcao && flightHistory[selectedIcao]) {{
                const targetHist = flightHistory[selectedIcao];
                const st = checkStatus(targetHist);
                updatePanel(targetHist[targetHist.length - 1], st.text, st.color, sourceNetwork);
            }}
        }}

        function updatePanel(latest, statusText, color, net) {{
            document.getElementById('p-callsign').innerText = latest.callsign;
            document.getElementById('p-callsign').style.color = color;
            document.getElementById('p-airline').innerText = latest.airline + " (" + net + "망 수신)";
            document.getElementById('p-type').innerText = latest.type;
            document.getElementById('p-alt').innerText = `${{Math.round(latest.alt).toLocaleString()}} ft`;
            document.getElementById('p-spd').innerText = `${{Math.round(latest.spd)}} kts`;
            document.getElementById('p-status').innerText = statusText;
            document.getElementById('p-status').style.color = color;
        }}

        function relocateHomePoint(newLat, newLon) {{
            homeLat = newLat; homeLon = newLon;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {{}}; polylines = {{}}; flightHistory = {{}}; selectedIcao = null;
            
            document.getElementById('p-callsign').innerText = '스캔 중...';
            document.getElementById('p-callsign').style.color = '#e74c3c';
            document.getElementById('p-airline').innerText = '새 위치 주변을 탐색 중입니다.';
            
            fetchFlightData();
        }}

        map.on('dblclick', function(e) {{ relocateHomePoint(e.latlng.lat, e.latlng.lng); }});
        
        // 8초 주기 자동 갱신
        fetchFlightData();
        setInterval(fetchFlightData, 8000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=850, scrolling=False)
