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

# 1. IATA(2자리) & ICAO(3자리) 통합 항공사 데이터베이스
DEFAULT_AIRLINES = {
    # 대한민국
    "KE": "대한항공 (Korean Air)", "KAL": "대한항공 (Korean Air)",
    "OZ": "아시아나항공 (Asiana Airlines)", "AAR": "아시아나항공 (Asiana Airlines)",
    "7C": "제주항공 (Jeju Air)", "JJA": "제주항공 (Jeju Air)",
    "LJ": "진에어 (Jin Air)", "JNA": "진에어 (Jin Air)",
    "TW": "티웨이항공 (T'way Air)", "TWB": "티웨이항공 (T'way Air)",
    "RS": "에어서울 (Air Seoul)", "ASV": "에어서울 (Air Seoul)",
    "BX": "에어부산 (Air Busan)", "ABL": "에어부산 (Air Busan)",
    "ZE": "이스타항공 (Eastar Jet)", "ESR": "이스타항공 (Eastar Jet)",
    "YP": "에어프레미아 (Air Premia)", "APZ": "에어프레미아 (Air Premia)",
    # 일본
    "MM": "피치항공 (Peach Aviation)", "APJ": "피치항공 (Peach Aviation)",
    "NH": "전일본공수 (ANA)", "ANA": "전일본공수 (ANA)",
    "JL": "일본항공 (JAL)", "JAL": "일본항공 (JAL)",
    "7G": "스타플라이어 (StarFlyer)", "SFJ": "스타플라이어 (StarFlyer)",
    # 대만 / 홍콩 / 중국
    "CX": "캐세이퍼시픽 (Cathay Pacific)", "CPA": "캐세이퍼시픽 (Cathay Pacific)",
    "CI": "중화항공 (China Airlines)", "CAL": "중화항공 (China Airlines)",
    "BR": "에바항공 (EVA Air)", "EVA": "에바항공 (EVA Air)",
    "CA": "중국국제항공 (Air China)", "CCA": "중국국제항공 (Air China)",
    "MU": "중국동방항공 (China Eastern)", "CES": "중국동방항공 (China Eastern)",
    "CZ": "중국남방항공 (China Southern)", "CSN": "중국남방항공 (China Southern)",
    "MF": "샤먼항공 (XiamenAir)", "CXA": "샤먼항공 (XiamenAir)",
    "SC": "산동항공 (Shandong Airlines)", "CDG": "산동항공 (Shandong Airlines)",
    # 동남아시아
    "SQ": "싱가포르항공 (Singapore Airlines)", "SIA": "싱가포르항공 (Singapore Airlines)",
    "TG": "타이항공 (Thai Airways)", "THA": "타이항공 (Thai Airways)",
    "MH": "말레이시아항공 (Malaysia Airlines)", "MAS": "말레이시아항공 (Malaysia Airlines)",
    "VN": "베트남항공 (Vietnam Airlines)", "HVN": "베트남항공 (Vietnam Airlines)",
    "VJ": "비엣젯항공 (VietJet Air)", "VJC": "비엣젯항공 (VietJet Air)",
    "PR": "필리핀항공 (Philippine Airlines)", "PAL": "필리핀항공 (Philippine Airlines)",
    "5J": "세부퍼시픽 (Cebu Pacific)", "CEB": "세부퍼시픽 (Cebu Pacific)",
    "GA": "가루다 인도네시아 (Garuda Indonesia)", "GIA": "가루다 인도네시아 (Garuda Indonesia)",
    # 중동 / 유럽
    "EK": "에미레이트항공 (Emirates)", "UAE": "에미레이트항공 (Emirates)",
    "QR": "카타르항공 (Qatar Airways)", "QTR": "카타르항공 (Qatar Airways)",
    "EY": "에티하드항공 (Etihad Airways)", "ETD": "에티하드항공 (Etihad Airways)",
    "LH": "루프트한자 (Lufthansa)", "DLH": "루프트한자 (Lufthansa)",
    "AF": "에어프랑스 (Air France)", "AFR": "에어프랑스 (Air France)",
    "KL": "KLM 네덜란드항공 (KLM)", "KLM": "KLM 네덜란드항공 (KLM)",
    "BA": "영국항공 (British Airways)", "BAW": "영국항공 (British Airways)",
    "AY": "핀에어 (Finnair)", "FIN": "핀에어 (Finnair)",
    "TK": "터키항공 (Turkish Airlines)", "THY": "터키항공 (Turkish Airlines)",
    # 미주 / 화물
    "UA": "유나이티드항공 (United Airlines)", "UAL": "유나이티드항공 (United Airlines)",
    "DL": "델타항공 (Delta Air Lines)", "DAL": "델타항공 (Delta Air Lines)",
    "AA": "아메리칸항공 (American Airlines)", "AAL": "아메리칸항공 (American Airlines)",
    "AC": "에어캐나다 (Air Canada)", "ACA": "에어캐나다 (Air Canada)",
    "FX": "페덱스 익스프레스 (FedEx)", "FDX": "페덱스 익스프레스 (FedEx)",
    "5X": "UPS 항공 (UPS Airlines)", "UPS": "UPS 항공 (UPS Airlines)",
    "5Y": "아틀라스항공 (Atlas Air)", "GTI": "아틀라스항공 (Atlas Air)"
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

# IATA(2자리)와 ICAO(3자리)를 모두 식별하는 지능형 파서
def resolve_airline_name(callsign):
    if not callsign or len(callsign) < 2:
        return ""
    
    clean_cs = callsign.strip().upper()
    
    # 1. ICAO 3자리 우선 매칭 (예: KAL, AAR, JJA)
    if len(clean_cs) >= 3:
        icao_cand = clean_cs[:3]
        if icao_cand in airlines_db:
            return airlines_db[icao_cand]
            
    # 2. IATA 2자리 매칭 (예: KE123 -> KE, 7C101 -> 7C, OZ741 -> OZ)
    iata_cand = clean_cs[:2]
    if iata_cand in airlines_db:
        return airlines_db[iata_cand]
        
    # 3. 정규식 기반 분리 (영문/숫자 혼합 접두사 파싱)
    match = re.match(r"^([A-Z0-9]{2,3})\d+", clean_cs)
    if match:
        code = match.group(1)
        if code in airlines_db:
            return airlines_db[code]
            
    return ""

# 2. 파이썬 백엔드 데이터 수집
def fetch_flight_data(lat, lon):
    radius_nm = 54  # 100km 커버리지
    lat_diff = radius_nm / 60.0
    lon_diff = radius_nm / (60.0 * math.cos(math.radians(lat)))
    
    # 1순위: Flightradar24
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
                # 편명(v[13]) 또는 콜사인(v[16])
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

    # 2순위: Airplanes.live
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

# 3. 홈포인트 좌표 동기화
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
            font-size: 13px; font-weight: 800; color: #1a365d; margin-bottom: 8px; 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 210px; 
        }}
        .card-metrics {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; font-size: 11px;
        }}
        .card-metrics div {{ display: flex; flex-direction: column; }}
        .card-label {{ font-size: 9px; color: #a0aec0; text-transform: uppercase; font-weight: 700; margin-bottom: 1px; }}
        .card-value {{ font-size: 13px; font-weight: 800; color: #2d3748; white-space: nowrap; }}
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
