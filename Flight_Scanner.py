import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import math
import csv
import re

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

# 1. 항공사 데이터베이스 (IATA/ICAO 듀얼 매핑)
DEFAULT_AIRLINES = {
    "KE": "대한항공 (Korean Air)", "KAL": "대한항공 (Korean Air)",
    "OZ": "아시아나항공 (Asiana Airlines)", "AAR": "아시아나항공 (Asiana Airlines)",
    "7C": "제주항공 (Jeju Air)", "JJA": "제주항공 (Jeju Air)",
    "LJ": "진에어 (Jin Air)", "JNA": "진에어 (Jin Air)",
    "TW": "티웨이항공 (T'way Air)", "TWB": "티웨이항공 (T'way Air)",
    "RS": "에어서울 (Air Seoul)", "ASV": "에어서울 (Air Seoul)",
    "BX": "에어부산 (Air Busan)", "ABL": "에어부산 (Air Busan)",
    "ZE": "이스타항공 (Eastar Jet)", "ESR": "이스타항공 (Eastar Jet)",
    "YP": "에어프레미아 (Air Premia)", "APZ": "에어프레미아 (Air Premia)",
    "MM": "피치항공 (Peach Aviation)", "APJ": "피치항공 (Peach Aviation)",
    "NH": "전일본공수 (ANA)", "ANA": "전일본공수 (ANA)",
    "JL": "일본항공 (JAL)", "JAL": "일본항공 (JAL)",
    "CX": "캐세이퍼시픽 (Cathay Pacific)", "CPA": "캐세이퍼시픽 (Cathay Pacific)",
    "CI": "중화항공 (China Airlines)", "CAL": "중화항공 (China Airlines)",
    "BR": "에바항공 (EVA Air)", "EVA": "에바항공 (EVA Air)",
    "CA": "중국국제항공 (Air China)", "CCA": "중국국제항공 (Air China)",
    "MU": "중국동방항공 (China Eastern)", "CES": "중국동방항공 (China Eastern)",
    "CZ": "중국남방항공 (China Southern)", "CSN": "중국남방항공 (China Southern)",
    "SQ": "싱가포르항공 (Singapore Airlines)", "SIA": "싱가포르항공 (Singapore Airlines)",
    "TG": "타이항공 (Thai Airways)", "THA": "타이항공 (Thai Airways)",
    "VN": "베트남항공 (Vietnam Airlines)", "HVN": "베트남항공 (Vietnam Airlines)",
    "VJ": "비엣젯항공 (VietJet Air)", "VJC": "비엣젯항공 (VietJet Air)",
    "EK": "에미레이트항공 (Emirates)", "UAE": "에미레이트항공 (Emirates)",
    "QR": "카타르항공 (Qatar Airways)", "QTR": "카타르항공 (Qatar Airways)",
    "LH": "루프트한자 (Lufthansa)", "DLH": "루프트한자 (Lufthansa)",
    "AF": "에어프랑스 (Air France)", "AFR": "에어프랑스 (Air France)",
    "BA": "영국항공 (British Airways)", "BAW": "영국항공 (British Airways)",
    "UA": "유나이티드항공 (United Airlines)", "UAL": "유나이티드항공 (United Airlines)",
    "DL": "델타항공 (Delta Air Lines)", "DAL": "델타항공 (Delta Air Lines)",
    "AA": "아메리칸항공 (American Airlines)", "AAL": "아메리칸항공 (American Airlines)",
    "FX": "페덱스 익스프레스 (FedEx)", "FDX": "페덱스 익스프레스 (FedEx)",
    "5X": "UPS 항공 (UPS Airlines)", "UPS": "UPS 항공 (UPS Airlines)"
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
                    name = row[1].strip()
                    iata = row[3].strip().upper()
                    icao = row[4].strip().upper()
                    if len(icao) == 3 and icao != "\\N" and icao not in db:
                        db[icao] = name
                    if len(iata) == 2 and iata != "\\N" and iata not in db:
                        db[iata] = name
    except Exception:
        pass
    return db

airlines_db = load_airlines()

def resolve_airline_name(callsign):
    if not callsign or len(callsign) < 2:
        return ""
    clean_cs = callsign.strip().upper()
    if len(clean_cs) >= 3 and clean_cs[:3] in airlines_db:
        return airlines_db[clean_cs[:3]]
    if clean_cs[:2] in airlines_db:
        return airlines_db[clean_cs[:2]]
    match = re.match(r"^([A-Z0-9]{2,3})\d+", clean_cs)
    if match and match.group(1) in airlines_db:
        return airlines_db[match.group(1)]
    return ""

# 2. 백엔드 데이터 수집
def fetch_flight_data(lat, lon):
    radius_nm = 54
    lat_diff = radius_nm / 60.0
    lon_diff = radius_nm / (60.0 * math.cos(math.radians(lat)))
    
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
                vspeed = v[15] if len(v) > 15 and v[15] is not None else None
                planes.append({
                    "hex": str(v[0]).upper(),
                    "lat": v[1],
                    "lon": v[2],
                    "track": v[3] or 0,
                    "alt": v[4] or 0,
                    "spd": v[5] or 0,
                    "vspeed": vspeed,
                    "type": v[8] or "N/A",
                    "callsign": callsign,
                    "airline": resolve_airline_name(callsign)
                })
            if planes:
                return planes, "Flightradar24"
    except Exception:
        pass

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
                vspeed = v.get("baro_rate") if v.get("baro_rate") is not None else v.get("geom_rate")
                planes.append({
                    "hex": v.get("hex", "").upper(),
                    "lat": v.get("lat"),
                    "lon": v.get("lon"),
                    "track": v.get("track", 0),
                    "alt": alt,
                    "spd": v.get("gs", 0),
                    "vspeed": vspeed,
                    "type": v.get("t", "N/A"),
                    "callsign": callsign,
                    "airline": resolve_airline_name(callsign)
                })
            return planes, "Airplanes.live"
    except Exception:
        pass

    return [], "No Signal"

# 3. 홈포인트 설정
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.151575, 126.743044]

qp = st.query_params
if "lat" in qp and "lon" in qp:
    try:
        new_lat = float(qp["lat"])
        new_lon = float(qp["lon"])
        if (new_lat != st.session_state.home_coords[0] or 
            new_lon != st.session_state.home_coords[1]):
            st.session_state.home_coords = [new_lat, new_lon]
            st.query_params.clear()
    except Exception:
        pass

with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("지도 위를 더블클릭/더블탭하면 홈포인트가 즉시 이동하고 100km 재스캔됩니다.")
    st.markdown("### 📍 Location Presets")
    if st.button("🏠 기본 홈포인트 복귀", use_container_width=True):
        st.session_state.home_coords = [37.151575, 126.743044]
        st.rerun()
    if st.button("🇰🇷 인천 국제공항 (RKSI)", use_container_width=True):
        st.session_state.home_coords = [37.4600, 126.4400]
        st.rerun()
    if st.button("🇰🇷 김포 국제공항 (RKSS)", use_container_width=True):
        st.session_state.home_coords = [37.5583, 126.7906]
        st.rerun()
    if st.button("🌴 제주 국제공항 (RKPC)", use_container_width=True):
        st.session_state.home_coords = [33.5113, 126.4930]
        st.rerun()

h_lat, h_lon = st.session_state.home_coords[0], st.session_state.home_coords[1]

# 4. 지도 프레임 렌더링
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

        .plane-hud-card {{
            background: rgba(255, 255, 255, 0.97) !important;
            border: 1px solid rgba(0,0,0,0.12) !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 24px rgba(0,0,0,0.22) !important;
            padding: 10px 14px !important;
            color: #2c3e50 !important;
            min-width: 200px !important;
            backdrop-filter: blur(8px) !important;
            pointer-events: auto !important;
        }}
        .plane-hud-card:before {{ border-right-color: rgba(255, 255, 255, 0.97) !important; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #edf2f7; padding-bottom: 5px; margin-bottom: 6px; gap: 8px; }}
        .card-callsign {{ font-size: 18px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .card-type {{ font-size: 10px; font-weight: bold; background: #edf2f7; padding: 2px 6px; border-radius: 4px; color: #4a5568; }}
        .card-airline {{ font-size: 13px; font-weight: 800; color: #1a365d; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 210px; }}
        .card-metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; font-size: 11px; }}
        .card-metrics div {{ display: flex; flex-direction: column; }}
        .card-label {{ font-size: 9px; color: #a0aec0; text-transform: uppercase; font-weight: 700; margin-bottom: 1px; }}
        .card-value {{ font-size: 13px; font-weight: 800; color: #2d3748; white-space: nowrap; }}

        /* 심플 Fix 스타일 */
        .fix-dot {{
            width: 5px; height: 5px; background: #718096; border-radius: 50%;
            border: 1px solid #ffffff; box-shadow: 0 0 2px rgba(0,0,0,0.5);
        }}
        .fix-dot-iaf {{ background: #3182ce; }}
        .fix-dot-faf {{ background: #e53e3e; }}
        .fix-dot-airway {{ background: #4a5568; width: 4px; height: 4px; }}
        
        .fix-text-tag {{
            font-size: 9px !important; font-weight: 700 !important; color: #4a5568 !important;
            text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff;
            white-space: nowrap; pointer-events: none; opacity: 0.85;
        }}

        /* 절제된 항로 라벨 스타일 */
        .airway-label {{
            font-size: 9px !important; font-weight: 800 !important;
            letter-spacing: 0.5px; opacity: 0.85;
            padding: 2px 6px !important; border-radius: 4px !important;
            pointer-events: none !important;
        }}
        .airway-label-south {{
            color: #2b6cb0 !important; background: rgba(235, 248, 255, 0.85) !important;
            border: 1px solid #90cdf4 !important;
        }}
        .airway-label-north {{
            color: #234e52 !important; background: rgba(230, 255, 250, 0.85) !important;
            border: 1px solid #81e6d9 !important;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="top-hud">
        <div class="hud-box" id="status-box">📡 100km 레이더 가동 중...</div>
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
            radius: 100000,
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
        }}).addTo(map).bindTooltip("Home Point (100km)");

        // -------------------------------------------------------------
        // 실측 Fix 기반 서울-제주 복선 항로 (Y711 남행 / Y722 북행)
        // -------------------------------------------------------------
        const airwayLayer = L.layerGroup().addTo(map);

        // 1. Y711 (남행: SEL -> OSN -> BURIM -> TJN -> GEOJE -> GOMHO -> JUGRY -> SOSDO)
        const y711Fixes = [
            {{ name: "SEL", pos: [37.4306, 126.9389], desc: "안양 VOR (Y711 출발)" }},
            {{ name: "OSN", pos: [37.0950, 127.0300], desc: "오산 VOR" }},
            {{ name: "BURIM", pos: [36.7833, 127.1833], desc: "Y711 경유 Fix" }},
            {{ name: "TJN", pos: [36.3783, 127.3917], desc: "대전 VOR" }},
            {{ name: "GEOJE", pos: [35.8833, 127.4333], desc: "Y711 경유 Fix" }},
            {{ name: "GOMHO", pos: [35.4333, 127.4667], desc: "Y711 경유 Fix (남원)" }},
            {{ name: "JUGRY", pos: [34.5833, 126.1500], desc: "Y711 남행 강하 개시점" }},
            {{ name: "SOSDO", pos: [33.8000, 126.6333], desc: "Y711 종착 / 제주 북부 IAF" }}
        ];

        const pathY711 = y711Fixes.map(f => f.pos);
        L.polyline(pathY711, {{
            color: '#3182ce',
            weight: 2,
            dashArray: '6, 6',
            opacity: 0.6
        }}).addTo(airwayLayer);

        L.marker([36.1000, 127.4150], {{
            icon: L.divIcon({{
                className: 'airway-label airway-label-south',
                html: 'Y711 (F711) ↓ Southbound',
                iconSize: [130, 18],
                iconAnchor: [65, 9]
            }}),
            interactive: false
        }}).addTo(airwayLayer);

        // 2. Y722 (북행: TAMNA -> MAKSO -> DOVRO -> KAE -> GUKDO -> BOPTA -> MALPA -> SOTSU -> SEL)
        const y722Fixes = [
            {{ name: "TAMNA", pos: [33.6833, 126.3500], desc: "제주 북서 출발 시발점" }},
            {{ name: "MAKSO", pos: [34.3333, 126.2500], desc: "Y722 북상 Fix" }},
            {{ name: "DOVRO", pos: [35.3167, 126.1833], desc: "Y722 서해안 Fix" }},
            {{ name: "KAE", pos: [36.2167, 126.3833], desc: "서산 외해 Fix" }},
            {{ name: "GUKDO", pos: [36.9833, 126.6500], desc: "태안반도 진입 Fix" }},
            {{ name: "BOPTA", pos: [37.0733, 126.2417], desc: "수도권 남서 분기/합류" }},
            {{ name: "MALPA", pos: [37.2167, 126.7833], desc: "화성 상공 Fix" }},
            {{ name: "SOTSU", pos: [37.3000, 126.9000], desc: "안양 남단 Fix" }},
            {{ name: "SEL", pos: [37.4306, 126.9389], desc: "안양 VOR (수도권 종착)" }}
        ];

        const pathY722 = y722Fixes.map(f => f.pos);
        L.polyline(pathY722, {{
            color: '#285e61',
            weight: 2,
            dashArray: '6, 6',
            opacity: 0.6
        }}).addTo(airwayLayer);

        L.marker([35.6500, 126.2100], {{
            icon: L.divIcon({{
                className: 'airway-label airway-label-north',
                html: 'Y722 (F722) ↑ Northbound',
                iconSize: [130, 18],
                iconAnchor: [65, 9]
            }}),
            interactive: false
        }}).addTo(airwayLayer);

        // -------------------------------------------------------------
        // 계기접근 IAF, IF, FAF 및 주요 Fix 렌더링
        // -------------------------------------------------------------
        const allNavFixes = [
            ...y711Fixes.map(f => ({{ ...f, cat: "Y711" }})),
            ...y722Fixes.map(f => ({{ ...f, cat: "Y722" }})),
            // [인천 RKSI 터미널 Fix]
            {{ name: "NOUTE", pos: [37.2167, 125.8667], cat: "SID", desc: "인천 서해 출역점" }},
            {{ name: "EGOBA", pos: [37.6667, 126.8833], cat: "IAF/SID", desc: "인천 북동 IAF / SID 전이" }},
            {{ name: "KARAS", pos: [37.1500, 126.0833], cat: "STAR", desc: "인천 남서 접근점" }},
            {{ name: "REKTO", pos: [37.2667, 126.1500], cat: "IAF", desc: "인천 RWY 33/34 진입 IAF" }},
            {{ name: "OSPUR", pos: [37.6833, 126.2667], cat: "IAF", desc: "인천 RWY 15/16 진입 IAF" }},
            {{ name: "DANAN", pos: [37.6017, 126.3350], cat: "IF", desc: "인천 RWY 15L/R 중간접근점" }},
            {{ name: "SI801", pos: [37.3317, 126.5417], cat: "IF", desc: "인천 RWY 33L/R 중간접근점" }},
            {{ name: "KASOM", pos: [37.5450, 126.3817], cat: "FAF", desc: "인천 RWY 15R 최종접근점 (FAF)" }},
            {{ name: "ENPIL", pos: [37.3883, 126.4983], cat: "FAF", desc: "인천 RWY 33L 최종접근점 (FAF)" }},
            // [김포 RKSS 터미널 Fix]
            {{ name: "BULLS", pos: [37.4167, 127.1833], cat: "IAF", desc: "김포 남동 진입 IAF" }},
            {{ name: "OLMEN", pos: [37.7833, 127.0500], cat: "STAR", desc: "김포 북동 접근 픽스" }},
            {{ name: "YAGI", pos: [37.5833, 126.5500], cat: "IAF", desc: "김포 서부 진입 IAF" }},
            {{ name: "SS801", pos: [37.4850, 126.8650], cat: "IF", desc: "김포 RWY 32 중간접근점" }},
            {{ name: "SS701", pos: [37.6350, 126.7150], cat: "IF", desc: "김포 RWY 14 중간접근점" }},
            {{ name: "KAE_VOR", pos: [37.5583, 126.7906], cat: "FAF", desc: "김포 VOR / RWY 32 FAF" }},
            {{ name: "METRO", pos: [37.6050, 126.7450], cat: "FAF", desc: "김포 RWY 14L 최종접근점 (FAF)" }},
            // [제주 RKPC 터미널 Fix]
            {{ name: "DOTOL", pos: [33.2833, 126.2167], cat: "IAF/SID", desc: "제주 남서 진입 IAF / SID" }},
            {{ name: "SARAS", pos: [33.4500, 126.8500], cat: "IAF", desc: "제주 동부 진입 IAF" }},
            {{ name: "PC801", pos: [33.4750, 126.3667], cat: "IF", desc: "제주 RWY 07 중간접근점" }},
            {{ name: "PC901", pos: [33.5450, 126.6200], cat: "IF", desc: "제주 RWY 25 중간접근점" }},
            {{ name: "PABSO", pos: [33.4933, 126.4300], cat: "FAF", desc: "제주 RWY 07 최종접근점 (FAF)" }},
            {{ name: "LAVAR", pos: [33.5283, 126.5567], cat: "FAF", desc: "제주 RWY 25 최종접근점 (FAF)" }}
        ];

        // 중복 제거 후 렌더링
        const renderedFixes = new Set();
        allNavFixes.forEach(f => {{
            const key = f.name;
            if (renderedFixes.has(key)) return;
            renderedFixes.add(key);

            let dotClass = 'fix-dot';
            if (f.cat.includes('IAF')) dotClass += ' fix-dot-iaf';
            else if (f.cat.includes('FAF')) dotClass += ' fix-dot-faf';
            else if (f.cat.startsWith('Y7')) dotClass += ' fix-dot-airway';

            const marker = L.marker(f.pos, {{
                icon: L.divIcon({{
                    className: '',
                    html: `<div class="${{dotClass}}"></div>`,
                    iconSize: [6, 6],
                    iconAnchor: [3, 3]
                }})
            }}).addTo(airwayLayer);
            marker.bindTooltip(`<b>${{f.name}}</b> [${{f.cat}}]<br>${{f.desc}}`, {{ direction: 'top', opacity: 0.9 }});

            L.marker(f.pos, {{
                icon: L.divIcon({{
                    className: 'fix-text-tag',
                    html: f.name,
                    iconSize: [40, 12],
                    iconAnchor: [-5, 6]
                }}),
                interactive: false
            }}).addTo(airwayLayer);
        }});

        // -------------------------------------------------------------
        // 실시간 항공기 추적 엔진
        // -------------------------------------------------------------
        let flightHistory = {{}};
        let markers = {{}};
        let polylines = {{}};
        let selectedIcao = null;

        function getIcon(heading, color) {{
            const html = `<div class="icon-wrapper" style="transform: rotate(${{heading}}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [24,24], iconAnchor: [12,12] }});
        }}

        function getStatus(hist, rawVspeed) {{
            let vsFpm = 0;
            if (rawVspeed !== null && rawVspeed !== undefined) {{
                vsFpm = Math.round(rawVspeed);
            }} else if (hist && hist.length >= 2) {{
                const p0 = hist[Math.max(0, hist.length - 4)];
                const p1 = hist[hist.length - 1];
                const dt = (p1.time - p0.time) / 1000;
                if (dt > 0) {{
                    vsFpm = Math.round(((p1.alt - p0.alt) / dt) * 60);
                }}
            }}

            let color = '#2ecc71';
            let text = 'Level';

            if (vsFpm > 150) {{
                color = '#f1c40f';
                text = 'Climb';
            }} else if (vsFpm < -150) {{
                color = '#3498db';
                text = 'Desc';
            }}

            const sign = vsFpm > 0 ? '+' : '';
            const fpmText = `${{sign}}${{vsFpm.toLocaleString()}} fpm`;

            return {{ color, text, fpmText, vsFpm }};
        }}

        function makeHudContent(p, statusObj) {{
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
                <div>
                    <span class="card-label">V. Rate (FPM)</span>
                    <span class="card-value" style="color: ${{statusObj.color}};">${{statusObj.fpmText}}</span>
                </div>
                <div>
                    <span class="card-label">Status</span>
                    <span class="card-value" style="color: ${{statusObj.color}};">${{statusObj.text}}</span>
                </div>
            </div>
            `;
        }}

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

        window.updateFlightRadar = function(payload) {{
            const planes = payload.planes || [];
            const sourceName = payload.source || '';
            const statusBox = document.getElementById('status-box');
            
            const now = Date.now();
            const currentIcaos = new Set();
            let countIn100km = 0;

            planes.forEach(p => {{
                const icao = p.hex;
                if (!icao || p.lat == null || p.lon == null) return;

                const distKm = Math.hypot(p.lat - homeLat, (p.lon - homeLon) * Math.cos(homeLat * Math.PI / 180)) * 111.32;
                if (distKm > 100) return;

                countIn100km++;
                currentIcaos.add(icao);

                if (!flightHistory[icao]) {{
                    flightHistory[icao] = [];
                    if (p.alt > 0 && p.spd > 100) {{
                        const rad = p.track * Math.PI / 180;
                        const backRad = (rad + Math.PI) % (2 * Math.PI);
                        [30, 15].forEach(pastSec => {{
                            const distKmB = (p.spd * pastSec / 3600.0) * 1.852;
                            const d = distKmB / 6371.0;
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
                    lat: p.lat, lon: p.lon, alt: p.alt, spd: p.spd,
                    track: p.track, callsign: p.callsign, airline: p.airline, type: p.type,
                    vspeed: p.vspeed, time: now
                }});

                flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 600000);
                if (flightHistory[icao].length > 80) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const statusObj = getStatus(hist, p.vspeed);
                const isSelected = (selectedIcao === icao);

                const newIcon = getIcon(p.track, statusObj.color);
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
                        marker.bindTooltip(makeHudContent(p, statusObj), {{
                            permanent: true,
                            direction: 'right',
                            offset: [15, -15],
                            className: 'plane-hud-card'
                        }}).openTooltip();
                    }});
                    
                    markers[icao] = marker;
                }}

                if (isSelected) {{
                    markers[icao].unbindTooltip();
                    markers[icao].bindTooltip(makeHudContent(p, statusObj), {{
                        permanent: true,
                        direction: 'right',
                        offset: [15, -15],
                        className: 'plane-hud-card'
                    }}).openTooltip();
                }} else if (!markers[icao].getTooltip()) {{
                    markers[icao].bindTooltip(`<b>${{p.callsign}}</b><br>${{Math.round(p.alt).toLocaleString()}} ft`, {{ direction: 'top' }});
                }}

                const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                if (polylines[icao]) {{
                    polylines[icao].setLatLngs(latlngs);
                    polylines[icao].setStyle({{ color: statusObj.color, weight: isSelected ? 4 : 3 }});
                }} else {{
                    polylines[icao] = L.polyline(latlngs, {{
                        color: statusObj.color,
                        weight: isSelected ? 4 : 3,
                        opacity: isSelected ? 0.9 : 0.75
                    }}).addTo(map);
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

            if (countIn100km === 0) {{
                statusBox.innerText = `📡 0대 (100km 내 트래픽 없음) [${{sourceName}}]`;
                statusBox.style.color = "#e74c3c";
            }} else {{
                statusBox.innerText = `📡 ${{countIn100km}}대 추적 중 [${{sourceName}}]`;
                statusBox.style.color = "#2ecc71";
            }}
        }};

        function relocateHome(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {{}};
            polylines = {{}};
            flightHistory = {{}};
            selectedIcao = null;
            
            document.getElementById('status-box').innerText = "📡 새 위치 재스캔 요청 중...";
            document.getElementById('status-box').style.color = "#f39c12";

            try {{
                const parentUrl = new URL(window.parent.location.href);
                parentUrl.searchParams.set("lat", newLat.toFixed(4));
                parentUrl.searchParams.set("lon", newLon.toFixed(4));
                window.parent.history.replaceState(null, "", parentUrl.toString());
            }} catch (e) {{}}
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

# 5. 실시간 브릿지 프래그먼트
@st.fragment(run_every="5s")
def sync_data_stream():
    lat = st.session_state.home_coords[0]
    lon = st.session_state.home_coords[1]
    
    qp = st.query_params
    if "lat" in qp and "lon" in qp:
        try:
            lat = float(qp["lat"])
            lon = float(qp["lon"])
            st.session_state.home_coords = [lat, lon]
        except Exception:
            pass

    planes, source_name = fetch_flight_data(lat, lon)
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
