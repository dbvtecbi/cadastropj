import streamlit as st
import requests
import os
from supabase import create_client, Client
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ==========================================
# CREDENCIAIS DO NOTION (Via Variáveis de Ambiente)
# ==========================================
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('DATABASE_ID')

# ==========================================
# CREDENCIAIS DO SUPABASE (Via Variáveis de Ambiente)
# ==========================================
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Inicializa a conexão com o Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "dossies"

# ==========================================
# ESTILO VISUAL DBV CAPITAL
# ==========================================
st.set_page_config(page_title="DBV Capital | Onboarding PJ", layout="centered")

css_dbv = """
<style>
    .stApp { background: linear-gradient(135deg, #050807 0%, #20352f 100%); color: #fafafa; }
    .st-emotion-cache-1wivap2, .st-emotion-cache-16txtl3, div[data-testid="stForm"] {
        background-color: #0b201a; border-radius: 12px; border-top: 4px solid #948161; padding: 20px;
    }
    h1, h2, h3 { color: #948161 !important; font-family: 'Segoe UI', sans-serif; }
    div[data-baseweb="input"] > div { background-color: rgba(5, 8, 7, 0.5) !important; border: 1px solid #20352f !important; color: #fafafa !important; }
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        background-color: #948161; color: #050807; font-weight: bold; border: none; width: 100%; transition: 0.3s;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background-color: #fafafa; color: #0b201a;
    }
</style>
"""
st.markdown(css_dbv, unsafe_allow_html=True)

# ==========================================
# LÓGICA DE BACKEND
# ==========================================
def consultar_cnpj(cnpj_limpo):
    url = f"https://api.opencnpj.org/{cnpj_limpo}?datasets=receita"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def processar_regras_docs(natureza, data_inicio_str):
    natureza = str(natureza).upper()
    try:
        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d")
        hoje = datetime.now()
        diferenca = relativedelta(hoje, data_inicio)
        meses_atuacao = (diferenca.years * 12) + diferenca.months
        anos_atuacao = diferenca.years
    except:
        meses_atuacao = 0
        anos_atuacao = 0

    # KYC e Ficha Cadastral removidos da obrigatoriedade desta tela
    docs = []

    if "MICROEMPREENDEDOR" in natureza or "MEI" in natureza:
        docs.extend(["Documento de identificação dos representantes", "CCMEI", "Declarações de patrimônio líquido e faturamento mensal"])
    elif "LIMITADA" in natureza or "LTDA" in natureza:
        docs.extend(["Documentos dos representantes", "Contrato Social ou Última Alteração", "Instrumento de eleição de administradores", "Comprovante de endereço"])
        if meses_atuacao > 12:
            docs.append("Balanço Patrimonial / DRE (Balancete)")
    elif "ANÔNIMA" in natureza or "S/A" in natureza or "ECONOMIA MISTA" in natureza:
        docs.extend(["Documentos dos representantes", "Estatuto Social registrado", "Atas de eleição da diretoria/administradores"])
        if anos_atuacao > 1:
            docs.append("Balanço Patrimonial (preferencialmente auditado)")
    else:
        docs.extend(["Documentos dos representantes", "Documentos de constituição da empresa"])

    return docs

def hospedar_no_supabase(arquivo_st, cnpj):
    nome_seguro = arquivo_st.name.replace(' ', '_')
    caminho_no_bucket = f"{cnpj}/{nome_seguro}"
    file_bytes = arquivo_st.getvalue()
    
    res = supabase.storage.from_(BUCKET_NAME).upload(
        path=caminho_no_bucket, 
        file=file_bytes, 
        file_options={"content-type": arquivo_st.type, "upsert": "true"}
    )
    
    return supabase.storage.from_(BUCKET_NAME).get_public_url(caminho_no_bucket)

def enviar_direto_notion(cnpj, razao_social, natureza, codigo_assessor, links_gerados):
    arquivos_formatados = []
    for nome_documento, link in links_gerados.items():
        arquivos_formatados.append({
            "type": "external",
            "name": nome_documento,
            "external": { "url": link } 
        })

    payload = {
        "parent": { "database_id": DATABASE_ID },
        "properties": {
            "Empresa": { "title": [ { "text": { "content": razao_social } } ] },
            "CNPJ": { "rich_text": [ { "text": { "content": cnpj } } ] },
            "Natureza": { "rich_text": [ { "text": { "content": natureza } } ] },
            "Assessor": { "rich_text": [ { "text": { "content": codigo_assessor } } ] },
            "Arquivos": { "files": arquivos_formatados } 
        }
    }
    
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    return requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

# ==========================================
# INTERFACE
# ==========================================
st.title("DBV CAPITAL")
st.subheader("Onboarding de Contas PJ")

if "dados_empresa" not in st.session_state:
    st.session_state.dados_empresa = None

cnpj_input = st.text_input("CNPJ da Empresa", placeholder="Digite o CNPJ (ex: 00000000000191)")

if st.button("Consultar Empresa"):
    cnpj_limpo = ''.join(filter(str.isdigit, cnpj_input))
    if len(cnpj_limpo) == 14:
        with st.spinner("Buscando dados na Receita Federal..."):
            dados = consultar_cnpj(cnpj_limpo)
            if dados:
                st.session_state.dados_empresa = dados
                st.success("Dados carregados com sucesso!")
            else:
                st.error("Falha ao buscar CNPJ.")
    else:
        st.error("CNPJ inválido.")

if st.session_state.dados_empresa:
    dados = st.session_state.dados_empresa
    st.markdown("---")
    st.markdown(f"### {dados['razao_social']}")
    st.markdown(f"**Natureza Jurídica:** {dados['natureza_juridica']}")
    
    docs_necessarios = processar_regras_docs(dados['natureza_juridica'], dados.get('data_inicio_atividade', '2024-01-01'))
    
    st.markdown("---")
    
    with st.form("form_notion"):
        st.markdown("### 📎 Anexar Documentos Obrigatórios")
        
        arquivos_recebidos = {}
        for doc in docs_necessarios:
            arquivos_recebidos[doc] = st.file_uploader(f"Anexar: {doc}", type=["pdf", "png", "jpg"], key=doc)
        
        st.markdown("---")
        codigo_ass = st.text_input("Código do Assessor", placeholder="Ex: A1234")
                
        submit_btn = st.form_submit_button("Enviar Documentos")       
        if submit_btn:
            docs_faltantes = [doc for doc, arq in arquivos_recebidos.items() if arq is None]
            
            if not codigo_ass:
                st.warning("Preencha o Código do Assessor antes de enviar.")
            elif len(docs_faltantes) > 0:
                st.error("Erro: Você precisa preencher todos os slots obrigatórios para avançar. Faltou anexar:")
                for faltante in docs_faltantes:
                    st.error(f"- {faltante}")
            else:
                try:
                    with st.spinner("Hospedando arquivos no Supabase..."):
                        links_para_notion = {}
                        for tipo_documento, arquivo_st in arquivos_recebidos.items():
                            link_supabase = hospedar_no_supabase(arquivo_st, dados['cnpj'])
                            links_para_notion[tipo_documento] = link_supabase
                            
                    with st.spinner("Sincronizando com Notion..."):
                        url_notion = "https://api.notion.com/v1/pages"
                        
                        arquivos_formatados = []
                        for nome_doc, link_doc in links_para_notion.items():
                            arquivos_formatados.append({"type": "external", "name": nome_doc, "external": {"url": link_doc}})

                        payload = {
                            "parent": { "database_id": DATABASE_ID },
                            "properties": {
                                "Empresa": { "title": [ { "text": { "content": dados['razao_social'] } } ] },
                                "CNPJ": { "rich_text": [ { "text": { "content": dados['cnpj'] } } ] },
                                "Natureza": { "rich_text": [ { "text": { "content": dados['natureza_juridica'] } } ] },
                                "Assessor": { "rich_text": [ { "text": { "content": codigo_ass } } ] },
                                "Arquivos": { "files": arquivos_formatados } 
                            }
                        }
                        
                        headers = {
                            "Authorization": f"Bearer {NOTION_TOKEN}",
                            "Notion-Version": "2022-06-28",
                            "Content-Type": "application/json"
                        }
                        
                        resposta = requests.post(url_notion, headers=headers, json=payload)
                        
                        if resposta.status_code == 200:
                            st.success("Dossiê processado com sucesso! Arquivos salvos e enviados ao CRM.")
                            st.balloons()
                        else:
                            st.error(f"Erro na API do Notion: {resposta.text}")
                            
                except Exception as e:
                    st.error(f"Erro crítico: {str(e)}")