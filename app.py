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
import hashlib
import base64
from io import BytesIO
import plotly.express as px  # 新增：用于绘制柱状图
import plotly.graph_objects as go # 新增：用于绘制雷达图
import folium # 新增：用于地图
from streamlit_folium import st_folium # 新增：用于网页显示地图
import re
import time
# ==========================================
# 1. 基础配置
# ==========================================
DEEPSEEK_API_KEY = "sk-9e305b3990ac4ddc8819da6072444544"
client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

if 'active_tab' not in st.session_state: st.session_state.active_tab = "🥗 餐厅"
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'current_plan' not in st.session_state: st.session_state.current_plan = ""

st.set_page_config(page_title="智生活", page_icon="🌟", layout="wide", initial_sidebar_state="collapsed")

AMAP_KEY = "b609ca55fb8d7dc44546632460d0e93a"  

# ==========================================
# 2. 数据库逻辑
# ==========================================
def init_db():
    with sqlite3.connect('history.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT, nickname TEXT, allergies TEXT)''')
        conn.execute('CREATE TABLE IF NOT EXISTS records (username TEXT, type TEXT, content TEXT, time TEXT)')

def save_user_profile(username, nickname, allergies):
    with sqlite3.connect('history.db') as conn:
        conn.execute("UPDATE users SET nickname=?, allergies=? WHERE username=?", (nickname, allergies, username))

def get_user_data(username):
    with sqlite3.connect('history.db') as conn:
        c = conn.cursor()
        c.execute("SELECT nickname, allergies FROM users WHERE username=?", (username,))
        return c.fetchone()

def login_user(username, password):
    with sqlite3.connect('history.db') as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username =? AND password = ?', (username, hashlib.sha256(str.encode(password)).hexdigest()))
        return c.fetchone()

def create_user(username, password):
    with sqlite3.connect('history.db') as conn:
        try:
            conn.execute('INSERT INTO users(username,password,nickname,allergies) VALUES (?,?,?,?)', 
                         (username, hashlib.sha256(str.encode(password)).hexdigest(), username, ""))
            return True
        except: return False

def save_record(rtype, content):
    with sqlite3.connect('history.db') as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (st.session_state.username, rtype, str(content), now))

# ==========================================
# 3. 核心功能函数
# ==========================================
@st.cache_resource
def get_ocr_reader(): return easyocr.Reader(['ch_sim', 'en'])

def analyze_food_image_with_qwen(image_file, user_goal):
    encoded_image = base64.b64encode(image_file.getvalue()).decode('utf-8')
    qwen_client = openai.OpenAI(api_key="sk-3277028448bf47fb84a4dd96a1cb9e4e", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    # 强制要求返回 JSON 格式以便可视化
    prompt = f"""
    你是AI营养师。过敏原：{user_goal}。请分析图片中的菜品。
    要求：1.先给出文字分析建议。2.最后必须提供一个JSON格式的数据块，包含各菜品及其热量(kcal)，格式如下：
    DATA_START
    {{"items": ["菜名1", "菜名2"], "calories": [150, 300], "health_scores": [90, 60]}}
    DATA_END
    """
    response = qwen_client.chat.completions.create(
        model="qwen-vl-plus",
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}]}]
    )
    return response.choices[0].message.content

def get_amap_info(address):
    try:
        geo_url = f"https://restapi.amap.com/v3/geocode/geo?address={address}&key={AMAP_KEY}"
        res = requests.get(geo_url).json()
        if res['status'] == '1' and res['geocodes']:
            loc = res['geocodes'][0]
            w_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={loc['adcode']}&key={AMAP_KEY}"
            w_data = requests.get(w_url).json()
            weather = w_data['lives'][0] if w_data['status']=='1' else None
            return {"address": loc['formatted_address'], "weather": weather, "location": loc['location']}
    except: return None

# ==========================================
# 4. 可视化组件
# ==========================================
def show_meal_visuals(json_str):
    """将从文本中提取的JSON字符串转换为动态图表"""
    try:
        data = json.loads(json_str)
        st.markdown("### 📊 营养成分动态监测")
        v_col1, v_col2 = st.columns(2)
        
        with v_col1:
            # 动态柱状图：展示 AI 提取出的真实菜名和热量
            fig_bar = px.bar(
                x=data['items'], 
                y=data['calories'],
                labels={'x':'菜品', 'y':'热量 (kcal)'},
                title="实时热量对比",
                color=data['calories'],
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with v_col2:
            # 动态雷达图：展示 AI 给出的真实评分
            fig_radar = go.Figure(data=go.Scatterpolar(
                r=data['health_scores'],
                theta=['健康度','油脂控制','控糖度','饱腹感','安全性'],
                fill='toself',
                line_color='#1E5EFF'
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False, 
                title="综合营养画像"
            )
            st.plotly_chart(fig_radar, use_container_width=True)
        return True
    except Exception as e:
        print(f"数据解析失败: {e}")
        return False

def show_travel_visuals(info):
    """绘制地图和实时指标"""
    if info:
        st.markdown("### 🛰️ 目的地实时运行看板")
        m_col1, m_col2, m_col3 = st.columns(3)
        w = info['weather']
        m_col1.metric("当前天气", w['weather'] if w else "未知")
        m_col2.metric("实时气温", f"{w['temperature']}℃" if w else "未知")
        m_col3.metric("建议指数", "🌟 极佳" if "晴" in str(w) else "⚠️ 注意")

        # 渲染 Folium 地图
        lon, lat = map(float, info['location'].split(','))
        m = folium.Map(location=[lat, lon], zoom_start=13, tiles='OpenStreetMap')
        folium.Marker([lat, lon], popup=info['address'], icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
        st_folium(m, width=700, height=300)

# ==========================================
# 5. 样式与主逻辑
# ==========================================
st.markdown("""
<style>
    header, footer, [data-testid="stHeader"] { display: none !important; }
    .stApp { background-color: #f8f9fb !important; }
    .main .block-container { padding-top: 250px !important; padding-bottom: 120px !important; max-width: 900px !important; margin: auto; }
    .fixed-header { position: fixed !important; top: 0px !important; left: 0px !important; width: 100% !important; background-color: white !important; box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important; z-index: 999999 !important; padding: 30px 0 35px 0 !important; text-align: center; }
    div.stButton > button { border-radius: 14px !important; height: 45px !important; font-weight: 600 !important; }
    .nav-container { position: fixed !important; bottom: 0 !important; left: 0 !important; width: 100% !important; background-color: white !important; padding: 10px 0 25px 0 !important; box-shadow: 0 -4px 15px rgba(0,0,0,0.08) !important; z-index: 999999 !important; }
</style>
""", unsafe_allow_html=True)

def main():
    init_db()
    if not st.session_state.logged_in:
        st.markdown("<br><br><br><h1 style='text-align: center; color: #1E5EFF;'>智生活助手</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            choice = st.radio("请选择", ["登录", "注册"], horizontal=True)
            u = st.text_input("账号"); p = st.text_input("密码", type='password')
            if choice == "登录" and st.button("进入系统", use_container_width=True, type="primary"):
                if login_user(u, p): st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                else: st.error("密码错误")
            elif choice == "注册" and st.button("注册", use_container_width=True, type="primary"):
                if create_user(u, p): st.success("成功！请登录")
        return

    user_nickname, user_allergies = get_user_data(st.session_state.username)

    # 固定头部
    st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
    st.markdown(f'<h1 style="margin:0; padding-bottom: 25px; color:#333; font-size: 32px; font-weight: 800;">🤖 智生活助手</h1>', unsafe_allow_html=True)
    nav_cols = st.columns(4)
    tabs = ["🥗 餐厅", "🚗 出行", "📂 历史", "👤 我的"]
    for i, tab in enumerate(tabs):
        with nav_cols[i]:
            if st.button(tab, key=f"n_{i}", use_container_width=True, type="primary" if st.session_state.active_tab == tab else "secondary"):
                st.session_state.active_tab = tab; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 场景：餐厅 ---
    if st.session_state.active_tab == "🥗 餐厅":
        st.markdown(f"#### 欢迎，{user_nickname}")
        with st.container(border=True):
            mode = st.radio("模式", ["📄 菜单文字", "🖼️ 菜品实拍"], horizontal=True)
            goal = st.text_input("健康需求", value=user_allergies)
            file = st.file_uploader("上传照片")
            if st.button("🚀 智能分析", use_container_width=True):
                if file:
                    import re  # 必须导入正则模块
                    with st.spinner("智生活正在深度感知并生成可视化画像..."):
                        if mode == "📄 菜单文字":
                            # 1. OCR 识字
                            img_pil = Image.open(file); img_pil.thumbnail((700, 700))
                            ocr_text = " ".join(get_ocr_reader().readtext(np.array(img_pil), detail=0))
                            
                            # 2. 增强 Prompt，强制 AI 输出数据块
                            prompt = f"""
                            你是一位AI营养师。忌口：{user_allergies}。需求：{goal}。
                            菜单文本：{ocr_text}。
                            请进行详细分析并给出建议。
                            
                            【重要：最后必须严格按以下格式提供可视化数据】
                            DATA_START
                            {{
                                "items": ["菜名1", "菜名2", "菜名3"],
                                "calories": [热量1, 热量2, 热量3],
                                "health_scores": [评分1, 评分2, 评分3, 评分4, 评分5]
                            }}
                            DATA_END
                            (注意：health_scores固定5个值，分别对应：健康度, 油脂控制, 控糖度, 饱腹感, 安全性，范围0-100)
                            """
                            res = client.chat.completions.create(
                                model="deepseek-chat", 
                                messages=[{"role":"user","content":prompt}]
                            ).choices[0].message.content
                        else:
                            # Qwen-VL 逻辑（确保函数内部也要求了 DATA_START 格式）
                            res = analyze_food_image_with_qwen(file, goal)

                        # --- 核心修复逻辑：提取数据并清洗文字 ---
                        
                        # A. 尝试提取 JSON 并绘图
                        chart_success = False
                        data_match = re.search(r"DATA_START(.*?)DATA_END", res, re.DOTALL)
                        if data_match:
                            data_str = data_match.group(1).strip()
                            # 调用你修改后的动态绘图函数（见下方补充）
                            chart_success = show_meal_visuals(data_str) 
                        
                        # B. 清洗文字：把那些 DATA_START 之类的代码块删掉，不给用户看
                        clean_report = re.sub(r"DATA_START.*?DATA_END", "", res, flags=re.DOTALL).strip()
                        
                        # C. 先显示图表（如果成功），再显示报告
                        if chart_success:
                            st.markdown("---")
                            st.markdown("### 📋 智能诊断报告")
                            st.write(clean_report)
                        else:
                            # 如果 AI 没按格式返回数据，至少把原始文字显出来
                            st.warning("⚠️ 实时数据抓取较弱，仅显示文字报告")
                            st.write(res)
                            
                        save_record("餐饮", clean_report)
                else: 
                    st.warning("请先上传照片")

    # --- 场景：出行 ---
    elif st.session_state.active_tab == "🚗 出行":
        st.markdown('<h3 style="font-size: 24px; color: #444;">🚗 智能出行规划</h3>', unsafe_allow_html=True)
        
        # 初始化状态
        if 'is_generating' not in st.session_state: st.session_state.is_generating = False
        
        with st.container(border=True):
            travel_mode = st.radio("出行方式", ["🚗 自驾", "🚌 公共交通"], horizontal=True)
            st.write("🎤 点击录制需求：")
            col_mic, _ = st.columns([0.2, 2.5]) 
            with col_mic: 
                v_text = speech_to_text(language='zh', start_prompt="🎤 点击录制", key="mic_v8")
            
            query = st.text_input("想法", value=v_text if v_text else "", placeholder="去哪玩？", key="tr_in_v8")
            c1, c2 = st.columns(2)

            def run_travel_ai(is_new=True):
                st.session_state.is_generating = True
                if is_new: st.session_state.travel_messages = []
                
                with st.spinner("智生活正在校准地图并规划..."):
                    # 1. 提取地名并纠偏
                    extract_res = client.chat.completions.create(
                        model="deepseek-chat", 
                        messages=[{"role":"user","content":f"从：'{query}' 提取目的地景点全称。只返回名称，不带标点。"}]
                    )
                    target_dest = extract_res.choices[0].message.content.strip().replace("。", "")
                    
                    # 2. 获取高德数据
                    info = get_amap_info(target_dest)
                    if info:
                        weather = get_real_weather(info['adcode'])
                        address = info['full_address']
                        st.info(f"📍 定位校准：**{address}**")
                        st.success(f"🌦️ 实时天气：{weather}")
                    else:
                        weather = "根据常年气候预估"
                        address = target_dest
                        st.warning(f"⚠️ 启动 AI 模拟定位：**{address}**")

                    # 3. 构造 AI 指令 (强调去除 <br>)
                    mode_tip = "自驾：含高速建议、停车提示。" if "自驾" in travel_mode else "公交：含地铁换乘、步行方案。"
                    sys_p = f"""
                    你是一位专业的资深旅游管家。
                    目的地：{address}，天气：{weather}，出行模式：{travel_mode}。
                    
                    【强制要求】：
                    1. 生成 Markdown 表格行程。
                    2. 绝对【禁止】使用 <br>、<div>、<p> 等任何 HTML 标签。
                    3. 在表格内如果需要分行，请直接使用分号“;”或空格。
                    4. 购票链接：[点击购票](https://m.ctrip.com/webapp/ticket/ticket?keyword={address})。
                    """
                    
                    st.session_state.travel_messages.append({"role":"user", "content":query})
                    ph = st.empty()
                    full_content = ""
                    
                    response = client.chat.completions.create(
                        model="deepseek-chat", 
                        messages=[{"role":"system","content":sys_p}] + st.session_state.travel_messages, 
                        stream=True
                    )
                    
                    for chunk in response:
                        if chunk.choices[0].delta.content:
                            # 【清洗逻辑】：每拿到一个字都对累计文本进行 HTML 标签清洗
                            raw_text = chunk.choices[0].delta.content
                            full_content += raw_text
                            
                            # 实时清洗掉所有可能的 <br> 变体
                            clean_display = full_content.replace("<br>", " ").replace("<br/>", " ").replace("<BR>", " ")
                            ph.markdown(clean_display)
                    
                    # 保存最终清洗后的内容
                    final_plan = full_content.replace("<br>", " ").replace("<br/>", " ").replace("<BR>", " ")
                    st.session_state.current_plan = final_plan
                    st.session_state.travel_messages.append({"role":"assistant", "content":final_plan})
                    save_record("出行", final_plan)
                
                st.session_state.is_generating = False

            if c1.button("🌟 生成全新行程", use_container_width=True): 
                run_travel_ai(True)
                st.rerun()
            if c2.button("🔄 修改/追加需求", use_container_width=True): 
                run_travel_ai(False)
                st.rerun()

        # --- 5. 结果显示与离线下载区 ---
        if st.session_state.current_plan and not st.session_state.is_generating:
            st.markdown("---")
            st.markdown(st.session_state.current_plan)
            
            # 【新增】：离线下载按钮
            st.download_button(
                label="📥 下载离线行程单 (Markdown格式)",
                data=st.session_state.current_plan,
                file_name=f"智生活_行程单_{datetime.now().strftime('%m%d_%H%M')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # 历史
    elif st.session_state.active_tab == "📂 历史":
        h_tab1, h_tab2 = st.tabs(["🥗 餐饮记录", "🚗 出行规划"])
        with sqlite3.connect('history.db') as conn:
            import pandas as pd
            with h_tab1:
                df = pd.read_sql_query("SELECT * FROM records WHERE username=? AND type='餐饮' ORDER BY time DESC", conn, params=(st.session_state.username,))
                for _, r in df.iterrows():
                    with st.expander(f"🍽️ {r['time']}"): st.markdown(r['content'])
            with h_tab2:
                df = pd.read_sql_query("SELECT * FROM records WHERE username=? AND type='出行' ORDER BY time DESC", conn, params=(st.session_state.username,))
                for _, r in df.iterrows():
                    with st.expander(f"🗺️ {r['time']}"): st.markdown(r['content'])

    # 我的
    elif st.session_state.active_tab == "👤 我的":
        st.header("👤 个人中心")
        with st.container(border=True):
            st.subheader("基本信息修改")
            new_nick = st.text_input("我的昵称", value=user_nickname)
            new_allergies = st.text_area("我的过敏原/饮食忌口 (智生活将自动记住)", value=user_allergies, help="例如：我不吃香菜，我对花生和虾过敏")
            if st.button("💾 保存画像信息", use_container_width=True, type="primary"):
                save_user_profile(st.session_state.username, new_nick, new_allergies)
                st.success("信息已同步！AI 现在更了解您了。")
                time.sleep(1); st.rerun()

        with st.container(border=True):
            st.subheader("安全设置")
            new_p = st.text_input("修改新密码", type="password")
            if st.button("🔒 修改密码", use_container_width=True):
                if len(new_p) >= 6:
                    update_password(st.session_state.username, new_p)
                    st.success("密码修改成功！")
                else: st.warning("密码至少6位")

        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
if __name__ == "__main__":
    main()
