import streamlit as st
import requests
from supabase import create_client, Client
from datetime import datetime
from dateutil.relativedelta import relativedelta
import unicodedata
import re
import os

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
BUCKET_NAME = "dossies"
# 1. INICIALIZAÇÃO CORRETA DO CLIENTE SUPABASE
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# CSS PERSONALIZADO
# ==========================================
css_dbv = """
<style>
    /* REMOVER FAIXA SUPERIOR E RODAPÉ DO STREAMLIT */
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }

    /* Fundo principal da página */
    .stApp { background: linear-gradient(135deg, #050807 0%, #20352f 100%); color: #fafafa; }
    
    /* Caixas de formulário e containers */
    .st-emotion-cache-1wivap2, .st-emotion-cache-16txtl3, div[data-testid="stForm"] {
        background-color: #0b201a; border-radius: 12px; border-top: 4px solid #948161; padding: 20px;
    }
    
    /* Títulos */
    h1, h2, h3 { color: #948161 !important; font-family: 'Segoe UI', sans-serif; }
    
    /* Labels e Textos gerais para garantir leitura no fundo escuro */
    label, p { color: #fafafa !important; }
    
    /* CAMPOS DE TEXTO (Inputs e Text Area) */
    div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div { 
        background-color: #f7f9f8 !important; 
        border: 1px solid #948161 !important; 
    }
    
    /* Forçando a cor do texto digitado para escuro (preto) */
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        color: #050807 !important;
        -webkit-text-fill-color: #050807 !important;
    }
    
    /* CORREÇÃO FORÇADA DO FILE UPLOADER */
    [data-testid="stFileUploadDropzone"] {
        background-color: #152b24 !important; 
        border: 2px dashed #948161 !important;
        border-radius: 8px !important;
    }
    [data-testid="stFileUploadDropzone"] * {
        color: #fafafa !important;
        -webkit-text-fill-color: #fafafa !important;
        opacity: 1 !important; 
    }
    [data-testid="stFileUploadDropzone"] button {
        background-color: #948161 !important;
        border: 1px solid #948161 !important;
        border-radius: 6px !important;
    }
    [data-testid="stFileUploadDropzone"] button,
    [data-testid="stFileUploadDropzone"] button * {
        color: #050807 !important; 
        -webkit-text-fill-color: #050807 !important;
        fill: #050807 !important;  
        font-weight: bold !important;
    }
    [data-testid="stFileUploadDropzone"] button:hover {
        background-color: #050807 !important; 
        border: 1px solid #948161 !important;
    }
    [data-testid="stFileUploadDropzone"] button:hover,
    [data-testid="stFileUploadDropzone"] button:hover * {
        color: #948161 !important; 
        -webkit-text-fill-color: #948161 !important;
        fill: #948161 !important;  
    }

    /* Botões Gerais */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        background-color: #948161; color: #050807; font-weight: bold; border: none; width: 100%; transition: 0.3s;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background-color: #fafafa; color: #0b201a;
    }
</style>
"""
st.markdown(css_dbv, unsafe_allow_html=True)

def consultar_cnpj(cnpj_limpo):
    url = f"https://api.opencnpj.org/{cnpj_limpo}?datasets=receita"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def processar_regras_docs(dados_empresa):
    # ==========================================
    # 1. EXTRAÇÃO DE TODOS OS CAMPOS RELEVANTES
    # ==========================================
    natureza = str(dados_empresa.get('natureza_juridica', ''))
    razao_social = str(dados_empresa.get('razao_social', ''))
    data_inicio_str = dados_empresa.get('data_inicio_atividade', '2024-01-01')
    
    # Extrai os textos dos CNAEs para reforçar a busca (ex: "Serviços de advocacia")
    cnaes = dados_empresa.get('cnaes', [])
    cnaes_desc = " ".join([str(cnae.get('descricao', '')) for cnae in cnaes])
    
    # Busca a opção MEI direto na raiz
    opcao_mei = str(dados_empresa.get('opcao_mei', '')).strip().upper()
    is_mei = opcao_mei in ['S', 'SIM', 'TRUE', '1']

    # Junta tudo em uma "super string" para não deixar nada escapar
    texto_busca = f"{natureza} {razao_social} {cnaes_desc}"

    # ==========================================
    # 2. NORMALIZAÇÃO ABSOLUTA DA STRING DE BUSCA
    # ==========================================
    # Remove acentos, pontuações, traços e deixa tudo em maiúsculo
    texto_limpo = unicodedata.normalize('NFKD', texto_busca).encode('ASCII', 'ignore').decode('utf-8')
    texto_limpo = re.sub(r'[^A-Z0-9]', ' ', texto_limpo.upper())
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()
    
    # Cálculo de tempo de atuação
    try:
        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d")
        diferenca = relativedelta(datetime.now(), data_inicio)
        meses_atuacao = (diferenca.years * 12) + diferenca.months
    except Exception:
        meses_atuacao = 999 

    docs_obrigatorios = []
    docs_opcionais = []

    def aplicar_regra_contabil_geral():
        if 6 <= meses_atuacao <= 12:
            docs_obrigatorios.append("Declaração de faturamento e patrimônio")
        elif meses_atuacao > 12:
            docs_obrigatorios.append("Balanço e DRE / Balancete / Sped (Se Não Simples) OU Declarações de PL e Faturamento (Se Simples Nacional)")

    # ==========================================
    # 3. LÓGICA DE CATEGORIZAÇÃO PRIORITÁRIA
    # ==========================================
    # Casos mais específicos (como Condomínio e Advogado) ficam no topo.

    # 1. MEI
    if is_mei:
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "CCMEI",
            "Declarações de Patrimônio Líquido e de Faturamento Mensal (Assinado pelo rep)"
        ]

    # 2. Condomínio Edifício (Pega no Nome, CNAE ou Natureza)
    elif any(termo in texto_limpo for termo in ["CONDOMINIO", "308 5"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Ata de eleição do Síndico",
            "Convenção do condomínio (Registro de Imóveis)",
            "Balancete mensal ou do último exercício (assinado)"
        ]
        docs_opcionais.append("Ata de Assembleia aprovando outorga de procurações (se houver)")

    # 3. Sociedade Simples - Advogados (Pega no Nome, CNAE ou Natureza)
    elif any(termo in texto_limpo for termo in ["ADVOGADO", "ADVOCACIA", "OAB", "323 9"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Contrato Social e/ou última Alteração Contratual Consolidada (Registrados na OAB)"
        ]
        docs_opcionais.append("Instrumento de delegação e/ou nomeação de Administradores (se houver)")
        aplicar_regra_contabil_geral()

    # 4. Cartório / Serviço Notarial
    elif any(termo in texto_limpo for termo in ["NOTARIAL", "CARTORIO", "REGISTRAL", "303 4"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Inscrição do Tabelião no Cadastro Específico do INSS (CEI)"
        ]
        if 6 <= meses_atuacao <= 12:
            docs_obrigatorios.append("Declaração de faturamento e patrimônio")
        elif meses_atuacao > 12:
            docs_obrigatorios.append("Balanço e DRE OU Demonstrativo financeiro oficial publicado no CNJ")

    # 5. Consórcio de Sociedades
    elif any(termo in texto_limpo for termo in ["CONSORCIO", "215 1"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Contrato Social e/ou última Alteração Contratual Consolidada"
        ]
        docs_opcionais.append("Instrumento de delegação e/ou nomeação de Administradores (se houver)")
        aplicar_regra_contabil_geral()

    # 6. Igrejas e Templos Religiosos
    elif any(termo in texto_limpo for termo in ["IGREJA", "TEMPLO", "RELIGIOSA"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Estatuto Social ou Consolidação",
            "Indicação/Nomeação dos representantes legais (Cartório ou Bula Papal)"
        ]
        docs_opcionais.append("Formulário de isenção fiscal IR/IOF preenchido e assinado (se aplicável)")
        aplicar_regra_contabil_geral()

    # 7. Associação, Fundação, Instituto e Cooperativa
    elif any(termo in texto_limpo for termo in ["ASSOCIACAO", "FUNDACAO", "INSTITUTO", "COOPERATIVA", "399 9", "306 9", "214 3"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Ata de Eleição da Diretoria Atual",
            "Estatuto Social ou Consolidação"
        ]
        docs_opcionais.append("Formulário de isenção fiscal IR/IOF + ECF (se aplicável)")
        aplicar_regra_contabil_geral()

    # 8. Partido Político
    elif any(termo in texto_limpo for termo in ["PARTIDO", "POLITICO", "320 4"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Estatuto Partidário de criação (TSE)",
            "Última Alteração do Estatuto Partidário Consolidado"
        ]
        aplicar_regra_contabil_geral()

    # 9. Produtor Rural
    elif "RURAL" in texto_limpo:
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Declarações de Patrimônio Líquido e de Faturamento Mensal"
        ]

    # 10. Sociedade Anônima S/A
    elif any(termo in texto_limpo for termo in ["ANONIMA", " S A ", " SA ", "204 6", "205 4"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Ata de Eleição da Diretoria Atual",
            "Boletim de subscrição, organograma ou livro de ações",
            "Estatuto Social ou Consolidação"
        ]
        docs_opcionais.append("Ata de Assembleia com o último aumento de capital (se houver)")
        aplicar_regra_contabil_geral()

    # 11. Empresário Individual (Código 213-5)
    elif any(termo in texto_limpo for termo in ["EMPRESARIO INDIVIDUAL", "FIRMA INDIVIDUAL", "213 5"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "RE - Requerimento de empresário individual"
        ]
        aplicar_regra_contabil_geral()

    # 12. Sociedade Limitada (LTDA) - Cai aqui se não foi filtrado nos específicos
    elif any(termo in texto_limpo for termo in ["LIMITADA", "LTDA", "SOCIEDADE EMPRESARIA", "206 2"]):
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Contrato Social e/ou última Alteração Contratual Consolidada"
        ]
        docs_opcionais.append("Instrumento de delegação e/ou nomeação de Administradores (se houver)")
        aplicar_regra_contabil_geral()

    # 13. Sociedade Simples Pura
    elif "SIMPLES" in texto_limpo and "EMPRESARIA" not in texto_limpo:
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Contrato Social e/ou última Alteração Contratual Consolidada"
        ]
        docs_opcionais.append("Instrumento de delegação e/ou nomeação de Administradores (se houver)")
        aplicar_regra_contabil_geral()

    # 14. Fallback Genérico (Se absolutamente nada der "match")
    else:
        docs_obrigatorios = [
            "Documento de identificação dos representantes",
            "Documentos de constituição da empresa"
        ]
        aplicar_regra_contabil_geral()

    return {"obrigatorios": docs_obrigatorios, "opcionais": docs_opcionais}

def hospedar_no_supabase(arquivo_st, cnpj):
    nome_seguro = arquivo_st.name.replace(' ', '_')
    caminho_no_bucket = f"{cnpj}/{nome_seguro}"
    file_bytes = arquivo_st.getvalue()
    
    res = supabase_client.storage.from_(BUCKET_NAME).upload(
        path=caminho_no_bucket, 
        file=file_bytes, 
        file_options={"content-type": arquivo_st.type, "upsert": "true"}
    )
    
    return supabase_client.storage.from_(BUCKET_NAME).get_public_url(caminho_no_bucket)

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
    st.markdown(f"### {dados.get('razao_social', 'Razão Social não encontrada')}")
    st.markdown(f"**Natureza Jurídica:** {dados.get('natureza_juridica', 'N/A')}")
    
    # AQUI ESTÁ A CORREÇÃO: Enviando todo o objeto 'dados'
    regras_docs = processar_regras_docs(dados)
    docs_obrigatorios = regras_docs["obrigatorios"]
    docs_opcionais = regras_docs["opcionais"]
    
    st.markdown("---")
    
    st.markdown("### 👤 Informações de Acesso")
    texto_acessos = st.text_area(
        "Acessos da Conta", 
        placeholder="Insira os dados do usuário:\nNome: João da Silva\nTelefone: (11) 99999-9999\nE-mail: joao@email.com\nNível de Acesso: Master / Operador / Emissor de Ordem",
        height=150
    )
    
    st.warning("⚠️ **Observação Importante:** Caso seja solicitado acesso nível **Master**, **Operador** ou **Emissor de Ordem**, é imprescindível que você providencie e anexe o **documento de identidade**, **e-mail** e **telefone** de contato na documentação.")
    
    st.markdown("---")

    with st.form("form_notion"):
        st.markdown("### 📎 Anexar Documentos Obrigatórios")
        
        arquivos_recebidos = {}
        
        # Gera os campos de upload apenas para documentos OBRIGATÓRIOS
        for doc in docs_obrigatorios:
            arquivos_recebidos[doc] = st.file_uploader(f"Anexar: {doc}", type=["pdf", "png", "jpg"], key=f"obrig_{doc}")
        
        # Gera os campos de upload para documentos OPCIONAIS (se existirem para a natureza jurídica)
        if len(docs_opcionais) > 0:
            st.markdown("### 📄 Documentos Complementares / Opcionais (Se aplicável)")
            for doc in docs_opcionais:
                arquivos_recebidos[doc] = st.file_uploader(f"Anexar: {doc}", type=["pdf", "png", "jpg"], key=f"opc_{doc}")
        
        st.markdown("---")
        codigo_ass = st.text_input("Código do Assessor", placeholder="Ex: A1234")
                
        submit_btn = st.form_submit_button("Enviar Documentos")       
        
        if submit_btn:
            # Validação: Garante que apenas os documentos OBRIGATÓRIOS foram preenchidos
            docs_faltantes = [doc for doc in docs_obrigatorios if arquivos_recebidos[doc] is None]
            
            if not codigo_ass:
                st.warning("Preencha o Código do Assessor antes de enviar.")
            elif len(docs_faltantes) > 0:
                st.error("Erro: Você precisa preencher todos os slots OBRIGATÓRIOS para avançar. Faltou anexar:")
                for faltante in docs_faltantes:
                    st.error(f"- {faltante}")
            else:
                try:
                    # Filtra apenas os arquivos que foram de fato enviados, ignorando os vazios (None)
                    arquivos_para_enviar = {nome: arq for nome, arq in arquivos_recebidos.items() if arq is not None}

                    with st.spinner("Hospedando arquivos no Supabase..."):
                        links_para_notion = {}
                        for tipo_documento, arquivo_st in arquivos_para_enviar.items():
                            link_supabase = hospedar_no_supabase(arquivo_st, dados['cnpj'])
                            links_para_notion[tipo_documento] = link_supabase
                            
                    with st.spinner("Sincronizando com Notion..."):
                        url_notion = "https://api.notion.com/v1/pages"
                        
                        arquivos_formatados = []
                        for nome_doc, link_doc in links_para_notion.items():
                            # CORREÇÃO: Limita o nome do arquivo a 100 caracteres para a API do Notion
                            nome_curto = nome_doc[:97] + "..." if len(nome_doc) > 100 else nome_doc
                            
                            arquivos_formatados.append({
                                "type": "external", 
                                "name": nome_curto, 
                                "external": {"url": link_doc}
                            })

                        propriedades_notion = {
                            "Empresa": { "title": [ { "text": { "content": dados.get('razao_social', '') } } ] },
                            "CNPJ": { "rich_text": [ { "text": { "content": dados.get('cnpj', '') } } ] },
                            "Natureza": { "rich_text": [ { "text": { "content": dados.get('natureza_juridica', '') } } ] },
                            "Assessor": { "rich_text": [ { "text": { "content": codigo_ass } } ] },
                            "Acessos": { "rich_text": [ { "text": { "content": texto_acessos } } ] },
                            "Arquivos": { "files": arquivos_formatados } 
                        }
                        
                        payload = {
                            "parent": { "database_id": DATABASE_ID },
                            "properties": propriedades_notion
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