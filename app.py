import streamlit as st
from comtrade import Comtrade
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import tempfile
import numpy as np
from datetime import timedelta, datetime

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="COMTRADE Viewer", page_icon="⚡")

# --- CACHED DATA ENGINE ---
@st.cache_data(show_spinner="Processing COMTRADE binary data...")
def process_comtrade(cfg_content, dat_content, station_name):
    """
    Handles the heavy lifting of parsing the binary DAT file and applying 
    primary/secondary scaling. Cached to prevent re-processing on UI changes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path, d_path = os.path.join(tmpdir, "t.cfg"), os.path.join(tmpdir, "t.dat")
        with open(c_path, "w", encoding="utf-8") as f: f.write(cfg_content)
        with open(d_path, "wb") as f: f.write(dat_content)
        
        rec = Comtrade()
        rec.load(c_path, d_path)

    # Determine Start Date (Repairing common 1999/format issues)
    start_dt = rec.start_timestamp
    
    real_times = [start_dt + timedelta(seconds=float(t)) for t in rec.time]
    df_p = pd.DataFrame({"DateTime": real_times})
    df_s = pd.DataFrame({"DateTime": real_times})

    # Process Analogs
    for i in range(len(rec.analog)):
        cid = rec.analog_channel_ids[i]
        raw_val = np.array(rec.analog[i])
        p, s = rec.cfg.analog_channels[i].primary, rec.cfg.analog_channels[i].secondary
        df_s[cid] = raw_val
        df_p[cid] = (raw_val * (p / s)) / 1000.0 if s != 0 else raw_val

    # Process Digitals & Activity Check
    digital_meta = []
    for i in range(len(rec.status)):
        sid = rec.status_channel_ids[i]
        data = np.array(rec.status[i])
        df_p[sid] = df_s[sid] = data
        is_empty = not (np.any(data != data[0]) or data[0] == 1)
        digital_meta.append({"id": sid, "label": f"[EMPTY] {sid}" if is_empty else sid, "empty": is_empty})

    df_p.set_index("DateTime", inplace=True)
    df_s.set_index("DateTime", inplace=True)
    
    return df_p, df_s, rec.analog_channel_ids, digital_meta, start_dt, (rec.time[1]-rec.time[0])

# --- UI LOGIC ---
st.title("⚡ COMTRADE Viewer")

uploaded_files = st.file_uploader(
    "Upload COMTRADE Bundle (.CFG, .DAT required; .HDR, .INF optional)", 
    type=["cfg", "dat", "hdr", "inf"], 
    accept_multiple_files=True
)

if uploaded_files:
    f_map = {f.name.split('.')[-1].lower(): f for f in uploaded_files}

    if "cfg" in f_map and "dat" in f_map:
        try:
            # Metadata Extraction
            hdr_text = f_map["hdr"].getvalue().decode("utf-8", errors="ignore") if "hdr" in f_map else ""
            inf_text = f_map["inf"].getvalue().decode("utf-8", errors="ignore") if "inf" in f_map else ""
            
            cfg_raw = f_map["cfg"].getvalue().decode("utf-8", errors="ignore")
            cfg_lines = cfg_raw.splitlines()
            station = cfg_lines[0].split(',')[0]

            # Trigger Cached Processing
            df_p, df_s, analog_ids, dig_meta, start_time, sample_period = process_comtrade(
                cfg_raw, f_map["dat"].getvalue(), station
            )

            st.success(f"Loaded Station: {station} | Event Time: {start_time}")
            
            # Metadata Display
            if hdr_text or inf_text:
                c1, c2 = st.columns(2)
                if hdr_text: 
                    with c1: 
                        with st.expander("📄 Header Info"): st.text(hdr_text)
                if inf_text: 
                    with c2: 
                        with st.expander("ℹ️ Extended Info"): st.text(inf_text)

            t_freq, t_wave, t_logic = st.tabs(["📉 Frequency", "📊 Waveforms", "🚦 Digitals"])

            with t_freq:
                f_ref = st.selectbox("Frequency Reference Channel:", analog_ids, index=min(4, len(analog_ids)-1))
                y = df_s[f_ref].values
                cross = np.where(np.diff(np.sign(y)) > 0)[0]
                if len(cross) > 1:
                    ts = [idx*sample_period - y[idx]*sample_period/(y[idx+1]-y[idx]) for idx in cross]
                    f_val = 1.0 / np.diff(ts)
                    f_t = [start_time + timedelta(seconds=t) for t in ts[1:]]
                    fig_f = go.Figure(go.Scatter(x=f_t, y=f_val, line=dict(color="#00FF00")))
                    fig_f.update_layout(template="plotly_dark", yaxis_title="Hz", yaxis_range=[48, 52])
                    st.plotly_chart(fig_f, use_container_width=True)

            with t_wave:
                col_a, col_b = st.columns(2)
                mode = col_a.radio("Units:", ["Primary (kV/A)", "Secondary (V/A)"], horizontal=True)
                rms = col_b.toggle("Show RMS (1-Cycle Window)")
                
                curr_df = df_p if "Primary" in mode else df_s
                sel_analog = st.multiselect("Select Channels:", analog_ids, default=analog_ids[:3])
                
                if sel_analog:
                    fig_w = go.Figure()
                    for c in sel_analog:
                        y_plot = curr_df[c]
                        if rms:
                            win = int(0.02 / sample_period)
                            y_plot = y_plot.pow(2).rolling(window=max(1, win)).mean().apply(np.sqrt)
                        fig_w.add_trace(go.Scatter(x=curr_df.index, y=y_plot, name=c))
                    
                    fig_w.update_layout(
                        template="plotly_dark", height=650, hovermode="x unified",
                        yaxis=dict(autorange=True, fixedrange=False),
                        uirevision='constant'
                    )
                    st.plotly_chart(fig_w, use_container_width=True, config={'doubleClick': 'reset+autosize'})

            with t_logic:
                all_labels = [d['label'] for d in dig_meta]
                active_labels = [d['label'] for d in dig_meta if not d['empty']]
                sel_labels = st.multiselect("Select Digital Signals:", all_labels, default=active_labels[:8])
                
                sel_digs = [l.replace("[EMPTY] ", "") for l in sel_labels]
                if sel_digs:
                    evts = []
                    for d in sel_digs:
                        s = df_p[d]
                        diff = s.diff().fillna(0)
                        up, down = s.index[diff == 1], s.index[diff == -1]
                        if s.iloc[0] == 1: up = up.insert(0, s.index[0])
                        if s.iloc[-1] == 1: down = down.append(pd.Index([s.index[-1]]))
                        for start, end in zip(up, down):
                            evts.append(dict(Signal=d, Start=start, Finish=end))
                    if evts:
                        fig_l = px.timeline(pd.DataFrame(evts), x_start="Start", x_end="Finish", y="Signal", color_discrete_sequence=["#FFA500"])
                        fig_l.update_layout(template="plotly_dark", height=400)
                        st.plotly_chart(fig_l, use_container_width=True)

        except Exception as e:
            st.error(f"Critical Error: {str(e)}")
    else:
        st.warning("Missing .CFG or .DAT file in upload.")