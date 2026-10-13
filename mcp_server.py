import sys
import logging

# 1. PASANG PEREKAM LOG (Black Box)
logging.basicConfig(
    filename='mcp_server.log', 
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
logging.info("=== SERVER MCP DIBANGUNKAN ===")

try:
    from mcp.server.fastmcp import FastMCP
    import tableauserverclient as TSC
    import json
    import warnings
    
    # Sembunyikan warning sistem agar tidak merusak jalur komunikasi STDIO
    warnings.filterwarnings("ignore")
    logging.info("Library berhasil diimpor.")

    # ============================================================
    # CONFIG TABLEAU CLOUD
    # ============================================================
    TABLEAU_URL = "https://prod-apsoutheast-c.online.tableau.com"
    SITE_ID = ""
    TOKEN_NAME = ""
    TOKEN_VALUE = ""

    mcp = FastMCP("Tableau_MCP")

    def get_tableau_server():
        logging.info("Mencoba login ke Tableau Cloud...")
        tableau_auth = TSC.PersonalAccessTokenAuth(TOKEN_NAME, TOKEN_VALUE, SITE_ID)
        server = TSC.Server(TABLEAU_URL, use_server_version=True)
        server.auth.sign_in(tableau_auth)
        logging.info("Login Tableau Berhasil!")
        return server

    @mcp.tool()
    def list_workbooks() -> str:
        """Mendapatkan daftar semua workbook di Tableau Cloud."""
        logging.info("Tool list_workbooks dipanggil.")
        try:
            server = get_tableau_server()
            workbooks, _ = server.workbooks.get()
            result = [{"name": wb.name, "id": wb.id} for wb in workbooks]
            logging.info(f"Berhasil menarik {len(workbooks)} workbook.")
            return json.dumps(result)
        except Exception as e:
            # Merekam error secara lengkap ke file log agar terlihat
            logging.exception("GAGAL MENARIK WORKBOOKS DARI TABLEAU:")
            return f"Error Tableau: {str(e)}"

    @mcp.tool()
    def list_views(workbook_id: str) -> str:
        """Mendapatkan daftar views/sheets berdasarkan workbook_id."""
        logging.info(f"Tool list_views dipanggil untuk ID: {workbook_id}")
        try:
            server = get_tableau_server()
            workbook = server.workbooks.get_by_id(workbook_id)
            server.workbooks.populate_views(workbook)
            result = [{"view_name": v.name, "view_id": v.id} for v in workbook.views]
            logging.info("Berhasil menarik views.")
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error list_views: {e}")
            return f"Error: {str(e)}"

    @mcp.tool()
    def get_view_data(view_id: str) -> str:
        """
        Gunakan alat ini untuk membaca dan mengunduh isi tabel data angka (CSV) dari sebuah view.
        Parameter 'view_id' wajib diisi dengan ID yang didapat dari alat list_views.
        """
        logging.info(f"Tool get_view_data dipanggil untuk ID: {view_id}")
        try:
            server = get_tableau_server()
            view_item = server.views.get_by_id(view_id)
            server.views.populate_csv(view_item)
            
            # Ekstrak CSV dan batasi 100 baris pertama untuk menghemat token Groq
            csv_bytes = b"".join(view_item.csv)
            csv_text = csv_bytes.decode('utf-8')
            lines = csv_text.splitlines()
            logging.info("Berhasil menarik data CSV.")
            
            return "\n".join(lines[:100])
        except Exception as e:
            logging.error(f"Error get_view_data: {e}")
            return f"Error Tableau: {str(e)}"    

    if __name__ == "__main__":
        logging.info("Memulai transport STDIO... Menunggu Client.")
        mcp.run(transport='stdio')

except Exception as e:
    logging.exception("SERVER CRASH SECARA FATAL:")