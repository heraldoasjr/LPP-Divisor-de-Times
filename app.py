import streamlit as st
import pandas as pd
import numpy as np
import itertools
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Divisor Hugo 2026",
    page_icon="⚽",
    layout="centered"
)

# --- CONSTANTES ---
FORMACAO_IDEAL = ['Z', 'L', 'L', 'V', 'M', 'M', 'A']
MAPA_SIGLAS = {
    'G': 'Goleiro', 'Z': 'Zagueiro', 'L': 'Lateral', 
    'V': 'Volante', 'M': 'Meia', 'A': 'Atacante', 'RESERVA': 'Reserva'
}

# --- FUNÇÕES DE DADOS ---

@st.cache_data
def carregar_dados_ranking(arquivo):
    try:
        df = pd.read_excel(arquivo, sheet_name='Ranking', header=1, engine='openpyxl')
        
        colunas_uteis = {'#': 'Posicao', 'Nome': 'Nome', 'Pontos/Jogo': 'Skill'}
        df.rename(columns=colunas_uteis, inplace=True)
        
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', na=False)]
        cols_nome = [c for c in df.columns if 'Nome' in str(c)]
        if cols_nome: df.rename(columns={cols_nome[0]: 'Nome'}, inplace=True)
        
        df = df.dropna(subset=['Nome'])
        df['Nome'] = df['Nome'].astype(str)
        df['Nome_Busca'] = df['Nome'].str.strip().str.lower()
        df['Skill'] = pd.to_numeric(df['Skill'], errors='coerce').fillna(df['Skill'].mean())
        
        # Identifica Posição Primária
        df['Pos_Prim_Bruta'] = df['Posicao'].astype(str).apply(lambda x: x.split('/')[0].strip())
        
        return df
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None

def obter_posicao_detalhada(string_posicao):
    if pd.isna(string_posicao): return 'M', 'M'
    partes = str(string_posicao).split('/')
    primaria = partes[0].strip()
    secundaria = partes[1].strip() if len(partes) > 1 else primaria
    
    def normalizar(pos):
        pos = pos.upper()
        if pos in ['LD', 'LE']: return 'L'
        if pos == 'S': return 'A'
        return pos
    return normalizar(primaria), normalizar(secundaria)

def map_nomes_posicoes(sigla):
    return MAPA_SIGLAS.get(sigla, sigla)

# --- LÓGICA TÁTICA E SORTEIO ---

def organizar_tatica(df_time):
    time_copia = df_time.copy()
    slots_abertos = FORMACAO_IDEAL.copy()
    escalacao_final = []
    
    # 1. Goleiros
    goleiros = time_copia[time_copia['Pos_Prim'] == 'G']
    for _, g in goleiros.iterrows():
        escalacao_final.append({'Posicao': 'Goleiro', 'Nome': g['Nome'], 'Skill': g['Skill'], 'Origem': g['Posicao']})
        time_copia.drop(g.name, inplace=True)

    # 2. Alocação
    def tentar_alocar(criterio):
        alocados = []
        for idx, row in time_copia.iterrows():
            pos = row[criterio]
            if pos in slots_abertos:
                escalacao_final.append({
                    'Posicao': map_nomes_posicoes(pos), 
                    'Nome': row['Nome'], 
                    'Skill': row['Skill'], 
                    'Origem': row['Posicao']
                })
                slots_abertos.remove(pos)
                alocados.append(idx)
        time_copia.drop(alocados, inplace=True)

    tentar_alocar('Pos_Prim')
    tentar_alocar('Pos_Sec')
    
    # 3. Improvisos
    for idx, row in time_copia.iterrows():
        if slots_abertos:
            vaga = slots_abertos.pop(0)
            escalacao_final.append({
                'Posicao': map_nomes_posicoes(vaga) + " (Imp)", 
                'Nome': row['Nome'], 
                'Skill': row['Skill'], 
                'Origem': row['Posicao']
            })
        else:
            escalacao_final.append({'Posicao': 'RESERVA', 'Nome': row['Nome'], 'Skill': row['Skill'], 'Origem': row['Posicao']})
    
    ordem = {'Goleiro': 0, 'Zagueiro': 1, 'Lateral': 2, 'Volante': 3, 'Meia': 4, 'Atacante': 5, 'RESERVA': 99}
    df_final = pd.DataFrame(escalacao_final)
    if not df_final.empty:
        df_final['Key'] = df_final['Posicao'].apply(lambda x: ordem.get(x.split()[0], 99))
        df_final = df_final.sort_values('Key').drop(columns=['Key'])
    return df_final

def gerar_divisao_combinatoria(df_linha, top_n_opcoes=4):
    ids = df_linha.index.tolist()
    n_jogadores = len(ids)
    
    # Se muitos jogadores, simplifica
    if n_jogadores > 18:
        shuffled = df_linha.sample(frac=1)
        mid = len(shuffled) // 2
        return shuffled.iloc[:mid], shuffled.iloc[mid:]

    k = n_jogadores // 2
    primeiro_id = ids[0]
    restante_ids = ids[1:]
    
    combinacoes = list(itertools.combinations(restante_ids, k - 1))
    # Limita loop se explodir combinações
    if len(combinacoes) > 4000: combinacoes = random.sample(combinacoes, 4000)
    
    cenarios = []
    total_skill = df_linha['Skill'].sum()
    
    for c in combinacoes:
        ids_time_a = [primeiro_id] + list(c)
        skill_a = df_linha.loc[ids_time_a, 'Skill'].sum()
        diff = abs(total_skill - 2 * skill_a)
        cenarios.append({'diff': diff, 'ids_a': ids_time_a})
        
    cenarios.sort(key=lambda x: x['diff'])
    limite = min(top_n_opcoes, len(cenarios))
    melhores_opcoes = cenarios[:limite]
    escolhido = random.choice(melhores_opcoes)
    
    ids_a = escolhido['ids_a']
    df_a = df_linha.loc[ids_a]
    df_b = df_linha.drop(ids_a)
    return df_a, df_b

def sortear_times_controller(sel_goleiros, sel_linha, convidados_struct, df_dados, nivel_variedade):
    # 1. Recupera Cadastrados
    lista_nomes_db = sel_goleiros + sel_linha
    selecionados = df_dados[df_dados['Nome'].isin(lista_nomes_db)].copy()
    
    # 2. Adiciona Convidados
    novos = []
    media_skill = df_dados['Skill'].mean()
    
    for item in convidados_struct:
        novos.append({
            'Nome': item['nome'] + " (C)", 
            'Posicao': item['posicao'], 
            'Skill': media_skill
        })
        
    if novos:
        selecionados = pd.concat([selecionados, pd.DataFrame(novos)], ignore_index=True)

    # 3. Processamento
    selecionados['Pos_Prim'], selecionados['Pos_Sec'] = zip(*selecionados['Posicao'].map(obter_posicao_detalhada))
    
    # 4. Separação
    goleiros = selecionados[selecionados['Pos_Prim'] == 'G'].sort_values('Skill', ascending=False)
    linha = selecionados[selecionados['Pos_Prim'] != 'G']
    
    # 5. Sorteio
    ta_gol, tb_gol = [], []
    for i, (_, g) in enumerate(goleiros.iterrows()):
        if i % 2 == 0: ta_gol.append(g)
        else: tb_gol.append(g)
            
    top_n = int(3 + (nivel_variedade * 10)) 
    df_linha_a, df_linha_b = gerar_divisao_combinatoria(linha, top_n_opcoes=top_n)
    
    df_a = pd.concat([pd.DataFrame(ta_gol), df_linha_a], ignore_index=True)
    df_b = pd.concat([pd.DataFrame(tb_gol), df_linha_b], ignore_index=True)
    
    return organizar_tatica(df_a), organizar_tatica(df_b)

def parse_input_convidados(texto, sigla_posicao):
    """Transforma 'Joao, Pedro' em lista estruturada"""
    nomes = [n.strip() for n in texto.split(',') if n.strip()]
    return [{'nome': n, 'posicao': sigla_posicao} for n in nomes]

# --- INTERFACE ---

st.title("⚽ Divisor Hugo 2026")

# Upload
arquivo_padrao = 'Planilha Futebol 2025.xlsx'
df = None
try:
    df = carregar_dados_ranking(arquivo_padrao)
except:
    pass

if df is None:
    st.warning("⚠️ Planilha padrão não encontrada.")
    up = st.file_uploader("Upload Excel", type=['xlsx'])
    if up: df = carregar_dados_ranking(up)

if df is not None:
    # Listas para Dropdown
    op_gol = sorted(df[df['Pos_Prim_Bruta'] == 'G']['Nome'].unique())
    op_lin = sorted(df[df['Pos_Prim_Bruta'] != 'G']['Nome'].unique())
    
    # --- ÁREA 1: JOGADORES DA PLANILHA ---
    st.header("1. Jogadores da Planilha")
    c1, c2 = st.columns(2)
    with c1:
        sel_gol_db = st.multiselect("🧤 Goleiros Cadastrados", op_gol)
    with c2:
        sel_lin_db = st.multiselect("🏃 Linha Cadastrados", op_lin)

    # --- ÁREA 2: CONVIDADOS POR POSIÇÃO ---
    st.markdown("---")
    st.header("2. Convidados (Separe nomes por vírgula)")
    
    col_a, col_b, col_c = st.columns(3)
    
    with col_a:
        txt_zag = st.text_input("🛡️ Zagueiros", placeholder="Ex: Primo do Edu")
        txt_lat = st.text_input("🏃 Laterais", placeholder="Ex: Vizinho")
        
    with col_b:
        txt_vol = st.text_input("🧱 Volantes", placeholder="Ex: Amigo do Jean")
        txt_mei = st.text_input("🎨 Meias", placeholder="Ex: Irmão do Caio")
        
    with col_c:
        txt_ata = st.text_input("⚽ Atacantes", placeholder="Ex: Tio do Hugo")
        txt_gol = st.text_input("🧤 Goleiros (Extra)", placeholder="Ex: Goleiro novo")

    # --- PROCESSAMENTO DOS INPUTS ---
    convidados_list = []
    convidados_list.extend(parse_input_convidados(txt_zag, 'Z'))
    convidados_list.extend(parse_input_convidados(txt_lat, 'L'))
    convidados_list.extend(parse_input_convidados(txt_vol, 'V'))
    convidados_list.extend(parse_input_convidados(txt_mei, 'M'))
    convidados_list.extend(parse_input_convidados(txt_ata, 'A'))
    convidados_list.extend(parse_input_convidados(txt_gol, 'G'))

    # --- CÁLCULOS E CONTADORES ---
    tot_goleiros = len(sel_gol_db) + len([c for c in convidados_list if c['posicao'] == 'G'])
    tot_linha = len(sel_lin_db) + len([c for c in convidados_list if c['posicao'] != 'G'])
    total_geral = tot_goleiros + tot_linha
    
    st.markdown("---")
    
    # Exibir KPI
    k1, k2, k3 = st.columns(3)
    with k1:
        lbl = f"🧤 Goleiros: {tot_goleiros}/2"
        if tot_goleiros == 2: st.success(lbl)
        elif tot_goleiros > 2: st.error(lbl)
        else: st.warning(lbl)
        
    with k2:
        lbl = f"🏃 Linha: {tot_linha}/14"
        if tot_linha > 14: st.error(lbl)
        elif tot_linha >= 8: st.success(lbl)
        else: st.info(lbl)
        
    with k3:
        st.caption("Configuração:")
        variedade = st.slider("Variedade do Sorteio", 0, 10, 2, label_visibility="collapsed")

    # --- BOTÃO ---
    if st.button("🎲 SORTEAR TIMES", type="primary", use_container_width=True):
        erro = False
        if tot_goleiros > 2:
            st.toast("Máximo de 2 goleiros!", icon="❌")
            erro = True
        if tot_linha > 14:
            st.toast("Máximo de 14 jogadores de linha!", icon="❌")
            erro = True
        if tot_linha < 2:
            st.toast("Mínimo de 2 jogadores de linha.", icon="⚠️")
            erro = True
            
        if not erro:
            df_a, df_b = sortear_times_controller(
                sel_gol_db, 
                sel_lin_db, 
                convidados_list, 
                df, 
                variedade
            )
            
            st.markdown("### 📋 Resultado")
            col_a, col_b = st.columns(2)
            
            with col_a:
                s_a = df_a[df_a['Posicao'] != 'Goleiro']['Skill'].sum()
                st.info(f"🟥 TIME A (Força: {s_a:.1f})")
                st.dataframe(df_a[['Posicao', 'Nome']], hide_index=True, use_container_width=True)
                
            with col_b:
                s_b = df_b[df_b['Posicao'] != 'Goleiro']['Skill'].sum()
                st.info(f"🟦 TIME B (Força: {s_b:.1f})")
                st.dataframe(df_b[['Posicao', 'Nome']], hide_index=True, use_container_width=True)
            
            # Texto WhatsApp
            txt = f"*⚽ TIMES SORTEADOS*\n\n"
            txt += "*🟥 TIME A*\n"
            for _, r in df_a.iterrows(): txt += f"{r['Posicao']}: {r['Nome']}\n"
            txt += "\n*🟦 TIME B*\n"
            for _, r in df_b.iterrows(): txt += f"{r['Posicao']}: {r['Nome']}\n"
            
            st.text_area("Copiar para WhatsApp:", value=txt, height=200)