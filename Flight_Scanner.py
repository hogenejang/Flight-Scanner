import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import time
import math
import csv
import os
import plotly.graph_objects as go

st.set_page_config(
    page_title="Live Flight Scanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

AIRLINES_DATA_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
LOCAL_AIRLINE_FILE = "airlines_db.dat"
MAX_HISTORY_SEC = 900
MAX_HISTORY_POINTS = 120

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

# 세션 상태 초기화
if "flight_history" not in st.session_state:
    st.session_state.flight_history = {}
if "home_coords" not in st.session_state:
    st.session_state.home_coords = (37.5665, 126.9780)
if "last_processed_click" not in st.session_state:
    st.session_state.last_processed_click = None

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ Radar Settings")
    st.info("💡 Tip: 지도 아무 곳이나 클릭/더블클릭하면 해당 위치로 홈포인트가 즉시 변경됩니다.")
    
    lat_input = st.number_input("Latitude", value=st.session_state.home_coords[0], format="%.4f")
    lon_input = st.number_input("Longitude", value=st.session_state.home_coords[1], format="%.4f")
    
    if st.button("📍 Set Coordinates Manually", use_container_width=True):
        st.session_state.home_coords = (lat_input, lon_input)
        st.session_state.flight_history.clear()
        st.rerun()

    display_limit_min = st.select_slider("Track Line Length (Min)", options=[1, 3, 5, 10, 15], value=5)
    display_limit_sec = display_limit_min * 60

    st.markdown("---")
    st.markdown("""
    **Status Legend:**
    * 🟢 **Level / Cruise / Taxi**
    * 🟡 **Climbing** (> +150 fpm)
    * 🔵 **Descending** (< -150 fpm)
    """)

def fetch_live_flights(home_lat, home_lon):
    radius_nm = 54
    url = f"https://api.adsb.lol/v2/point/{home_lat:.4f}/{home_lon:.4f}/{radius_nm}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get('ac', [])
    except Exception:
        pass
    return []

def get_flight_status(hist):
    if len(hist) < 2:
        return "#2ecc71", "Level / Cruise"
    recent = hist[-4:]
    p0, p1 = recent[0], recent[-1]
    dt = p1['time'] - p0['time']
    if dt <= 0:
        return "#2ecc71", "Level / Cruise"
    vs_fpm = ((p1['alt'] - p0['alt']) / dt) * 60.0
    if vs_fpm > 150:
        return "#f1c40f", f"Climbing (+{vs_fpm:.0f} fpm)"
    elif vs_fpm < -150:
        return "#3498db", f"Descending ({vs_fpm:.0f} fpm)"
    return "#2ecc71", "Level / Cruise"

# 데이터 수집 및 롤링 윈도우 처리
current_time = time.time()
raw_aircraft = fetch_live_flights(*st.session_state.home_coords)

for ac in raw_aircraft:
    icao = ac.get('hex', '').strip().upper()
    callsign = ac.get('flight', '').strip()
    lat, lon = ac.get('lat'), ac.get('lon')

    if not icao or lat is None or lon is None or not callsign:
        continue

    alt_ft = ac.get('alt_baro')
    on_ground = (alt_ft == "ground" or alt_ft is None)
    alt_val = 0 if on_ground else alt_ft

    spd_kts = ac.get('gs', 0.0) or 0.0
    true_track = ac.get('track', 0.0) or 0.0
    ac_type = ac.get('t', 'Unknown')
    airline_name, airline_country = get_airline_info(callsign)

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

for icao in list(st.session_state.flight_history.keys()):
    st.session_state.flight_history[icao] = [
        pt for pt in st.session_state.flight_history[icao] 
        if current_time - pt['time'] <= MAX_HISTORY_SEC
    ]
    if len(st.session_state.flight_history[icao]) > MAX_HISTORY_POINTS:
        st.session_state.flight_history[icao] = st.session_state.flight_history[icao][-MAX_HISTORY_POINTS:]
    if not st.session_state.flight_history[icao]:
        del st.session_state.flight_history[icao]

tab_map, tab_chart = st.tabs(["🗺️ Radar Map", "📊 Flight Telemetry"])

with tab_map:
    # API 키 제한 없는 OpenStreetMap 기본 타일
    m = folium.Map(
        location=st.session_state.home_coords,
        zoom_start=9,
        tiles="OpenStreetMap"
    )

    # 100km 원형 경계선
    folium.Circle(
        location=st.session_state.home_coords,
        radius=100000,
        color="#2980b9",
        weight=2,
        fill=True,
        fill_opacity=0.05
    ).add_to(m)

    # 홈포인트 십자가 마커
    folium.Marker(
        st.session_state.home_coords,
        tooltip="Home point (Double-click/tap anywhere to move)",
        icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")
    ).add_to(m)

    # 항공기 마커 및 항적선
    for icao, hist in st.session_state.flight_history.items():
        if not hist:
            continue
        latest = hist[-1]
        color_hex, status_text = get_flight_status(hist)

        visible_hist = [pt for pt in hist if current_time - pt['time'] <= display_limit_sec]
        coords = [(pt['lat'], pt['lon']) for pt in visible_hist]
        if len(coords) > 1:
            folium.PolyLine(coords, color=color_hex, weight=2.5, opacity=0.8).add_to(m)

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
            color=color_hex,
            fill=True,
            fill_color=color_hex,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"{latest['callsign']} ({latest['alt']:,} ft)"
        ).add_to(m)

    # 클릭/더블클릭 좌표 이벤트 수신 (last_clicked만 수신하여 깜빡임 최소화)
    map_state = st_folium(
        m, 
        width="100%", 
        height=520, 
        returned_objects=["last_clicked"]
    )

    # 지도 클릭 시 홈포인트 재설정 로직
    if map_state and map_state.get("last_clicked"):
        click_coords = (round(map_state["last_clicked"]["lat"], 4), round(map_state["last_clicked"]["lng"], 4))
        if click_coords != st.session_state.last_processed_click and click_coords != st.session_state.home_coords:
            st.session_state.last_processed_click = click_coords
            st.session_state.home_coords = click_coords
            st.session_state.flight_history.clear()
            st.rerun()

with tab_chart:
    active_planes = {
        f"{hist[-1]['callsign']} ({icao})": icao 
        for icao, hist in st.session_state.flight_history.items() if hist
    }

    if active_planes:
        selected_label = st.selectbox("Select Aircraft", options=list(active_planes.keys()), label_visibility="collapsed")
        selected_icao = active_planes[selected_label]
        target_hist = st.session_state.flight_history[selected_icao]
        latest_data = target_hist[-1]
        _, trend_str = get_flight_status(target_hist)

        st.write(f"✈️ **{latest_data['callsign']}** | {latest_data.get('airline', 'N/A')} ({latest_data.get('type', 'Unknown')})")
        st.write(f"• **Status:** {trend_str} | **Alt:** {latest_data['alt']:,} ft | **Speed:** {latest_data['spd']:.0f} kts")

        x_relative = [int(pt['time'] - current_time) for pt in target_hist]
        y_alt = [pt['alt'] for pt in target_hist]
        y_spd = [pt['spd'] for pt in target_hist]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x_relative, y=y_alt, name="Alt(ft)", line=dict(color="#e74c3c", width=2)))
        fig.add_trace(go.Scatter(x=x_relative, y=y_spd, name="Speed(kts)", yaxis="y2", line=dict(color="#3498db", width=2)))

        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=20, b=10),
            yaxis=dict(title="Alt (ft)"),
            yaxis2=dict(title="Speed (kts)", overlaying="y", side="right"),
            xaxis=dict(title="Seconds Ago (0=Now)"),
            legend=dict(orientation="h", y=1.2, x=0.1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No aircraft detected within 100km radius.")

# 하단 수동 갱신 버튼
if st.button("🔄 Refresh Radar Data", use_container_width=True):
    st.rerun()
