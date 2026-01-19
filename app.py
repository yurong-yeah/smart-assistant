import streamlit as st
import openai
from PIL import Image
import numpy as np
import sqlite3
from datetime import datetime
import json
import requests
import hashlib
import base64
from io import BytesIO
import gc

# ==========================================
# 1. 基础配置
# ==========================================
DEEPSEEK_API_KEY = "sk-9e305b3990ac4ddc8819da6072444544"
client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

if 'active_tab' not in st.session_state: st.session_state.active_tab = "🥗 餐厅"
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'travel_messages' not in st.session_state: st.session_state.travel_messages = []
if 'current_plan' not in st.session_state: st.session_state.current_plan = ""

st.set_page_config(page_title="智生活", page_icon="🌟", layout="wide", initial_sidebar_state="collapsed")

AMAP_KEY = "b609ca55fb8d7dc44546632460d0e93a"  

# ==========================================
# 2. 数据库逻辑 (保持不变)
# ==========================================
def init_db():
    with sqlite3.connect('history.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT, nickname TEXT, allergies TEXT)''')
        conn.execute('CREATE TABLE IF NOT EXISTS records (username TEXT, type TEXT, content TEXT, time TEXT)')

def save_record(rtype, content):
    with sqlite3.connect('history.db') as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (st.session_state.username, rtype, content, now))

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

# ==========================================
# 3. 核心工具函数（POI 搜索强化版）
# ==========================================
@st.cache_resource
def get_ocr_reader(): return easyocr.Reader(['ch_sim', 'en'])

def get_amap_info(address):
    """三级渐进式 POI 搜索逻辑"""
    search_list = [address, f"{address}景区", f"四川{address}"] # 尝试多种搜索词组合
    
    for kw in search_list:
        try:
            # 使用 place/text 接口，增加 types=风景名胜 权重
            poi_url = f"https://restapi.amap.com/v3/place/text?keywords={kw}&key={AMAP_KEY}&types=风景名胜&offset=1&page=1"
            res = requests.get(poi_url).json()
            if res['status'] == '1' and res['pois']:
                poi = res['pois'][0]
                return {
                    "full_address": f"{poi['pname']}{poi['cityname']}{poi['adname']}{poi['name']}",
                    "adcode": poi['adcode'],
                    "city": poi['cityname'],
                    "location": poi['location']
                }
        except: continue
    return None

def get_real_weather(adcode):
    """获取真实天气数据"""
    try:
        url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={AMAP_KEY}"
        res = requests.get(url).json()
        if res['status'] == '1' and res['lives']:
            w = res['lives'][0]
            return f"{w['weather']}，气温{w['temperature']}℃，风力{w['windpower']}级"
    except: return "晴（实时天气同步失败，采用标准气候建议）"
    return "未知"

def analyze_food_image_with_qwen(image_file, user_goal):
    encoded_image = base64.b64encode(image_file.getvalue()).decode('utf-8')
    qwen_client = openai.OpenAI(api_key="sk-3277028448bf47fb84a4dd96a1cb9e4e", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    response = qwen_client.chat.completions.create(
        model="qwen-vl-plus",
        messages=[{"role": "user", "content": [{"type": "text", "text": f"你是AI营养师。过敏原：{user_goal}。请识图中食材，给建议和热量。"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}]}]
    )
    return response.choices[0].message.content

# ==========================================
# 4. 样式与布局
# ==========================================
st.markdown("""
<style>
    header, footer, .stDeployButton, [data-testid="stHeader"], [data-testid="stStatusWidget"] { display: none !important; }
    .stApp { background-color: #f8f9fb !important; }
    .main .block-container { padding-top: 260px !important; padding-bottom: 120px !important; max-width: 800px !important; margin: auto; }
    .fixed-header { position: fixed !important; top: 0px !important; left: 0px !important; width: 100% !important; background-color: white !important; box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important; z-index: 999999 !important; padding: 40px 0 30px 0 !important; text-align: center; }
    .fixed-header [data-testid="stHorizontalBlock"] { display: flex !important; gap: 10px !important; max-width: 700px !important; margin: 0 auto !important; }
    div.stButton > button { border-radius: 14px !important; height: 45px !important; font-weight: 600 !important; border: none !important; outline: none !important; box-shadow: none !important; }
    div.stButton > button[kind="primary"] { background-color: #1E5EFF !important; color: white !important; }
    div.stButton > button[kind="secondary"] { background-color: #fcfcfc !important; color: #666 !important; border: 1px solid #f0f2f6 !important; }
    iframe[title="streamlit_mic_recorder.speech_to_text"] { width: 160px !important; height: 60px !important; border: none !important; background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 5. 主逻辑渲染
# ==========================================
def main():
    init_db()

    if not st.session_state.logged_in:
        st.markdown("<br><br><br><h1 style='text-align: center; color: #1E5EFF;'>智生活助手</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            choice = st.radio("请选择", ["登录", "注册"], horizontal=True)
            u = st.text_input("账号"); p = st.text_input("密码", type='password')
            if choice == "登录" and st.button("立即登录", use_container_width=True, type="primary"):
                if login_user(u, p): st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                else: st.error("账号或密码错误")
            elif choice == "注册" and st.button("点击注册", use_container_width=True, type="primary"):
                if create_user(u, p): st.success("成功！请登录")
                else: st.error("账号已存在")
        return

    user_nickname, user_allergies = get_user_data(st.session_state.username)

    # 固定头部
    st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
    st.markdown(f'<h1 style="margin:0; padding-bottom: 25px; color:#333; font-size: 38px; font-weight: 800;">🤖 智生活助手</h1>', unsafe_allow_html=True)
    nav_cols = st.columns(4)
    tabs = ["🥗 餐厅", "🚗 出行", "📂 历史", "👤 我的"]
    for i, tab in enumerate(tabs):
        with nav_cols[i]:
            if st.button(tab, key=f"nav_{i}", use_container_width=True, type="primary" if st.session_state.active_tab == tab else "secondary"):
                st.session_state.active_tab = tab; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 场景：餐厅 ---
    if st.session_state.active_tab == "🥗 餐厅":
        st.markdown(f"#### 欢迎回来，{user_nickname}")
        with st.container(border=True):
            # 去掉模式选择，直接一个上传框
            st.info("💡 提示：支持直接拍摄菜单或菜品，云端引擎将自动感知")
            goal = st.text_input("📋 健康需求", value=user_allergies)
            file = st.file_uploader("📸 上传图片", type=['jpg', 'jpeg', 'png'])
            
            result_area = st.empty()

            if st.button("🚀 开始智能分析", use_container_width=True):
                if file:
                    with st.spinner("智生活云端引擎正在感知图片内容..."):
                        # --- 核心修改：不再运行本地 EasyOCR，直接把图发给阿里云 ---
                        try:
                            # 无论菜单还是菜品，Qwen-VL 都能看懂
                            vision_report = analyze_food_image_with_qwen(file, goal)
                            result_area.markdown(vision_report)
                            save_record("餐饮识别", vision_report)
                        except Exception as e:
                            st.error(f"分析失败，请检查 API Key 余额或网络: {e}")
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
            new_allergies = st.text_area("我的过敏原/饮食忌口 (之生活将自动记住)", value=user_allergies, help="例如：我不吃香菜，我对花生和虾过敏")
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
