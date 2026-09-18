import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 여백 및 상하 스크롤바 제거
st.markdown("""
<style>
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)

# 순수 프론트엔드 단일 페이지:
# 1. Leaflet 지도를 최초 1회만 로드
# 2. CORS 우회 프록시(allorigins)를 통해 8초마다 adsb.lol 데이터를 백그라운드 수신
# 3. 지도 파괴 없이 마커 좌표(.setLatLng)와 선만 부드럽게 갱신 (st.rerun 없음 = 깜빡임 원천 차단)
# 4. 더블클릭 시 홈포인트 및 100km 원형 즉시 이동
radar_standalone_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        #map { height: calc(100vh - 90px); width: 100%; background: #e5e9ec; }
        .header-bar {
            height: 38px; background: #1e272c; color: #ecf0f1; padding: 0 12px;
            display: flex; justify-content: space-between; align-items: center; font-size: 12px;
        }
        .legend-item { display: inline-flex; align-items: center; margin-left: 10px; }
        .legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }
        .telemetry-bar {
            height: 52px; background: #ffffff; border-top: 1px solid #dcdde1; padding: 4px 12px;
            display: flex; align-items: center; gap: 8px; overflow-x: auto; font-size: 12px; white-space: nowrap;
        }
        .badge { background: #f1f2f6; padding: 4px 8px; border-radius: 4px; color: #2f3542; border: 1px solid #e4e7eb; }
        .badge b { color: #1e272c; }
        .plane-marker-icon {
            display: flex; justify-content: center; align-items: center;
            transition: transform 0.4s linear;
        }
    </style>
</head>
<body>
    <div class="header-bar">
        <span>🎯 <b>100km Coverage Radar</b> (Double-click/tap map to relocate)</span>
        <div>
            <span class="legend-item"><span class="legend-dot" style="background:#2ecc71;"></span>Level</span>
            <span class="legend-item"><span class="legend-dot" style="background:#f1c40f;"></span>Climb</span>
            <span class="legend-item"><span class="legend-dot" style="background:#3498db;"></span>Desc</span>
        </div>
    </div>

    <div id="map"></div>

    <div class="telemetry-bar">
        <span class="badge">Plane: <b id="tel-callsign">Click a plane</b></span>
        <span class="badge">Model: <b id="tel-type">-</b></span>
        <span class="badge">Alt: <b id="tel-alt">-</b></span>
        <span class="badge">Speed: <b id="tel-spd">-</b></span>
        <span class="badge">Status: <b id="tel-status">-</b></span>
        <span class="badge">Count: <b id="tel-count">0</b></span>
    </div>

    <script>
        // 기본 좌표 (서울)
        let homeLat = 37.5665;
        let homeLon = 126.9780;

        const map = L.map('map', {
            center: [homeLat, homeLon],
            zoom: 9,
            zoomControl: false,
            doubleClickZoom: false
        });
        L.control.zoom({ position: 'topright' }).addTo(map);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '© OpenStreetMap'
        }).addTo(map);

        // 100km 반경 원형 및 홈포인트 마커
        let radarCircle = L.circle([homeLat, homeLon], {
            radius: 100000,
            color: '#2980b9',
            weight: 2,
            fillColor: '#3498db',
            fillOpacity: 0.04
        }).addTo(map);

        let homeMarker = L.circleMarker([homeLat, homeLon], {
            radius: 7,
            color: '#c0392b',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 3
        }).addTo(map).bindTooltip("Home point");

        // 런타임 저장소 (DOM을 지우지 않고 마커를 계속 재사용)
        let flightHistory = {};
        let markers = {};
        let polylines = {};
        let selectedIcao = null;

        // 세모 모양 SVG 아이콘 (상태 색상 + 기수 각도 회전)
        function getTriangleIcon(heading, color) {
            const deg = heading || 0;
            const svg = `
            <svg width="20" height="20" viewBox="0 0 20 20" style="transform: rotate(${deg}deg); filter: drop-shadow(0 1px 2px rgba(0,0,0,0.35));">
                <polygon points="10,1 2,19 10,14 18,19" fill="${color}" stroke="#1e272c" stroke-width="1.5" />
            </svg>`;
            return L.divIcon({
                className: 'plane-marker-icon',
                html: svg,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
        }

        // 고도 변화율 판별
        function checkStatus(hist) {
            if (hist.length < 2) return { color: '#2ecc71', text: 'Level / Cruise' };
            const p0 = hist[Math.max(0, hist.length - 4)];
            const p1 = hist[hist.length - 1];
            const dt = (p1.time - p0.time) / 1000;
            if (dt <= 0) return { color: '#2ecc71', text: 'Level / Cruise' };

            const vsFpm = ((p1.alt - p0.alt) / dt) * 60;
            if (vsFpm > 150) return { color: '#f1c40f', text: `Climbing (+${Math.round(vsFpm)} fpm)` };
            if (vsFpm < -150) return { color: '#3498db', text: `Descending (${Math.round(vsFpm)} fpm)` };
            return { color: '#2ecc71', text: 'Level / Cruise' };
        }

        // 데이터 비동기 수신 (CORS 차단 방지)
        async function fetchFlightData() {
            const radiusNm = 54; // 100km
            const targetUrl = `https://api.adsb.lol/v2/point/${homeLat.toFixed(4)}/${homeLon.toFixed(4)}/${radiusNm}`;
            
            let data = null;
            // 1차: 직접 fetch 시도
            try {
                const res = await fetch(targetUrl, { mode: 'cors' });
                if (res.ok) data = await res.json();
            } catch (e) {
                // 2차: iframe CORS 차단 시 공용 프록시 폴백
                try {
                    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(targetUrl)}`;
                    const resProxy = await fetch(proxyUrl);
                    if (resProxy.ok) data = await resProxy.json();
                } catch (err) {}
            }

            if (!data || !data.ac) return;

            const planes = data.ac;
            const now = Date.now();
            const currentIcaos = new Set();
            document.getElementById('tel-count').innerText = planes.length;

            planes.forEach(ac => {
                const icao = ac.hex ? ac.hex.trim().toUpperCase() : null;
                const callsign = ac.flight ? ac.flight.trim() : null;
                if (!icao || ac.lat == null || ac.lon == null || !callsign) return;

                currentIcaos.add(icao);
                const alt = (ac.alt_baro === "ground" || ac.alt_baro == null) ? 0 : ac.alt_baro;
                const spd = ac.gs || 0;
                const heading = ac.track || 0;
                const type = ac.t || "Unknown";

                // 최초 감지 시 30초 이전 가상 꼬리선 생성
                if (!flightHistory[icao]) {
                    flightHistory[icao] = [];
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
                    lat: ac.lat, lon: ac.lon, alt: alt, spd: spd,
                    heading: heading, callsign: callsign, type: type, time: now
                });

                // 최근 15분(900초) 슬라이딩 윈도우
                flightHistory[icao] = flightHistory[icao].filter(p => now - p.time <= 900000);
                if (flightHistory[icao].length > 120) flightHistory[icao].shift();

                const hist = flightHistory[icao];
                const status = checkStatus(hist);

                // 마커 객체가 이미 있으면 setLatLng으로 위치만 살짝 이동 (지도를 다시 안 그림)
                const newIcon = getTriangleIcon(heading, status.color);
                if (markers[icao]) {
                    markers[icao].setLatLng([ac.lat, ac.lon]);
                    markers[icao].setIcon(newIcon);
                } else {
                    const m = L.marker([ac.lat, ac.lon], { icon: newIcon }).addTo(map);
                    m.bindTooltip(`${callsign} (${alt.toLocaleString()} ft)`, { direction: 'top' });
                    m.on('click', () => {
                        selectedIcao = icao;
                        showTelemetry(hist[hist.length - 1], status.text);
                    });
                    markers[icao] = m;
                }

                // 꼬리선 갱신 (기존 Polyline의 좌표 배열만 교체)
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
                    showTelemetry(hist[hist.length - 1], status.text);
                }
            });

            // 반경을 벗어난 기체만 선택 제거
            Object.keys(markers).forEach(icao => {
                if (!currentIcaos.has(icao)) {
                    map.removeLayer(markers[icao]);
                    map.removeLayer(polylines[icao]);
                    delete markers[icao];
                    delete polylines[icao];
                    delete flightHistory[icao];
                }
            });
        }

        function showTelemetry(latest, statusText) {
            document.getElementById('tel-callsign').innerText = latest.callsign;
            document.getElementById('tel-alt').innerText = `${latest.alt.toLocaleString()} ft`;
            document.getElementById('tel-spd').innerText = `${Math.round(latest.spd)} kts`;
            document.getElementById('tel-type').innerText = latest.type;
            document.getElementById('tel-status').innerText = statusText;
        }

        // 지도 더블클릭/더블탭 시 홈포인트 이동 (깜빡임 없이 레이더 원만 슥 이동)
        map.on('dblclick', function(e) {
            homeLat = e.latlng.lat;
            homeLon = e.latlng.lng;
            homeMarker.setLatLng([homeLat, homeLon]);
            radarCircle.setLatLng([homeLat, homeLon]);

            // 새 구역 탐색을 위해 마커 정리 후 즉시 호출
            Object.values(markers).forEach(m => map.removeLayer(m));
            Object.values(polylines).forEach(p => map.removeLayer(p));
            markers = {};
            polylines = {};
            flightHistory = {};
            selectedIcao = null;
            document.getElementById('tel-callsign').innerText = 'Scanning new area...';

            fetchFlightData();
        });

        // 8초 타이머 비동기 반복 (브라우저가 지도를 절대 새로고침하지 않음)
        fetchFlightData();
        setInterval(fetchFlightData, 8000);
    </script>
</body>
</html>
"""

components.html(radar_standalone_html, height=720, scrolling=False)
