"""Localization helpers for UI and language-aware analysis output."""

from __future__ import annotations

import re
import threading
import time

import requests
from flask import g, has_app_context, has_request_context, request

SUPPORTED_LOCALES = ('en', 'zh-CN')
DEFAULT_LOCALE = 'zh-CN'
LANG_COOKIE = 'lanescope-lang'

_DD_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
_DD_CHAMPIONS_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/{locale}/champion.json'
_DD_ITEMS_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/{locale}/item.json'

_LOCK = threading.Lock()
_VERSION_CACHE = {'value': '', 'expires_at': 0.0}
_CHAMPION_NAME_CACHE: dict[tuple[str, str], dict[str, str]] = {}
_ITEM_NAME_CACHE: dict[tuple[str, str], dict[int, str]] = {}
_REFRESH_IN_FLIGHT: set[str] = set()


def _cache_get(key: str):
    if not has_app_context():
        return None
    try:
        from app.extensions import cache
        return cache.get(key)
    except Exception:
        return None


def _cache_set(key: str, value, timeout: int) -> None:
    if not has_app_context():
        return
    try:
        from app.extensions import cache
        cache.set(key, value, timeout=timeout)
    except Exception:
        return

QUEUE_LABELS = {
    'en': {
        'Ranked Solo': 'Ranked Solo/Duo',
        'Ranked Flex': 'Ranked Flex',
        'Normal Draft': 'Normal Draft',
        'Normal Blind': 'Normal Blind',
        'ARAM': 'ARAM',
        'Clash': 'Clash',
        'ARURF': 'ARURF',
        'One for All': 'One for All',
        'Nexus Blitz': 'Nexus Blitz',
        'Ultimate Spellbook': 'Ultimate Spellbook',
        'Other': 'Other',
    },
    'zh-CN': {
        'Ranked Solo': '单/双排位',
        'Ranked Flex': '灵活排位',
        'Normal Draft': '召唤师峡谷（征召模式）',
        'Normal Blind': '召唤师峡谷（盲选模式）',
        'ARAM': '极地大乱斗',
        'Clash': '冠军杯赛',
        'ARURF': '无限乱斗',
        'One for All': '克隆大作战',
        'Nexus Blitz': '极限闪击',
        'Ultimate Spellbook': '终极魔典',
        'Other': '其他模式',
    },
}

LANE_LABELS = {
    'en': {'TOP': 'Top', 'JUNGLE': 'Jungle', 'MIDDLE': 'Mid', 'BOTTOM': 'Bot', 'UTILITY': 'Support'},
    'zh-CN': {'TOP': '上路', 'JUNGLE': '打野', 'MIDDLE': '中路', 'BOTTOM': '下路', 'UTILITY': '辅助'},
}

LANE_SHORT_LABELS = {
    'en': {'TOP': 'TOP', 'JUNGLE': 'JGL', 'MIDDLE': 'MID', 'BOTTOM': 'BOT', 'UTILITY': 'SUP'},
    'zh-CN': {'TOP': '上', 'JUNGLE': '野', 'MIDDLE': '中', 'BOTTOM': '下', 'UTILITY': '辅'},
}

RANK_TIERS = {
    'en': {
        'IRON': 'Iron',
        'BRONZE': 'Bronze',
        'SILVER': 'Silver',
        'GOLD': 'Gold',
        'PLATINUM': 'Platinum',
        'EMERALD': 'Emerald',
        'DIAMOND': 'Diamond',
        'MASTER': 'Master',
        'GRANDMASTER': 'Grandmaster',
        'CHALLENGER': 'Challenger',
        'UNRANKED': 'Unranked',
    },
    'zh-CN': {
        'IRON': '坚韧黑铁',
        'BRONZE': '英勇黄铜',
        'SILVER': '不屈白银',
        'GOLD': '荣耀黄金',
        'PLATINUM': '华贵铂金',
        'EMERALD': '流光翡翠',
        'DIAMOND': '璀璨钻石',
        'MASTER': '超凡大师',
        'GRANDMASTER': '傲世宗师',
        'CHALLENGER': '最强王者',
        'UNRANKED': '未定级',
    },
}

WEEKDAY_LABELS = {
    'en': {
        'Monday': 'Monday', 'Tuesday': 'Tuesday', 'Wednesday': 'Wednesday', 'Thursday': 'Thursday',
        'Friday': 'Friday', 'Saturday': 'Saturday', 'Sunday': 'Sunday',
    },
    'zh-CN': {
        'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三', 'Thursday': '周四',
        'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日',
    },
}

TRANSLATIONS = {
    'en': {
        'theme.light': 'Light',
        'theme.dark': 'Dark',
        'theme.switch_to': 'Switch to {theme} theme',
        'theme.label': 'Theme',
        'lang.switch_to': 'Switch language',
        'lang.current': 'Language',
        'lang.en': 'EN',
        'lang.zh-CN': '中',
        'flash.login_required': 'Please log in to access this page.',
        'flash.welcome_back': 'Welcome back!',
        'flash.invalid_credentials': 'Invalid email or password.',
        'flash.account_created': 'Account created! Link your Riot account to get started.',
        'flash.logged_out': 'You have been logged out.',
        'flash.access_denied': 'Access denied.',
        'flash.too_many_attempts': 'Too many attempts. Please wait and try again.',
        'flash.ai_failed': 'AI analysis failed.',
        'validation.email_invalid': 'Please enter a valid email address.',
        'validation.password_required': 'Password is required.',
        'validation.confirm_password_required': 'Please confirm your password.',
        'validation.password_min': 'Password must be at least 8 characters.',
        'validation.password_match': 'Passwords must match.',
        'validation.email_exists': 'An account with this email already exists.',
        'validation.summoner_required': 'Summoner name is required.',
        'validation.summoner_too_long': 'Summoner name is too long.',
        'validation.tagline_required': 'Tagline is required (the part after # in your Riot ID).',
        'validation.tagline_too_long': 'Tagline is too long.',
        'validation.tagline_no_hash': 'Do not include the # symbol. Just enter the tag itself (e.g. "NA1").',
        'validation.tagline_alnum': 'Tagline should only contain letters and numbers.',
        'validation.channel_required': 'Channel ID is required.',
        'validation.channel_too_long': 'Channel ID is too long.',
        'validation.channel_format': 'Channel ID must be a 17-20 digit number. Right-click the channel in Discord to copy it.',
        'validation.guild_format': 'Server ID must be a 17-20 digit number.',
        'form.email': 'Email',
        'form.password': 'Password',
        'form.confirm_password': 'Confirm Password',
        'form.sign_in': 'Sign In',
        'form.create_account': 'Create Account',
        'form.summoner_name': 'Summoner Name',
        'form.tagline': 'Tagline',
        'form.region': 'Region',
        'form.link_account': 'Link Account',
        'form.channel_id': 'Channel ID',
        'form.server_id_optional': 'Server ID (optional)',
        'form.save_discord': 'Save Discord Config',
        'form.check_interval': 'Check Interval (minutes)',
        'form.weekly_summary_day': 'Weekly Summary Day',
        'form.weekly_summary_time': 'Weekly Summary Time',
        'form.enable_discord_notifications': 'Enable Discord Notifications',
        'form.save_preferences': 'Save Preferences',
    },
    'zh-CN': {
        'theme.light': '浅色',
        'theme.dark': '深色',
        'theme.switch_to': '切换到{theme}模式',
        'theme.label': '主题',
        'lang.switch_to': '切换语言',
        'lang.current': '语言',
        'lang.en': 'EN',
        'lang.zh-CN': '中',
        'flash.login_required': '请先登录后再访问该页面。',
        'flash.welcome_back': '欢迎回来！',
        'flash.invalid_credentials': '邮箱或密码不正确。',
        'flash.account_created': '账号已创建！请先绑定 Riot 账号开始使用。',
        'flash.logged_out': '你已退出登录。',
        'flash.access_denied': '无权访问。',
        'flash.too_many_attempts': '尝试次数过多，请稍后再试。',
        'flash.ai_failed': 'AI 分析失败。',
        'validation.email_invalid': '请输入有效的邮箱地址。',
        'validation.password_required': '密码不能为空。',
        'validation.confirm_password_required': '请确认密码。',
        'validation.password_min': '密码至少需要 8 个字符。',
        'validation.password_match': '两次输入的密码不一致。',
        'validation.email_exists': '该邮箱已注册账号。',
        'validation.summoner_required': '召唤师名称不能为空。',
        'validation.summoner_too_long': '召唤师名称过长。',
        'validation.tagline_required': '请输入标签（Riot ID 中 # 后面的部分）。',
        'validation.tagline_too_long': '标签过长。',
        'validation.tagline_no_hash': '请不要输入 #，只填标签本身（例如“NA1”）。',
        'validation.tagline_alnum': '标签只能包含字母和数字。',
        'validation.channel_required': '频道 ID 不能为空。',
        'validation.channel_too_long': '频道 ID 过长。',
        'validation.channel_format': '频道 ID 必须是 17-20 位数字。可在 Discord 右键频道复制。',
        'validation.guild_format': '服务器 ID 必须是 17-20 位数字。',
        'form.email': '邮箱',
        'form.password': '密码',
        'form.confirm_password': '确认密码',
        'form.sign_in': '登录',
        'form.create_account': '创建账号',
        'form.summoner_name': '召唤师名称',
        'form.tagline': '标签',
        'form.region': '大区',
        'form.link_account': '绑定账号',
        'form.channel_id': '频道 ID',
        'form.server_id_optional': '服务器 ID（可选）',
        'form.save_discord': '保存 Discord 配置',
        'form.check_interval': '检查间隔（分钟）',
        'form.weekly_summary_day': '每周总结日期',
        'form.weekly_summary_time': '每周总结时间',
        'form.enable_discord_notifications': '启用 Discord 通知',
        'form.save_preferences': '保存偏好设置',
    },
}

RECOMMENDATION_TRANSLATIONS = {
    "Focus on survival - your death rate is high. Consider backing off in dangerous situations.": "优先保证生存，你的死亡率偏高。危险局面建议及时后撤。",
    "Great KDA! Consider taking more calculated risks to snowball games.": "KDA 很优秀！可考虑在可控风险下主动滚雪球扩大优势。",
    "Vision score is low. Buy control wards and place them strategically.": "视野分偏低。建议补控卫并在关键区域提前布置。",
    "You're getting a high gold share - make sure to capitalize on your lead.": "你的经济占比很高，请确保把领先转化为地图资源与团战优势。",
    "Consider focusing more on farming or looking for opportunities to help your team.": "建议提升补刀效率，或主动寻找机会支援队友。",
    "High damage output - great job carrying!": "伤害占比很高，带队能力很强，继续保持！",
    "Look for ways to increase your damage contribution.": "可优化站位与输出节奏，进一步提高伤害贡献。",
    "Overall solid performance. Keep practicing!": "整体表现稳健，继续保持练习节奏！",
    "Focus on consistency and decision-making": "提升稳定性与决策质量",
    "Work on survival and engagement timing": "优化生存能力与开团时机",
    "Improve farming efficiency and objective taking": "提升补刀效率与资源目标控制",
}

LOGIN_MESSAGE_KEY_MAP = {
    'Please log in to access this page.': 'flash.login_required',
}


def normalize_locale(value: str | None) -> str:
    value = (value or '').strip()
    if not value:
        return DEFAULT_LOCALE
    value_l = value.lower()
    if value_l in ('en', 'en-us', 'en_us', 'en-gb', 'en_gb'):
        return 'en'
    if value_l.startswith('zh'):
        return 'zh-CN'
    return DEFAULT_LOCALE


def is_supported_locale(value: str | None) -> bool:
    return normalize_locale(value) in SUPPORTED_LOCALES


def get_locale() -> str:
    if has_request_context():
        cached = getattr(g, '_lanescope_locale', None)
        if cached:
            return cached
        cookie_val = request.cookies.get(LANG_COOKIE)
        locale = normalize_locale(cookie_val)
        g._lanescope_locale = locale
        return locale
    return DEFAULT_LOCALE


def resolve_api_language(value: str | None) -> str:
    if value is None:
        return get_locale()
    return normalize_locale(value)


def t(key: str, locale: str | None = None, **kwargs) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    table = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
    text = table.get(key) or TRANSLATIONS['en'].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def lt(en_text: str, zh_text: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    return zh_text if lang == 'zh-CN' else en_text


def localize_login_message(message: str) -> str:
    key = LOGIN_MESSAGE_KEY_MAP.get(message, message)
    return t(key)


def queue_label(queue: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    labels = QUEUE_LABELS.get(lang, QUEUE_LABELS['en'])
    return labels.get(queue, queue or labels.get('Other', 'Other'))


def lane_label(code: str, short: bool = False, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    table = LANE_SHORT_LABELS if short else LANE_LABELS
    labels = table.get(lang, table['en'])
    return labels.get(code or '', code or '')


def rank_tier_label(tier: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    table = RANK_TIERS.get(lang, RANK_TIERS['en'])
    return table.get((tier or '').upper(), tier or '')


def weekday_label(day: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    table = WEEKDAY_LABELS.get(lang, WEEKDAY_LABELS['en'])
    return table.get(day, day)


def result_label(win: bool, locale: str | None = None) -> str:
    return lt('Victory', '胜利', locale=locale) if win else lt('Defeat', '失败', locale=locale)


def localize_recommendation(text: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    if lang == 'zh-CN':
        return RECOMMENDATION_TRANSLATIONS.get(text, text)
    return text


def _normalize_alias(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _dd_locale(lang: str) -> str:
    return 'zh_CN' if normalize_locale(lang) == 'zh-CN' else 'en_US'


def _fetch_latest_version() -> str:
    shared_cached = _cache_get('i18n:dd:version')
    if isinstance(shared_cached, str) and shared_cached:
        return shared_cached

    now = time.time()
    with _LOCK:
        if _VERSION_CACHE['expires_at'] > now:
            return _VERSION_CACHE['value']
    version = ''
    ttl = 120
    try:
        resp = requests.get(_DD_VERSIONS_URL, timeout=5)
        if resp.status_code == 200:
            rows = resp.json()
            if isinstance(rows, list) and rows:
                version = rows[0]
                ttl = 6 * 3600
    except requests.RequestException:
        version = ''
    with _LOCK:
        if version:
            _VERSION_CACHE['value'] = version
            _cache_set('i18n:dd:version', version, timeout=ttl)
        _VERSION_CACHE['expires_at'] = now + ttl
        return _VERSION_CACHE['value']


def _champion_name_map(version: str, lang: str) -> dict[str, str]:
    if not version:
        return {}
    dd_locale = _dd_locale(lang)
    cache_key = (version, dd_locale)
    shared_key = f'i18n:champ:{version}:{dd_locale}'
    now = time.time()
    shared_cached = _cache_get(shared_key)
    if isinstance(shared_cached, dict) and shared_cached:
        return dict(shared_cached)

    with _LOCK:
        cached = _CHAMPION_NAME_CACHE.get(cache_key)
        if cached and cached.get('_expires_at', 0.0) > now:
            data = dict(cached)
            data.pop('_expires_at', None)
            return data
    mapping: dict[str, str] = {}
    try:
        resp = requests.get(_DD_CHAMPIONS_URL.format(version=version, locale=dd_locale), timeout=6)
        if resp.status_code == 200:
            champions = resp.json().get('data', {})
            if isinstance(champions, dict):
                for champ in champions.values():
                    name = champ.get('name', '')
                    aliases = {
                        _normalize_alias(champ.get('id', '')),
                        _normalize_alias(champ.get('name', '')),
                        _normalize_alias(str(champ.get('key', ''))),
                    }
                    for alias in aliases:
                        if alias and name:
                            mapping[alias] = name
    except requests.RequestException:
        mapping = {}
    with _LOCK:
        cached_data = dict(mapping)
        cached_data['_expires_at'] = now + 6 * 3600
        _CHAMPION_NAME_CACHE[cache_key] = cached_data
    _cache_set(shared_key, mapping, timeout=6 * 3600)
    return mapping


def _item_name_map(version: str, lang: str) -> dict[int, str]:
    if not version:
        return {}
    dd_locale = _dd_locale(lang)
    cache_key = (version, dd_locale)
    shared_key = f'i18n:item:{version}:{dd_locale}'
    now = time.time()
    shared_cached = _cache_get(shared_key)
    if isinstance(shared_cached, dict) and shared_cached:
        restored = {}
        for k, v in shared_cached.items():
            try:
                restored[int(k)] = v
            except (TypeError, ValueError):
                continue
        return restored

    with _LOCK:
        cached = _ITEM_NAME_CACHE.get(cache_key)
        if cached and cached.get(-1, 0) > now:
            return {k: v for k, v in cached.items() if k >= 0}
    mapping: dict[int, str] = {}
    try:
        resp = requests.get(_DD_ITEMS_URL.format(version=version, locale=dd_locale), timeout=6)
        if resp.status_code == 200:
            items = resp.json().get('data', {})
            if isinstance(items, dict):
                for item_id, item_data in items.items():
                    try:
                        iid = int(item_id)
                    except (TypeError, ValueError):
                        continue
                    mapping[iid] = item_data.get('name', f'Item {iid}')
    except requests.RequestException:
        mapping = {}
    cached = dict(mapping)
    cached[-1] = now + 6 * 3600
    with _LOCK:
        _ITEM_NAME_CACHE[cache_key] = cached
    _cache_set(shared_key, mapping, timeout=6 * 3600)
    return mapping


def _cached_champion_name_map(lang: str) -> dict[str, str]:
    dd_locale = _dd_locale(lang)
    version_shared = _cache_get('i18n:dd:version')
    if isinstance(version_shared, str) and version_shared:
        shared_cached = _cache_get(f'i18n:champ:{version_shared}:{dd_locale}')
        if isinstance(shared_cached, dict) and shared_cached:
            return dict(shared_cached)
    with _LOCK:
        version = _VERSION_CACHE.get('value', '')
        if not version:
            return {}
        cached = _CHAMPION_NAME_CACHE.get((version, dd_locale))
        if not cached:
            return {}
        return {k: v for k, v in cached.items() if k != '_expires_at'}


def _cached_item_name_map(lang: str) -> dict[int, str]:
    dd_locale = _dd_locale(lang)
    version_shared = _cache_get('i18n:dd:version')
    if isinstance(version_shared, str) and version_shared:
        shared_cached = _cache_get(f'i18n:item:{version_shared}:{dd_locale}')
        if isinstance(shared_cached, dict) and shared_cached:
            restored = {}
            for k, v in shared_cached.items():
                try:
                    restored[int(k)] = v
                except (TypeError, ValueError):
                    continue
            return restored
    with _LOCK:
        version = _VERSION_CACHE.get('value', '')
        if not version:
            return {}
        cached = _ITEM_NAME_CACHE.get((version, dd_locale))
        if not cached:
            return {}
        return {k: v for k, v in cached.items() if k >= 0}


def _refresh_ddragon_locale_assets(lang: str) -> None:
    try:
        version = _fetch_latest_version()
        if version:
            _champion_name_map(version, lang)
            _item_name_map(version, lang)
    finally:
        with _LOCK:
            _REFRESH_IN_FLIGHT.discard(lang)


def _schedule_locale_refresh(lang: str) -> None:
    locale = normalize_locale(lang)
    if locale != 'zh-CN':
        return
    with _LOCK:
        if locale in _REFRESH_IN_FLIGHT:
            return
        _REFRESH_IN_FLIGHT.add(locale)
    threading.Thread(
        target=_refresh_ddragon_locale_assets,
        args=(locale,),
        daemon=True,
        name=f'i18n-ddragon-refresh-{locale}',
    ).start()


def champion_name(name: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    if lang != 'zh-CN':
        return name
    mapping = _cached_champion_name_map(lang)
    localized = mapping.get(_normalize_alias(name))
    if localized:
        return localized
    _schedule_locale_refresh(lang)
    return name


def item_name(item_id: int | None, fallback: str = '', locale: str | None = None) -> str:
    lang = normalize_locale(locale) if locale else get_locale()
    if lang != 'zh-CN':
        return fallback or (f'Item {item_id}' if item_id else '')
    mapping = _cached_item_name_map(lang)
    if item_id is not None and item_id in mapping:
        return mapping[item_id]
    _schedule_locale_refresh(lang)
    return fallback or (f'物品 {item_id}' if item_id else '')


def js_i18n_payload(locale: str | None = None) -> dict:
    lang = normalize_locale(locale) if locale else get_locale()
    return {
        'locale': lang,
        'themeLabel': t('theme.label', locale=lang),
        'themeLight': t('theme.light', locale=lang),
        'themeDark': t('theme.dark', locale=lang),
        'themeSwitchTemplate': t('theme.switch_to', locale=lang, theme='{theme}'),
        'streamStatus': [
            lt('Reading lane pressure', '正在读取对线压制信息', locale=lang),
            lt('Comparing team tempo', '正在对比团队节奏', locale=lang),
            lt('Writing focused coaching', '正在生成针对性建议', locale=lang),
        ],
        'labels': {
            'you': lt('You', '你', locale=lang),
            'team': lt('Team Avg', '队伍均值', locale=lang),
            'lobby': lt('Lobby Avg', '对局均值', locale=lang),
            'allies': lt('Allies', '我方', locale=lang),
            'enemies': lt('Enemies', '敌方', locale=lang),
            'overview': lt('Overview', '概览', locale=lang),
            'visuals': lt('Visuals', '图表', locale=lang),
            'aiAnalysis': lt('AI Analysis', 'AI 分析', locale=lang),
            'compare': lt('Compare', '对比', locale=lang),
            'shares': lt('Shares', '占比', locale=lang),
            'lane': lt('Lane', '对线', locale=lang),
            'details': lt('Details', '详情', locale=lang),
            'live': lt('Live', '实时', locale=lang),
            'laneVs': lt('Lane vs ', '对线 ', locale=lang),
            'visionShort': lt('VS', '视野分', locale=lang),
            'langSwitch': lt('Switch language', '切换语言', locale=lang),
            'loading': lt('Loading...', '加载中...', locale=lang),
            'loadMore': lt('Load More', '加载更多', locale=lang),
            'runAi': lt('Run AI Analysis', '运行 AI 分析', locale=lang),
            'regenAi': lt('Regenerate AI Analysis', '重新生成 AI 分析', locale=lang),
            'analyzing': lt('Analyzing...', '分析中...', locale=lang),
            'noMatches': lt('No matches found for this filter.', '该筛选条件下暂无对局数据。', locale=lang),
            'showingMatches': lt('Showing {displayed} of {total} matches', '显示 {displayed} / {total} 场对局', locale=lang),
            'filterTabWithCount': lt('{queue}: {count} matches', '{queue}：{count} 场', locale=lang),
            'noMatchesHelp': lt('Connect your Riot account in settings and sync recent matches to populate this queue.', '请先在设置中绑定 Riot 账号并同步最近对局，以填充该队列。', locale=lang),
            'goSettings': lt('Go to Settings', '前往设置', locale=lang),
            'noLaneOpponent': lt('No direct lane opponent data in this match.', '该对局缺少直接对位数据。', locale=lang),
            'streamFallback': lt('Live stream interrupted. Falling back to standard analysis...', 'AI教练分析实时流中断，正在切换为标准分析...', locale=lang),
            'streamUnavailable': lt('Live stream is unavailable in this browser. Running standard analysis...', '当前浏览器不支持 AI 教练实时流，正在执行标准分析...', locale=lang),
            'staleFallback': lt('Live stream returned cached analysis. Retrying with standard analysis...', 'AI 教练实时流返回了缓存分析，正在使用标准分析重试...', locale=lang),
            'cachedBecauseFailed': lt('Using cached analysis because regeneration failed: ', '重生成失败，已使用缓存分析：', locale=lang),
            'aiStatusLoading': lt('Status: running AI analysis...', '状态：正在运行 AI 分析...', locale=lang),
            'aiStatusStreaming': lt('Status: streaming AI analysis...', '状态：AI 实时流分析中...', locale=lang),
            'aiStatusSuccess': lt('Status: analysis updated.', '状态：分析已更新。', locale=lang),
            'aiStatusFailed': lt('Status: analysis failed.', '状态：分析失败。', locale=lang),
            'aiStatusCached': lt('Status: fallback to cached analysis due to generation error.', '状态：生成失败，已回退到缓存分析。', locale=lang),
            'aiStatusLoaded': lt('Status: loaded last saved analysis.', '状态：已加载上次保存的分析。', locale=lang),
            'aiFailed': t('flash.ai_failed', locale=lang),
            'aiHeader': lt('AI Match Analysis', 'AI 对局分析', locale=lang),
            'aiSub': lt('Live coaching generated from lane, comp, and team-tempo context.', '基于对线、阵容和团队节奏实时生成建议。', locale=lang),
            'aiEmpty': lt('Generate AI coaching for this match from in-game metrics, rank context, and composition.', '基于对局数据、段位上下文和阵容信息生成 AI 建议。', locale=lang),
            'victory': result_label(True, locale=lang),
            'defeat': result_label(False, locale=lang),
        },
        'metrics': {
            'gold_per_min': lt('Gold/min', '金币/分', locale=lang),
            'damage_per_min': lt('Damage/min', '伤害/分', locale=lang),
            'cs_per_min': lt('CS/min', '补刀/分', locale=lang),
            'vision_per_min': lt('Vision/min', '视野/分', locale=lang),
            'kda': 'KDA',
            'gold_share_pct': lt('Gold Share', '经济占比', locale=lang),
            'damage_share_pct': lt('Damage Share', '伤害占比', locale=lang),
            'cs_share_pct': lt('CS Share', '补刀占比', locale=lang),
            'vision_share_pct': lt('Vision Share', '视野占比', locale=lang),
            'kill_participation_pct': lt('Kill Part.', '参团率', locale=lang),
            'gpm_delta': lt('Gold/min Delta', '金币/分差值', locale=lang),
            'dpm_delta': lt('Damage/min Delta', '伤害/分差值', locale=lang),
            'cspm_delta': lt('CS/min Delta', '补刀/分差值', locale=lang),
            'vpm_delta': lt('Vision/min Delta', '视野/分差值', locale=lang),
            'kda_delta': lt('KDA Delta', 'KDA 差值', locale=lang),
        },
        'laneShort': LANE_SHORT_LABELS.get(lang, LANE_SHORT_LABELS['en']),
    }
