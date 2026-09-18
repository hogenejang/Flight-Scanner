import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 숨김 CSS: 불필요한 여백 제거로 모바일 화면 최대 활용
st.markdown("""
<style>
    .block-container { padding: 0.5rem 1rem 1rem 1rem !important; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# Leaflet.js 기반의 무깜빡임 실시간 레이더 HTML/JS 엔진
radar_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        #map { height: calc(100vh - 120px); min-height: 520px; width: 100%; }
        .control-bar {
            background: #2c3e50; color: white; padding: 10px 14px;
            display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
            font-size: 13px; font-weight: 500;
        }
        .legend-item { display: inline-flex; align-items: center; margin-right: 12px; }
        .legend-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .telemetry-card {
            background: #ffffff; border-top: 1px solid #e0e0e0; padding: 10px 16px;
            display: flex; flex-wrap: wrap; gap: 15px; font-size: 13px; align-items: center;
        }
        .telemetry-badge { background: #f0f2f5; padding: 4px 8px; border-radius: 4px; }
        .plane-marker-icon {
            display: flex; justify-content: center; align-items: center;
            transition: transform 0.3s linear;
        }
    </style>
</head>
<body>
    <div class="control-bar">
        <div>
            <span>🎯 <b>Double-click/Tap map</b> to set Home point (100km radius)</span>
        </div>
        <div>
            <span class="legend-item"><span class="legend-dot" style="background:#2ecc71;"></span>Level</span>
            <span class="legend-item"><span class="legend-dot" style="background:#f1c40f;"></span>Climbing</span>
            <span class="legend-item"><span class="legend-dot" style="background:#3498db;"></span>Descending</span>
        </div>
    </div>

    <div id="map"></div>

    <div class="telemetry-card" id="telemetry">
        <span><b>Selected:</b> <span id="tel-callsign">None (Click a plane)</span></span>
        <span class="telemetry-badge">Alt: <b id="tel-alt">-</b></span>
        <span class="telemetry-badge">Speed: <b id="tel-spd">-</b></span>
        <span class="telemetry-badge">Model: <b id="tel-type">-</b></span>
        <span class="telemetry-badge">Status: <b id="tel-status">-</b></span>
    </div>

    <script>
        let homeLat = 37.5665;
        let homeLon = 126.9780;
        
        // 지도 초기화
        const map = L.map('map', {
            center: [homeLat, homeLon],
            zoom: 9,
            zoomControl: false,
            doubleClickZoom: false // 더블클릭 줌 해제 -> 홈포인트 이동 전용
        });
        L.control.zoom({ position: 'topright' }).add_to(map);

        // 오픈스트리트맵 타일
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '© OpenStreetMap'
        }).addTo(map);

        // 100km 원형 경계선 및 홈 마커
        let radarCircle = L.circle([homeLat, homeLon], {
            radius: 100000,
            color: '#2980b9',
            weight: 2,
            fillColor: '#3498db',
            fillOpacity: 0.05
        }).addTo(map);

        let homeMarker = L.circleMarker([homeLat, homeLon], {
            radius: 7,
            color: '#e74c3c',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 3
        }).addTo(map).bindTooltip("Home Point", { permanent: false });

        // 데이터 캐시
        let flightHistory = {}; // icao -> [{lat, lon, alt, time, ...}]
        let markers = {};       // icao -> L.marker
        let polylines = {};     // icao -> L.polyline
        let selectedIcao = null;

        // 세모 모양 SVG 아이콘 생성
        function createTriangleIcon(heading, color) {
            const angle = heading || 0;
            const svg = `
            <svg width="20" height="20" viewBox="0 0 20 20" style="transform: rotate(${angle}deg);">
                <polygon points="10,2 2,18 10,14 18,18" fill="${color}" stroke="#1e272c" stroke-width="1.5" />
            </svg>`;
            return L.divIcon({
                className: 'plane-marker-icon',
                html: svg,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
        }

        // 고도 변화율 계산 (상태 판별)
        function getStatus(history) {
            if (history.length < 2) return { color: '#2ecc71', text: 'Level / Cruise' };
            const p0 = history[Math.max(0, history.length - 4)];
            const p1 = history[history.length - 1];
            const dt = (p1.time - p0.time) / 1000;
            if (dt <= 0) return { color: '#2ecc71', text: 'Level / Cruise' };
            
            const vsFpm = ((p1.alt - p0.alt) / dt) * 60;
            if (vsFpm > 150) return { color: '#f1c40f', text: `Climbing (+${Math.round(vsFpm)} fpm)` };
            if (vsFpm < -150) return { color: '#3498db', text: `Descending (${Math.round(vsFpm)} fpm)` };
            return { color: '#2ecc71', text: 'Level / Cruise' };
        }

        // 실시간 비동기 데이터 갱신 (화면 깜빡임 없음)
        async function fetchFlightData() {
            try {
                const radiusNm = 54; // 100km
                const res = await fetch(`https://api.adsb.lol/v2/point/${homeLat.toFixed(4)}/${homeLon.toFixed(4)}/${radiusNm}`);
                if (!res.ok) return;
                const data = await res.json();
                const planes = data.ac || [];
                const now = Date.now();
                const currentIcaos = new Set();

                planes.forEach(ac => {
                    const icao = ac.hex ? ac.hex.trim().toUpperCase() : null;
                    const callsign = ac.flight ? ac.flight.trim() : null;
                    if (!icao || ac.lat == null || ac.lon == null || !callsign) return;

                    currentIcaos.add(icao);
                    const alt = (ac.alt_baro === "ground" || ac.alt_baro == null) ? 0 : ac.alt_baro;
                    const spd = ac.gs || 0;
                    const heading = ac.track || 0;
                    const type = ac.t || "Unknown";

                    if (!flightHistory[icao]) {
                        flightHistory[icao] = [];
                        // 30초 이전 가상 꼬리선 보간
                        if (alt > 0 && spd > 100) {
                            const rad = heading * Math.PI / 180;
                            const backRad = (rad + Math.PI) % (2 * Math.PI);
                            [30, 15].forEach(pastSec => {
                                const distKm = (spd * pastSec / 3600.0) * 1.852;
                                const d = distKm / 6371.0;
                                const pLat = Math.asin(Math.sin(ac.lat * Math.PI / 180) * Math.cos(d) +
                                             Math.cos(ac.lat * Math.PI / 180) * Math.sin(d) * Math.cos(backRad));
                                const pLon = (ac.lon * Math.PI / 180) + Math.atan2(
                                    Math.sin(backRad) * Math.sin(d) * Math.cos(ac.lat * Math.PI / 180),
                                    Math.cos(d) - Math.sin(ac.lat * Math.PI / 180) * Math.sin(pLat)
                                );
                                flightHistory[icao].push({
                                    lat: pLat * 180 / Math.PI,
                                    lon: pLon * 180 / Math.PI,
                                    alt: alt,
                                    time: now - (pastSec * 1000)
                                });
                            });
                        }
                    }

                    flightHistory[icao].push({
                        lat: ac.lat,
                        lon: ac.lon,
                        alt: alt,
                        spd: spd,
                        heading: heading,
                        callsign: callsign,
                        type: type,
                        time: now
                    });

                    // 15분 이상 경과된 항적 가지치기
                    flightHistory[icao] = flightHistory[icao].filter(p => now - p.time <= 900000);
                    if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                    const hist = flightHistory[icao];
                    const status = getStatus(hist);

                    // 1. 마커 위치/아이콘 갱신 (재성성이 아닌 위치만 부드럽게 이동)
                    const icon = createTriangleIcon(heading, status.color);
                    if (markers[icao]) {
                        markers[icao].setLatLng([ac.lat, ac.lon]);
                        markers[icao].setIcon(icon);
                    } else {
                        const m = L.marker([ac.lat, ac.lon], { icon: icon }).addTo(map);
                        m.bindTooltip(`${callsign} (${alt.toLocaleString()} ft)`, { direction: 'top' });
                        m.on('click', () => {
                            selectedIcao = icao;
                            updateTelemetry(hist[hist.length - 1], status.text);
                        });
                        markers[icao] = m;
                    }

                    // 2. 꼬리선 갱신
                    const latlngs = hist.map(pt => [pt.lat, pt.lon]);
                    if (polylines[icao]) {
                        polylines[icao].setLatLngs(latlngs);
                        polylines[icao].setStyle({ color: status.color });
                    } else {
                        polylines[icao] = L.polyline(latlngs, {
                            color: status.color,
                            weight: 2.5,
                            opacity: 0.8
                        }).addTo(map);
                    }

                    if (selectedIcao === icao) {
                        updateTelemetry(hist[hist.length - 1], status.text);
                    }
                });

                // 감지 범위를 벗어난 기체 정리
                Object.keys(markers).forEach(icao => {
                    if (!currentIcaos.has(icao)) {
                        map.removeLayer(markers[icao]);
                        map.removeLayer(polylines[icao]);
                        delete markers[icao];
                        delete polylines[icao];
                        delete flightHistory[icao];
                    }
                });

            } catch (err) {
                console.error("ADS-B Fetch Error:", err);
            }
        }

        function updateTelemetry(latest, statusText) {
            document.getElementById('tel-callsign').innerText = latest.callsign;
            document.getElementById('tel-alt').innerText = `${latest.alt.toLocaleString()} ft`;
            document.getElementById('tel-spd').innerText = `${Math.round(latest.spd)} kts`;
            document.getElementById('tel-type').innerText = latest.type;
            document.getElementById('tel-status').innerText = statusText;
        }

        // 지도 더블클릭 이벤트: 홈포인트 재설정
        map.on('dblclick', function(e) {
            homeLat = e.latlng.lat;
            homeLon = e.latlng.lng;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);
            
            // 기존 항적 및 마커 초기화 후 재스캔
            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {};
            polylines = {};
            flightHistory = {};
            selectedIcao = null;
            document.getElementById('tel-callsign').innerText = 'Scanning new area...';
            
            fetchFlightData();
        });

        // 8초 주기로 비동기 데이터 갱신 (지도는 가만히 있고 데이터만 바뀜)
        fetchFlightData();
        setInterval(fetchFlightData, 8000);
    </script>
</body>
</html>
"""

components.html(radar_html, height=760, scrolling=False)
