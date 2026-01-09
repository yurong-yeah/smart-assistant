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
    st.markdown("""
    <style>
    /* 去掉 Tab 内容默认上边距 */
    [data-testid="stTabContent"] {
        padding-top: 0 !important;
        margin-top: 0 !important;
    }
    /* ===== 全局背景 ===== */
    .stApp {
        background: linear-gradient(180deg, #f6f8fb 0%, #eef2f7 100%);
        font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }

    /* ===== 主内容区宽度 ===== */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1100px;
    }

    /* ===== 标题 ===== */
    h1, h2, h3 {
        font-weight: 700;
    }

    /* ===== Tabs 美化 ===== */
    [data-baseweb="tab-list"] {
        gap: 12px;
    }

    [data-baseweb="tab"] {
        background: #ffffff;
        border-radius: 14px;
        padding: 10px 22px;
        font-weight: 600;
        color: #666;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
    }

    [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #4f8cff, #6fb1ff);
        color: white;
    }

    /* ===== 卡片容器 ===== */
    .app-card {
        background: white;
        border-radius: 18px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.06);
    }

    /* ===== 输入框 ===== */
    input, textarea {
        border-radius: 12px !important;
    }

    /* ===== 按钮统一风格 ===== */
    button[kind="primary"] {
        background: linear-gradient(135deg, #4f8cff, #6fb1ff) !important;
        border-radius: 14px !important;
        height: 46px;
        font-weight: 600;
    }

    button[kind="secondary"] {
        border-radius: 14px !important;
        height: 46px;
        font-weight: 600;
    }

    /* ===== Download 按钮 ===== */
    [data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #34c759, #4cd964) !important;
        color: white !important;
        border-radius: 14px;
        height: 46px;
    }

    /* ===== 展示 Markdown 内容更舒服 ===== */
    .stMarkdown {
        line-height: 1.75;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("智能生活服务助手")
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["🥗 智能餐厅", "🚗 出行规划", "📂 历史/离线"])

    # --- Tab 1: 餐饮场景 ---
    with tab1:
        # ===== 样式（仅作用于本 Tab）=====
        st.markdown("""
            <style>
            /* 卡片容器 */
            .menu-card {
                background: white;
                border-radius: 18px;
                padding: 24px;
                box-shadow: 0 12px 30px rgba(0,0,0,0.06);
                margin-bottom: 24px;
            }

            /* 上传区域文字隐藏 */
            [data-testid="stFileUploaderDropzoneInstructions"] div span,
            [data-testid="stFileUploaderDropzoneInstructions"] div small {
                display: none !important;
            }

            /* 上传区域中文提示 */
            [data-testid="stFileUploaderDropzoneInstructions"] div::before {
                content: "将图片拖拽至此或上传菜单照片";
                display: block;
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 6px;
            }

            [data-testid="stFileUploaderDropzoneInstructions"] div::after {
                content: "支持 JPG / PNG / JPEG，单张 ≤ 200MB";
                display: block;
                font-size: 12px;
                color: #808495;
            }

            /* 只改上传按钮 */
            [data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"] {
                font-size: 0 !important;
                border-radius: 12px !important;
                padding: 6px 16px !important;
            }

            [data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"]::after {
                content: "📷 浏览文件";
                font-size: 14px !important;
                font-weight: 600;
            }

            /* 主按钮 */
            .menu-analyze-btn button {
                width: 100%;
                height: 46px;
                border-radius: 14px;
                font-weight: 600;
            }
            </style>
        """, unsafe_allow_html=True)

        # ===== 卡片开始 =====
        st.header("🥗 菜单智能识别")
        st.caption("拍照上传菜单，获取安全、健康的饮食建议")

        goal = st.text_input(
            "你的健康需求",
            placeholder="例如：控糖、少油、花生过敏"
        )

        file = st.file_uploader(
            "上传菜单图片",
            type=['jpg', 'png', 'jpeg']
        )

        st.markdown('<div class="menu-analyze-btn">', unsafe_allow_html=True)
        analyze_clicked = st.button("🚀 开始分析")
        st.markdown('</div>', unsafe_allow_html=True)

        # ===== 分析逻辑（完全不变）=====
        if file and analyze_clicked:
            with st.spinner("智生活正在分析菜单..."):
                res_text = analyze_menu(file, goal)

                st.markdown("---")
                st.subheader("📋 餐饮健康分析报告")
                st.markdown(res_text)

                save_record("餐饮", res_text)

    # --- Tab 2: 出行场景 ---
    with tab2:
        # ===== 样式（只影响 Tab2）=====
        st.markdown("""
        <style>
        .travel-card {
            background: white;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.06);
            margin-bottom: 24px;
        }

        .travel-btn button {
            width: 100%;
            height: 46px;
            border-radius: 14px;
            font-weight: 600;
        }

        .travel-result {
            background: #fafbff;
            border-radius: 16px;
            padding: 20px;
        }
        </style>
        """, unsafe_allow_html=True)

        # ===== Session 初始化（不动）=====
        if 'travel_chat_history' not in st.session_state:
            st.session_state.travel_chat_history = []
        if 'current_plan' not in st.session_state:
            st.session_state.current_plan = ""

        st.header("🚗 旅游行程智能规划")
        st.caption("支持语音输入，可多轮修改行程")

        st.write("🎤 点击下方按钮说话或直接输入旅行需求：")
        v_text = speech_to_text(
            language='zh',
            start_prompt="🎤 点击说话",
            just_once=True,
            key="travel_stt"
        )
        input_val = st.text_input(
            "你的旅行想法 / 修改需求",
            value=v_text if v_text else "",
            placeholder="例如：带 5 岁小孩去北京自然博物馆 / 把午饭换成素食"
        )

        col1, col2 = st.columns(2)
        with col1:
            generate_btn = st.button("🌟 生成全新行程")
        with col2:
            update_btn = st.button("🔄 修改 / 追加需求")

        # ===== 业务逻辑（完全不变）=====
        if generate_btn and input_val:
            st.session_state.travel_chat_history = []
            with st.spinner("智生活正在为您规划全新行程..."):
                messages = [
                    {"role": "system", "content": "你是一位专业的旅游管家。请生成带天气、穿着建议和Markdown表格行程的计划。"},
                    {"role": "user", "content": input_val}
                ]

                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages
                )

                new_plan = response.choices[0].message.content.replace("<br>", " ")

                st.session_state.current_plan = new_plan
                st.session_state.travel_chat_history.append({"role": "user", "content": input_val})
                st.session_state.travel_chat_history.append({"role": "assistant", "content": new_plan})
                save_record("出行", new_plan)

        if update_btn and input_val:
            if not st.session_state.current_plan:
                st.warning("请先生成一个基础行程，再提出修改要求哦！")
            else:
                with st.spinner("智生活正在根据新需求调整行程..."):
                    messages = [{"role": "system", "content": "你是一位专业的旅游管家。请根据最新要求更新完整行程。"}]
                    for chat in st.session_state.travel_chat_history:
                        messages.append(chat)
                    messages.append({"role": "user", "content": f"请修改需求：{input_val}"})

                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=messages
                    )

                    updated_plan = response.choices[0].message.content.replace("<br>", " ")

                    st.session_state.current_plan = updated_plan
                    st.session_state.travel_chat_history.append({"role": "user", "content": input_val})
                    st.session_state.travel_chat_history.append({"role": "assistant", "content": updated_plan})
                    save_record("出行-修改", updated_plan)

        # ===== 结果卡片 =====
        if st.session_state.current_plan:
            st.markdown('<div class="travel-card travel-result">', unsafe_allow_html=True)

            st.info(f"📊 实时同步：已根据当前需求更新 {datetime.now().month} 月穿着指南")
            st.markdown(st.session_state.current_plan)

            st.download_button(
                label="💾 下载最终版离线行程单",
                data=st.session_state.current_plan,
                file_name="trip_plan_updated.md"
            )

            st.markdown('</div>', unsafe_allow_html=True)

            
    # --- Tab 3: 历史记录/离线查看 ---
    with tab3:
        # ===== 样式（只影响 Tab3）=====
        st.markdown("""
        <style>
        .history-card {
            background: white;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.06);
        }

        .history-empty {
            text-align: center;
            color: #888;
            padding: 40px 0;
        }

        /* expander 标题美化 */
        details > summary {
            font-size: 15px;
            font-weight: 600;
            padding: 12px 8px;
        }
        </style>
        """, unsafe_allow_html=True)

        # ===== 卡片开始 =====

        st.header("📂 最近记录")

        conn = sqlite3.connect('history.db')
        import pandas as pd
        df = pd.read_sql_query(
            "SELECT * FROM records ORDER BY time DESC LIMIT 10",
            conn
        )
        conn.close()

        if df.empty:
            st.markdown('<div class="history-empty">暂无历史记录</div>', unsafe_allow_html=True)
        else:
            for _, row in df.iterrows():
                with st.expander(f"🕒 {row['time']} · {row['type']}"):
                    st.markdown(row['content'])


if __name__ == "__main__":
    main()
