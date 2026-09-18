import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import csv

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 및 전체 화면 여백/스크롤바 제거
st.markdown("""
<style>
    .block-container { padding: 0 !important; max-width: 100% !important; overflow: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    iframe { border: none !important; width: 100% !important; height: 100vh !important; }
</style>
""", unsafe_allow_html=True)

# 항공사 ICAO 코드 DB 로드 (JSON 주입용)
AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
@st.cache_data(ttl=86400)
def get_airlines_dict():
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
    return json.dumps(db)

airlines_json_str = get_airlines_dict()

# 초기 기준점 (인천국제공항)
init_lat = 37.4600
init_lon = 126.4400

# 단일 iframe 내에서 모든 실시간 루프가 깜빡임 없이 동작하는 HTML/JS 엔진
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
        #map {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #e5e9ec; }}
        
        /* 상단 상태바 */
        .top-hud {{
            position: absolute; top: 12px; left: 12px; right: 12px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: center; pointer-events: none;
        }}
        .hud-box {{
            background: rgba(255, 255, 255, 0.95); padding: 8px 14px; border-radius: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18); font-size: 13px; font-weight: bold; color: #2c3e50;
            pointer-events: auto; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(0,0,0,0.08);
        }}
        
        /* 하단 비행기 정보 패널 */
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
        <div class="hud-box" id="status-box">
            📡 레이더 스캔 시작...
        </div>
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
        <div class="plane-airline" id="p-airline">지도를 더블클릭하여 위치를 변경할 수 있습니다.</div>
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
        const airlinesDB = {airlines_json_str};
        let homeLat = {init_lat};
        let homeLon = {init_lon};

        // 지도 생성
        const map = L.map('map', {{
            center: [homeLat, homeLon],
            zoom: 9,
            zoomControl: false,
            doubleClickZoom: false // 더블클릭 줌 해제 -> 홈포인트 이동 전용
        }});
        L.control.zoom({{ position: 'bottomright' }}).addTo(map);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 18,
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        // 180km 원형 레이더 범위
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
        }}).addTo(map).bindTooltip("Home Point (Double-click to relocate)");

        // 런타임 캐시 (DOM 객체를 재생성하지 않고 유지)
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

        // 비동기 다중 데이터 수신 (CORS 자동 우회)
        async function fetchFlightData() {{
            const latDiff = 1.6;
            const lonDiff = 2.0;
            const bounds = `${{(homeLat+latDiff).toFixed(3)}},${{(homeLat-latDiff).toFixed(3)}},${{(homeLon-lonDiff).toFixed(3)}},${{(homeLon+lonDiff).toFixed(3)}}`;
            const fr24Url = `https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds=${{bounds}}&faa=1&mlat=1&flarm=1&adsb=1&gnd=1&air=1&vehicles=0&estimated=1`;

            let planes = [];
            let sourceName = "";

            // 1차 시도: Allorigins 프록시로 Flightradar24 수신
            try {{
                const res = await fetch(`https://api.allorigins.win/get?url=${{encodeURIComponent(fr24Url)}}`);
                if (res.ok) {{
                    const json = await res.json();
                    if (json.contents) {{
                        const raw = JSON.parse(json.contents);
                        for (let k in raw) {{
                            if (['full_count', 'version', 'stats'].includes(k)) continue;
                            const v = raw[k];
                            const cs = (v[13] || v[16] || v[0] || "Unknown").trim();
                            planes.push({{
                                hex: String(v[0]).toUpperCase(),
                                lat: v[1],
                                lon: v[2],
                                track: v[3] || 0,
                                alt: v[4] || 0,
                                spd: v[5] || 0,
                                type: v[8] || "N/A",
                                callsign: cs,
                                airline: airlinesDB[cs.substring(0,3).toUpperCase()] || "일반 / 개인 항공기"
                            }});
                        }}
                        if (planes.length > 0) sourceName = "Flightradar24";
                    }}
                }}
            }} catch (e) {{}}

            // 2차 시도: 오픈소스 ADSB.lol 직통 수신 (CORS 지원)
            if (planes.length === 0) {{
                try {{
                    const res = await fetch(`https://api.adsb.lol/v2/point/${{homeLat.toFixed(3)}}/${{homeLon.toFixed(3)}}/100`);
                    if (res.ok) {{
                        const json = await res.json();
                        (json.ac || []).forEach(v => {{
                            const cs = (v.flight || "Unknown").trim();
                            let alt = v.alt_baro;
                            if (alt === "ground" || alt == null) alt = 0;
                            planes.push({{
                                hex: (v.hex || "").toUpperCase(),
                                lat: v.lat,
                                lon: v.lon,
                                track: v.track || 0,
                                alt: alt,
                                spd: v.gs || 0,
                                type: v.t || "N/A",
                                callsign: cs,
                                airline: airlinesDB[cs.substring(0,3).toUpperCase()] || "일반 / 개인 항공기"
                            }});
                        }});
                        if (planes.length > 0) sourceName = "ADSB.lol";
                    }}
                }} catch (e) {{}}
            }}

            // 3차 시도: Airplanes.live 폴백
            if (planes.length === 0) {{
                try {{
                    const res = await fetch(`https://api.airplanes.live/v2/point/${{homeLat.toFixed(3)}}/${{homeLon.toFixed(3)}}/100`);
                    if (res.ok) {{
                        const json = await res.json();
                        (json.ac || []).forEach(v => {{
                            const cs = (v.flight || "Unknown").trim();
                            let alt = v.alt_baro;
                            if (alt === "ground" || alt == null) alt = 0;
                            planes.push({{
                                hex: (v.hex || "").toUpperCase(),
                                lat: v.lat,
                                lon: v.lon,
                                track: v.track || 0,
                                alt: alt,
                                spd: v.gs || 0,
                                type: v.t || "N/A",
                                callsign: cs,
                                airline: airlinesDB[cs.substring(0,3).toUpperCase()] || "일반 / 개인 항공기"
                            }});
                        }});
                        if (planes.length > 0) sourceName = "Airplanes.live";
                    }}
                }} catch (e) {{}}
            }}

            const statusBox = document.getElementById('status-box');
            if (planes.length === 0) {{
                statusBox.innerText = "📡 0대 (해당 반경 트래픽 없음)";
                statusBox.style.color = "#7f8c8d";
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

                // 가상 과거 꼬리선 보간 (첫 감지 시)
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

                // 15분 이상 경과된 항적 정리
                flightHistory[icao] = flightHistory[icao].filter(pt => now - pt.time <= 900000);
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = getStatus(hist);

                // 마커 위치만 부드럽게 이동 (깜빡임 0%)
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

                // 꼬리선 좌표 배열만 갱신
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

            // 범위 벗어난 기체 제거
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

            // 하단 패널 업데이트 (선택된 기체 또는 가장 가까운 기체)
            let focused = planes.find(p => p.hex === selectedIcao) || nearestPlane;
            if (focused) {{
                const st = getStatus(flightHistory[focused.hex]);
                updatePanel(focused, st.text, st.color);
            }}
        }}

        // 더블클릭/더블탭 시 홈포인트 재설정
        function relocateHome(newLat, newLon) {{
            homeLat = newLat;
            homeLon = newLon;
            
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            map.panTo([homeLat, homeLon]);

            document.getElementById('status-box').innerText = "📡 새 위치 스캔 중...";
            fetchFlightData();
        }}

        // PC 마우스 더블클릭 이벤트
        map.on('dblclick', function(e) {{
            relocateHome(e.latlng.lat, e.latlng.lng);
        }});

        // 모바일 터치 더블탭 이벤트 (300ms)
        let lastTap = 0;
        map.on('click', function(e) {{
            const curTime = new Date().getTime();
            const interval = curTime - lastTap;
            if (interval < 300 && interval > 0) {{
                relocateHome(e.latlng.lat, e.latlng.lng);
            }}
            lastTap = curTime;
        }});

        // 최초 1회 실행 후 5초 주기로 데이터만 조용히 갱신 (지도는 재생성되지 않음)
        fetchFlightData();
        setInterval(fetchFlightData, 5000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=850, scrolling=False)
