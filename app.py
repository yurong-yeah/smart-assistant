import streamlit as st
import openai
import easyocr
from PIL import Image
import numpy as np
import sqlite3
from datetime import datetime
import json
from streamlit_mic_recorder import speech_to_text
from datetime import datetime

# ==========================================
# 1. 基础配置（在这里填入你的 API Key）
# ==========================================
DEEPSEEK_API_KEY = "sk-9e305b3990ac4ddc8819da6072444544"

client = openai.OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# ==========================================
# 2. 数据库逻辑（实现离线存储功能）
# ==========================================
def init_db():
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records 
                 (type TEXT, content TEXT, time TEXT)''')
    conn.commit()
    conn.close()

def save_record(type, content):
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO records VALUES (?, ?, ?)", (type, content, now))
    conn.commit()
    conn.close()

# ==========================================
# 3. 核心功能函数
# ==========================================

# 加载OCR引擎（缓存以提高速度）
@st.cache_resource
def get_ocr_reader():
    return easyocr.Reader(['ch_sim', 'en'])

# 餐饮场景逻辑
def analyze_menu(image, user_goal):
    reader = get_ocr_reader()
    # 将上传的文件转为OCR可读格式
    img_np = np.array(Image.open(image))
    result = reader.readtext(img_np, detail=0)
    menu_text = " ".join(result)

    prompt = f"""
    【重要指令：安全第一】
    用户当前的身体状况与目标：{user_goal}
    菜单内容：{menu_text}
    
    作为“智生活”营养顾问，你必须严格遵守以下审核流程：
    
    1. ❌ 【过敏原红线】：
       - 仔细检查菜单，如果发现任何含有用户过敏成分（如：{user_goal}中提到的海鲜、花生等）的菜品，**严禁**将其列入推荐名单。
       - 必须在报告开头明确列出这些“禁忌菜品”并给予强烈警告。

    2. ✅ 【安全推荐】：
       - 在排除了过敏原后，从剩余菜品中挑选最符合“控糖、少油”目标的菜。
       - 理由要结合健康和安全。

    3. 🔄 【优化替代】：
       - 提供健康的替换方案，同样要确保替代品不含过敏原。

    4. 💡 【热量与寄语】：预估热量并给出叮嘱。

    请用非常严肃且负责任的语气回答。如果发现菜单全是海鲜而用户海鲜过敏，请直接告知用户“这份菜单对您不安全”。
    """
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": "你是一位极度严谨、优先考虑食品安全的营养医师。"},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# 出行场景逻辑
def generate_itinerary(user_input):
    # 模拟外部API数据（如果是比赛演示，可以手动在这里改一下城市和天气，让它看起来更真实）
    # 也可以让 AI 根据当前月份（1月）自动推断当地的大致气候
    current_month = datetime.now().strftime("%m")
    
    prompt = f"""
    用户需求：{user_input}
    当前月份：{current_month}月
    
    任务：请为用户生成一份详细的周末游行程规划。
    要求输出内容必须包含以下三个板块：

    1. 🌦️ 【天气与穿着建议】
       - 根据目的地和当前月份，预估当地的温度区间。
       - 给出具体的天气状况（如：晴、多云）。
       - **重点**：给出详细的穿衣建议（如：建议叠穿、带厚羽绒服、由于有徒步建议穿运动鞋等）。

    2. 📅 【结构化行程表】
       - 使用 Markdown 表格。
       -**绝对不要**在表格中使用<br>、<div>等HTML标签。
       -确保输出的是纯净的文本格式。
       - 包含列：时间段、活动内容、交通建议、预约提醒/链接。

    3. 💡 【出行小贴士】
       - 包含防晒、补水、离线地图下载等建议。

    请用亲切、专业的语气回答，并多使用 Emoji 增加可读性。
    """
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": "你是一位贴心的旅游管家。"},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# ==========================================
# 4. Streamlit 界面布局
# ==========================================
def main():
    init_db()
    st.set_page_config(page_title="AI智能生活助手", page_icon="🌟")
    
    st.title("🤖 智能生活服务助手")
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["🥗 智能餐厅", "🚗 出行规划", "📂 历史/离线"])

    # --- Tab 1: 餐饮场景 ---
    with tab1:
        st.markdown("""
            <style>
                /* 1. 只针对上传组件内部的文字进行隐藏 */
                [data-testid="stFileUploaderDropzoneInstructions"] div span {
                    display: none !important;
                }
                [data-testid="stFileUploaderDropzoneInstructions"] div small {
                    display: none !important;
                }
                
                /* 2. 添加中文提示词 */
                [data-testid="stFileUploaderDropzoneInstructions"] div::before {
                    content: "将图片拖拽至此或上传图片";
                    display: block;
                    font-size: 16px;
                    margin-bottom: 5px;
                }
                [data-testid="stFileUploaderDropzoneInstructions"] div::after {
                    content: "单张图片最大限制 200MB • 支持 JPG, PNG, JPEG";
                    display: block;
                    font-size: 12px;
                    color: #808495;
                }
                
                /* 3. 【关键修改】只修改上传组件里的那个按钮，不影响“开始分析”按钮 */
                [data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"] {
                    font-size: 0 !important; /* 隐藏原始文字 */
                    padding: 0px 10px !important;
                }
                
                [data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"]::after {
                    content: "浏览文件";
                    font-size: 14px !important; /* 恢复显示中文 */
                    display: block;
                }
            </style>
        """, unsafe_allow_html=True)
        st.header("菜单智能识别")
        goal = st.text_input("输入你的健康需求：", placeholder="例如：控糖、少油、花生过敏")
        file = st.file_uploader("拍摄或上传菜单照片", type=['jpg', 'png', 'jpeg'])
        
        if file and st.button("开始分析"):
            with st.spinner("智生活正在分析菜单..."):
                res_text = analyze_menu(file, goal)
                st.markdown("---") # 加一条分割线
                st.subheader("📋 您的餐饮健康分析报告")
                
                # 直接展示文字，AI 会自动处理好加粗、列表等格式
                st.markdown(res_text) 
                
                # 保存记录
                save_record("餐饮", res_text)

    # --- Tab 2: 出行场景 ---
    with tab2:
        st.header("旅游行程智能规划")
        if 'travel_chat_history' not in st.session_state:
            st.session_state.travel_chat_history = []
        if 'current_plan' not in st.session_state:
            st.session_state.current_plan = ""
        st.write("点击下方按钮开始说话，应用将自动识别您的语音：")
    
        # --- 【新增】应用自带的语音识别组件 ---
        # 语言设为 'zh' 代表中文
        st.write("🎤 点击下方按钮说话或在框中输入需求：")
        v_text = speech_to_text(language='zh', start_prompt="点击开始录音", key='travel_stt')
        
        # 逻辑处理：优先使用语音识别出的文字
        input_val = st.text_input("您的旅行想法/修改需求：", 
                                   value=v_text if v_text else "",
                                   placeholder="例如：带5岁小孩去北京自然博物馆 / 或者说：把午饭换成素食")

        col1, col2 = st.columns(2)
        with col1:
            generate_btn = st.button("🌟 生成全新行程")
        with col2:
            update_btn = st.button("🔄 修改/追加需求")

        # --- 3. 处理逻辑 ---
        
        # 情况 A：生成全新行程 (清除记忆)
        if generate_btn and input_val:
            st.session_state.travel_chat_history = [] # 清空旧记忆
            with st.spinner("智生活正在为您规划全新行程..."):
                # 构造发送给 AI 的消息
                messages = [
                    {"role": "system", "content": "你是一位专业的旅游管家。请生成带天气、穿着建议和Markdown表格行程的计划。"},
                    {"role": "user", "content": input_val}
                ]
                
                # 这里调用 AI (建议使用流式传输，代码略，同之前方案)
                response = client.chat.completions.create(model="deepseek-chat", messages=messages)
                new_plan = response.choices[0].message.content.replace("<br>", " ")
                
                # 存入记忆
                st.session_state.current_plan = new_plan
                st.session_state.travel_chat_history.append({"role": "user", "content": input_val})
                st.session_state.travel_chat_history.append({"role": "assistant", "content": new_plan})
                save_record("出行", new_plan)

        # 情况 B：修改/追加需求 (带着记忆去问)
        if update_btn and input_val:
            if not st.session_state.current_plan:
                st.warning("请先生成一个基础行程，再提出修改要求哦！")
            else:
                with st.spinner("智生活正在根据新需求调整行程..."):
                    # 构造包含历史记忆的消息列表
                    messages = [{"role": "system", "content": "你是一位专业的旅游管家。用户会对你之前的行程提出修改意见，请根据最新要求更新整个行程表。"}]
                    # 把之前的对话全部喂给 AI
                    for chat in st.session_state.travel_chat_history:
                        messages.append(chat)
                    # 加入最新的修改要求
                    messages.append({"role": "user", "content": f"请修改需求：{input_val}"})

                    response = client.chat.completions.create(model="deepseek-chat", messages=messages)
                    updated_plan = response.choices[0].message.content.replace("<br>", " ")
                    
                    # 更新记忆
                    st.session_state.current_plan = updated_plan
                    st.session_state.travel_chat_history.append({"role": "user", "content": input_val})
                    st.session_state.travel_chat_history.append({"role": "assistant", "content": updated_plan})
                    save_record("出行-修改", updated_plan)

        # --- 4. 显示当前最新的行程 ---
        if st.session_state.current_plan:
            st.markdown("---")
            st.info(f"📊 实时同步：已根据当前需求更新 {datetime.now().month} 月份穿着指南。")
            st.markdown(st.session_state.current_plan)
            
            st.download_button(
                label="💾 下载最终版离线行程单",
                data=st.session_state.current_plan,
                file_name="trip_plan_updated.md"
            )

    # --- Tab 3: 历史记录/离线查看 ---
    with tab3:
        st.header("最近记录")
        conn = sqlite3.connect('history.db')
        import pandas as pd
        df = pd.read_sql_query("SELECT * FROM records ORDER BY time DESC LIMIT 10", conn)
        conn.close()
        if df.empty:
            st.write("暂无历史记录。")
        else:
            for index, row in df.iterrows():
                # 用一个“折叠框”包裹每一条记录
                with st.expander(f"【{row['type']}】 - 记录时间: {row['time']}"):
                    # 如果是出行记录，它含有很多Markdown表格，直接显示出来
                    st.markdown(row['content'])

if __name__ == "__main__":
    main()
