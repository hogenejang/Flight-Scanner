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

# 오버레이 플로팅 UI 및 CORS 안전 레이더 엔진
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
        
        /* 상단 플로팅 상태바 */
        .top-hud {{
            position: absolute; top: 12px; left: 12px; right: 12px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: center;
            pointer-events: none;
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 12px; font-weight: bold; color: #2c3e50;
            pointer-events: auto;
        }}
        
        /* 하단 비행기 정보 카드 (Floating Overlay) */
        .bottom-hud {{
            position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 1000;
            width: 90%; max-width: 480px; background: rgba(255, 255, 255, 0.96); border-radius: 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.22); padding: 14px 18px; pointer-events: auto;
            display: flex; flex-direction: column; border: 1px solid rgba(0,0,0,0.06);
            backdrop-filter: blur(8px);
        }}
        .plane-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }}
        .plane-callsign {{ font-size: 22px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .plane-type {{ font-size: 12px; font-weight: bold; color: #7f8c8d; background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
        .plane-airline {{ font-size: 13px; color: #4a5568; margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }}
        
        .grid-info {{ display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #edf2f7; padding-top: 8px; }}
        .grid-item {{ display: flex; flex-direction: column; width: 33%; }}
        .grid-val {{ font-size: 17px; font-weight: 800; color: #2d3748; }}
        .grid-lbl {{ font-size: 10px; color: #a0aec0; text-transform: uppercase; font-weight: 700; margin-bottom: 2px; }}
        
        .icon-wrapper {{
            width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 3px rgba(0,0,0,0.5)); transition: transform 0.4s linear;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="top-hud">
        <div class="hud-box" id="status-box">📡 신호 수신 대기 중...</div>
        <div class="hud-box" style="display: flex; gap: 8px;">
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
        <div class="plane-airline" id="p-airline">반경 100km 이내 기체를 스캔하고 있습니다.</div>
        
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
                <span class="grid-lbl">Vertical</span>
                <span class="grid-val" id="p-status" style="font-size:15px;">-</span>
            </div>
        </div>
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
        L.control.zoom({{ position: 'bottomright' }}).addTo(map);

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

        // CORS 완전 지원 엔드포인트 및 다중 폴백
        async function fetchFlightData() {{
            const radiusNm = 54; // 100km
            const lat = homeLat.toFixed(4);
            const lon = homeLon.toFixed(4);
            
            const urls = [
                `https://api.airplanes.live/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`,
                `https://opendata.adsb.fi/api/v2/lat/${{lat}}/lon/${{lon}}/dist/${{radiusNm}}`,
                `https://corsproxy.io/?url=` + encodeURIComponent(`https://api.airplanes.live/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`),
                `https://api.allorigins.win/raw?url=` + encodeURIComponent(`https://api.airplanes.live/v2/point/${{lat}}/${{lon}}/${{radiusNm}}`)
            ];

            let data = null;
            for (let targetUrl of urls) {{
                try {{
                    const res = await fetch(targetUrl);
                    if (res.ok) {{
                        const json = await res.json();
                        if (json && json.ac !== undefined) {{
                            data = json;
                            break;
                        }}
                    }}
                }} catch (e) {{
                    // 다음 URL 시도
                }}
            }}

            if (!data || !data.ac) {{
                document.getElementById('status-box').innerText = "❌ 데이터 연결 실패 (재시도 중)";
                document.getElementById('status-box').style.color = "#e74c3c";
                return;
            }}

            const planes = data.ac;
            document.getElementById('status-box').innerText = `📡 탐지된 기체: ${{planes.length}}대`;
            document.getElementById('status-box').style.color = planes.length > 0 ? "#2ecc71" : "#7f8c8d";

            if (planes.length === 0) {{
                document.getElementById('p-callsign').innerText = "기체 없음";
                document.getElementById('p-airline').innerText = "반경 100km 내 비행 중인 항공기가 없습니다.";
                document.getElementById('p-type').innerText = "-";
                document.getElementById('p-alt').innerText = "-";
                document.getElementById('p-spd').innerText = "-";
                document.getElementById('p-status').innerText = "-";
                return;
            }}

            const now = Date.now();
            const currentIcaos = new Set();
            let nearestIcao = null;
            let minDistance = 999999;

            planes.forEach(ac => {{
                const icao = ac.hex ? ac.hex.trim().toUpperCase() : null;
                const callsign = ac.flight ? ac.flight.trim() : null;
                if (!icao || ac.lat == null || ac.lon == null || !callsign) return;

                currentIcaos.add(icao);
                
                // 중심점과의 거리 계산
                const dist = Math.hypot(ac.lat - homeLat, ac.lon - homeLon);
                if (dist < minDistance) {{
                    minDistance = dist;
                    nearestIcao = icao;
                }}

                const alt = (ac.alt_baro === "ground" || ac.alt_baro == null) ? 0 : ac.alt_baro;
                const spd = ac.gs || 0;
                const heading = ac.track || 0;
                const typeCode = ac.t || "Unknown";

                let airlineName = "일반 / 개인 항공기";
                if (callsign.length >= 3) {{
                    const prefix = callsign.substring(0, 3).toUpperCase();
                    if (airlinesDB[prefix]) airlineName = airlinesDB[prefix];
                }}

                if (!flightHistory[icao]) {{
                    flightHistory[icao] = [];
                    // 30초 이전 과거 항적 보간
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
                    heading: heading, callsign: callsign, airline: airlineName, type: typeCode, time: now
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
            }});

            // 범위 이탈 기체 제거
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

            // 선택된 기체가 없으면 가장 가까운 비행기 자동 선택
            if (!selectedIcao || !flightHistory[selectedIcao]) {{
                selectedIcao = nearestIcao;
            }}

            if (selectedIcao && flightHistory[selectedIcao]) {{
                const targetHist = flightHistory[selectedIcao];
                const st = checkStatus(targetHist);
                updatePanel(targetHist[targetHist.length - 1], st.text, st.color);
            }}
        }}

        function updatePanel(latest, statusText, color) {{
            document.getElementById('p-callsign').innerText = latest.callsign;
            document.getElementById('p-callsign').style.color = color;
            document.getElementById('p-airline').innerText = latest.airline;
            document.getElementById('p-type').innerText = latest.type;
            document.getElementById('p-alt').innerText = `${{latest.alt.toLocaleString()}} ft`;
            document.getElementById('p-spd').innerText = `${{Math.round(latest.spd)}} kts`;
            document.getElementById('p-status').innerText = statusText;
            document.getElementById('p-status').style.color = color;
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
            
            document.getElementById('p-callsign').innerText = '스캔 중...';
            document.getElementById('p-airline').innerText = '새 위치 주변을 탐색 중입니다.';
            
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

        // 5초 주기 실시간 데이터 갱신
        fetchFlightData();
        setInterval(fetchFlightData, 5000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=850, scrolling=False)
