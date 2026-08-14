#
# This file is part of realme-ota (https://github.com/R0rt1z2/realme-ota).
# Copyright (c) 2022 Roger Ortiz.
#
# Fetch and cache the BBK device model list from Google's official
# supported_devices.html (Play Store registered devices).
#

import os
import re
import json
import tempfile

import requests

# Google official source
GOOGLE_DEVICES_URL = 'https://storage.googleapis.com/play_public/supported_devices.html'

# BBK brands we care about (case-insensitive match on the "Retail Branding" column)
BBK_BRANDS = {'realme', 'oppo', 'oneplus'}

# Cache file location (user-writable temp dir)
CACHE_DIR = os.path.join(tempfile.gettempdir(), 'realme_ota_cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'bbk_models.json')
# Cache validity: 7 days (Google updates roughly monthly)
CACHE_TTL_SECONDS = 7 * 24 * 3600


def _fetch_and_parse():
    """Download Google's supported_devices.html and extract BBK entries.

    Returns a list of dicts:
        [{'brand':..., 'name':..., 'device':..., 'model':...}, ...]
    """
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(
                GOOGLE_DEVICES_URL,
                headers={'User-Agent': 'Mozilla/5.0 (realme-ota)'},
                timeout=30,
            )
            resp.raise_for_status()
            html = resp.text
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                import time as _t
                _t.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f'Failed to fetch device list after 3 attempts: {last_err}')

    # Each row: <tr><td>brand</td><td>name</td><td>device</td><td>model</td></tr>
    row_re = re.compile(
        r'<tr>\s*<td[^>]*>(.*?)</td>\s*'
        r'<td[^>]*>(.*?)</td>\s*'
        r'<td[^>]*>(.*?)</td>\s*'
        r'<td[^>]*>(.*?)</td>\s*</tr>',
        re.DOTALL
    )
    tag_re = re.compile(r'<[^>]+>')

    def clean(s):
        s = tag_re.sub('', s).strip()
        s = s.replace('&amp;', '&').replace('&#39;', "'")
        return s

    results = []
    for m in row_re.finditer(html):
        brand_raw = clean(m.group(1))
        if brand_raw.lower() not in BBK_BRANDS:
            continue
        results.append({
            'brand': brand_raw,
            'name': clean(m.group(2)),
            'device': clean(m.group(3)),
            'model': clean(m.group(4)),
        })
    return results


def get_device_list(force_refresh=False):
    """Return the BBK device list, using cache when available.

    Args:
        force_refresh: If True, ignore cache and re-download.

    Returns:
        List of dicts with keys: brand, name, device, model.
    """
    import time as _time

    if not force_refresh and os.path.exists(CACHE_FILE):
        age = _time.time() - os.path.getmtime(CACHE_FILE)
        if age < CACHE_TTL_SECONDS:
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # cache corrupt, re-fetch

    devices = _fetch_and_parse()

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(devices, f, ensure_ascii=False, indent=0)
    except IOError:
        pass  # caching is best-effort

    return devices


def search_devices(query, force_refresh=False):
    """Search the BBK device list by model, name, or device codename.

    Args:
        query: Search string (case-insensitive substring match).
        force_refresh: If True, ignore cache.

    Returns:
        List of matching device dicts.
    """
    devices = get_device_list(force_refresh=force_refresh)
    q = query.lower().strip()
    if not q:
        return devices
    return [
        d for d in devices
        if q in d['model'].lower()
        or q in d['name'].lower()
        or q in d['device'].lower()
        or q in d['brand'].lower()
    ]


def lookup_model(model, force_refresh=False):
    """Look up a specific model number and return its info.

    Args:
        model: Model string (e.g. 'RMX3471').
        force_refresh: If True, ignore cache.

    Returns:
        Dict with brand, name, device, model — or None if not found.
    """
    devices = get_device_list(force_refresh=force_refresh)
    m = model.upper().strip()
    for d in devices:
        if d['model'].upper() == m:
            return d
    # Fallback: partial match (e.g. user passed 'RMX3471' but DB has 'RMX3471')
    partials = [d for d in devices if m in d['model'].upper()]
    return partials[0] if partials else None


def detect_brand_from_model(model, force_refresh=False):
    """Determine the brand string ('realme'/'coloros'/'oneplus') from a model
    number by looking it up in the Google device list.

    Falls back to prefix heuristics if the model isn't found online.

    Returns one of: 'realme', 'coloros', 'oneplus'
    """
    info = lookup_model(model, force_refresh=force_refresh)
    if info:
        b = info['brand'].lower()
        if b == 'realme':
            return 'realme'
        elif b == 'oneplus':
            return 'oneplus'
        else:  # OPPO
            return 'coloros'

    # Fallback: prefix heuristics (same logic as main.py)
    m = (model or '').upper()
    if m.startswith('RMX'):
        return 'realme'
    elif any(m.startswith(p) for p in ('CPH', 'PEG', 'PFG', 'PJH', 'PJV', 'PJU', 'PJY', 'PKA', 'PKB', 'PKC', 'OP', 'DE', 'PF')):
        return 'coloros'
    elif any(m.startswith(p) for p in ('PG', 'PH', 'PJD', 'ONEPLUS')):
        return 'oneplus'
    else:
        return 'coloros'
