import streamlit as st
import asyncio
import json
import sys
import os
from groq import AsyncGroq

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ============================================================
# CONFIG & GROQ API
# ============================================================
# MASUKKAN API KEY UTUH ANDA DI SINI (JANGAN LUPA)
GROQ_API_KEY = "" 
MODEL = "qwen/qwen3.8-27b"
MAX_TOOL_ROUNDS = 5
client_groq = AsyncGroq(api_key=GROQ_API_KEY)

# ============================================================
# PAGE CONFIG & DARK MODE CSS
# ============================================================
st.set_page_config(page_title="Tableau MCP Assistant", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #121212 !important; color: #e0e0e0 !important; }
    h1, h2, h3, p, span, div { color: #e0e0e0 !important; }
    .block-container { max-width: 1050px; padding-top: 2rem; padding-bottom: 6rem; }
    div[data-testid="stChatInput"] { border-radius: 18px; background-color: #2d2d2d !important; border-color: #404040 !important; }
    div[data-testid="stChatInput"] textarea { color: white !important; }
    div[data-testid="stChatMessage"] { padding: 10px 0; background-color: transparent !important; }
    section[data-testid="stSidebar"] { background-color: #1e1e1e !important; border-right: 1px solid #333 !important; }
    </style>
    """, unsafe_allow_html=True
)

if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================================================
# SIDEBAR & HEADER
# ============================================================
with st.sidebar:
    st.markdown("### 📊 Tableau Data Assistant")
    st.caption("AI Data Analysis • Groq + MCP")
    st.divider()
    if st.button("＋ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.markdown("# 📊 Tableau Data Assistant")
st.markdown("AI Data Analysis • Groq + MCP")
st.divider()

if not st.session_state.messages:
    st.markdown("### Halo! Ada yang boleh saya bantu?")
    st.caption("Contoh: 'Berapa banyak workbook yang saya ada?'")

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])

# ============================================================
# QWEN (GROQ) + MCP LOGIC
# ============================================================
async def ask_qwen(question):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    server_params = StdioServerParameters(
        command=sys.executable, 
        args=["-u", "mcp_server.py"],
        env=env
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_result = await session.list_tools()

                # =======================================================
                # PERBAIKAN: NORMALISASI SKEMA UNTUK GROQ API
                # =======================================================
                tools = []
                for tool in mcp_result.tools:
                    # Ambil schema dari versi library mcp manapun
                    schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {}))
                    
                    if not isinstance(schema, dict):
                        schema = {}
                    
                    # Groq mewajibkan key "type" dan "properties" ada secara eksplisit
                    if "type" not in schema:
                        schema["type"] = "object"
                    if "properties" not in schema:
                        schema["properties"] = {}

                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "Tanpa deskripsi",
                            "parameters": schema
                        }
                    })

                SYSTEM_PROMPT = """
                Anda adalah Senior Data Analyst yang bekerja dengan data Tableau melalui tool MCP.
                Tugas Anda: mengubah data view Tableau menjadi angka yang akurat, ringkasan, dan insight yang bisa ditindaklanjuti. Bukan sekadar membacakan data.

                ## ALUR KERJA
                1. Pahami pertanyaan: metrik apa, dimensi apa (region, kategori, waktu), dan jenis pertanyaannya (ringkasan, perbandingan, tren, "kenapa").
                2. Temukan view yang tepat. Jika belum jelas view mana yang relevan, panggil list_views lebih dulu. Jangan menebak nama view.
                3. Ambil datanya, lalu periksa dulu: nama kolom, tipe data, jumlah baris, rentang tanggal, nilai kosong, dan apakah ada filter yang aktif di view.
                4. Hitung. Lakukan semua perhitungan dengan tool kalkulasi/kode (mis. pandas), jangan menghitung di kepala. Jika tidak ada tool kalkulasi, hitung langkah demi langkah dan tunjukkan rumusnya.
                5. Interpretasikan hasilnya, lalu jawab dengan format di bawah.

                ## ATURAN PERHITUNGAN
                - Rasio (profit margin, discount rate, AOV) dihitung dari total: SUM(numerator) / SUM(denominator). Jangan merata-ratakan rasio per baris.
                - Sebutkan definisi metrik yang dipakai, misalnya "Profit Margin = SUM(Profit) / SUM(Sales)".
                - Untuk perbandingan, sertakan selisih absolut dan persentase, serta periode pembanding yang jelas (MoM, YoY, vs rata-rata).
                - Untuk ranking, tampilkan top/bottom N beserta kontribusinya terhadap total (% of total).
                - Cek outlier dan baris duplikat sebelum menyimpulkan sesuatu.
                - Jika data terpotong (jumlah baris sama dengan batas maksimum tool) atau view sudah terfilter, katakan itu dan jangan klaim angka sebagai total keseluruhan.

                ## MENJAWAB "KENAPA"
                - Uraikan metrik ke dalam komponen penyusunnya (mis. Profit turun: karena Sales turun, Quantity turun, atau Discount naik?).
                - Bandingkan segmen yang tinggi vs rendah pada Sales, Quantity, Discount, Profit, kategori, dan region. Periksa juga perubahan dari waktu ke waktu.
                - Bedakan fakta (terlihat di data) dari hipotesis (dugaan penyebab). Korelasi bukan bukti sebab-akibat; gunakan kata seperti "kemungkinan" atau "konsisten dengan".
                - Jika data di view ini tidak cukup untuk menjelaskan penyebabnya, katakan dengan jujur. Lalu panggil list_views, pilih view yang kemungkinan menyimpan data pendukung, dan tawarkan atau langsung lakukan pemeriksaan tambahan.

                ## ATURAN KEJUJURAN
                - Jangan mengarang angka, kolom, atau view yang tidak ada di data.
                - Jika pertanyaan ambigu dan jawabannya bisa sangat berbeda (mis. "penjualan" bisa Sales atau Quantity), ajukan satu pertanyaan klarifikasi singkat, atau nyatakan asumsi yang Anda pakai.
                - Jika tool gagal atau mengembalikan data kosong, laporkan apa adanya dan jangan mengisi dengan perkiraan.

                ## FORMAT JAWABAN (Bahasa Indonesia, ringkas)
                1. **Jawaban singkat**: 1-2 kalimat yang langsung menjawab pertanyaan.
                2. **Angka kunci**: tabel atau poin berisi angka penting dengan format yang rapi (pemisah ribuan, satuan mata uang, 1-2 desimal untuk persen).
                3. **Insight & alasan**: 2-4 temuan yang didukung angka, disusun dari yang paling berdampak.

                Untuk pertanyaan sederhana (satu angka), cukup jawab singkat tanpa seluruh struktur di atas.
                """.strip()

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ]

                for _ in range(MAX_TOOL_ROUNDS):
                    # =======================================================
                    # PERBAIKAN: TANGKAP ERROR GROQ DISINI AGAR SERVER TIDAK CRASH
                    # =======================================================
                    try:
                        response = await client_groq.chat.completions.create(
                            model=MODEL,
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                            temperature=0.1
                        )
                    except Exception as api_err:
                        return f"❌ **Error dari Groq API:** {str(api_err)}"
                    
                    message = response.choices[0].message
                    tool_calls = message.tool_calls

                    if not tool_calls:
                        return message.content

                    messages.append({
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}} 
                            for t in tool_calls
                        ]
                    })

                    for call in tool_calls:
                        tool_name = call.function.name
                        arguments = json.loads(call.function.arguments)

                        try:
                            result = await session.call_tool(tool_name, arguments)
                            output = [content.text if hasattr(content, "text") else str(content) for content in result.content]
                            tool_output = "\n".join(output)
                        except Exception as e:
                            tool_output = f"Ralat mengeksekusi tool '{tool_name}': {str(e)}"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": tool_name,
                            "content": tool_output
                        })

                return "Maaf, proses analisis mencapai batas maksimum loop."

    except Exception as client_err:
        return f"❌ **Error Komunikasi Server:** {str(client_err)}"

def run_qwen(question):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(ask_qwen(question))

# ============================================================
# CHAT INPUT
# ============================================================
question = st.chat_input("Tanyakan sesuatu tentang data Tableau...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="👤"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Menganalisis data..."):
            answer = run_qwen(question)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})