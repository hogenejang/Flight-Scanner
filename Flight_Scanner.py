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

# 모바일 및 전체 화면 최적화
st.markdown("""
<style>
    .block-container { padding: 0 !important; max-width: 100% !important; overflow: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    iframe { border: none !important; width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# 1. 항공사 데이터베이스 (국내 및 주요 국제선 사전 탑재 + OpenFlights 자동 병합)
DEFAULT_AIRLINES = {
    "KAL": "대한항공 (Korean Air)",
    "AAR": "아시아나항공 (Asiana Airlines)",
    "JJA": "제주항공 (Jeju Air)",
    "JNA": "진에어 (Jin Air)",
    "TWB": "티웨이항공 (T'way Air)",
    "ASV": "에어서울 (Air Seoul)",
    "ABL": "에어부산 (Air Busan)",
    "ESR": "이스타항공 (Eastar Jet)",
    "FGW": "플라이강원 (Fly Gangwon)",
    "APJ": "피치항공 (Peach Aviation)",
    "ANA": "전일본공수 (All Nippon Airways)",
    "JAL": "일본항공 (Japan Airlines)",
    "CPA": "캐세이퍼시픽 (Cathay Pacific)",
    "CAL": "중화항공 (China Airlines)",
    "EVA": "에바항공 (EVA Air)",
    "CCA": "중국국제항공 (Air China)",
    "CES": "중국동방항공 (China Eastern)",
    "CSN": "중국남방항공 (China Southern)",
    "SIA": "싱가포르항공 (Singapore Airlines)",
    "THA": "타이항공 (Thai Airways)",
    "MAS": "말레이시아항공 (Malaysia Airlines)",
    "HVN": "베트남항공 (Vietnam Airlines)",
    "VJC": "비엣젯항공 (VietJet Air)",
    "PAL": "필리핀항공 (Philippine Airlines)",
    "CEB": "세부퍼시픽 (Cebu Pacific)",
    "UAE": "에미레이트항공 (Emirates)",
    "QTR": "카타르항공 (Qatar Airways)",
    "ETD": "에티하드항공 (Etihad Airways)",
    "DLH": "루프트한자 (Lufthansa)",
    "AFR": "에어프랑스 (Air France)",
    "KLM": "KLM 네덜란드항공 (KLM)",
    "BAW": "영국항공 (British Airways)",
    "UAL": "유나이티드항공 (United Airlines)",
    "DAL": "델타항공 (Delta Air Lines)",
    "AAL": "아메리칸항공 (American Airlines)",
    "FDX": "페덱스 익스프레스 (FedEx)",
    "UPS": "UPS 항공 (UPS Airlines)",
    "GTI": "아틀라스항공 (Atlas Air)",
    "PAC": "폴라에어카고 (Polar Air Cargo)"
}

AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
@st.cache_data(ttl=86400)
def load_airlines():
    db = dict(DEFAULT_AIRLINES)
    try:
        res = requests.get(AIRLINES_DATA_URL, timeout=4)
        if res.status_code == 200:
            reader = csv.reader(res.text.strip().splitlines())
            for row in reader:
                if len(row) >= 7:
                    icao = row[4].strip().upper()
                    name = row[1].strip()
                    if len(icao) == 3 and icao != "\\N" and icao not in db:
                        db[icao] = name
    except Exception:
        pass
    return db

airlines_db = load_airlines()

def resolve_airline_name(callsign):
    if not callsign or len(callsign) < 3:
        return ""
    code = callsign[:3].upper()
    return airlines_db.get(code, "")

# 2. 파이썬 백엔드 실시간 데이터 수집 (CORS 원천 배제)
def fetch_flight_data(lat, lon):
    radius_nm = 54  # 커버리지
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
                callsign = (v[13] or v[16] or v[0] or "").strip()
                planes.append({
                    "hex": str(v[0]).upper(),
                    "lat": v[1],
                    "lon": v[2],
                    "track": v[3] or 0,
                    "alt": v[4] or 0,
                    "spd": v[5] or 0,
                    "type": v[8] or "N/A",
                    "callsign": callsign,
                    "airline": resolve_airline_name(callsign)
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
                callsign = v.get("flight", "").strip()
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
                    "airline": resolve_airline_name(callsign)
                })
            return planes, "Airplanes.live"
    except Exception:
        pass

    return [], "No Signal"

# 세션 상태 초기화
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.4600, 126.4400]  # 인천국제공항 기본값

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

# 3. 지도 프레임 렌더링
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
        
        .icon-wrapper {{
            width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.4s linear;
        }}

        /* 비행기 옆에 고정 부착되는 상세 정보 카드 */
        .plane-hud-card {{
            background: rgba(255, 255, 255, 0.97) !important;
            border: 1px solid rgba(0,0,0,0.12) !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 24px rgba(0,0,0,0.22) !important;
            padding: 10px 14px !important;
            color: #2c3e50 !important;
            min-width: 180px !important;
            backdrop-filter: blur(8px) !important;
            pointer-events: auto !important;
        }}
        .plane-hud-card:before {{
            border-right-color: rgba(255, 255, 255, 0.97) !important;
        }}
        .card-header {{
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid #edf2f7; padding-bottom: 5px; margin-bottom: 6px; gap: 8px;
        }}
        .card-callsign {{ font-size: 18px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .card-type {{ font-size: 10px; font-weight: bold; background: #edf2f7; padding: 2px 6px; border-radius: 4px; color: #4a5568; }}
        .card-airline {{ 
            font-size: 13px; font-weight: 700; color: #1a365d; margin-bottom: 8px; 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 190px; 
        }}
        .card-metrics {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 11px;
        }}
        .card-metrics div {{ display: flex; flex-direction: column; }}
        .card-label {{ font-size: 9px; color: #a0aec0; text-transform: uppercase; font-weight: 700; margin-bottom: 1px; }}
        .card-value {{ font-size: 13px; font-weight: 800; color: #2d3748; }}
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

        // 항공기 옆에 부착되는 카드 템플릿 (항공사 이름 확실하게 표시)
        function makeHudContent(p, statusTxt, color) {{
            const airlineHtml = p.airline ? `<div class="card-airline">${{p.airline}}</div>` : '';
            return `
            <div class="card-header">
                <span class="card-callsign">${{p.callsign || p.hex}}</span>
                <span class="card-type">${{p.type || 'N/A'}}</span>
            </div>
            ${{airlineHtml}}
            <div class="card-metrics">
                <div>
                    <span class="card-label">Altitude</span>
                    <span class="card-value">${{Math.round(p.alt).toLocaleString()}} ft</span>
                </div>
                <div>
                    <span class="card-label">Speed</span>
                    <span class="card-value">${{Math.round(p.spd)}} kts</span>
                </div>
                <div style="grid-column: span 2; margin-top: 3px;">
                    <span class="card-label">Status</span>
                    <span class="card-value" style="color: ${{color}};">${{statusTxt}}</span>
                </div>
            </div>
            `;
        }}

        // 지도 빈 공간 클릭 시 카드 닫기
        map.on('click', function() {{
            if (selectedIcao && markers[selectedIcao]) {{
                markers[selectedIcao].unbindTooltip();
                const hist = flightHistory[selectedIcao];
                const latest = hist ? hist[hist.length - 1] : null;
                if (latest) {{
                    markers[selectedIcao].bindTooltip(`<b>${{latest.callsign}}</b><br>${{Math.round(latest.alt).toLocaleString()}} ft`, {{ direction: 'top' }});
                }}
            }}
            selectedIcao = null;
        }});

        // 실시간 데이터 수신 및 마커 추종
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

            planes.forEach(p => {{
                const icao = p.hex;
                if (!icao || p.lat == null || p.lon == null) return;
                currentIcaos.add(icao);

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
                                Math.sin(backRad) * Math.sin(d) * Math.cos(acLat = p.lat * Math.PI / 180),
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
                    callsign: p.callsign,
                    airline: p.airline,
                    type: p.type,
                    time: now
                }});

                flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 900000);
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = getStatus(hist);
                const isSelected = (selectedIcao === icao);

                const newIcon = getIcon(p.track, status.color);
                if (markers[icao]) {{
                    markers[icao].setLatLng([p.lat, p.lon]);
                    markers[icao].setIcon(newIcon);
                }} else {{
                    const marker = L.marker([p.lat, p.lon], {{ icon: newIcon }}).addTo(map);
                    
                    marker.on('click', L.DomEvent.stopPropagation);
                    marker.on('click', () => {{
                        if (selectedIcao && markers[selectedIcao] && selectedIcao !== icao) {{
                            markers[selectedIcao].unbindTooltip();
                            const prevHist = flightHistory[selectedIcao];
                            const prevP = prevHist ? prevHist[prevHist.length - 1] : null;
                            if (prevP) {{
                                markers[selectedIcao].bindTooltip(`<b>${{prevP.callsign}}</b><br>${{Math.round(prevP.alt).toLocaleString()}} ft`, {{ direction: 'top' }});
                            }}
                        }}

                        selectedIcao = icao;
                        marker.unbindTooltip();
                        marker.bindTooltip(makeHudContent(p, status.text, status.color), {{
                            permanent: true,
                            direction: 'right',
                            offset: [15, -15],
                            className: 'plane-hud-card'
                        }}).openTooltip();
                    }});
                    
                    markers[icao] = marker;
                }}

                // 선택된 상태인 경우 마커 위치를 따라 카드 갱신
                if (isSelected) {{
                    markers[icao].unbindTooltip();
                    markers[icao].bindTooltip(makeHudContent(p, status.text, status.color), {{
                        permanent: true,
                        direction: 'right',
                        offset: [15, -15],
                        className: 'plane-hud-card'
                    }}).openTooltip();
                }} else if (!markers[icao].getTooltip()) {{
                    markers[icao].bindTooltip(`<b>${{p.callsign}}</b><br>${{Math.round(p.alt).toLocaleString()}} ft`, {{ direction: 'top' }});
                }}

                // 꼬리선 갱신
                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: status.color, weight: isSelected ? 4 : 3 }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{
                        color: status.color,
                        weight: isSelected ? 4 : 3,
                        opacity: isSelected ? 0.9 : 0.75
                    }}).addTo(map);
                }}
            }});

            // 화면 이탈 기체 제거
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
        }};

        // 더블클릭/더블탭 시 홈포인트 이동
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

components.html(radar_base_html, height=850, scrolling=False)

# 4. 실시간 브릿지 프래그먼트 (5초 주기 파이썬 백엔드 Fetch & 인라인 주입)
@st.fragment(run_every="5s")
def sync_data_stream():
    planes, source_name = fetch_flight_data(st.session_state.home_coords[0], st.session_state.home_coords[1])
    payload = json.dumps({"planes": planes, "source": source_name})

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
