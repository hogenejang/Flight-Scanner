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
    initial_sidebar_state="collapsed"
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

# 세션 상태 초기화
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.5665, 126.9780] 

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 아무 곳이나 더블클릭(더블탭)하면 스캔 위치가 즉시 이동합니다.")
    
    st.markdown("### 🧪 Coverage Test")
    st.write("해당 지역에 비행기가 없는지 확인하려면 아래 테스트 버튼을 눌러보세요.")
    
    if st.button("🗼 테스트: 도쿄 하네다 공항", use_container_width=True):
        st.session_state.home_coords = [35.5494, 139.7798]
        st.rerun()
        
    if st.button("🗽 테스트: 뉴욕 JFK 공항", use_container_width=True):
        st.session_state.home_coords = [40.6413, -73.7781]
        st.rerun()
        
    if st.button("🏠 내 위치로 복귀 (서울)", use_container_width=True):
        st.session_state.home_coords = [37.5665, 126.9780]
        st.rerun()

init_lat = st.session_state.home_coords[0]
init_lon = st.session_state.home_coords[1]

# 오버레이(Floating) UI가 적용된 무깜빡임 HTML 레이더
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
        
        /* 지도 전체 화면 채우기 */
        #map {{ position: absolute; top: 0; left: 0; height: 100%; width: 100%; z-index: 1; background: #e5e9ec; }}
        
        /* 상단 상태바 오버레이 */
        .top-hud {{
            position: absolute; top: 10px; left: 10px; right: 10px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: flex-start;
            pointer-events: none; /* 클릭 통과 */
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 8px 12px; border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 13px; font-weight: bold; color: #2c3e50;
            pointer-events: auto;
        }}
        
        /* 하단 비행기 정보 패널 오버레이 (무조건 보이도록 플로팅 처리) */
        .bottom-hud {{
            position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 1000;
            width: 92%; max-width: 500px; background: white; border-radius: 15px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.25); padding: 18px; pointer-events: auto;
            display: flex; flex-direction: column;
        }}
        .plane-title {{ font-size: 24px; font-weight: 900; color: #e74c3c; margin: 0; line-height: 1; }}
        .plane-subtitle {{ font-size: 13px; color: #7f8c8d; margin-top: 5px; margin-bottom: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        
        .grid-info {{ display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #f1f2f6; padding-top: 12px; }}
        .grid-item {{ display: flex; flex-direction: column; width: 33%; }}
        .grid-val {{ font-size: 18px; font-weight: bold; color: #2c3e50; }}
        .grid-lbl {{ font-size: 11px; color: #95a5a6; text-transform: uppercase; font-weight: bold; margin-bottom: 2px; }}
        
        .icon-wrapper {{
            width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 3px 3px rgba(0,0,0,0.5)); transition: transform 0.4s linear;
        }}
    </style>
</head>
<body>
    <!-- 배경 지도 -->
    <div id="map"></div>

    <!-- 상단 플로팅 UI -->
    <div class="top-hud">
        <div class="hud-box" id="status-box">
            📡 연결 중...
        </div>
        <div class="hud-box" style="display: flex; gap: 8px;">
            <span style="color:#2ecc71;">● 수평</span>
            <span style="color:#f1c40f;">● 상승</span>
            <span style="color:#3498db;">● 하강</span>
        </div>
    </div>

    <!-- 하단 비행기 정보 플로팅 패널 -->
    <div class="bottom-hud">
        <div class="plane-title" id="p-callsign">지도를 클릭하세요</div>
        <div class="plane-subtitle" id="p-airline">추적할 비행기 마커를 선택해주세요. (더블클릭 시 중심 이동)</div>
        
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
                <span class="grid-val" id="p-status" style="font-size:15px;">-</span>
            </div>
        </div>
    </div>

    <script>
        // 전 세계 항공사 DB 파싱
        const airlinesDB = {airlines_json_str};
        
        let homeLat = {init_lat};
        let homeLon = {init_lon};

        // 지도 생성 (더블클릭 줌 해제)
        const map = L.map('map', {{
            center: [homeLat, homeLon],
            zoom: 9,
            zoomControl: false,
            doubleClickZoom: false
        }});
        L.control.zoom({{ position: 'bottomright' }}).addTo(map); // 줌 버튼 우측 하단으로 이동

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
        }}).addTo(map).bindTooltip("Home Point (100km)");

        let flightHistory = {{}};
        let markers = {{}};
        let polylines = {{}};
        let selectedIcao = null;

        function getTriangleIcon(heading, color) {{
            const deg = heading || 0;
            const html = `
            <div class="icon-wrapper" style="transform: rotate(${{deg}}deg);">
                <svg width="22" height="22" viewBox="0 0 20 20">
                    <polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" />
                </svg>
            </div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [22, 22], iconAnchor: [11, 11] }});
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

        // 실시간 비동기 데이터 갱신
        async function fetchFlightData() {{
            const radiusNm = 54;
            const lat = homeLat.toFixed(4);
            const lon = homeLon.toFixed(4);
            const url = `https://api.adsb.lol/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`;

            let data = null;
            try {{
                const res = await fetch(url);
                if (res.ok) {{ data = await res.json(); }}
            }} catch (e) {{
                document.getElementById('status-box').innerText = "❌ 데이터 연결 실패";
                document.getElementById('status-box').style.color = "#e74c3c";
                return;
            }}

            if (!data || !data.ac) {{
                document.getElementById('status-box').innerText = "📡 탐지된 비행기: 0대";
                return;
            }}

            const planes = data.ac;
            document.getElementById('status-box').innerText = `📡 탐지된 비행기: ${{planes.length}}대`;
            document.getElementById('status-box').style.color = planes.length > 0 ? "#2ecc71" : "#7f8c8d";

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

                let airlineName = "Unknown / General Aviation";
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
                    m.bindTooltip(`${{callsign}}`, {{ direction: 'top' }});
                    m.on('click', () => {{
                        selectedIcao = icao;
                        updatePanel(hist[hist.length - 1], status.text, status.color);
                    }});
                    markers[icao] = m;
                }}

                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: status.color }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{ color: status.color, weight: 3, opacity: 0.7 }}).addTo(map);
                }}

                if (selectedIcao === icao) {{
                    updatePanel(hist[hist.length - 1], status.text, status.color);
                }}
            }});

            // 화면에서 사라진 기체 지우기
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

        // 하단 패널 업데이트 함수
        function updatePanel(latest, statusText, color) {{
            document.getElementById('p-callsign').innerText = latest.callsign;
            document.getElementById('p-callsign').style.color = color;
            document.getElementById('p-airline').innerText = latest.airline;
            document.getElementById('p-alt').innerText = `${{latest.alt.toLocaleString()}} ft`;
            document.getElementById('p-spd').innerText = `${{Math.round(latest.spd)}} kts`;
            document.getElementById('p-status').innerText = statusText;
            document.getElementById('p-status').style.color = color;
        }}

        // 홈포인트 더블클릭 변경 로직
        function relocateHomePoint(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {{}}; polylines = {{}}; flightHistory = {{}}; selectedIcao = null;
            
            document.getElementById('p-callsign').innerText = '지도를 클릭하세요';
            document.getElementById('p-callsign').style.color = '#e74c3c';
            document.getElementById('p-airline').innerText = '새로운 지역을 스캔 중입니다...';
            document.getElementById('p-alt').innerText = '-';
            document.getElementById('p-spd').innerText = '-';
            document.getElementById('p-status').innerText = '-';
            
            fetchFlightData();
        }}

        map.on('dblclick', function(e) {{ relocateHomePoint(e.latlng.lat, e.latlng.lng); }});
        
        // 모바일 더블탭 지원
        let lastTouchTime = 0;
        map.on('click', function(e) {{
            const currentTime = new Date().getTime();
            if (currentTime - lastTouchTime < 300 && currentTime - lastTouchTime > 0) {{
                relocateHomePoint(e.latlng.lat, e.latlng.lng);
            }}
            lastTouchTime = currentTime;
        }});

        // 프로그램 시작 및 5초 주기 반복
        fetchFlightData();
        setInterval(fetchFlightData, 5000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=850, scrolling=False)
