import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import math
import csv
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

# 1. 전 세계 항공사 데이터베이스 로드
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

# 2. 파이썬 백엔드 데이터 수집 엔진 (CORS 문제 완전 배제)
def fetch_flight_data(lat, lon):
    radius_nm = 100  # 약 180km 커버리지
    lat_diff = radius_nm / 60.0
    lon_diff = radius_nm / (60.0 * math.cos(math.radians(lat)))
    
    # 1순위: Flightradar24 (인천공항 및 한반도 완벽 커버)
    url_fr24 = f"https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds={lat+lat_diff:.3f},{lat-lat_diff:.3f},{lon-lon_diff:.3f},{lon+lon_diff:.3f}&faa=1&mlat=1&flarm=1&adsb=1&gnd=1&air=1&vehicles=0&estimated=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url_fr24, headers=headers, timeout=4)
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
            if planes:
                return planes, "Flightradar24"
    except Exception:
        pass

    # 2순위: Airplanes.live (오픈망 폴백)
    url_live = f"https://api.airplanes.live/v2/point/{lat:.3f}/{lon:.3f}/{radius_nm}"
    try:
        res = requests.get(url_live, timeout=4)
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

    return [], "No Signal"

# 세션 상태 초기화
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.4600, 126.4400]  # 인천공항 기본값

# 사이드바 프리셋
with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 위를 더블클릭/더블탭하면 홈포인트가 즉시 이동합니다.")
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

h_lat, h_lon = st.session_state.home_coords[0], st.session_state.home_coords[1]

# 3. 지도 프레임 렌더링 (최초 1회만 생성, 이후 재성성하지 않음)
radar_base_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #e5e9ec; }}
        
        .top-hud {{
            position: absolute; top: 12px; left: 12px; right: 12px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: center; pointer-events: none;
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 13px; font-weight: bold; color: #2c3e50;
            pointer-events: auto; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(0,0,0,0.08);
        }}
        
        .bottom-hud {{
            position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%); z-index: 1000;
            width: 90%; max-width: 480px; background: rgba(255, 255, 255, 0.96); border-radius: 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.22); padding: 16px 20px; pointer-events: auto;
            display: flex; flex-direction: column; border: 1px solid rgba(0,0,0,0.06); backdrop-filter: blur(8px);
        }}
        .plane-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }}
        .plane-callsign {{ font-size: 24px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .plane-type {{ font-size: 12px; font-weight: bold; color: #7f8c8d; background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
        .plane-airline {{ font-size: 13px; color: #4a5568; margin-top: 4px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        
        .grid-info {{ display: flex; justify-content: space-between; text-align: center; border-top: 1px solid #edf2f7; padding-top: 10px; margin-top: 10px; }}
        .grid-item {{ display: flex; flex-direction: column; width: 33%; }}
        .grid-val {{ font-size: 17px; font-weight: 800; color: #2d3748; margin-top: 2px; }}
        .grid-lbl {{ font-size: 11px; color: #a0aec0; text-transform: uppercase; font-weight: 700; }}
        
        .icon-wrapper {{
            width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.4s linear;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="top-hud">
        <div class="hud-box" id="status-box">📡 위성 레이더 준비 중...</div>
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
        <div class="plane-airline" id="p-airline">지도 위의 기체를 터치하거나 클릭하세요.</div>
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
                <span class="grid-val" id="p-status">-</span>
            </div>
        </div>
    </div>

    <script>
        let homeLat = {h_lat};
        let homeLon = {h_lon};

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
            radius: 180000,
            color: '#2980b9',
            weight: 2,
            fillColor: '#3498db',
            fillOpacity: 0.04
        }}).addTo(map);

        let homeMarker = L.circleMarker([homeLat, homeLon], {{
            radius: 6,
            color: '#c0392b',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 3
        }}).addTo(map).bindTooltip("Home Point (Double-click to move)");

        let flightHistory = {{}};
        let markers = {{}};
        let polylines = {{}};
        let selectedIcao = null;

        function getIcon(heading, color) {{
            const html = `<div class="icon-wrapper" style="transform: rotate(${{heading}}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [24,24], iconAnchor: [12,12] }});
        }}

        function getStatus(hist) {{
            if (!hist || hist.length < 2) return {{ color: '#2ecc71', text: 'Level' }};
            const p0 = hist[Math.max(0, hist.length - 4)];
            const p1 = hist[hist.length - 1];
            const dt = (p1.time - p0.time) / 1000;
            if (dt <= 0) return {{ color: '#2ecc71', text: 'Level' }};

            const vsFpm = ((p1.alt - p0.alt) / dt) * 60;
            if (vsFpm > 150) return {{ color: '#f1c40f', text: `Climb (+${{Math.round(vsFpm)}})` }};
            if (vsFpm < -150) return {{ color: '#3498db', text: `Desc (${{Math.round(vsFpm)}})` }};
            return {{ color: '#2ecc71', text: 'Level' }};
        }}

        function updatePanel(p, statusTxt, color) {{
            document.getElementById('p-callsign').innerText = p.callsign;
            document.getElementById('p-callsign').style.color = color;
            document.getElementById('p-type').innerText = p.type || 'N/A';
            document.getElementById('p-airline').innerText = p.airline || '일반 / 개인 항공기';
            document.getElementById('p-alt').innerText = `${{Math.round(p.alt).toLocaleString()}} ft`;
            document.getElementById('p-spd').innerText = `${{Math.round(p.spd)}} kts`;
            document.getElementById('p-status').innerText = statusTxt;
            document.getElementById('p-status').style.color = color;
        }}

        // 파이썬에서 push된 데이터를 수신하여 깜빡임 없이 마커/항적선 갱신
        window.updateFlightRadar = function(payload) {{
            const planes = payload.planes || [];
            const sourceName = payload.source || '';
            const statusBox = document.getElementById('status-box');
            
            if (planes.length === 0) {{
                statusBox.innerText = `📡 0대 (트래픽 없음) [${{sourceName}}]`;
                statusBox.style.color = "#e74c3c";
                return;
            }}

            statusBox.innerText = `📡 ${{planes.length}}대 추적 중 [${{sourceName}}]`;
            statusBox.style.color = "#2ecc71";

            const now = Date.now();
            const currentIcaos = new Set();
            let nearestPlane = null;
            let minDist = 999999;

            planes.forEach(p => {{
                const icao = p.hex;
                if (!icao || p.lat == null || p.lon == null) return;
                currentIcaos.add(icao);

                const dist = Math.hypot(p.lat - homeLat, p.lon - homeLon);
                if (dist < minDist) {{
                    minDist = dist;
                    nearestPlane = p;
                }}

                // 최초 감지 시 30초 이전 가상 꼬리선 보간
                if (!flightHistory[icao]) {{
                    flightHistory[icao] = [];
                    if (p.alt > 0 && p.spd > 100) {{
                        const rad = p.track * Math.PI / 180;
                        const backRad = (rad + Math.PI) % (2 * Math.PI);
                        [30, 15].forEach(pastSec => {{
                            const distKm = (p.spd * pastSec / 3600.0) * 1.852;
                            const d = distKm / 6371.0;
                            const pLat = Math.asin(Math.sin(p.lat * Math.PI / 180) * Math.cos(d) +
                                         Math.cos(p.lat * Math.PI / 180) * Math.sin(d) * Math.cos(backRad));
                            const pLon = (p.lon * Math.PI / 180) + Math.atan2(
                                Math.sin(backRad) * Math.sin(d) * Math.cos(p.lat * Math.PI / 180),
                                Math.cos(d) - Math.sin(p.lat * Math.PI / 180) * Math.sin(pLat)
                            );
                            flightHistory[icao].push({{
                                lat: pLat * 180 / Math.PI,
                                lon: pLon * 180 / Math.PI,
                                alt: p.alt,
                                time: now - (pastSec * 1000)
                            }});
                        }});
                    }}
                }}

                flightHistory[icao].push({{
                    lat: p.lat,
                    lon: p.lon,
                    alt: p.alt,
                    spd: p.spd,
                    track: p.track,
                    time: now
                }});

                flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 900000);
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = getStatus(hist);

                // 마커 위치 및 각도만 부드럽게 갱신 (지우지 않음)
                const newIcon = getIcon(p.track, status.color);
                if (markers[icao]) {{
                    markers[icao].setLatLng([p.lat, p.lon]);
                    markers[icao].setIcon(newIcon);
                }} else {{
                    const marker = L.marker([p.lat, p.lon], {{ icon: newIcon }}).addTo(map);
                    marker.bindTooltip(`<b>${{p.callsign}}</b><br>${{Math.round(p.alt).toLocaleString()}} ft`, {{ direction: 'top' }});
                    marker.on('click', () => {{
                        selectedIcao = icao;
                        updatePanel(p, status.text, status.color);
                    }});
                    markers[icao] = marker;
                }}

                // 꼬리선 갱신
                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: status.color }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{
                        color: status.color,
                        weight: 3,
                        opacity: 0.75
                    }}).addTo(map);
                }}
            }});

            // 반경 이탈 기체 정리
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

            let focused = planes.find(p => p.hex === selectedIcao) || nearestPlane;
            if (focused) {{
                const st = getStatus(flightHistory[focused.hex]);
                updatePanel(focused, st.text, st.color);
            }}
        }};

        // 더블클릭/더블탭 홈포인트 즉시 재설정
        function relocateHome(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);
            document.getElementById('status-box').innerText = "📡 새 위치 재스캔 중...";
        }}

        map.on('dblclick', function(e) {{
            relocateHome(e.latlng.lat, e.latlng.lng);
        }});

        let lastTap = 0;
        map.on('click', function(e) {{
            const curTime = new Date().getTime();
            if (curTime - lastTap < 300 && curTime - lastTap > 0) {{
                relocateHome(e.latlng.lat, e.latlng.lng);
            }}
            lastTap = curTime;
        }});
    </script>
</body>
</html>
"""

components.html(radar_base_html, height=820, scrolling=False)

# 4. 실시간 브릿지 프래그먼트 (5초마다 파이썬이 데이터를 긁어와 브라우저 함수를 직접 호출)
@st.fragment(run_every="5s")
def sync_data_stream():
    planes, source_name = fetch_flight_data(st.session_state.home_coords[0], st.session_state.home_coords[1])
    payload = json.dumps({"planes": planes, "source": source_name})

    # 지도를 다시 그리지 않고, 이미 떠 있는 iframe 내부의 updateFlightRadar 함수만 호출
    injector_script = f"""
    <script>
        const iframes = window.parent.document.querySelectorAll('iframe');
        iframes.forEach(f => {{
            try {{
                if (f.contentWindow && f.contentWindow.updateFlightRadar) {{
                    f.contentWindow.updateFlightRadar({payload});
                }}
            }} catch(e) {{}}
        }});
    </script>
    """
    components.html(injector_script, height=0, width=0)

sync_data_stream()
