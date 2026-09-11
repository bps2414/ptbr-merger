#!/usr/bin/env python3
"""Local Radarr PT-BR coordinator. No video re-encoding; fail closed on sync errors."""
import argparse, collections, fcntl, hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path
from common import api
from configure import BR, PT, DUAL
from qbit import Qbit, seed_complete
try:
    import discord_notify
except Exception:
    discord_notify = None

BASE = Path(__file__).resolve().parent
STATE = BASE / 'state.json'
WORK = Path('/srv/appdata/ptbr-worker/work-v2')
MAIN = 'radarr'
DONOR = 'radarr-ptbr'

class CandidateError(RuntimeError):
    pass

def log(msg):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), msg, flush=True)

def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)

def read_state():
    data = json.loads(STATE.read_text()) if STATE.exists() else {'version': 2, 'movies': {}, 'cleanup': []}
    data.setdefault('movies', {})
    data.setdefault('cleanup', [])
    return data

def command(args, timeout=7200):
    p = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=timeout)
    if p.returncode not in ([0, 1] if str(args[0]) == 'mkvmerge' else [0]):
        raise RuntimeError(f'{args[0]} exit {p.returncode}: {p.stderr[-1500:]}')
    return p.stdout

def probe(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_chapters', '-show_format', '-of', 'json', str(path)], 120))

def audio(p):
    return [s for s in p.get('streams', []) if s.get('codec_type') == 'audio']

def video(p):
    return next(s for s in p.get('streams', []) if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic'))

def lang(s):
    return s.get('tags', {}).get('language', '').lower().replace('_', '-')

def is_br(s, evidence='', relaxed=False):
    text = lang(s) + ' ' + s.get('tags', {}).get('title', '')
    if re.search(PT, text):
        return False
    if re.search(BR, text):
        return True
    if re.search(PT, evidence):
        return False
    if lang(s) in ['por', 'pt', 'pt-br'] and bool(re.search(BR, evidence)):
        return True
    # Untagged or generic audio stream in a confirmed Brazilian donor release
    if bool(re.search(BR, evidence)) and lang(s) in ['', 'und', 'por', 'pt', 'pt-br']:
        return True
    # Relaxed mode (Tier 2): accept any Portuguese audio not explicitly European
    if relaxed and lang(s) in ['por', 'pt', 'pt-br'] and not re.search(PT, evidence):
        return True
    return False

def is4k(p):
    v = video(p)
    return v.get('width', 0) >= 3000 and v.get('height', 0) >= 1500

def hostpath(raw):
    p = Path(raw)
    if p.is_relative_to('/data'):
        p = Path('/srv/data') / p.relative_to('/data')
    return p

def movie_path(m):
    f = m.get('movieFile') or {}
    return hostpath(f.get('path') or str(Path(m['path']) / f.get('relativePath', ''))) if f else None

def fingerprint(p):
    s = p.stat()
    return f'{p}:{s.st_dev}:{s.st_ino}:{s.st_size}:{s.st_mtime_ns}'

def evidence(m):
    f = m.get('movieFile') or {}
    parts = [
        str(f.get('sceneName', '')),
        str(f.get('relativePath', '')),
        str(f.get('originalFilePath', '')),
        str(m.get('title', ''))
    ]
    return ' '.join(p for p in parts if p)

SOURCE_PATTERNS = {
    'DSNP': r'(?i)\bDSNP\b|Disney\s*\+',
    'AMZN': r'(?i)\bAMZN\b|Amazon',
    'NF':   r'(?i)\bNF\b|Netflix',
    'ATVP': r'(?i)\bATVP\b|Apple\s*TV',
    'HMAX': r'(?i)\bHMAX\b|HBO\s*Max',
    'PMTP': r'(?i)\bPMTP\b|Paramount',
    'MA':   r'(?i)\bMA\b|Movies\s*Anywhere',
}

def detect_source(text):
    for key, pattern in SOURCE_PATTERNS.items():
        if re.search(pattern, text):
            return key
    return None

def source_match_score(main_ev, title):
    s1 = detect_source(main_ev)
    s2 = detect_source(title)
    return 1000 if s1 and s2 and s1 == s2 else 0

NON_PT_LANGS = r'(?i)\b(?:latino|latin|spanish|castellano|espa[nñ]ol|french|fran[cç]ais|italian|italiano|german|deutsch|hindi|telugu|tamil|russian|rus)\b'
HAS_PT_LANGS = r'(?i)\b(?:pt[ ._-]?br|por[ ._-]?br|portugu[eê]s|brazilian|brasil|brazil|dublado)\b'

def is_non_pt_title(title):
    return bool(re.search(NON_PT_LANGS, title)) and not bool(re.search(HAS_PT_LANGS, title))

def eligible_tier2(r, rejected):
    """Fallback: Dual Audio/Multi releases that might contain PT-BR."""
    if release_key(r) in rejected:
        return False
    q = r.get('quality', {}).get('quality', {}).get('id')
    if q not in {5, 14, 6, 3, 15, 7}:
        return False
    if r.get('seeders', 0) < 1:
        return False
    title = r.get('title', '')
    if re.search(PT, title):
        return False
    if re.search(BR, title):
        return False  # would be Tier 1
    if is_non_pt_title(title):
        return False  # reject foreign Multi/Latino that doesn't mention PT-BR
    if re.search(DUAL, title):
        return True
    if re.search(r'(?i)portuguese|portugu[eê]s', title):
        return True
    return False

def probe_has_portuguese(path):
    """Probe a file and check if it has Portuguese audio."""
    p = probe(path)
    for s in audio(p):
        l = lang(s)
        title = s.get('tags', {}).get('title', '').lower()
        if l in ['por', 'pt', 'pt-br'] and not re.search(PT, title + ' ' + l):
            return True, s, p
        if 'brasil' in title or 'brazilian' in title:
            return True, s, p
    return False, None, p

def extract_hash(release):
    """Extract torrent hash from release data (infoHash, guid, or magnetUrl)."""
    h = release.get('infoHash', '').strip()
    if h and len(h) == 40:
        return h.lower()
    # Check guid for hash (TorrentDownload, Pirate Bay embed it in the URL)
    for field in ['guid', 'magnetUrl', 'downloadUrl']:
        val = release.get(field) or ''
        m = re.search(r'btih[:/]([0-9a-fA-F]{40})', val)
        if m:
            return m.group(1).lower()
        # Some GUIDs have the hash as a path segment
        m = re.search(r'/([0-9a-fA-F]{40})(?:/|$|\?)', val)
        if m:
            return m.group(1).lower()
    return None

def prowlarr_url(url):
    """Rewrite Prowlarr Docker-internal URLs to localhost."""
    if url and 'prowlarr:9696' in url:
        return url.replace('prowlarr:9696', '127.0.0.1:9696')
    return url

def find_video_file(path):
    """Find the main video file in a path (file or directory)."""
    p = Path(path)
    if p.is_file():
        return p
    exts = ['*.mkv', '*.mp4', '*.avi', '*.ts', '*.m4v']
    videos = []
    for ext in exts:
        videos.extend(p.glob(ext))
    if not videos:
        raise CandidateError('No video files found in download')
    return max(videos, key=lambda x: x.stat().st_size)

def choose_common(a, b):
    aliases = {'en': 'eng', 'fr': 'fra', 'fre': 'fra', 'ger': 'deu', 'de': 'deu', 'es': 'spa', 'ja': 'jpn', 'pt': 'por'}
    def norm(s):
        return aliases.get(lang(s), lang(s))
    def weight(s):
        codec = s.get('codec_name', '').lower()
        heavy = 100 if any(k in codec for k in ['truehd', 'dts', 'pcm', 'flac']) else 0
        return heavy, s.get('channels', 2)
    pairs = []
    for x in a:
        if norm(x) in ['', 'und', 'por', 'pt-br', 'pt-pt']:
            continue
        if re.search('comment|description', x.get('tags', {}).get('title', ''), re.I):
            continue
        for y in b:
            if norm(x) == norm(y) and not re.search('comment|description', y.get('tags', {}).get('title', ''), re.I):
                score = (weight(x)[0] + weight(y)[0], weight(x)[1] + weight(y)[1])
                pairs.append((score, x, y))
    if pairs:
        pairs.sort(key=lambda item: item[0])
        return pairs[0][1], pairs[0][2]
    return None

def extract(path, idx, out):
    command(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-map', f'0:{idx}', '-c', 'copy', str(out)])

def redsync(args, report):
    try:
        result = command(['RedSync', 'sync', *args, '--verify', '--json', '--quiet'])
    except RuntimeError as e:
        raise CandidateError(str(e)) from e
    report.write_text(result)
    try:
        d = json.loads(result)
    except ValueError:
        raise CandidateError('RedSync did not return a machine-readable verification result')
    rows = d if isinstance(d, list) else [d]
    if not rows or any(r.get('verification', {}).get('passed') is not True for r in rows):
        raise CandidateError('RedSync strict verification failed; see ' + str(report))
    return d

def video_hash(path, duration=None):
    args = ['ffmpeg', '-v', 'error']
    if duration is not None:
        args += ['-t', str(duration)]
    args += ['-i', str(path), '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-']
    return command(args).strip()

def validate_mux(source, out):
    a = probe(source)
    b = probe(out)
    if not is4k(b):
        raise RuntimeError('Output is not 4K')
    va = video(a)
    vb = video(b)
    for attr in ['codec_name', 'width', 'height', 'r_frame_rate']:
        if va.get(attr) != vb.get(attr):
            raise RuntimeError(f'Video attribute {attr} changed: {va.get(attr)} vs {vb.get(attr)}')
    if video_hash(source, 30) != video_hash(out, 30):
        raise RuntimeError('Video payload changed')
    ca = collections.Counter(s['codec_type'] for s in a['streams'])
    cb = collections.Counter(s['codec_type'] for s in b['streams'])
    for k, v in ca.items():
        if cb[k] < v:
            raise RuntimeError('A source track was lost: ' + k)
    if len(a.get('chapters', [])) != len(b.get('chapters', [])):
        raise RuntimeError('Chapters were lost')
    br = [s for s in audio(b) if is_br(s)]
    br = [s for s in br if s.get('disposition', {}).get('default')]
    if len(br) != 1 or sum(bool(s.get('disposition', {}).get('default')) for s in audio(b)) != 1:
        raise RuntimeError('Missing unique default Brazilian track')
    duration = float(b['format']['duration'])
    for pos in [min(30, duration / 10), duration / 2, max(0, duration - 40)]:
        command(['ffmpeg', '-v', 'error', '-ss', str(pos), '-i', str(out), '-map', f'0:{br[-1]["index"]}', '-t', '10', '-f', 'null', '-'], 120)

def sync_files(source, donor, donor_evidence, work, job=None, state=None, relaxed=False):
    work.mkdir(parents=True, exist_ok=True)
    a = probe(source)
    b = probe(donor)

    # Duration pre-check: reject obvious mismatches before expensive RedSync
    dur_main = float(a['format'].get('duration', 0))
    dur_donor = float(b['format'].get('duration', 0))
    if dur_main > 0 and dur_donor > 0:
        diff_pct = abs(dur_main - dur_donor) / dur_main * 100
        if diff_pct > 5.0:
            raise CandidateError(
                f'Duration mismatch: main={dur_main:.0f}s ({dur_main/60:.1f}min) '
                f'vs donor={dur_donor:.0f}s ({dur_donor/60:.1f}min) — '
                f'{diff_pct:.1f}% difference (max 5%)')
        if diff_pct > 2.0:
            log(f'Duration warning: {diff_pct:.1f}% difference — proceeding with caution')

    pt = next((s for s in sorted(audio(b), key=lambda x: x.get('channels', 0), reverse=True) if is_br(s, donor_evidence, relaxed=relaxed)), None)
    if not pt:
        raise CandidateError('Donor has no confirmed Brazilian audio')
    if shutil.disk_usage(source.parent).free < source.stat().st_size + donor.stat().st_size * 2 + 2 * 1024**3:
        raise RuntimeError('Insufficient temporary disk space')

    def update_phase(num, name, detail=None):
        if job is not None and state is not None:
            job['phase_num'] = num
            job['phase_name'] = name
            atomic_json(STATE, state)
        if discord_notify and job and job.get('title'):
            try:
                discord_notify.notify_ptbr_phase(job.get('title'), num, 5, name, detail)
            except Exception as ex:
                log(f'Discord phase notify error: {ex}')

    update_phase(1, 'Extração do Áudio Doador', 'Extraindo faixa em Português Brasileiro (5.1) do release doador.')
    ptfile = work / 'ptbr.mka'
    synced = work / 'ptbr.synced.mka'
    extract(donor, pt['index'], ptfile)

    update_phase(2, 'Extração do Áudio 4K', 'Extraindo áudio de referência do arquivo 4K para alinhamento.')
    pair = choose_common(audio(a), audio(b))
    ref = work / 'main-ref.mka'
    if not audio(a):
        raise CandidateError('Main has no reference audio')
    extract(source, (pair[0] if pair else audio(a)[0])['index'], ref)

    update_phase(3, 'Alinhamento RedSync', 'Calculando correlação acústica milimétrica e gerando alinhamento.')
    if pair:
        target = work / 'donor-ref.mka'
        aligned = work / 'aligned-ref.mka'
        plan = work / 'timeline.json'
        extract(donor, pair[1]['index'], target)
        redsync([ref, target, '--output', aligned, '--write-alignment-plan', plan, '--overwrite'], work / 'reference-report.json')
        if not plan.exists():
            raise CandidateError('RedSync did not write verified timeline')
        redsync([ref, ptfile, '--alignment-plan', plan, '--verification-reference', aligned, '--output', synced, '--overwrite'], work / 'ptbr-report.json')
    else:
        redsync([ref, ptfile, '--output', synced, '--overwrite'], work / 'ptbr-report.json')

    update_phase(4, 'Remux do Vídeo 4K', 'Mesclando o vídeo 4K com o áudio dublado sincronizado.')
    tracks = json.loads(command(['mkvmerge', '-J', str(source)]))['tracks']
    ssd_free = shutil.disk_usage(work).free
    source_size = source.stat().st_size
    if ssd_free > source_size + 4 * 1024**3:
        out = work / f'tmp-mux-{source.stem}.mkv'
    else:
        out = source.with_name('.' + source.stem + '.ptbr-tmp.mkv')
    if out.exists():
        out.unlink()
    args = ['mkvmerge', '--engage', 'dont_normalize_parameter_sets', '-q', '-o', str(out)]
    for t in tracks:
        if t['type'] == 'audio':
            args += ['--default-track-flag', f'{t["id"]}:no']
    args += [str(source), '--no-chapters', '--language', '0:pt-BR', '--track-name', '0:Português Brasileiro', '--default-track-flag', '0:yes', str(synced)]
    command(args)

    update_phase(5, 'Validação e Plex', 'Validando integridade dos fluxos e atualizando o Plex.')
    validate_mux(source, out)
    return out

def normalize_existing(source, stream):
    out = source.with_name('.' + source.stem + '.ptbr-tmp.mkv')
    if shutil.disk_usage(source.parent).free < source.stat().st_size + 2 * 1024**3:
        raise RuntimeError('Insufficient space to set default audio')
    tracks = json.loads(command(['mkvmerge', '-J', str(source)]))['tracks']
    aud = audio(probe(source))
    ordinal = next(i for i, x in enumerate(aud) if x['index'] == stream['index'])
    ids = [x['id'] for x in tracks if x['type'] == 'audio']
    chosen = ids[ordinal]
    args = ['mkvmerge', '--engage', 'dont_normalize_parameter_sets', '-q', '-o', str(out)]
    for tid in ids:
        args += ['--default-track-flag', f'{tid}:{"yes" if tid == chosen else "no"}']
    args += ['--language', f'{chosen}:pt-BR', '--track-name', f'{chosen}:Português Brasileiro', str(source)]
    command(args)
    validate_mux(source, out)
    return out

def recover(job):
    t = job.get('transaction')
    if not t:
        return
    original = Path(t['original'])
    backup = Path(t['backup'])
    final = Path(t['final'])
    out = Path(t['output'])
    if t.get('committed'):
        if final.exists():
            backup.unlink(missing_ok=True)
            out.unlink(missing_ok=True)
            job.pop('transaction', None)
            return
    if backup.exists():
        if final.exists():
            final.unlink()
        os.replace(backup, original)
    out.unlink(missing_ok=True)
    job.pop('transaction', None)

def commit(source, out, job, state):
    final = source.with_suffix('.mkv')
    backup = source.with_name('.' + source.name + '.pre-ptbr')
    if backup.exists() or (final != source and final.exists()):
        raise RuntimeError('Conflicting recovery/output file')

    # If out was built on SSD, copy it sequentially to HDD parent first
    if out.stat().st_dev != source.stat().st_dev:
        hdd_tmp = source.with_name('.' + source.stem + '.ptbr-transfer.mkv')
        if hdd_tmp.exists():
            hdd_tmp.unlink()
        shutil.copyfile(out, hdd_tmp)
        out.unlink(missing_ok=True)
        out = hdd_tmp

    job['transaction'] = {'original': str(source), 'backup': str(backup), 'final': str(final), 'output': str(out), 'committed': False}
    atomic_json(STATE, state)
    os.replace(source, backup)
    try:
        os.replace(out, final)
        fd = os.open(final, os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
        job['transaction']['committed'] = True
        job['fingerprint'] = fingerprint(final)
        job['status'] = 'muxed'
        job.pop('phase_num', None)
        job.pop('phase_name', None)
        atomic_json(STATE, state)
        backup.unlink()
        job.pop('transaction')
        atomic_json(STATE, state)
    except Exception:
        if final.exists():
            final.unlink()
        if backup.exists():
            os.replace(backup, source)
        raise
    return final

def set_monitored(m, value):
    if m['monitored'] != value:
        m['monitored'] = value
        api(DONOR, f'movie/{m["id"]}', 'PUT', m)

def profile_id(app, name):
    matches = [x['id'] for x in api(app, 'qualityprofile') if x['name'] == name]
    if len(matches) != 1:
        raise RuntimeError('Missing or ambiguous quality profile: ' + name)
    return matches[0]

def lock_profile(m, locked):
    p = profile_id(MAIN, '4K PT-BR Concluído' if locked else '4K PT-BR')
    if m['qualityProfileId'] != p:
        m['qualityProfileId'] = p
        api(MAIN, f'movie/{m["id"]}', 'PUT', m)

def rescan(mid):
    c = api(MAIN, 'command', 'POST', {'name': 'RescanMovie', 'movieId': mid})
    for _ in range(30):
        s = api(MAIN, f'command/{c["id"]}')
        if s['status'] == 'completed':
            return
        if s['status'] == 'failed':
            raise RuntimeError('Radarr rescan failed')
        time.sleep(2)
    raise RuntimeError('Radarr rescan still pending')

def plex_refresh():
    import xml.etree.ElementTree as ET, urllib.request
    p = Path('/srv/appdata/plex/Library/Application Support/Plex Media Server/Preferences.xml')
    if not p.exists():
        return
    token = ET.parse(p).getroot().get('PlexOnlineToken')
    if not token:
        return
    def get(path):
        return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:32400' + path, headers={'X-Plex-Token': token}), timeout=20).read()
    for section in ET.fromstring(get('/library/sections')):
        if section.get('type') == 'movie':
            get('/library/sections/' + section.get('key') + '/refresh')

def torrent_for(m):
    h = api(DONOR, f'history/movie?movieId={m["id"]}')
    for row in reversed(sorted(h, key=lambda r: r.get('date', ''))):
        if row.get('eventType') == 'downloadFolderImported' and row.get('downloadId'):
            return row['downloadId'].lower()
    return None

def enqueue_cleanup(m, state, immediate=True):
    path = movie_path(m)
    h = torrent_for(m)
    file_id = (m.get('movieFile') or {}).get('id')
    key = f'{m["id"]}:{file_id or h or int(time.time())}'
    item = next((x for x in state['cleanup'] if x['key'] == key), None)
    if not item:
        item = {
            'key': key,
            'movieId': m['id'],
            'fileId': file_id,
            'path': str(path or ''),
            'hash': h,
            'created': time.time(),
            'immediate': immediate
        }
        state['cleanup'].append(item)
    else:
        if immediate:
            item['immediate'] = True

def cleanup(state):
    if not state['cleanup']:
        return
    q = Qbit()
    prefs = q.call('app/preferences')
    torrents = {t['hash'].lower(): t for t in q.call('torrents/info')}
    for item in list(state['cleanup']):
        h = item.get('hash')
        if not h:
            item['reason'] = 'No torrent association; retained'
            continue
        t = torrents.get(h)
        if t:
            if t.get('category') != 'movies-ptbr':
                item['reason'] = 'Category changed; retained'
                continue
            if not (item.get('immediate') or seed_complete(t, prefs)):
                item['reason'] = 'Waiting for seeding goal'
                continue
            cp = hostpath(t.get('content_path', '')).resolve()
            if not cp.is_relative_to('/srv/data/downloads') or cp == Path('/srv/data/downloads'):
                item['reason'] = 'Unsafe content path'
                continue
            q.call('torrents/delete', {'hashes': h, 'deleteFiles': 'true'}, raw=True)
        if item.get('path'):
            path = Path(item['path']).resolve()
            if path.is_relative_to('/srv/data/donor/movies'):
                current = api(DONOR, f'movie/{item["movieId"]}')
                if (current.get('movieFile') or {}).get('id') == item.get('fileId'):
                    api(DONOR, f'moviefile/{item["fileId"]}', 'DELETE')
                else:
                    path.unlink(missing_ok=True)
        state['cleanup'].remove(item)
        atomic_json(STATE, state)

def seed_defaults():
    pass

def release_key(r):
    return str(r.get('infoHash') or r.get('guid') or r.get('title')).lower()

def eligible(r, rejected):
    return (
        r.get('approved', not r.get('rejected', False))
        and not r.get('rejected', False)
        and r.get('quality', {}).get('quality', {}).get('id') in {5, 14, 6, 3, 15, 7}
        and re.search(BR, r.get('title', ''))
        and not re.search(PT, r.get('title', ''))
        and release_key(r) not in rejected
    )

def attempt_4k_pivot(m, job, state, dry=False, last_donor_title=None):
    """
    Pivot de 4K: Quando nenhum doador PT-BR sincroniza com a master 4K atual,
    busca no Radarr 4K um release alternativo em 4K que seja:
      1) Nativamente Dual Audio / Dublado (dispensa sincronização); OU
      2) Da mesma fonte do doador verificado (ex: WEBRip 4K com WEBRip doador).
    
    Ressalva do Usuário:
    - O 4K existente NUNCA é apagado previamente; a busca/download ocorre em paralelo.
    - Se nenhum 4K compatível for encontrado, o 4K existente é mantido permanentemente (legendado).
    """
    if job.get('pivot_4k_attempts', 0) >= 1:
        return False

    # Verifica se o Radarr 4K já está baixando algum release para este filme
    try:
        queued = api(MAIN, 'queue?page=1&pageSize=1000')['records']
        if any(r.get('movieId') == m['id'] for r in queued):
            job['status'] = 'downloading_pivoted_4k'
            atomic_json(STATE, state)
            return True
    except Exception as e:
        log(f"{m['title']}: Erro ao verificar fila do Radarr 4K: {e}")

    log(f"{m['title']}: Avaliando pivot de 4K (buscando release 4K nativo Dual Audio ou compatível com doador)...")
    try:
        releases = api(MAIN, f'release?movieId={m["id"]}', timeout=120)
    except Exception as e:
        log(f"{m['title']}: Falha ao buscar releases 4K no Radarr: {e}")
        return False

    rejected_4k = set(job.get('rejected_4k', []))
    candidates_4k = []
    for r in releases:
        key = release_key(r)
        if key in rejected_4k:
            continue
        q = r.get('quality', {}).get('quality', {}).get('id')
        if q not in {18, 17, 19}:  # 2160p
            continue
        if r.get('seeders', 0) < 3:
            continue
        candidates_4k.append(r)

    if not candidates_4k:
        log(f"{m['title']}: Nenhum release 4K alternativo com >=3 seeds encontrado para pivot.")
        return False

    # Prioridade 1: Release 4K nativamente Dual Audio / Dublado
    native_dual = []
    for r in candidates_4k:
        title = r.get('title', '')
        score = r.get('customFormatScore', 0)
        if score >= 10000 or re.search(BR, title) or (re.search(DUAL, title) and not is_non_pt_title(title)):
            native_dual.append(r)

    chosen = None
    if native_dual:
        native_dual.sort(key=lambda r: (-r.get('seeders', 0), -r.get('customFormatScore', 0), r.get('size', 0)))
        chosen = native_dual[0]
        log(f"{m['title']}: Pivot 4K selecionou release nativamente Dual Audio: {chosen['title']}")
    else:
        # Prioridade 2: Release 4K com a mesma fonte do doador
        donor_source = detect_source(last_donor_title or (job.get('candidate') or {}).get('title', ''))
        if donor_source:
            matching_source = [r for r in candidates_4k if detect_source(r.get('title', '')) == donor_source]
            if matching_source:
                matching_source.sort(key=lambda r: (-r.get('seeders', 0), -r.get('customFormatScore', 0), r.get('size', 0)))
                chosen = matching_source[0]
                log(f"{m['title']}: Pivot 4K selecionou release compatível com fonte [{donor_source}]: {chosen['title']}")

    if not chosen:
        log(f"{m['title']}: Nenhum 4K compatível ou Dual Audio disponível. Mantendo 4K atual legendado.")
        return False

    if dry:
        log(f"{m['title']}: [DRY-RUN] Dispararia pivot de 4K para {chosen['title']}")
        return True

    job['pivot_4k_attempts'] = job.get('pivot_4k_attempts', 0) + 1
    job['status'] = 'downloading_pivoted_4k'
    job['pivoted_4k_candidate'] = {'title': chosen['title'], 'key': release_key(chosen)}
    atomic_json(STATE, state)

    try:
        api(MAIN, 'release', 'POST', chosen, timeout=120)
        log(f"{m['title']}: Download do novo 4K disparado em segundo plano no Radarr: {chosen['title']}")
        if discord_notify:
            discord_notify.notify_ptbr_donor_downloading(
                m['title'],
                chosen['title'] + ' ⟨Pivot 4K — buscando base compatível com dublagem⟩',
                chosen.get('seeders'), chosen.get('size')
            )
        return True
    except Exception as e:
        log(f"{m['title']}: Falha ao enviar release de pivot para o Radarr 4K: {e}")
        return False

def process(m, state, dry=False):
    key = str(m['tmdbId'])
    job = state['movies'].setdefault(key, {'title': m['title'], 'rejected': []})
    if not dry:
        recover(job)
        if job.get('needs_rescan'):
            rescan(m['id'])
            m = api(MAIN, f'movie/{m["id"]}')
    source = movie_path(m)
    if not source or not source.is_file():
        job['status'] = 'waiting_4k'
        if not dry and m.get('monitored') and m.get('isAvailable') and time.time() - job.get('main_search', 0) > 21600:
            queued = api(MAIN, 'queue?page=1&pageSize=1000')['records']
            if not any(r.get('movieId') == m['id'] for r in queued):
                job['main_search'] = time.time()
                atomic_json(STATE, state)
                api(MAIN, 'command', 'POST', {'name': 'MoviesSearch', 'movieIds': [m['id']]})
        return
    if not source.resolve().is_relative_to('/srv/data/media/movies'):
        raise RuntimeError('Main file outside movie library')
    fp = fingerprint(source)
    cached = job.get('probe_cache', {})
    if cached.get('fingerprint') == fp:
        p = cached['probe']
    else:
        p = probe(source)
        if fingerprint(source) != fp:
            raise RuntimeError('Main changed during inspection')
        job['probe_cache'] = {'fingerprint': fp, 'probe': p}
    if not is4k(p):
        job['status'] = 'waiting_4k'
        return

    has_br = any(is_br(s, evidence(m)) for s in audio(p))
    if has_br:
        if dry:
            log(m['title'] + ': already has Brazilian audio')
            return
        br_stream = next(s for s in audio(p) if is_br(s, evidence(m)))
        defaults = [s for s in audio(p) if s.get('disposition', {}).get('default')]
        if len(defaults) != 1 or defaults[0]['index'] != br_stream['index']:
            out = normalize_existing(source, br_stream)
            if fingerprint(source) != fp:
                raise RuntimeError('Main changed during audio default normalization')
            job['needs_rescan'] = True
            source = commit(source, out, job, state)
            fp = fingerprint(source)
        lock_profile(m, True)
        job.update(status='complete', fingerprint=fp)
        job.pop('reason', None)
        d = next((d for d in api(DONOR, 'movie') if d['tmdbId'] == m['tmdbId']), None)
        if d:
            set_monitored(d, False)
            if d.get('hasFile'):
                enqueue_cleanup(d, state, immediate=True)
        if job.get('needs_rescan') or job.get('plex_refreshed_fingerprint') != fp:
            job['needs_rescan'] = True
            atomic_json(STATE, state)
            rescan(m['id'])
            plex_refresh()
            job.pop('needs_rescan', None)
            job['plex_refreshed_fingerprint'] = fp
        return

    # Se o usuário já optou por manter o 4K legendado definitivo, encerra
    if job.get('status') == 'complete_subs_only':
        return

    # Se o Radarr já estiver baixando um novo 4K (pivot ou upgrade), aguarda em paralelo
    queued = api(MAIN, 'queue?page=1&pageSize=1000')['records']
    if any(r.get('movieId') == m['id'] for r in queued):
        job['status'] = 'downloading_pivoted_4k'
        return

    if dry:
        log(m['title'] + ': would seek PT-BR donor')
        return

    lock_profile(m, False)
    if job.get('fingerprint') != fp:
        job.update(fingerprint=fp, rejected=[], last_search=0)

    d = next((d for d in api(DONOR, 'movie') if d['tmdbId'] == m['tmdbId']), None)
    if not d:
        lookup = api(DONOR, f'movie/lookup/tmdb?tmdbId={m["tmdbId"]}')
        lookup.update(
            qualityProfileId=profile_id(DONOR, '720p-1080p PT-BR Donor'),
            rootFolderPath='/data/donor/movies',
            monitored=False,
            minimumAvailability='released',
            addOptions={'searchForMovie': False}
        )
        d = api(DONOR, 'movie', 'POST', lookup)
    set_monitored(d, False)

    if d.get('hasFile'):
        dp = movie_path(d)
        if not dp or not dp.resolve().is_relative_to('/srv/data/donor/movies'):
            raise RuntimeError('Invalid donor file path')
        rejected_file = (d.get('movieFile') or {}).get('id') in job.get('rejected_files', [])
        if not rejected_file:
            ed1 = (m.get('movieFile') or {}).get('edition', '').strip().lower()
            ed2 = (d.get('movieFile') or {}).get('edition', '').strip().lower()
            job['status'] = 'syncing'
            atomic_json(STATE, state)
            if discord_notify and not dry:
                discord_notify.notify_ptbr_syncing(m['title'], dp.name)
            work = WORK / key
            donor_ev = evidence(d) + ' ' + (job.get('candidate') or {}).get('title', '')
            try:
                if ed1 and ed2 and ed1 != ed2:
                    raise CandidateError('Different editions: ' + ed1 + ' / ' + ed2)
                out = sync_files(source, dp, donor_ev, work, job=job, state=state)
                latest = api(MAIN, f'movie/{m["id"]}')
                if movie_path(latest) != source or fingerprint(source) != fp:
                    raise RuntimeError('Main changed while processing')
                job['needs_rescan'] = True
                final = commit(source, out, job, state)
                rescan(m['id'])
                lock_profile(api(MAIN, f'movie/{m["id"]}'), True)
                plex_refresh()
                job.pop('needs_rescan', None)
                job['plex_refreshed_fingerprint'] = fingerprint(final)
                enqueue_cleanup(d, state, immediate=True)
                job.update(status='complete', fingerprint=fingerprint(final))
                job.pop('reason', None)
                shutil.rmtree(work, ignore_errors=True)
                log(m['title'] + ': completed')
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_complete(m['title'], final.name)
                return
            except CandidateError as e:
                file_id = (d.get('movieFile') or {}).get('id')
                if file_id:
                    job.setdefault('rejected_files', []).append(file_id)
                h = torrent_for(d)
                if h:
                    job['rejected'].append(h)
                    try:
                        Qbit().call('torrents/delete', {'hashes': h, 'deleteFiles': 'true'}, raw=True)
                    except Exception:
                        pass
                if job.get('candidate'):
                    job['rejected'].append(job['candidate']['key'])
                job['reason'] = str(e)
                job['last_search'] = 0
                enqueue_cleanup(d, state, immediate=True)
                if d.get('movieFile'):
                    api(DONOR, f'moviefile/{d["movieFile"]["id"]}', 'DELETE')
                shutil.rmtree(work, ignore_errors=True)
                atomic_json(STATE, state)
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_rejected(m['title'], str(e), (job.get('candidate') or {}).get('title'))
        else:
            job['status'] = 'rejected_donor'
            return

    if len(job.get('rejected_files', [])) >= 3:
        if attempt_4k_pivot(m, job, state, dry=dry, last_donor_title=donor_ev if 'donor_ev' in locals() else None):
            return
        prev_status = job.get('status')
        job['status'] = 'complete_subs_only'
        job['reason'] = 'Candidatos a doador falharam; 4K legendado mantido como definitivo'
        lock_profile(m, True)
        atomic_json(STATE, state)
        log(f"{m['title']}: mantendo 4K legendado definitivo (perfil travado)")
        if discord_notify and not dry and prev_status != 'complete_subs_only':
            discord_notify.notify_ptbr_complete(m['title'], f"{m['title']} (4K Legendado — definitivo)")
        return

    queue = api(DONOR, 'queue?page=1&pageSize=1000&includeUnknownMovieItems=true')['records']
    pending = next((r for r in queue if r.get('movieId') == d['id']), None)
    if pending:
        job['status'] = 'downloading_donor'
        h = str(pending.get('downloadId', '')).lower()
        t = next((t for t in Qbit().call('torrents/info') if t['hash'].lower() == h), None)
        reason = stalled_reason(t, job, time.time()) if t else None
        if not reason:
            return
        if h not in job['rejected']:
            job['rejected'].append(h)
        if job.get('candidate') and job['candidate']['key'] not in job['rejected']:
            job['rejected'].append(job['candidate']['key'])
        job.update(status='rejecting_stalled_donor', reason=reason)
        atomic_json(STATE, state)
        api(DONOR, f'queue/{pending["id"]}?removeFromClient=true&blocklist=true&skipRedownload=true', 'DELETE')
        job.update(status='stalled_donor_rejected', last_search=time.time())
        atomic_json(STATE, state)
        log(m['title'] + ': ' + reason + '; waiting cooldown')
        if discord_notify and not dry:
            discord_notify.notify_ptbr_rejected(m['title'], f'Torrent travado: {reason}', (job.get('candidate') or {}).get('title'))
        return

    # --- Tier 2: check for direct download in progress ---
    t2 = job.get('tier2')
    if t2 and t2.get('hash'):
        q = Qbit()
        torrents = {t['hash'].lower(): t for t in q.call('torrents/info')}
        t = torrents.get(t2['hash'].lower())
        if not t:
            log(m['title'] + ': Tier 2 torrent disappeared')
            job.pop('tier2', None)
        elif t.get('progress', 0) >= 1:
            job['status'] = 'probing_tier2'
            atomic_json(STATE, state)
            content_path = hostpath(t.get('content_path', ''))
            try:
                donor_path = find_video_file(content_path)
                has_pt, stream, donor_probe = probe_has_portuguese(donor_path)
                if not has_pt:
                    raise CandidateError(f'Tier 2 probe: no PT-BR audio in {t2["title"]}')
                log(f'{m["title"]}: Tier 2 probe found PT-BR audio in {t2["title"]}')
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_syncing(m['title'], donor_path.name)
                job['status'] = 'syncing'
                atomic_json(STATE, state)
                work = WORK / key
                out = sync_files(source, donor_path, t2.get('title', ''), work, job=job, state=state, relaxed=True)
                latest = api(MAIN, f'movie/{m["id"]}')
                if movie_path(latest) != source or fingerprint(source) != fp:
                    raise RuntimeError('Main changed while processing')
                job['needs_rescan'] = True
                final = commit(source, out, job, state)
                rescan(m['id'])
                lock_profile(api(MAIN, f'movie/{m["id"]}'), True)
                plex_refresh()
                job.pop('needs_rescan', None)
                job['plex_refreshed_fingerprint'] = fingerprint(final)
                q.call('torrents/delete', {'hashes': t2['hash'], 'deleteFiles': 'true'}, raw=True)
                job.pop('tier2', None)
                job.update(status='complete', fingerprint=fingerprint(final))
                job.pop('reason', None)
                shutil.rmtree(work, ignore_errors=True)
                shutil.rmtree(f'/srv/data/downloads/ptbr-tier2/{key}', ignore_errors=True)
                log(m['title'] + ': completed (Tier 2)')
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_complete(m['title'], final.name)
                return
            except CandidateError as e:
                job['rejected'].append(t2['key'])
                if t2['hash'] not in job['rejected']:
                    job['rejected'].append(t2['hash'])
                try:
                    q.call('torrents/delete', {'hashes': t2['hash'], 'deleteFiles': 'true'}, raw=True)
                except Exception:
                    pass
                job.pop('tier2', None)
                job['reason'] = str(e)
                job['last_search'] = 0
                shutil.rmtree(WORK / key, ignore_errors=True)
                shutil.rmtree(f'/srv/data/downloads/ptbr-tier2/{key}', ignore_errors=True)
                atomic_json(STATE, state)
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_rejected(m['title'], str(e), t2.get('title'))
                log(f'{m["title"]}: {e}')
                if attempt_4k_pivot(m, job, state, dry=dry, last_donor_title=t2.get('title')):
                    return
                # fall through to search
        else:
            job['status'] = 'downloading_tier2'
            reason = stalled_reason(t, job, time.time())
            if reason:
                job['rejected'].append(t2['key'])
                if t2['hash'] not in job['rejected']:
                    job['rejected'].append(t2['hash'])
                try:
                    q.call('torrents/delete', {'hashes': t2['hash'], 'deleteFiles': 'true'}, raw=True)
                except Exception:
                    pass
                job.pop('tier2', None)
                job['reason'] = f'Tier 2 stalled: {reason}'
                job['last_search'] = 0
                atomic_json(STATE, state)
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_rejected(m['title'], job['reason'], t2.get('title'))
                # fall through to search
            else:
                return  # still downloading

    if time.time() - job.get('last_search', 0) < 21600:
        job['status'] = 'waiting_retry'
        return

    job.update(last_search=time.time(), status='searching')
    atomic_json(STATE, state)
    releases = api(DONOR, f'release?movieId={d["id"]}', timeout=240)
    good = [r for r in releases if eligible(r, job['rejected'])]
    tier2_candidates = [r for r in releases if eligible_tier2(r, job['rejected'])]
    job['search_summary'] = {
        'total': len(releases),
        'eligible': len(good),
        'tier2_eligible': len(tier2_candidates),
        'rejection_reasons': dict(collections.Counter(reason for r in releases for reason in r.get('rejections', [])))
    }
    if not good:
        # Tier 2 fallback: Dual Audio / Multi releases
        tier2_attempts = job.get('tier2_attempts', 0)
        if tier2_candidates and tier2_attempts < 2:
            main_ev = evidence(m)
            tier2_candidates.sort(key=lambda r: (
                -source_match_score(main_ev, r.get('title', '')),
                -r.get('seeders', 0),
                r.get('size', 0)
            ))
            for chosen in tier2_candidates:
                h = extract_hash(chosen)
                url = prowlarr_url(chosen.get('downloadUrl') or chosen.get('magnetUrl') or '')
                if not h or not url:
                    job['rejected'].append(release_key(chosen))
                    continue
                job['candidate'] = {'title': chosen['title'], 'key': release_key(chosen), 'tier': 2}
                job['tier2'] = {
                    'title': chosen['title'],
                    'key': release_key(chosen),
                    'hash': h,
                }
                job['tier2_attempts'] = tier2_attempts + 1
                # qBit runs in Docker: /srv/data -> /data, use Docker path for API
                host_save = Path(f'/srv/data/downloads/ptbr-tier2/{key}')
                host_save.mkdir(parents=True, exist_ok=True)
                docker_save = f'/data/downloads/ptbr-tier2/{key}'
                Qbit().call('torrents/add', {'urls': url, 'savepath': docker_save, 'category': 'movies-ptbr'}, raw=True)
                job['status'] = 'downloading_tier2'
                atomic_json(STATE, state)
                log(f'{m["title"]}: Tier 2 download started — {chosen["title"]}')
                if discord_notify and not dry:
                    discord_notify.notify_ptbr_donor_downloading(
                        m['title'], chosen['title'] + ' ⟨Tier 2 — verificação pós-download⟩',
                        chosen.get('seeders'), chosen.get('size'))
                return
        if attempt_4k_pivot(m, job, state, dry=dry):
            return
        job['status'] = 'complete_subs_only'
        job['reason'] = 'Sem candidatos PT-BR viáveis; 4K legendado mantido como definitivo'
        lock_profile(m, True)
        atomic_json(STATE, state)
        log(f"{m['title']}: sem candidatos PT-BR viáveis; mantendo 4K legendado definitivo")
        return
    # Tier 1: sort with source preference
    main_ev = evidence(m)
    good.sort(key=lambda r: (
        -source_match_score(main_ev, r.get('title', '')),
        -r.get('seeders', 0),
        -r.get('customFormatScore', 0),
        r.get('size', 0)
    ))
    chosen = good[0]
    job['candidate'] = {'title': chosen['title'], 'key': release_key(chosen)}
    atomic_json(STATE, state)
    api(DONOR, 'release', 'POST', chosen, timeout=120)
    job['status'] = 'downloading_donor'
    if discord_notify and not dry:
        discord_notify.notify_ptbr_donor_downloading(m['title'], chosen['title'], chosen.get('seeders'), chosen.get('size'))

def stalled_reason(t, job, now):
    if t.get('category') != 'movies-ptbr' or t.get('progress', 0) >= 1:
        return None
    h = t['hash'].lower()
    progress = t.get('downloaded', 0)
    if job.get('progress_hash') != h:
        since = now
        if t.get('state') == 'metaDL' and progress == 0:
            since = min(now, max(0, t.get('added_on', now)))
        job.update(progress_hash=h, progress_bytes=progress, progress_since=since)
    elif job.get('progress_bytes') != progress:
        job.update(progress_bytes=progress, progress_since=now)
    if t.get('dlspeed', 0) > 0:
        return None
    age = now - job.get('progress_since', now)
    peers = t.get('num_seeds', 0) + t.get('num_leechs', 0)
    if t.get('state') == 'metaDL' and peers == 0 and age >= 30 * 60:
        return 'Metadata unavailable and no peers for 30 minutes'
    if t.get('state') == 'stalledDL' and peers == 0 and age >= 2 * 3600:
        return 'No peers or download progress for 2 hours'
    if t.get('state') in ['metaDL', 'stalledDL', 'downloading'] and age >= 6 * 3600:
        return 'No download progress for 6 hours'
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--movie', type=int, help='TMDB ID')
    parser.add_argument('--limit', type=int, default=1)
    args = parser.parse_args()
    if args.status:
        print(json.dumps(read_state(), indent=2, ensure_ascii=False))
        return
    with (BASE / 'worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('Another worker is running')
            return
        state = read_state()
        managed_profiles = {
            profile['id']
            for profile in api(MAIN, 'qualityprofile')
            if profile['name'] in {'4K PT-BR', '4K PT-BR Concluído'}
        }
        movies = [
            movie for movie in api(MAIN, 'movie')
            if movie.get('qualityProfileId') in managed_profiles
        ]
        if args.movie:
            movies = [m for m in movies if m['tmdbId'] == args.movie]
        movies.sort(key=lambda m: state['movies'].get(str(m['tmdbId']), {}).get('last_checked', 0))
        if not args.dry_run:
            try:
                seed_defaults()
                cleanup(state)
            except Exception as e:
                log('Cleanup deferred: ' + str(e)[:300])
        count = 0
        for m in movies:
            if not args.dry_run and count >= args.limit:
                break
            try:
                process(m, state, args.dry_run)
            except Exception as e:
                job = state['movies'].setdefault(str(m['tmdbId']), {'title': m['title'], 'rejected': []})
                prev_reason = job.get('reason')
                err_text = str(e)[:1800]
                job.update(status='error', reason=err_text)
                log(m['title'] + ': ' + str(e)[:350])
                if discord_notify and not args.dry_run and prev_reason != err_text:
                    discord_notify.notify_ptbr_error(m['title'], str(e)[:500])
            if not args.dry_run:
                state['movies'][str(m['tmdbId'])]['last_checked'] = time.time()
                atomic_json(STATE, state)
            if m.get('hasFile'):
                count += 1
        if not args.dry_run:
            log('Cycle finished')

if __name__ == '__main__':
    main()
