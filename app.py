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

# ==========================================
# 1. 基础配置
# ==========================================
DEEPSEEK_API_KEY = "sk-9e305b3990ac4ddc8819da6072444544"
client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# 初始化状态
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🥗 餐厅"
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'travel_chat_history' not in st.session_state: st.session_state.travel_chat_history = []
if 'current_plan' not in st.session_state: st.session_state.current_plan = ""

st.set_page_config(page_title="智生活", page_icon="🌟", layout="wide")

# 高德地图配置
AMAP_KEY = "b609ca55fb8d7dc44546632460d0e93a"  

# ==========================================
# 2. 数据库逻辑 (新增个人画像字段)
# ==========================================
def init_db():
    with sqlite3.connect('history.db') as conn:
        # 用户表增加：昵称(nickname)、过敏原(allergies)
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT, nickname TEXT, allergies TEXT)''')
        conn.execute('CREATE TABLE IF NOT EXISTS records (username TEXT, type TEXT, content TEXT, time TEXT)')

def save_user_profile(username, nickname, allergies):
    with sqlite3.connect('history.db') as conn:
        conn.execute("UPDATE users SET nickname=?, allergies=? WHERE username=?", (nickname, allergies, username))

def update_password(username, new_password):
    with sqlite3.connect('history.db') as conn:
        conn.execute("UPDATE users SET password=? WHERE username=?", (hashlib.sha256(str.encode(new_password)).hexdigest(), username))

def get_user_data(username):
    with sqlite3.connect('history.db') as conn:
        c = conn.cursor()
        c.execute("SELECT nickname, allergies FROM users WHERE username=?", (username,))
        return c.fetchone()

# (其他数据库函数 login_user, create_user, save_record 保持不变但需确保逻辑一致)
def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()

def create_user(username, password):
    with sqlite3.connect('history.db') as conn:
        try:
            conn.execute('INSERT INTO users(username,password,nickname,allergies) VALUES (?,?,?,?)', 
                         (username, make_hashes(password), username, ""))
            return True
        except: return False

def login_user(username, password):
    with sqlite3.connect('history.db') as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username =? AND password = ?', (username, make_hashes(password)))
        return c.fetchone()

def save_record(rtype, content):
    with sqlite3.connect('history.db') as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (st.session_state.username, rtype, str(content), now))

# ==========================================
# 3. 核心功能与 CSS
# ==========================================
@st.cache_resource
def get_ocr_reader(): return easyocr.Reader(['ch_sim', 'en'])

def get_amap_info(address):
    try:
        geo_url = f"https://restapi.amap.com/v3/geocode/geo?address={address}&key={AMAP_KEY}"
        geo_data = requests.get(geo_url).json()
        if geo_data['status'] == '1' and geo_data['geocodes']:
            loc = geo_data['geocodes'][0]
            weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={loc['adcode']}&key={AMAP_KEY}"
            w_data = requests.get(weather_url).json()
            weather = f"{w_data['lives'][0]['weather']} {w_data['lives'][0]['temperature']}℃" if w_data['status']=='1' else "未知"
            return {"full_address": loc['formatted_address'], "weather": weather}
    except: return None

# --- 样式注入 ---
st.markdown("""
<style>
    /* 录音组件消除背景和边框，高度自适应 */
    iframe[title="streamlit_mic_recorder.speech_to_text"] { 
        width: 160px !important; 
        height: 60px !important; 
        border: none !important; 
        background: transparent !important; 
    }

    /* 强制让录音插件所在的容器不带额外装饰 */
    [data-testid="stVerticalBlock"] div:has(iframe) {
        background-color: transparent !important;
        border: none !important;
    }
    header, footer, .stDeployButton, [data-testid="stHeader"] { display: none !important; }
    .stApp { background-color: #f8f9fb !important; }
    .main .block-container { padding-top: 250px !important; padding-bottom: 120px !important; max-width: 800px !important; margin: auto; }
    
    .fixed-header {
        position: fixed !important; top: 0px !important; left: 0px !important; width: 100% !important;
        background-color: white !important; box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important;
        z-index: 999999 !important; padding: 30px 0 35px 0 !important; text-align: center;
    }
    .fixed-header [data-testid="stHorizontalBlock"] { display: flex !important; gap: 10px !important; max-width: 700px !important; margin: 0 auto !important; }

    div.stButton > button {
        border-radius: 14px !important; height: 45px !important; font-weight: 600 !important;
        border: none !important; outline: none !important; box-shadow: none !important;
    }
    div.stButton > button[kind="primary"] { background-color: #1E5EFF !important; color: white !important; }
    div.stButton > button[kind="secondary"] { background-color: #fcfcfc !important; color: #666 !important; border: 1px solid #f0f2f6 !important; }
    
    /* 底部导航栏 */
    .nav-container {
        position: fixed !important; bottom: 0 !important; left: 0 !important; width: 100% !important;
        background-color: white !important; padding: 10px 0 25px 0 !important;
        box-shadow: 0 -4px 15px rgba(0,0,0,0.08) !important; z-index: 999999 !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 页面逻辑
# ==========================================
def main():
    init_db()

    # --- 1. 登录逻辑 ---
    if not st.session_state.logged_in:
        st.markdown("<br><br><br><h1 style='text-align: center; color: #1E5EFF;'>智生活助手</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            choice = st.radio("请选择", ["登录", "注册"], horizontal=True)
            u = st.text_input("账号")
            p = st.text_input("密码", type='password')
            if choice == "登录" and st.button("立即登录", use_container_width=True, type="primary"):
                if login_user(u, p):
                    st.session_state.logged_in, st.session_state.username = True, u
                    st.rerun()
                else: st.error("账号或密码错误")
            elif choice == "注册" and st.button("点击注册", use_container_width=True, type="primary"):
                if create_user(u, p): st.success("注册成功！请切换到登录")
                else: st.error("账号已存在")
        return

    # --- 2. 获取用户画像 ---
    user_nickname, user_allergies = get_user_data(st.session_state.username)

    # --- 3. 渲染固定头部 ---
    st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
    st.markdown(f'<h1 style="margin:0; padding-bottom: 25px; color:#333; font-size: 38px; font-weight: 800;">🤖 智生活助手</h1>', unsafe_allow_html=True)
    nav_cols = st.columns(4) # 改为4列
    tabs = ["🥗 餐厅", "🚗 出行", "📂 历史", "👤 我的"]
    for i, tab in enumerate(tabs):
        with nav_cols[i]:
            if st.button(tab, key=f"nav_{i}", use_container_width=True, 
                         type="primary" if st.session_state.active_tab == tab else "secondary"):
                st.session_state.active_tab = tab
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 4. 页面分发 ---
    # 场景：餐厅 (智能画像集成)
    if st.session_state.active_tab == "🥗 餐厅":
        st.markdown(f"#### 欢迎回来，{user_nickname}")
        with st.container(border=True):
            # 自动读取用户画像里的过敏原
            goal = st.text_input("健康需求 (已自动加载您的画像)", value=user_allergies, placeholder="如：海鲜过敏")
            file = st.file_uploader("上传菜单照片")
            if st.button("🚀 开始分析", use_container_width=True):
                if file:
                    with st.spinner("分析中..."):
                        img_np = np.array(Image.open(file))
                        ocr_text = " ".join(get_ocr_reader().readtext(img_np, detail=0))
                        ph = st.empty(); full = ""
                        # AI 提示词集成用户画像
                        prompt = f"用户画像：{user_nickname}，长期忌口：{user_allergies}。当前特殊需求：{goal}。菜单：{ocr_text}。请分析。"
                        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":prompt}], stream=True)
                        for chunk in response:
                            if chunk.choices[0].delta.content:
                                full += chunk.choices[0].delta.content
                                ph.markdown(full)
                        save_record("餐饮识别", full)

    # 场景：出行
    elif st.session_state.active_tab == "🚗 出行":
        st.markdown('<h3 style="font-size: 24px; color: #444; margin-bottom: 10px;">🚗 智能出行规划</h3>', unsafe_allow_html=True)
        
        # 1. 初始化页面状态
        if 'travel_messages' not in st.session_state:
            st.session_state.travel_messages = []
        if 'is_generating' not in st.session_state:
            st.session_state.is_generating = False

        with st.container(border=True):
            st.write("🎤 **语音录入需求**：")
            col_mic, _ = st.columns([0.2, 2.5]) 
            with col_mic:
                v_text = speech_to_text(language='zh', start_prompt="🎤 点击录制", key="mic_v_final")
            
            query = st.text_input("您的想法", value=v_text if v_text else "", placeholder="例如：去瓦屋山玩4天", key="travel_input_v_final")
            
            c1, c2 = st.columns(2)

            def run_travel_ai(is_new=True):
                if not query:
                    st.warning("请输入目的地")
                    return

                # 【关键逻辑 1】开启生成状态，暂时关闭底部的静态显示
                st.session_state.is_generating = True 
                
                with st.spinner("智生活正在校准并为您规划行程..."):
                    if is_new:
                        st.session_state.travel_messages = []
                        # 地名纠偏
                        correct_res = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": f"请返回'{query}'对应的省份城市景区全称，仅返回地名。"}]
                        )
                        target_dest = correct_res.choices[0].message.content.strip()
                    else:
                        target_dest = st.session_state.get('last_located_address', query)

                    info = get_amap_info(target_dest)
                    if info:
                        st.session_state.last_located_address = info['full_address']
                        
                        # 构造系统提示词
                        sys_prompt = f"""
                        你是一位旅游管家。目的地：{info['full_address']}，天气：{info['weather']}。
                        要求：
                        1. 严格按照用户要求的天数生成行程表。
                        2. 必须使用 Markdown 表格。
                        3. **禁止**使用 <br>、<div> 等任何 HTML 标签，换行请直接使用空格或分号。
                        4. 购票链接：[点击购票](https://m.ctrip.com/webapp/ticket/ticket?keyword={info['full_address']})。
                        """
                        
                        st.session_state.travel_messages.append({"role": "user", "content": query})
                        
                        # 【关键逻辑 2】使用唯一的显示占位符
                        ph = st.empty() 
                        full_content = ""
                        
                        response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.travel_messages[:-1] + [{"role":"user", "content":query}],
                            stream=True
                        )
                        
                        for chunk in response:
                            if chunk.choices[0].delta.content:
                                text_chunk = chunk.choices[0].delta.content
                                # 【关键逻辑 3】实时清洗 <br> 标签
                                text_chunk = text_chunk.replace("<br>", " ").replace("<br/>", " ")
                                full_content += text_chunk
                                ph.markdown(full_content)
                        
                        # 保存结果并重置生成状态
                        st.session_state.current_plan = full_content
                        st.session_state.travel_messages.append({"role": "assistant", "content": full_content})
                        save_record("行程规划", full_content)
                        st.session_state.is_generating = False
                    else:
                        st.error("定位失败")
                        st.session_state.is_generating = False

            if c1.button("🌟 生成全新行程", use_container_width=True, key="gen_final"):
                run_travel_ai(is_new=True)
                st.rerun() # 生成完强制刷新一次，清理掉占位符，交给底部的静态显示
            
            if c2.button("🔄 修改/追加需求", use_container_width=True, key="upd_final"):
                run_travel_ai(is_new=False)
                st.rerun()

        # --- 【关键逻辑 4】静态显示区 ---
        # 只有在不处于生成状态时才显示，彻底解决显示 2 次的问题
        if st.session_state.current_plan and not st.session_state.is_generating:
            st.markdown("---")
            st.markdown(st.session_state.current_plan)
                

    # 场景：历史
    elif st.session_state.active_tab == "📂 历史":
        with sqlite3.connect('history.db') as conn:
            import pandas as pd
            df = pd.read_sql_query("SELECT * FROM records WHERE username=? ORDER BY time DESC", conn, params=(st.session_state.username,))
            for _, r in df.iterrows():
                with st.expander(f"{r['type']} - {r['time']}"): st.markdown(r['content'])

    # 场景：我的 (个人中心)
    elif st.session_state.active_tab == "👤 我的":
        st.header("👤 个人中心")
        with st.container(border=True):
            st.subheader("基本信息修改")
            new_nick = st.text_input("我的昵称", value=user_nickname)
            new_allergies = st.text_area("我的过敏原/饮食忌口 (AI将自动记住)", value=user_allergies, help="例如：我不吃香菜，我对花生和虾过敏")
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
    import time
    main()
