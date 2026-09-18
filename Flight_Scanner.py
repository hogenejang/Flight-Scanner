import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import time
import math
import csv
import os
import plotly.graph_objects as go

# 페이지 기본 설정
st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide"
)

AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
LOCAL_AIRLINE_FILE = "airlines_db.dat"

# 최적화를 위한 최대 보존 시간 (15분 = 900초) 및 최대 포인트 수
MAX_HISTORY_SEC = 900
MAX_HISTORY_POINTS = 120

# 1. 전 세계 항공사 DB 캐싱
@st.cache_data(ttl=86400)
def load_global_airlines():
    data_text = ""
    if os.path.exists(LOCAL_AIRLINE_FILE):
        try:
            with open(LOCAL_AIRLINE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                data_text = f.read()
        except Exception:
            pass

    if not data_text:
        try:
            res = requests.get(AIRLINES_DATA_URL, timeout=10)
            if res.status_code == 200:
                data_text = res.text
                with open(LOCAL_AIRLINE_FILE, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(data_text)
        except Exception:
            pass

    db = {}
    if data_text:
        reader = csv.reader(data_text.strip().splitlines())
        for row in reader:
            if len(row) >= 7:
                airline_name = row[1].strip()
                icao_code = row[4].strip().upper()
                country = row[6].strip()
                if len(icao_code) == 3 and icao_code != "\\N":
                    db[icao_code] = {"name": airline_name, "country": country}
    return db

airlines_db = load_global_airlines()

def get_airline_info(callsign):
    if not callsign or len(callsign) < 3:
        return "Private / General", "N/A"
    code = callsign[:3].upper()
    if code in airlines_db:
        return airlines_db[code]["name"], airlines_db[code]["country"]
    return "Unknown Airline", "Unknown"

# 2. 세션 상태 초기화
if "flight_history" not in st.session_state:
    st.session_state.flight_history = {}
if "home_coords" not in st.session_state:
    st.session_state.home_coords = (37.5665, 126.9780)

# 사이드바 제어 패널
with st.sidebar:
    st.title("⚙️ Radar Settings")
    st.markdown("100 km Radius Flight Scanner")
    
    lat_input = st.number_input("Home Latitude", value=st.session_state.home_coords[0], format="%.4f")
    lon_input = st.number_input("Home Longitude", value=st.session_state.home_coords[1], format="%.4f")
    
    if st.button("📍 Update Home Point", use_container_width=True):
        st.session_state.home_coords = (lat_input, lon_input)
        st.session_state.flight_history.clear()
        st.rerun()

    # 지도에 표시할 항적선 표시 기간 (최대 15분까지 지원)
    display_limit_min = st.select_slider(
        "Map Track Tail Length (Minutes)",
        options=[1, 3, 5, 10, 15],
        value=5
    )
    display_limit_sec = display_limit_min * 60

    st.markdown("---")
    st.markdown("""
    **Aircraft Status Legend:**
    * 🟢 **Level / Cruise / Taxi**: Stable Altitude
    * 🟡 **Climbing**: > +150 ft/min
    * 🔵 **Descending**: < -150 ft/min
    """)

# 3. adsb.lol 실시간 데이터 조회
def fetch_live_flights(home_lat, home_lon):
    radius_nm = 54  # 100km
    url = f"https://api.adsb.lol/v2/point/{home_lat:.4f}/{home_lon:.4f}/{radius_nm}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get('ac', [])
    except Exception:
        pass
    return []

# 실시간 데이터 수집 및 롤링 윈도우 누적
current_time = time.time()
raw_aircraft = fetch_live_flights(*st.session_state.home_coords)

for ac in raw_aircraft:
    icao = ac.get('hex', '').strip().upper()
    callsign = ac.get('flight', '').strip()
    lat = ac.get('lat')
    lon = ac.get('lon')

    if not icao or lat is None or lon is None or not callsign:
        continue

    alt_ft = ac.get('alt_baro')
    on_ground = (alt_ft == "ground" or alt_ft is None)
    alt_val = 0 if on_ground else alt_ft

    spd_kts = ac.get('gs', 0.0) or 0.0
    true_track = ac.get('track', 0.0) or 0.0
    ac_type = ac.get('t', 'Unknown')
    airline_name, airline_country = get_airline_info(callsign)

    # 신규 기체 감지 시: 30초 이전 가상 꼬리선 초기화
    if icao not in st.session_state.flight_history:
        st.session_state.flight_history[icao] = []
        if not on_ground and spd_kts > 100:
            rad = math.radians(true_track)
            for past_sec in [30, 15]:
                dist_km = (spd_kts * past_sec / 3600.0) * 1.852
                d = dist_km / 6371.0
                back_b = (rad + math.pi) % (2 * math.pi)
                p_lat = math.asin(math.sin(math.radians(lat)) * math.cos(d) +
                                  math.cos(math.radians(lat)) * math.sin(d) * math.cos(back_b))
                p_lon = math.radians(lon) + math.atan2(
                    math.sin(back_b) * math.sin(d) * math.cos(math.radians(lat)),
                    math.cos(d) - math.sin(math.radians(lat)) * math.sin(p_lat)
                )
                st.session_state.flight_history[icao].append({
                    'time': current_time - past_sec, 'lat': math.degrees(p_lat), 'lon': math.degrees(p_lon),
                    'alt': alt_val, 'spd': spd_kts
                })

    st.session_state.flight_history[icao].append({
        'time': current_time, 'lat': lat, 'lon': lon,
        'alt': alt_val, 'spd': spd_kts, 'callsign': callsign,
        'track': true_track, 'type': ac_type, 'airline': airline_name,
        'country': airline_country, 'on_ground': on_ground
    })

# 슬라이딩 윈도우 데이터 정리 (최근 15분 초과 또는 과도한 포인트 큐 제거)
for icao in list(st.session_state.flight_history.keys()):
    # 1. 15분(900초) 지난 오래된 데이터 버림
    st.session_state.flight_history[icao] = [
        pt for pt in st.session_state.flight_history[icao] 
        if current_time - pt['time'] <= MAX_HISTORY_SEC
    ]
    # 2. 성능 최적화를 위해 최근 MAX_HISTORY_POINTS개만 유지
    if len(st.session_state.flight_history[icao]) > MAX_HISTORY_POINTS:
        st.session_state.flight_history[icao] = st.session_state.flight_history[icao][-MAX_HISTORY_POINTS:]
        
    if not st.session_state.flight_history[icao]:
        del st.session_state.flight_history[icao]

# 4. 화면 분할 렌더링
col_map, col_details = st.columns([7, 3])

def get_flight_status(hist):
    if len(hist) < 2:
        return "green", "Level / Cruise"
    recent = hist[-4:]
    p0, p1 = recent[0], recent[-1]
    dt = p1['time'] - p0['time']
    if dt <= 0:
        return "green", "Level / Cruise"
    vs_fpm = ((p1['alt'] - p0['alt']) / dt) * 60.0
    if vs_fpm > 150:
        return "orange", f"Climbing (+{vs_fpm:.0f} fpm)"
    elif vs_fpm < -150:
        return "blue", f"Descending ({vs_fpm:.0f} fpm)"
    return "green", "Level / Cruise"

with col_map:
    st.subheader("📡 Live Radar Map")
    
    m = folium.Map(
        location=st.session_state.home_coords,
        zoom_start=9,
        tiles="CartoDB positron"
    )

    # 100km 원형 경계선
    folium.Circle(
        location=st.session_state.home_coords,
        radius=100000,
        color="#2980b9",
        weight=2,
        fill=True,
        fill_opacity=0.04
    ).add_to(m)

    # 홈포인트 마커
    folium.Marker(
        st.session_state.home_coords,
        popup="Home Point",
        icon=folium.Icon(color="black", icon="crosshairs", prefix="fa")
    ).add_to(m)

    # 항공기 및 항적 표시
    for icao, hist in st.session_state.flight_history.items():
        if not hist:
            continue
        latest = hist[-1]
        color, status_text = get_flight_status(hist)

        # 사이드바에서 선택한 길이(초) 이내의 항적만 선으로 그림
        visible_hist = [pt for pt in hist if current_time - pt['time'] <= display_limit_sec]
        coords = [(pt['lat'], pt['lon']) for pt in visible_hist]
        if len(coords) > 1:
            folium.PolyLine(coords, color=color, weight=2.5, opacity=0.7).add_to(m)

        popup_html = f"""
        <b>Callsign:</b> {latest['callsign']}<br>
        <b>Airline:</b> {latest.get('airline', 'N/A')}<br>
        <b>Type:</b> {latest.get('type', 'N/A')}<br>
        <b>Alt:</b> {latest['alt']:,} ft<br>
        <b>Speed:</b> {latest['spd']:.0f} kts<br>
        <b>Status:</b> {status_text}
        """
        folium.CircleMarker(
            location=[latest['lat'], latest['lon']],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{latest['callsign']} ({latest['alt']:,} ft)"
        ).add_to(m)

    st_folium(m, width="100%", height=620)

with col_details:
    st.subheader("✈️ Flight Telemetry")
    
    active_planes = {
        f"{hist[-1]['callsign']} ({icao})": icao 
        for icao, hist in st.session_state.flight_history.items() if hist
    }

    if active_planes:
        selected_label = st.selectbox("Select Aircraft", options=list(active_planes.keys()))
        selected_icao = active_planes[selected_label]
        target_hist = st.session_state.flight_history[selected_icao]
        latest_data = target_hist[-1]
        _, trend_str = get_flight_status(target_hist)

        st.markdown(f"""
        * **Callsign:** `{latest_data['callsign']}`
        * **Airline:** {latest_data.get('airline', 'N/A')} ({latest_data.get('country', '')})
        * **Model:** `{latest_data.get('type', 'Unknown')}`
        * **Status:** {trend_str}
        * **Altitude:** **{latest_data['alt']:,} ft** ({latest_data['alt'] * 0.3048:,.0f} m)
        * **Ground Speed:** **{latest_data['spd']:.0f} kts** ({latest_data['spd'] * 1.852:.0f} km/h)
        * **Track Points Collected:** `{len(target_hist)}`
        """)

        # Plotly 차트: 현재 시점 기준 상대 시간(초 전)으로 계산하여 무한 롤링 표시
        x_relative = [int(pt['time'] - current_time) for pt in target_hist]
        y_alt = [pt['alt'] for pt in target_hist]
        y_spd = [pt['spd'] for pt in target_hist]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x_relative, 
            y=y_alt, 
            name="Alt (ft)", 
            mode="lines+markers",
            marker=dict(size=4),
            line=dict(color="#e74c3c", width=2)
        ))
        fig.add_trace(go.Scatter(
            x=x_relative, 
            y=y_spd, 
            name="Speed (kts)", 
            yaxis="y2", 
            mode="lines+markers",
            marker=dict(size=4),
            line=dict(color="#3498db", width=2)
        ))

        fig.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=25, b=10),
            yaxis=dict(title="Altitude (ft)"),
            yaxis2=dict(title="Speed (kts)", overlaying="y", side="right"),
            xaxis=dict(title="Timeline (Seconds Ago, 0 = Now)"),
            legend=dict(orientation="h", y=1.15, x=0.15)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No aircraft detected within 100km radius.")

if st.button("🔄 Refresh Radar Data", use_container_width=True):
    st.rerun()