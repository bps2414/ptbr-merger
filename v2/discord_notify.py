#!/usr/bin/env python3
"""Unified Discord notification dispatcher for Home Server & PT-BR Automation.
Formatação limpa, profissional e em português brasileiro (sem emojis e sem tags colchetes).
"""
import datetime
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

BASE = Path('/home/servidorcasa/server')
ENV_FILE = BASE / '.env'

def _load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

_CACHED_ENV = None

def get_webhook(key):
    global _CACHED_ENV
    if _CACHED_ENV is None:
        _CACHED_ENV = _load_env()
    key_env = f'DISCORD_WEBHOOK_{key.upper()}'
    return os.environ.get(key_env) or _CACHED_ENV.get(key_env)

def send_embed(target_key_or_url, embed, content=None, username='Servidor Casa', avatar_url=None):
    """Sends a Discord embed safely without throwing exceptions."""
    url = target_key_or_url if target_key_or_url.startswith('http') else get_webhook(target_key_or_url)
    if not url:
        return False
    
    payload = {
        'username': username,
        'embeds': [embed]
    }
    if content:
        payload['content'] = content
    if avatar_url:
        payload['avatar_url'] = avatar_url
    
    if 'timestamp' not in embed:
        embed['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if 'footer' not in embed:
        embed['footer'] = {'text': 'Servidor Casa • Infraestrutura e Automação'}

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'HomeServer-DiscordNotifier/2.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[discord_notify] Falha ao enviar para {target_key_or_url}: {e}", flush=True)
        return False

# ----------------- Helper Functions ----------------- #

def notify_ptbr_donor_downloading(movie_title, candidate_title, seeders=None, size_bytes=None):
    size_str = f"{size_bytes / (1024**3):.2f} GB" if size_bytes else "N/A"
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': False},
        {'name': 'Release Doador', 'value': f"`{candidate_title}`", 'inline': False},
        {'name': 'Seeders', 'value': str(seeders) if seeders is not None else 'N/A', 'inline': True},
        {'name': 'Tamanho', 'value': size_str, 'inline': True},
        {'name': 'Status', 'value': 'Download iniciado no qBittorrent', 'inline': True}
    ]
    embed = {
        'title': 'Automação PT-BR • Doador Selecionado',
        'description': 'Um release com dublagem em português foi localizado e enviado para download.',
        'color': 0xF1C40F, # Amarelo ouro
        'fields': fields
    }
    return send_embed('filmes', embed, username='Automação PT-BR')

def notify_ptbr_syncing(movie_title, donor_filename):
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': False},
        {'name': 'Arquivo Doador', 'value': f"`{donor_filename}`", 'inline': False},
        {'name': 'Etapas em Execução', 'value': '• Extração do áudio nacional\n• Alinhamento acústico via RedSync\n• Remux direto sem recodificação via mkvmerge', 'inline': False},
        {'name': 'Status', 'value': 'Processamento em andamento', 'inline': False}
    ]
    embed = {
        'title': 'Automação PT-BR • Sincronização em Andamento',
        'description': 'Download do áudio concluído. Iniciando alinhamento acústico com a versão 4K.',
        'color': 0x3498DB, # Azul
        'fields': fields
    }
    return send_embed('filmes', embed, username='Automação PT-BR')

def notify_ptbr_phase(movie_title, phase_num, total_phases, phase_name, detail=None):
    progress_bar = "▓" * phase_num + "░" * (total_phases - phase_num)
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': True},
        {'name': 'Progresso', 'value': f"`[{progress_bar}]` Etapa {phase_num}/{total_phases}", 'inline': True},
        {'name': 'Fase Atual', 'value': f"**{phase_name}**", 'inline': False}
    ]
    if detail:
        fields.append({'name': 'Status', 'value': detail, 'inline': False})

    embed = {
        'title': f'Automação PT-BR • Etapa {phase_num}/{total_phases}: {phase_name}',
        'description': f'Atualização de processamento para **{movie_title}**.',
        'color': 0x3498DB,
        'fields': fields
    }
    return send_embed('filmes', embed, username='Automação PT-BR')

def notify_ptbr_complete(movie_title, final_filename):
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': False},
        {'name': 'Arquivo Final', 'value': f"`{final_filename}`", 'inline': False},
        {'name': 'Faixa de Áudio', 'value': 'Português Brasileiro (definida como padrão)', 'inline': True},
        {'name': 'Qualidade do Vídeo', 'value': 'Intacta (Stream Copy 4K)', 'inline': True},
        {'name': 'Espaço em Disco', 'value': 'Arquivo temporário removido', 'inline': True},
        {'name': 'Biblioteca Plex', 'value': 'Metadados atualizados e disponível', 'inline': True}
    ]
    embed = {
        'title': 'Automação PT-BR • Dublagem Concluída',
        'description': f'O filme **{movie_title}** foi sincronizado com sucesso e já está pronto para reprodução.',
        'color': 0x2ECC71, # Verde
        'fields': fields
    }
    return send_embed('filmes', embed, username='Automação PT-BR')

def humanize_error(msg):
    text = str(msg or '').strip()
    if 'audio confidence lacks distributed evidence' in text:
        return 'Incompatibilidade de montagem: O áudio deste doador possui cortes ou duração diferente da versão 4K em 25% ou mais do filme (possível corte de cinema vs versão estendida). O arquivo 4K original foi protegido.'
    if 'RedSync strict verification failed' in text:
        return 'Falha no alinhamento acústico: Os espectrogramas de áudio não bateram com precisão milimétrica garantida.'
    if 'Different editions' in text:
        return f'Edições incompatíveis entre o doador e o filme 4K: {text.split("Different editions:")[-1].strip()}.'
    if 'Donor has no confirmed Brazilian audio' in text:
        return 'O arquivo doador não contém faixa de dublagem em Português Brasileiro confirmada.'
    if 'Main has no reference audio' in text:
        return 'O arquivo 4K não possui faixa de áudio de referência.'
    if 'Duration mismatch' in text:
        return f'Incompatibilidade de duração entre 4K e doador: {text.split("—")[-1].strip() if "—" in text else text}. Possível edição diferente (theatrical vs extended) ou fonte incompatível.'
    if 'Tier 2 probe: no PT-BR audio' in text:
        return 'O candidato Dual Audio/Multi foi baixado e inspecionado, mas não contém faixa de áudio em Português. Arquivo removido automaticamente.'
    if 'Tier 2 stalled' in text:
        return f'Download Tier 2 travou sem progresso: {text.split("Tier 2 stalled:")[-1].strip()}.'
    return text

def notify_ptbr_rejected(movie_title, reason, candidate_title=None, next_action=None):
    clean_reason = humanize_error(reason)
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': False},
        {'name': 'Diagnóstico', 'value': clean_reason, 'inline': False}
    ]
    if candidate_title:
        fields.insert(1, {'name': 'Release Descartado (Blocklist)', 'value': f"`{candidate_title}`", 'inline': False})
    if next_action:
        fields.append({'name': 'Próxima Ação', 'value': next_action, 'inline': False})
    else:
        fields.append({'name': 'Status da Busca', 'value': 'Release colocado na lista negra. O sistema buscará novos releases nos indexadores.', 'inline': False})
    embed = {
        'title': 'Automação PT-BR • Doador Descartado',
        'description': 'O candidato avaliado não atendeu aos critérios de sincronia e foi removido do qBittorrent.',
        'color': 0xE67E22, # Laranja
        'fields': fields
    }
    return send_embed('filmes', embed, username='Automação PT-BR')

def notify_ptbr_error(movie_title, error_msg):
    fields = [
        {'name': 'Filme', 'value': movie_title, 'inline': False},
        {'name': 'Registro de Erro', 'value': f"```{error_msg[:900]}```", 'inline': False}
    ]
    embed = {
        'title': 'Automação PT-BR • Falha de Processamento',
        'description': f'Ocorreu um erro durante o fluxo de automação do filme **{movie_title}**.',
        'color': 0xE74C3C, # Vermelho
        'fields': fields
    }
    send_embed('filmes', embed, username='Automação PT-BR')
    target = 'homelab' if get_webhook('homelab') else 'alertas'
    return send_embed(target, embed, username='Automação PT-BR')

def notify_system_alert(title, description, fields=None, level='warning'):
    color = 0xE74C3C if level == 'critical' else 0xE67E22
    embed = {
        'title': title,
        'description': description,
        'color': color,
        'fields': fields or []
    }
    target = 'homelab' if get_webhook('homelab') else 'alertas'
    return send_embed(target, embed, username='Monitor do Servidor')

def notify_system_resolved(title, description, fields=None):
    embed = {
        'title': title,
        'description': description,
        'color': 0x2ECC71, # Verde
        'fields': fields or []
    }
    target = 'homelab' if get_webhook('homelab') else 'alertas'
    return send_embed(target, embed, username='Monitor do Servidor')

def notify_system_digest(hardware_fields, services_summary, ptbr_summary):
    fields = hardware_fields + [
        {'name': 'Containers Docker', 'value': services_summary, 'inline': False},
        {'name': 'Biblioteca PT-BR', 'value': ptbr_summary, 'inline': False}
    ]
    embed = {
        'title': 'Relatório Diário • Servidor Casa',
        'description': 'Estado operacional da infraestrutura e das bibliotecas de mídia.',
        'color': 0x5865F2, # Blurple
        'fields': fields
    }
    target = 'homelab' if get_webhook('homelab') else 'notificacoes'
    return send_embed(target, embed, username='Relatório do Servidor')

