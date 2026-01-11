import streamlit as st
import openai
import easyocr
from PIL import Image
import numpy as np
import sqlite3
from datetime import datetime
import json
from streamlit_mic_recorder import speech_to_text
import requests

# ==========================================
# 1. 基础配置
# ==========================================
DEEPSEEK_API_KEY = "sk-9e305b3990ac4ddc8819da6072444544"
client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

if 'active_tab' not in st.session_state: st.session_state.active_tab = "🥗 餐厅"
if 'travel_chat_history' not in st.session_state: st.session_state.travel_chat_history = []
if 'current_plan' not in st.session_state: st.session_state.current_plan = ""

st.set_page_config(page_title="智生活", page_icon="🌟", layout="wide")

# 高德地图配置
AMAP_KEY = "b609ca55fb8d7dc44546632460d0e93a"  

def get_amap_info(address):
    """获取目的地的城市代码、经纬度和实时天气"""
    try:
        # 1. 地理编码：查地址
        geo_url = f"https://restapi.amap.com/v3/geocode/geo?address={address}&key={AMAP_KEY}"
        geo_data = requests.get(geo_url).json()
        
        if geo_data['status'] == '1' and geo_data['geocodes']:
            # 优先匹配更出名的旅游城市（针对同名地点优化）
            location = geo_data['geocodes'][0]
            adcode = location['adcode']      
            lon_lat = location['location']    
            formatted_address = location['formatted_address'] # 获取详细地址
            
            # 2. 查询实时天气
            weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={AMAP_KEY}"
            weather_data = requests.get(weather_url).json()
            real_weather = "暂无天气数据"
            if weather_data['status'] == '1' and weather_data['lives']:
                w = weather_data['lives'][0]
                real_weather = f"{w['weather']}，气温{w['temperature']}℃，风力{w['windpower']}级"
            
            return {
                "full_address": formatted_address,
                "weather": real_weather,
                "location": lon_lat
            }
    except: return None
    return None

# ==========================================
# 2. 数据库逻辑
# ==========================================
def init_db():
    with sqlite3.connect('history.db') as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS records (type TEXT, content TEXT, time TEXT)')

def save_record(rtype, content):
    with sqlite3.connect('history.db') as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO records VALUES (?, ?, ?)", (rtype, str(content), now))

@st.cache_resource
def get_ocr_reader():
    return easyocr.Reader(['ch_sim', 'en'])

def get_ocr_text(image):
    img_np = np.array(Image.open(image))
    result = get_ocr_reader().readtext(img_np, detail=0)
    return " ".join(result)

# ==========================================
# 3. 终极 CSS（整合去红边、固定头部、打字机、录音按钮美化）
# ==========================================
st.markdown("""
<style>
    /* 6. 录音组件深度美化：消除白色长条 */
    /* 强制定位录音插件的容器，使其宽度自适应内容而非铺满整行 */
    [data-testid="stVerticalBlock"] div:has(iframe[title="streamlit_mic_recorder.speech_to_text"]) {
        width: fit-content !important;
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }

    /* 强制调整 iframe 窗口本身的大小 */
    iframe[title="streamlit_mic_recorder.speech_to_text"] {
        width: 160px !important; /* 调整为你按钮文字的大致宽度 */
        height: 60px !important;
        border: none !important;
        background: transparent !important;
    }
    /* 1. 隐藏官方元素 */
    header, footer, .stDeployButton, [data-testid="stHeader"] { display: none !important; }
    .stApp { background-color: #f8f9fb !important; }

    /* 2. 主内容区顶部预留位 */
    .main .block-container {
        padding-top: 240px !important; 
        padding-bottom: 2rem !important; 
        max-width: 800px !important; margin: auto;
    }

    /* 3. 固定头部容器 */
    .fixed-header {
        position: fixed !important; top: 0px !important; left: 0px !important; width: 100% !important;
        background-color: white !important; box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important;
        z-index: 999999 !important; padding: 30px 0 35px 0 !important; text-align: center;
    }

    /* 4. 导航按钮间距与布局 */
    .fixed-header [data-testid="stHorizontalBlock"] {
        display: flex !important; flex-direction: row !important; justify-content: center !important;
        gap: 20px !important; max-width: 650px !important; margin: 0 auto !important;
    }

    /* 5. 按钮样式：去红边、蓝色高亮 */
    div.stButton > button {
        border-radius: 14px !important; height: 45px !important; font-weight: 600 !important;
        border: 0px solid transparent !important; outline: none !important; box-shadow: none !important;
    }
    div.stButton > button[kind="primary"] { background-color: #1E5EFF !important; color: white !important; }
    div.stButton > button[kind="secondary"] { background-color: #fcfcfc !important; color: #666 !important; border: 1px solid #f0f2f6 !important; }
    div.stButton > button:focus, div.stButton > button:active { outline: none !important; box-shadow: none !important; border: none !important; }

    /* 6. 录音组件美化 */
    iframe[title="streamlit_mic_recorder.speech_to_text"] { 
        height: 70px !important; 
        width: 100% !important; /* 改为 100%，由外面 st.columns 控制 */
        border: none !important; 
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 渲染标题与导航栏
# ==========================================
def render_fixed_header():
    st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
    st.markdown('<h1 style="margin:0; padding-bottom: 25px; color:#333; letter-spacing: 2px; font-size: 38px; font-weight: 800;">🤖 智生活服务助手</h1>', unsafe_allow_html=True)
    nav_col1, nav_col2, nav_col3 = st.columns(3)
    with nav_col1:
        if st.button("🥗 餐厅", key="h1", use_container_width=True, type="primary" if st.session_state.active_tab == "🥗 餐厅" else "secondary"):
            st.session_state.active_tab = "🥗 餐厅"; st.rerun()
    with nav_col2:
        if st.button("🚗 出行", key="h2", use_container_width=True, type="primary" if st.session_state.active_tab == "🚗 出行" else "secondary"):
            st.session_state.active_tab = "🚗 出行"; st.rerun()
    with nav_col3:
        if st.button("📂 历史", key="h3", use_container_width=True, type="primary" if st.session_state.active_tab == "📂 历史" else "secondary"):
            st.session_state.active_tab = "📂 历史"; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 5. 主程序逻辑
# ==========================================
def main():
    init_db()
    render_fixed_header()
    
    if st.session_state.active_tab == "🥗 餐厅":
        st.markdown('<h3 style="font-size: 24px; color: #444; margin-bottom: 10px;">🥗 智能餐厅</h3>', unsafe_allow_html=True)
        with st.container(border=True):
            goal = st.text_input("健康需求", placeholder="例如：海鲜过敏、控糖", key="rest_goal")
            file = st.file_uploader("上传菜单照片", type=['jpg', 'png', 'jpeg'])
            if st.button("🚀 开始分析成分", use_container_width=True, key="do_ocr"):
                if file:
                    with st.spinner("智生活分析中..."):
                        menu_text = get_ocr_text(file)
                        ph = st.empty(); full_res = ""
                        response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": f"目标：{goal}。菜单：{menu_text}。请检查风险并推荐。"}],
                            stream=True 
                        )
                        for chunk in response:
                            if chunk.choices[0].delta.content:
                                full_res += chunk.choices[0].delta.content
                                ph.markdown(full_res + "▌")
                        ph.markdown(full_res)
                        save_record("餐饮识别", full_res)

    elif st.session_state.active_tab == "🚗 出行":
        st.markdown('<h3 style="font-size: 24px; color: #444; margin-bottom: 10px;">🚗 智能出行规划</h3>', unsafe_allow_html=True)
        
        with st.container(border=True):
            st.write("🎤 **语音录入需求**：")
            
            # 使用更小的比例，比如 0.2，让第一列尽可能窄
            col_mic, col_empty = st.columns([0.2, 1.9]) 
            
            with col_mic:
                v_text = speech_to_text(
                    language='zh', 
                    start_prompt="🎤 点击录制需求", 
                    stop_prompt="停止录音", 
                    just_once=True, 
                    key="travel_mic_final_fixed"
                )
            
            # 紧跟在录音按钮下方的输入框
            query = st.text_input(
                "您的想法", 
                value=v_text if v_text else "", 
                placeholder="例如：这周末带孩子去瓦屋山玩",
                key="travel_query_input"
            )
            
            if st.button("🌟 生成/修改精准行程", use_container_width=True, key="btn_plan_pro"):
                if query:
                    with st.spinner("智生活正在校准地理位置与实时天气..."):
                        # --- 步骤 1：提取干净地名 ---
                        extract_prompt = f"请从这段话中提取出目的地景点名称：'{query}'。注意：1. 如果该景点有多个同名地点，请返回全国最知名的那个旅游景区全称（例如：瓦屋山 -> 四川眉山瓦屋山国家森林公园）。2. 只需返回地名，不要任何解释。"
                        extract_res = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": extract_prompt}]
                        )
                        clean_dest = extract_res.choices[0].message.content.strip()

                        # --- 步骤 2：调用高德 API ---
                        amap_data = get_amap_info(clean_dest)
                        
                        if amap_data:
                            st.info(f"📍 已为您定位到：**{amap_data['full_address']}**")
                            st.success(f"🌦️ 实时天气：{amap_data['weather']}")
                            
                            # --- 步骤 3：生成行程 ---
                            ph = st.empty()
                            full_content = ""
                            prompt_with_real_data = f"【真实背景数据】目的地：{amap_data['full_address']}。当前天气：{amap_data['weather']}。【用户原始需求】{query}。请生成4日Markdown行程、穿衣建议及[点击购票](https://m.ctrip.com/webapp/ticket/ticket?keyword={clean_dest})链接。禁止使用<br>标签。"
                            
                            response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=[
                                    {"role": "system", "content": "你是一位拒绝虚假信息、严谨、贴心的旅游管家。"},
                                    {"role": "user", "content": prompt_with_real_data}
                                ],
                                stream=True
                            )
                            for chunk in response:
                                if chunk.choices[0].delta.content:
                                    full_content += chunk.choices[0].delta.content
                                    ph.markdown(full_content + "▌")
                            ph.markdown(full_content)
                            st.session_state.current_plan = full_content
                            save_record("行程规划", full_content)
                        else:
                            st.error("无法定位该目的地，请确认地名是否正确。")

        if st.session_state.current_plan:
            st.markdown("---")
            st.markdown(st.session_state.current_plan)

    elif st.session_state.active_tab == "📂 历史":
        st.header("📂 最近记录")
        with sqlite3.connect('history.db') as conn:
            import pandas as pd
            try:
                df = pd.read_sql_query("SELECT * FROM records ORDER BY time DESC LIMIT 15", conn)
                for _, row in df.iterrows():
                    with st.expander(f"🕒 {row['time']} · {row['type']}"):
                        st.markdown(row['content'])
            except: st.write("暂无记录")

if __name__ == "__main__":
    main()
