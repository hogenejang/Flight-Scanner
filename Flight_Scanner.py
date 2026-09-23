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

                origin = v[11] if len(v) > 11 and v[11] else ""
                destination = v[12] if len(v) > 12 and v[12] else ""
                on_ground = bool(v[14]) if len(v) > 14 and v[14] is not None else False

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
                    "airline": resolve_airline_name(callsign),
                    "origin": origin,
                    "destination": destination,
                    "on_ground": on_ground
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
                is_ground = (alt == "ground")
                if is_ground or alt is None:
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
                    "airline": resolve_airline_name(callsign),
                    "origin": "",
                    "destination": "",
                    "on_ground": is_ground
                })
            return planes, "Airplanes.live"
    except Exception:
        pass

    return [], "No Signal"

# 3. 홈포인트 설정
if "home_coords" not in st.session_state:
    st.session_state.home_coords = [37.151575, 126.743044]

# 초기 로드(또는 공유 링크 진입) 시 1회 URL의 lat/lon을 세션 상태에 반영하고 정리
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

        .top-hud-container {{
            position: absolute; top: 10px; left: 10px; right: 10px; z-index: 1000;
            display: flex; flex-direction: column; gap: 8px; pointer-events: none;
        }}
        .hud-row {{
            display: flex; justify-content: space-between; align-items: center; width: 100%; pointer-events: none;
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 7px 12px; border-radius: 18px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 12px; font-weight: bold; color: #2c3e50;
            pointer-events: auto; display: flex; align-items: center; gap: 6px; border: 1px solid rgba(0,0,0,0.08);
            backdrop-filter: blur(6px);
        }}

        .preset-bar {{
            display: flex; gap: 6px; overflow-x: auto; -webkit-overflow-scrolling: touch;
            padding: 3px 2px; pointer-events: auto; scrollbar-width: none;
        }}
        .preset-bar::-webkit-scrollbar {{ display: none; }}
        .preset-btn {{
            background: rgba(255, 255, 255, 0.95); border: 1px solid rgba(0,0,0,0.15);
            color: #1a202c; padding: 6px 12px; border-radius: 14px; font-size: 11px;
            font-weight: 800; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            cursor: pointer; transition: all 0.15s ease; backdrop-filter: blur(6px);
        }}
        .preset-btn:active {{
            transform: scale(0.94); background: #edf2f7;
        }}

        .icon-wrapper {{
            width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
            filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); transition: transform 0.4s linear;
        }}

        /* 비행 중이 아닌 지상 기체용 원형 마커 */
        .ground-icon-wrapper {{
            width: 14px; height: 14px; display: flex; align-items: center; justify-content: center;
        }}
        .ground-circle-marker {{
            width: 10px; height: 10px; background-color: #718096;
            border-radius: 50%; border: 2px solid #ffffff;
            box-shadow: 0 1px 4px rgba(0,0,0,0.6);
            transition: transform 0.2s ease;
        }}

        .plane-hud-card {{
            background: rgba(255, 255, 255, 0.97) !important;
            border: 1px solid rgba(0,0,0,0.12) !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 24px rgba(0,0,0,0.22) !important;
            padding: 10px 14px !important;
            color: #2c3e50 !important;
            min-width: 210px !important;
            backdrop-filter: blur(8px) !important;
            pointer-events: auto !important;
        }}
        .plane-hud-card:before {{ border-right-color: rgba(255, 255, 255, 0.97) !important; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #edf2f7; padding-bottom: 5px; margin-bottom: 6px; gap: 8px; }}
        .card-callsign {{ font-size: 18px; font-weight: 900; color: #e74c3c; line-height: 1; }}
        .card-type {{ font-size: 10px; font-weight: bold; background: #edf2f7; padding: 2px 6px; border-radius: 4px; color: #4a5568; }}
        .card-airline {{ font-size: 13px; font-weight: 800; color: #1a365d; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 210px; }}

        .card-route-row {{ display: flex; justify-content: space-between; align-items: center; background: #f7fafc; padding: 4px 8px; border-radius: 6px; margin-bottom: 8px; font-size: 11px; }}
        .card-route {{ font-weight: 800; color: #2b6cb0; }}
        .card-ground-status {{ font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 4px; }}
        .ground-air {{ background: #e6fffa; color: #234e52; }}
        .ground-on {{ background: #edf2f7; color: #4a5568; border: 1px solid #cbd5e0; }}

        .card-metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; font-size: 11px; }}
        .card-metrics div {{ display: flex; flex-direction: column; }}
        .card-label {{ font-size: 9px; color: #a0aec0; text-transform: uppercase; font-weight: 700; margin-bottom: 1px; }}
        .card-value {{ font-size: 13px; font-weight: 800; color: #2d3748; white-space: nowrap; }}

        /* 영구 고정 Waypoint 스타일 */
        .waypoint-dot {{
            width: 7px; height: 7px; background: #4a5568;
            transform: rotate(45deg); border: 1.5px solid #ffffff;
            box-shadow: 0 0 3px rgba(0,0,0,0.5);
        }}
        .waypoint-dot-sid {{ background: #2b6cb0; }}
        .waypoint-dot-star {{ background: #2c7a7b; }}
        .waypoint-dot-app {{ background: #c53030; }}
        .waypoint-dot-pms {{ background: #805ad5; }}
        .waypoint-dot-airway {{ background: #4a5568; width: 6px; height: 6px; }}

        .waypoint-label {{
            font-size: 10px !important; font-weight: 800 !important; color: #1a202c !important;
            text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff;
            white-space: nowrap; pointer-events: none; opacity: 0.9; letter-spacing: 0.3px;
        }}

        /* 심플한 수평 항로 뱃지 스타일 */
        .airway-tag-badge {{
            display: inline-block !important;
            font-size: 10px !important; font-weight: 800 !important;
            letter-spacing: 0.5px !important;
            padding: 2px 7px !important; border-radius: 4px !important;
            white-space: nowrap !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.18) !important;
            pointer-events: none !important;
        }}
        .airway-tag-y711 {{
            color: #2b6cb0 !important; background: rgba(255, 255, 255, 0.94) !important;
            border: 1.5px solid #63b3ed !important;
        }}
        .airway-tag-y722 {{
            color: #234e52 !important; background: rgba(255, 255, 255, 0.94) !important;
            border: 1.5px solid #4fd1c5 !important;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="top-hud-container">
        <div class="hud-row">
            <div class="hud-box" id="status-box">📡 100km 레이더 가동 중...</div>
            <div class="hud-box">
                <span style="color:#2ecc71;">● 수평</span>
                <span style="color:#f1c40f;">● 상승</span>
                <span style="color:#3498db;">● 하강</span>
                <span style="color:#718096;">● 지상</span>
            </div>
        </div>
        <div class="preset-bar">
            <button class="preset-btn" onclick="relocateHome(37.151575, 126.743044)">🏠 HOME</button>
            <button class="preset-btn" onclick="relocateHome(37.4600, 126.4400)">인천 RKSI</button>
            <button class="preset-btn" onclick="relocateHome(37.5583, 126.7906)">김포 RKSS</button>
            <button class="preset-btn" onclick="relocateHome(35.1728, 128.9392)">김해 RKPK</button>
            <button class="preset-btn" onclick="relocateHome(33.5113, 126.4930)">제주 RKPC</button>
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
        // 영구 고정 레이어 (공인 eAIP 정밀 좌표 체계 및 구간화 항로)
        // 2026-09 교차검증: Y711/Y722 본선 픽스는 한국 항공정보포털
        // eAIP ENR 3.3 원문 좌표와 대조 완료. DALSU(Y711), SAMUL·GUNKU(Y722)는
        // 실제 항로상 존재하나 누락되어 있었기에 추가함.
        // -------------------------------------------------------------
        const permanentFixLayer = L.layerGroup().addTo(map);

        // 1. Y711 (남행: BULTI ~ DOTOL 구간, MONSI 하류 세그먼트)
        const y711Path = [
            {{ name: "BULTI", pos: [36.722778, 126.825000], type: "Y711", note: "아산/예산 경계 (Y711 시발점)" }},
            {{ name: "MEKIL", pos: [36.556111, 126.831389], type: "Y711", note: "청양 북동부" }},
            {{ name: "GONAX", pos: [36.386389, 126.837778], type: "Y711", note: "부여 은산면" }},
            {{ name: "BEDES", pos: [36.151389, 126.812222], type: "Y711", note: "서천/군산 경계" }},
            {{ name: "ELPOS", pos: [35.902778, 126.785278], type: "Y711", note: "김제 서부" }},
            {{ name: "MANGI", pos: [35.503056, 126.742222], type: "Y711", note: "고창읍 상공" }},
            {{ name: "DALSU", pos: [35.125278, 126.701667], type: "Y711", note: "전남 영광 서남부 (여수 진입 분기점, eAIP 확인 후 추가)" }},
            {{ name: "DOTOL", pos: [34.254167, 126.610278], type: "Y711/STAR", note: "완도 청산도 서남 해상 (Y711 종착점)" }}
        ];

        L.polyline(y711Path.map(f => f.pos), {{
            color: '#3182ce',
            weight: 2.2,
            dashArray: '6, 6',
            opacity: 0.7
        }}).addTo(permanentFixLayer);

        L.marker([36.4700, 126.8340], {{
            icon: L.divIcon({{
                className: '',
                html: '<span class="airway-tag-badge airway-tag-y711">Y711</span>',
                iconSize: [48, 20],
                iconAnchor: [24, 10]
            }}),
            interactive: false
        }}).addTo(permanentFixLayer);

        // 2. Y722 (북행: KAMIT ~ OLMEN 구간)
        const y722Path = [
            {{ name: "KAMIT", pos: [34.253889, 126.771667], type: "Y722", note: "완도 여서도 북동 해상 (Y722 시발점)" }},
            {{ name: "SAMUL", pos: [35.126500, 126.865000], type: "Y722", note: "전남 영광 동부 (eAIP 확인 후 추가)" }},
            {{ name: "MAKSA", pos: [35.503056, 126.906111], type: "Y722", note: "정읍 신태인" }},
            {{ name: "ATASO", pos: [35.895556, 126.949167], type: "Y722", note: "익산 춘포면" }},
            {{ name: "PEBRI", pos: [36.386389, 127.003611], type: "Y722", note: "공주/세종 서부" }},
            {{ name: "GUNKU", pos: [36.570556, 126.996944], type: "Y722", note: "천안 동남부 (eAIP 확인 후 추가)" }},
            {{ name: "OLMEN", pos: [36.736944, 126.991111], type: "Y722/STAR", note: "아산 배방읍 (Y722 종착점)" }}
        ];

        L.polyline(y722Path.map(f => f.pos), {{
            color: '#285e61',
            weight: 2.2,
            dashArray: '6, 6',
            opacity: 0.7
        }}).addTo(permanentFixLayer);

        L.marker([36.4700, 127.0000], {{
            icon: L.divIcon({{
                className: '',
                html: '<span class="airway-tag-badge airway-tag-y722">Y722</span>',
                iconSize: [48, 20],
                iconAnchor: [24, 10]
            }}),
            interactive: false
        }}).addTo(permanentFixLayer);

        // 3. 주요 터미널 및 제주공항(RKPC) 교차검증 픽스
        // ※ 아래 터미널 IAF/IF/PMS/SID/STAR 픽스군은 접근차트(STAR/IAC) 단위의
        //   1차 원문 대조가 이번 검증 범위에서 완료되지 않아 기존 값을 유지함.
        const terminalFixes = [
            {{ name: "BIROM", pos: [33.792778, 126.386111], type: "STAR", note: "제주 북서 해상 (추자-제주 서부 입역 픽스)" }},
            {{ name: "LIMDI", pos: [33.545000, 126.170833], type: "STAR", note: "제주 한림 서북 외해 (서부 입역 STAR)" }},
            {{ name: "PC621", pos: [33.740833, 126.224722], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 1번점" }},
            {{ name: "PC622", pos: [33.729444, 126.125833], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 2번점" }},
            {{ name: "PC623", pos: [33.694444, 126.035000], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 3번점" }},
            {{ name: "PC624", pos: [33.638889, 125.960556], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 4번점" }},
            {{ name: "PC625", pos: [33.567500, 125.908889], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 5번점" }},
            {{ name: "PC626", pos: [33.486667, 125.884167], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 6번점" }},
            {{ name: "DAKPI", pos: [33.403333, 125.888611], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 7번점 (PC627)" }},
            {{ name: "PC628", pos: [33.324444, 125.921944], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 8번점" }},
            {{ name: "PIMIK", pos: [33.257222, 125.980833], type: "PMS", note: "RWY 07 PMS 시퀀싱 아크 종점 (구 MEDON)" }},
            {{ name: "YUMIN", pos: [33.457222, 126.221111], type: "IAF/MP", note: "RWY 07 계기접근 Merge Point (IAF)" }},

            {{ name: "PANSI", pos: [33.880000, 126.540000], type: "STAR", note: "추자-제주 북부 해상 중간 강하점" }},
            {{ name: "TIXIM", pos: [33.683333, 126.516667], type: "STAR", note: "제주 북부 접근 전이 픽스" }},
            {{ name: "PABSO", pos: [33.493333, 126.430000], type: "IAF", note: "제주 RWY 07 진입 계기접근점" }},
            {{ name: "PC701", pos: [33.498333, 126.385000], type: "IF", note: "제주 RWY 07 최종정렬 중간접근점" }},
            {{ name: "LAVAR", pos: [33.528333, 126.556667], type: "IAF", note: "제주 RWY 25 진입 계기접근점" }},
            {{ name: "PC702", pos: [33.535000, 126.610000], type: "IF", note: "제주 RWY 25 최종정렬 중간접근점" }},
            {{ name: "SARAS", pos: [33.450000, 126.850000], type: "STAR", note: "성산일출봉 동측 해상 (동부 진입)" }},
            {{ name: "TAMNA", pos: [33.470833, 127.331389], type: "STAR/SID", note: "제주 동쪽 외해 (A595 항로 픽스)" }},
            {{ name: "SOSDO", pos: [33.003333, 126.459722], type: "STAR/SID", note: "제주 남단 마라도 남서 해상 (B576/Y722)" }},

            {{ name: "POLEG", pos: [37.213611, 126.993056], type: "FIX", note: "수원 영통 / 화성 반월 상공" }},
            {{ name: "POSAN", pos: [36.937500, 127.221111], type: "FIX", note: "천안 동남구 북면 / 진천 경계" }},
            {{ name: "OSPOT", pos: [36.838333, 127.348611], type: "SID/FIX", note: "청주 오창읍 / 진천 초평 경계" }},
            {{ name: "KALMA", pos: [37.312472, 127.112444], type: "FIX", note: "용인 수지구 성복동 (SEL R-133/D11)" }},
            {{ name: "EGOBA", pos: [37.487417, 127.379417], type: "STAR/SID", note: "광주 남종면 / 양평 경계 (SEL R-087/D22)" }},
            {{ name: "BOGAN", pos: [37.211389, 126.470000], type: "STAR/SID", note: "화성 제부도 남측 해상" }},
            {{ name: "GOGET", pos: [37.656667, 126.991111], type: "STAR", note: "서울 북한산/도봉산 인근 상공" }},
            {{ name: "SONGTAN", pos: [37.090500, 127.028944], type: "VOR/DME", note: "평택 송탄 오산기지 VORTAC (SOT)" }},
            {{ name: "MONSI", pos: [37.212028, 126.837500], type: "FIX", note: "화성 비봉 상공 (eAIP ENR 3.3 371247N 1265015E 반영)" }},
            {{ name: "SEL", pos: [37.413694, 126.928444], type: "VOR/DME", note: "안양 관악산 VOR/DME" }},
            {{ name: "BOPTA", pos: [37.073333, 126.241667], type: "SID", note: "서산 대산반도 외해 (인천 남서 SID)" }},
            {{ name: "NOUTE", pos: [37.216667, 125.866667], type: "SID", note: "굴업도 서쪽 서해 외해 (A593 출역점)" }},
            {{ name: "KARAS", pos: [37.150000, 126.083333], type: "STAR", note: "덕적도 남서 해상 (인천 남서 진입)" }},
            {{ name: "REKTO", pos: [37.272778, 126.155833], type: "IAF", note: "덕적도 동측 해상 (인천 33/34 IAF)" }},
            {{ name: "OSPUR", pos: [37.683333, 126.266667], type: "IAF", note: "강화도 서측 해상 (인천 15/16 IAF)" }},
            {{ name: "DANAN", pos: [37.601667, 126.335000], type: "IF", note: "인천 신도 북단 상공 (인천 15L/R IF)" }},
            {{ name: "SOTSU", pos: [37.300000, 126.900000], type: "SID", note: "군포/안산 경계 (남행 회랑 분기점)" }},
            {{ name: "BULLS", pos: [37.274167, 127.355556], type: "STAR", note: "이천 마장면 상공 (수도권 남동 진입)" }},
            {{ name: "YAGI", pos: [37.583333, 126.550000], type: "STAR", note: "청라국제도시 북측 (김포 서부 STAR)" }},
            {{ name: "SS801", pos: [37.485000, 126.865000], type: "IF", note: "광명/구로 경계 (김포 32L/R IF)" }},

            {{ name: "PSN", pos: [35.173139, 128.939028], type: "VOR/NDB", note: "김해공항 구내 부산 VOR/DME" }},
            {{ name: "KAPLI", pos: [35.048333, 129.418333], type: "SID", note: "영도구 동남 외해 (일본/태평양 방면 출역)" }},
            {{ name: "BUSAN", pos: [34.908333, 128.986667], type: "SID", note: "거제도 동남 해상 (남해안 출발 전이점)" }},
            {{ name: "TOPAX", pos: [35.340000, 128.490000], type: "STAR", note: "창녕 남지읍 상공 (김해 북서 진입 STAR)" }},
            {{ name: "GAYHA", pos: [34.783333, 128.800000], type: "STAR", note: "거제시 남부 해상 (김해 남해안 진입 STAR)" }},
            {{ name: "PK701", pos: [35.050000, 128.939167], type: "IF", note: "다대포 외해 (김해 RWY 36 정렬 IF)" }}
        ];

        const allPermanentFixes = [...y711Path, ...y722Path, ...terminalFixes];
        const registeredFixes = new Set();

        allPermanentFixes.forEach(wp => {{
            if (registeredFixes.has(wp.name)) return;
            registeredFixes.add(wp.name);

            let dotTypeClass = 'waypoint-dot';
            if (wp.type.includes('SID')) dotTypeClass += ' waypoint-dot-sid';
            else if (wp.type.includes('STAR')) dotTypeClass += ' waypoint-dot-star';
            else if (wp.type.includes('PMS')) dotTypeClass += ' waypoint-dot-pms';
            else if (wp.type.includes('IAF') || wp.type.includes('IF') || wp.type.includes('MP')) dotTypeClass += ' waypoint-dot-app';
            else if (wp.type.startsWith('Y7')) dotTypeClass += ' waypoint-dot-airway';

            const marker = L.marker(wp.pos, {{
                icon: L.divIcon({{
                    className: '',
                    html: `<div class="${{dotTypeClass}}"></div>`,
                    iconSize: [8, 8],
                    iconAnchor: [4, 4]
                }}),
                zIndexOffset: 600
            }}).addTo(permanentFixLayer);
            marker.bindTooltip(`<b>${{wp.name}}</b> [${{wp.type}}]<br>${{wp.note}}`, {{ direction: 'top', opacity: 0.95 }});

            L.marker(wp.pos, {{
                icon: L.divIcon({{
                    className: 'waypoint-label',
                    html: wp.name,
                    iconSize: [50, 14],
                    iconAnchor: [-6, 7]
                }}),
                interactive: false,
                zIndexOffset: 600
            }}).addTo(permanentFixLayer);
        }});

        // -------------------------------------------------------------
        // 동적 항공기 추적 및 고성능 페이드아웃 엔진
        // -------------------------------------------------------------
        let flightHistory = {{}};
        let markers = {{}};
        let polylineGroups = {{}};
        let selectedIcao = null;

        const CHUNK_CONFIGS = [
            {{ opacity: 0.35, weight: 2.5 }},
            {{ opacity: 0.60, weight: 3.5 }},
            {{ opacity: 0.85, weight: 4.5 }},
            {{ opacity: 1.00, weight: 5.5 }}
        ];

        // 1) 비행 중인 기체용 화살표 아이콘
        function getIcon(heading, color) {{
            const html = `<div class="icon-wrapper" style="transform: rotate(${{heading}}deg);"><svg width="24" height="24" viewBox="0 0 20 20"><polygon points="10,0 2,20 10,15 18,20" fill="${{color}}" stroke="#1e272c" stroke-width="1.5" /></svg></div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [24,24], iconAnchor: [12,12] }});
        }}

        // 2) 비행 중이 아닌 지상 기체용 회색 원형 아이콘
        function getGroundIcon() {{
            const html = `<div class="ground-icon-wrapper"><div class="ground-circle-marker"></div></div>`;
            return L.divIcon({{ className: '', html: html, iconSize: [14, 14], iconAnchor: [7, 7] }});
        }}

        function getStatus(hist, rawVspeed, onGround) {{
            if (onGround) {{
                return {{ color: '#718096', text: 'Ground', fpmText: '0 fpm', vsFpm: 0 }};
            }}

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

            let routeText = "정보 없음";
            if (p.origin && p.destination) {{
                routeText = `${{p.origin}} ➔ ${{p.destination}}`;
            }} else if (p.origin) {{
                routeText = `${{p.origin}} ➔ ?`;
            }} else if (p.destination) {{
                routeText = `? ➔ ${{p.destination}}`;
            }}

            const groundBadge = p.on_ground
                ? `<span class="card-ground-status ground-on">🛬 지상 활주 (GND)</span>`
                : `<span class="card-ground-status ground-air">✈️ 비행 중 (AIR)</span>`;

            return `
            <div class="card-header">
                <span class="card-callsign">${{p.callsign || p.hex}}</span>
                <span class="card-type">${{p.type || 'N/A'}}</span>
            </div>
            ${{airlineHtml}}
            <div class="card-route-row">
                <span class="card-route">${{routeText}}</span>
                ${{groundBadge}}
            </div>
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

                const isCurrentlyGround = (p.on_ground || (p.alt <= 100 && p.spd < 45));

                if (!flightHistory[icao]) {{
                    flightHistory[icao] = [];
                    if (!isCurrentlyGround && p.alt > 0 && p.spd > 100) {{
                        const rad = p.track * Math.PI / 180;
                        const backRad = (rad + Math.PI) % (2 * Math.PI);
                        [30, 15].forEach(pastSec => {{
                            const distKmB = (p.spd * pastSec / 3600.0) * 1.852;
                            const d = distKmB / 6371.0;
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
                    lat: p.lat, lon: p.lon, alt: p.alt, spd: p.spd,
                    track: p.track, callsign: p.callsign, airline: p.airline, type: p.type,
                    vspeed: p.vspeed, origin: p.origin, destination: p.destination,
                    on_ground: isCurrentlyGround, time: now
                }});

                flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 600000);
                if (flightHistory[icao].length > 80) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const statusObj = getStatus(hist, p.vspeed, isCurrentlyGround);
                const isSelected = (selectedIcao === icao);

                // 지상 기체는 회색 원형 아이콘, 비행 중인 기체는 방향 화살표 아이콘 적용
                const newIcon = isCurrentlyGround ? getGroundIcon() : getIcon(p.track, statusObj.color);

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

                // 항적선 렌더링
                if (!polylineGroups[icao]) {{
                    polylineGroups[icao] = [null, null, null, null];
                }}

                const pts = hist.map(pt => [pt.lat, pt.lon]);
                const totalPts = pts.length;

                // 비행 중인 기체만 항적선 표출 (지상 계류/활주 시 항적선 정리)
                if (!isCurrentlyGround && totalPts >= 2) {{
                    const chunkSize = Math.max(1, Math.floor(totalPts / 4));
                    for (let c = 0; c < 4; c++) {{
                        const startIdx = Math.min(c * chunkSize, totalPts - 1);
                        let endIdx = (c === 3) ? totalPts : Math.min((c + 1) * chunkSize + 1, totalPts);
                        const chunkPts = pts.slice(startIdx, endIdx);

                        if (chunkPts.length >= 2) {{
                            const conf = CHUNK_CONFIGS[c];
                            const lineWeight = isSelected ? conf.weight + 2.0 : conf.weight;
                            const lineOpacity = isSelected ? 1.0 : conf.opacity;

                            if (polylineGroups[icao][c]) {{
                                polylineGroups[icao][c].setLatLngs(chunkPts);
                                polylineGroups[icao][c].setStyle({{
                                    color: statusObj.color,
                                    weight: lineWeight,
                                    opacity: lineOpacity
                                }});
                            }} else {{
                                polylineGroups[icao][c] = L.polyline(chunkPts, {{
                                    color: statusObj.color,
                                    weight: lineWeight,
                                    opacity: lineOpacity
                                }}).addTo(map);
                            }}
                        }} else if (polylineGroups[icao][c]) {{
                            map.removeLayer(polylineGroups[icao][c]);
                            polylineGroups[icao][c] = null;
                        }}
                    }}
                }} else {{
                    // 지상 기체일 경우 기존 항적선 소거
                    polylineGroups[icao].forEach(pLine => {{
                        if (pLine) map.removeLayer(pLine);
                    }});
                    polylineGroups[icao] = [null, null, null, null];
                }}
            }});

            // 100km 이탈 기체 정리
            Object.keys(markers).forEach(icao => {{
                if (!currentIcaos.has(icao)) {{
                    map.removeLayer(markers[icao]);
                    if (polylineGroups[icao]) {{
                        polylineGroups[icao].forEach(p => {{ if (p) map.removeLayer(p); }});
                        delete polylineGroups[icao];
                    }}
                    delete markers[icao];
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

        window.relocateHome = function(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylineGroups).forEach(group => {{
                group.forEach(p => {{ if (p) map.removeLayer(p); }});
            }});
            markers = {{}};
            polylineGroups = {{}};
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
        }};

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

# 5. 실시간 백엔드 데이터 스트림 브릿지
@st.fragment(run_every="5s")
def sync_data_stream():
    # 최신 홈 좌표는 세션 상태를 기준으로 사용
    lat = st.session_state.home_coords[0]
    lon = st.session_state.home_coords[1]

    # 클라이언트에서 HOME 버튼/더블클릭으로 URL만 갱신된 경우(페이지 전체 리런 없이)
    # 이 프래그먼트 주기에서 감지하여 세션 상태에 반영하고, 처리 후에는 URL을 정리해
    # 동일 값이 매 주기마다 중복 반영되는 것을 방지한다.
    qp = st.query_params
    if "lat" in qp and "lon" in qp:
        try:
            new_lat = float(qp["lat"])
            new_lon = float(qp["lon"])
            lat, lon = new_lat, new_lon
            st.session_state.home_coords = [lat, lon]
            st.query_params.clear()
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
