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
import pandas as pd
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
# 修改 init_db 函数，增加 reminders 表
def init_db():
    with sqlite3.connect('history.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT, nickname TEXT, allergies TEXT)''')
        conn.execute('CREATE TABLE IF NOT EXISTS records (username TEXT, type TEXT, content TEXT, time TEXT)')
        # 新增：提醒/备忘录表 (status: 0-进行中, 1-已完成)
        conn.execute('''CREATE TABLE IF NOT EXISTS reminders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, type TEXT, content TEXT, trigger_time TEXT, status INTEGER)''')


# 1. 添加提醒/备忘到数据库
def add_reminder(username, r_type, content, t_time):
    with sqlite3.connect('history.db') as conn:
        conn.execute("INSERT INTO reminders (username, type, content, trigger_time, status) VALUES (?,?,?,?,0)",
                     (username, r_type, content, t_time))

# 2. 获取提醒列表
def get_reminders(username):
    with sqlite3.connect('history.db') as conn:
        import pandas as pd
        return pd.read_sql_query("SELECT * FROM reminders WHERE username=? ORDER BY trigger_time ASC", conn, params=(username,))

# 3. 彻底删除提醒
def delete_reminder(r_id):
    with sqlite3.connect('history.db') as conn:
        conn.execute("DELETE FROM reminders WHERE id=?", (r_id,))

# 4. 切换提醒状态（待办 <-> 已完成）
def toggle_reminder_status(r_id, current_status):
    new_status = 1 if current_status == 0 else 0
    with sqlite3.connect('history.db') as conn:
        conn.execute("UPDATE reminders SET status=? WHERE id=?", (new_status, r_id))

def save_user_profile(username, nickname, allergies):
    with sqlite3.connect('history.db') as conn:
        conn.execute("UPDATE users SET nickname=?, allergies=? WHERE username=?", (nickname, allergies, username))

def get_user_data(username):
    with sqlite3.connect('history.db') as conn:
        c = conn.cursor()
        c.execute("SELECT nickname, allergies FROM users WHERE username=?", (username,))
        return c.fetchone()
def update_password(username, new_password):
    with sqlite3.connect('history.db') as conn:
        hashed_pw = hashlib.sha256(str.encode(new_password)).hexdigest()
        conn.execute("UPDATE users SET password=? WHERE username=?", (hashed_pw, username))
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
    /* 1. 全局基础样式 */
    header, footer, [data-testid="stHeader"] { display: none !important; }
    .stApp { background-color: #f8f9fb !important; }
    .main .block-container { padding-top: 250px !important; padding-bottom: 120px !important; max-width: 900px !important; margin: auto; }
    
    /* 2. 固定头部样式 */
    .fixed-header { 
        position: fixed !important; top: 0px !important; left: 0px !important; width: 100% !important; 
        background-color: white !important; box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important; 
        z-index: 999999 !important; padding: 30px 0 35px 0 !important; text-align: center; 
    }

    /* 3. 按钮样式：修改为蓝色 */
    /* 普通按钮 (Secondary Buttons) */
    div.stButton > button {
        border-radius: 14px !important;
        height: 45px !important;
        font-weight: 600 !important;
        border: 1px solid #1E5EFF !important; /* 蓝色边框 */
        color: #1E5EFF !important;            /* 蓝色文字 */
        background-color: white !important;
    }

    /* 主按钮 & 选中的导航按钮 (Primary Buttons) */
    div.stButton > button[kind="primary"] {
        background-color: #1E5EFF !important; /* 蓝色背景 */
        color: white !important;             /* 白色文字 */
        border: none !important;
        box-shadow: 0 4px 12px rgba(30, 94, 255, 0.3) !important;
    }

    /* 悬停效果 (Hover) */
    div.stButton > button:hover {
        border-color: #0046CC !important;
        color: #0046CC !important;
        background-color: #f0f4ff !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #0046CC !important; /* 深蓝色悬停 */
        color: white !important;
    }

    /* 4. 单选框 (Radio) 选中颜色改为蓝色 */
    div[data-baseweb="radio"] div[aria-checked="true"] > div:first-child {
        border-color: #1E5EFF !important;
        background-color: #1E5EFF !important;
    }
    
    /* 5. 语音录音按钮样式修正（如果是红色白条的话） */
    div[data-testid="stHorizontalBlock"] button {
        border-radius: 12px !important;
    }

    .nav-container { 
        position: fixed !important; bottom: 0 !important; left: 0 !important; width: 100% !important; 
        background-color: white !important; padding: 10px 0 25px 0 !important; 
        box-shadow: 0 -4px 15px rgba(0,0,0,0.08) !important; z-index: 999999 !important; 
    }
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
    nav_cols = st.columns(5) 
    tabs = ["🥗 餐厅", "🚗 出行", "⏰ 提醒", "📂 历史", "👤 我的"]
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
        import urllib.parse
        st.markdown('<h3 style="font-size: 24px; color: #444;">🚗 智能出行规划</h3>', unsafe_allow_html=True)
        
        # 1. 初始化出行特有的状态变量（防止刷新消失）
        if 'travel_info' not in st.session_state: st.session_state.travel_info = None
        if 'travel_plan_content' not in st.session_state: st.session_state.travel_plan_content = ""
        if 'is_generating' not in st.session_state: st.session_state.is_generating = False

        with st.container(border=True):
            travel_mode = st.radio("出行方式", ["🚗 自驾", "🚌 公共交通"], horizontal=True)
            
            # 优化布局：将语音按钮和输入框放在同一行
            # col1 是按钮，col2 是输入框
            col_btn, col_txt = st.columns([1, 4]) 
            
            with col_btn:
                # start_prompt 留空或只放图标，可以让按钮变短，消除白条感
                v_text = speech_to_text(
                    language='zh', 
                    start_prompt="🎤 点击录音", 
                    key="mic_travel_v10",
                    use_container_width=True # 让按钮填满它所在的窄列
                )
            
            with col_txt:
                query = st.text_input(
                    "要去哪儿？有什么特别想法？", 
                    value=v_text if v_text else "", 
                    placeholder="例如：瓦屋山4日游", 
                    label_visibility="collapsed", # 隐藏标签让高度对齐按钮
                    key="tr_input_v10"
                )
            
            # 下方按钮保持不变
            c1, c2 = st.columns(2)

            # --- 核心逻辑函数 ---
            def generate_travel_service(is_new=True):
                st.session_state.is_generating = True
                try:
                    with st.spinner("智生活正在为您精准校准地图并规划行程..."):
                        # (1) 智能地名提取：防止定位到甘肃等偏僻同名地
                        extract_prompt = f"""
                        从用户描述：'{query}' 中提取唯一的旅游目的地全称。
                        注意：
                        1. 如果地名有歧义，务必返回【全国最著名、热门】的那个（例如：瓦屋山请返回'四川省眉山市瓦屋山'）。
                        2. 只返回‘省份+城市+景点名’，不带任何标点。
                        """
                        extract_res = client.chat.completions.create(
                            model="deepseek-chat", 
                            messages=[{"role":"user","content": extract_prompt}]
                        ).choices[0].message.content.strip()

                        # (2) 调用高德获取经纬度和天气
                        info = get_amap_info(extract_res)
                        st.session_state.travel_info = info # 存入状态

                        # (3) 生成详细行程
                        weather_str = "根据季节气候预估"
                        addr_str = extract_res
                        if info and info['weather']:
                            w = info['weather']
                            weather_str = f"{w['weather']} {w['temperature']}℃"
                            addr_str = info['address']

                        sys_p = f"""你是一位专业的金牌旅游管家。目的地：{addr_str}，当前天气：{weather_str}，模式：{travel_mode}。
                        要求：1.表格展示行程；2.严禁使用HTML标签；3.针对用户提到的特定人群（如小孩）给出避坑建议。"""
                        
                        plan_res = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role":"system","content":sys_p}, {"role":"user","content":query}]
                        ).choices[0].message.content
                        
                        st.session_state.travel_plan_content = plan_res
                        save_record("出行", plan_res)
                except Exception as e:
                    st.error(f"规划方案时出错：{e}")
                st.session_state.is_generating = False

            # 按钮触发
            if c1.button("🌟 生成全新行程", use_container_width=True, type="primary"):
                generate_travel_service(True)
                st.rerun()
            if c2.button("🗑️ 清空当前方案", use_container_width=True):
                st.session_state.travel_info = None
                st.session_state.travel_plan_content = ""
                st.rerun()

        # --- 2. 结果展示区（在按钮外部，保证持久显示） ---
        if st.session_state.travel_info:
            info = st.session_state.travel_info
            lon, lat = info['location'].split(',')
            
            # A. 顶部卡片：显示地址、天气和导航按钮
            with st.container(border=True):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.success(f"📍 **已锁定目的地**：{info['address']}")
                    if info['weather']:
                        st.info(f"🌦️ **实时天气**：{info['weather']['weather']} | 🌡️ {info['weather']['temperature']}℃")
                with col_b:
                    # 高德地图导航跳转链接
                    nav_url = f"https://uri.amap.com/marker?position={lon},{lat}&name={urllib.parse.quote(info['address'])}&coordinate=gaode&callnative=1"
                    st.markdown(f'''<a href="{nav_url}" target="_blank">
                        <button style="background-color: #007bff; color: white; border: none; padding: 12px; border-radius: 10px; width: 100%; cursor: pointer; font-weight: bold;">
                        🚀 高德导航
                        </button></a>''', unsafe_allow_html=True)
                
                # B. 渲染小地图
                m = folium.Map(location=[float(lat), float(lon)], zoom_start=13)
                folium.Marker([float(lat), float(lon)], popup=info['address']).add_to(m)
                st_folium(m, width=None, height=300, key="travel_map_fixed")

        # C. 显示行程文本
        if st.session_state.travel_plan_content:
            st.markdown("### 📋 详细行程方案")
            st.markdown(st.session_state.travel_plan_content)
            
            # 下载按钮
            st.download_button(
                label="📥 下载行程单",
                data=st.session_state.travel_plan_content,
                file_name=f"行程单_{datetime.now().strftime('%m%d')}.md",
                mime="text/markdown",
                use_container_width=True
            )
    # --- 场景：提醒与备忘录 ---
    elif st.session_state.active_tab == "⏰ 提醒":
        st.markdown('<h3 style="font-size: 24px; color: #444;">⏰ 智能备忘清单</h3>', unsafe_allow_html=True)
        
        # --- A. 实时闹钟弹窗检测逻辑 ---
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        reminders_df = get_reminders(st.session_state.username)
        
        # 记录已经弹窗过的 ID，防止页面刷新重复弹窗
        if 'alerted_ids' not in st.session_state: st.session_state.alerted_ids = set()

        # 扫描所有未完成的提醒
        active_reminders = reminders_df[reminders_df['status'] == 0]
        for _, row in active_reminders.iterrows():
            # 如果 当前时间 >= 设定时间 且 还没弹过窗
            if row['trigger_time'] <= now_str and row['id'] not in st.session_state.alerted_ids:
                st.error(f"🔔 **提醒时间已到！** \n\n 任务内容：{row['content']} \n\n 设定时间：{row['trigger_time']}")
                st.toast(f"时间到：{row['content']}", icon="⏰")
                # 标记已弹窗
                st.session_state.alerted_ids.add(row['id'])

        # --- B. 添加区域 ---
        with st.container(border=True):
            r_content = st.text_input("📝 我要做什么？", placeholder="输入任务内容...")
            
            # 布局：日期占一半，时/分各占四分之一
            col_date, col_h, col_m = st.columns([2, 1, 1])
            
            with col_date:
                d = st.date_input("提醒日期", value=datetime.now())
                
            with col_h:
                # 小时输入：支持键盘输入 0-23
                h = st.number_input("小时", min_value=0, max_value=23, value=datetime.now().hour)
                
            with col_m:
                # 分钟输入：支持键盘输入 0-59
                m = st.number_input("分钟", min_value=0, max_value=59, value=datetime.now().minute)
                    
            # 组合最终时间字符串 (使用 :02d 确保 9:5 显示为 09:05，方便数据库排序)
            target_time = f"{d} {h:02d}:{m:02d}"
            
            st.info(f"🕒 最终提醒时间设定为：**{target_time}**")
            
            if st.button("➕ 加入清单", use_container_width=True, type="primary"):
                if r_content:
                    # 这里的 add_reminder 必须已经在数据库函数区定义好
                    add_reminder(st.session_state.username, "智能提醒", r_content, target_time)
                    st.success("添加成功！")
                    time.sleep(0.5)
                    st.rerun()

        # --- C. 清单展示区域 ---
        st.markdown("---")
        
        # 分栏显示：待办 vs 已完成
        tab_pending, tab_done = st.tabs(["📌 待办中", "✅ 已完成"])
        
        # --- 找到 tab_pending 下方的循环并替换 ---
        with tab_pending:
            pending = reminders_df[reminders_df['status'] == 0]
            if pending.empty:
                st.info("暂无待办事项")
            else:
                for _, row in pending.iterrows():
                    # 逻辑：检测是否超时
                    is_overdue = row['trigger_time'] <= now_str
                    
                    c1, c2 = st.columns([0.85, 0.15])
                    with c1:
                        # 【修正点 1】：使用 Markdown 语法拼接 label，去掉 HTML 标签
                        # Streamlit 的 label 支持简单的 Markdown（如 **加粗**）
                        # 注意：label 中不能直接用换行符，我们用括号把时间括起来
                        overdue_tag = "⚠️ [超时] " if is_overdue else "⏰ "
                        label = f"{overdue_tag}**{row['content']}** ({row['trigger_time']})"
                        
                        # 【修正点 2】：去掉 unsafe_allow_html=True
                        if st.checkbox(label, key=f"box_{row['id']}"):
                            toggle_reminder_status(row['id'], 0)
                            st.rerun()
                    with c2:
                        if st.button("🗑️", key=f"del_{row['id']}"):
                            delete_reminder(row['id'])
                            st.rerun()

        with tab_done:
            done = reminders_df[reminders_df['status'] == 1]
            if done.empty:
                st.write("还没有完成的任务")
            else:
                for _, row in done.iterrows():
                    c1, c2 = st.columns([0.85, 0.15])
                    with c1:
                        # 已完成的任务显示灰色删除线
                        st.checkbox(f"~~{row['content']}~~", value=True, key=f"done_{row['id']}")
                        # 如果取消勾选，则恢复
                        if not st.session_state[f"done_{row['id']}"]:
                            toggle_reminder_status(row['id'], 1)
                            st.rerun()
                    with c2:
                        if st.button("🗑️", key=f"cdel_{row['id']}"):
                            delete_reminder(row['id'])
                            st.rerun()

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
