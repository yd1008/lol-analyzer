// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
    var THEME_STORAGE_KEY = 'lanescope-theme';
    var LANG_STORAGE_KEY = 'lanescope-lang';
    var I18N = window.__i18n || {};
    var LABELS = I18N.labels || {};
    var METRICS = I18N.metrics || {};
    var COACH_MODE_STORAGE_KEY = 'lanescope-coach-mode';
    var coachModeSelect = document.getElementById('coach-mode-select');

    function txt(key, fallback) {
        if (LABELS && Object.prototype.hasOwnProperty.call(LABELS, key)) {
            return LABELS[key];
        }
        return fallback;
    }

    function metricTxt(key, fallback) {
        if (METRICS && Object.prototype.hasOwnProperty.call(METRICS, key)) {
            return METRICS[key];
        }
        return fallback;
    }

    function setLocaleCookie(locale) {
        document.cookie = 'lanescope-lang=' + encodeURIComponent(locale) + '; path=/; max-age=31536000; SameSite=Lax';
    }

    function getStoredLocale() {
        try {
            var stored = localStorage.getItem(LANG_STORAGE_KEY);
            return stored === 'en' || stored === 'zh-CN' ? stored : null;
        } catch (err) {
            return null;
        }
    }

    function getCurrentLocale() {
        var locale = document.documentElement.getAttribute('lang');
        return locale === 'en' ? 'en' : 'zh-CN';
    }

    function getStoredTheme() {
        try {
            var stored = localStorage.getItem(THEME_STORAGE_KEY);
            return stored === 'light' || stored === 'dark' ? stored : null;
        } catch (err) {
            return null;
        }
    }

    function getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    function updateThemeToggleUi(theme) {
        var toggle = document.getElementById('theme-toggle');
        if (!toggle) return;

        var nextTheme = theme === 'dark' ? 'light' : 'dark';
        var label = toggle.querySelector('.theme-toggle-label');
        var nextThemeLabel = nextTheme === 'dark' ? (I18N.themeDark || 'Dark') : (I18N.themeLight || 'Light');
        var switchTemplate = I18N.themeSwitchTemplate || 'Switch to {theme} theme';
        var switchText = switchTemplate.replace('{theme}', nextThemeLabel);

        toggle.dataset.theme = theme;
        toggle.setAttribute('aria-label', switchText);
        toggle.setAttribute('title', switchText);
        toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
        if (label) {
            label.textContent = theme === 'dark' ? (I18N.themeDark || 'Dark') : (I18N.themeLight || 'Light');
        }
    }

    function applyTheme(theme, persist) {
        document.documentElement.setAttribute('data-theme', theme);
        if (persist) {
            try {
                localStorage.setItem(THEME_STORAGE_KEY, theme);
            } catch (err) {
                // Ignore storage failures in strict browsing modes.
            }
        }
        updateThemeToggleUi(theme);
    }

    function initializeThemeToggle() {
        var toggle = document.getElementById('theme-toggle');
        var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

        updateThemeToggleUi(getCurrentTheme());

        if (toggle) {
            toggle.addEventListener('click', function () {
                var nextTheme = getCurrentTheme() === 'dark' ? 'light' : 'dark';
                applyTheme(nextTheme, true);
            });
        }

        if (!getStoredTheme() && media && media.addEventListener) {
            media.addEventListener('change', function (event) {
                applyTheme(event.matches ? 'dark' : 'light', false);
            });
        }
    }

    function updateLocaleToggleUi(locale) {
        var toggle = document.getElementById('lang-toggle');
        if (!toggle) return;
        var label = toggle.querySelector('.theme-toggle-label');
        if (label) {
            label.textContent = locale === 'zh-CN' ? '中' : 'EN';
        }
        var switchLabel = txt('langSwitch', 'Switch language');
        toggle.setAttribute('aria-label', switchLabel);
        toggle.setAttribute('title', switchLabel);
    }

    function initializeLocaleToggle() {
        var toggle = document.getElementById('lang-toggle');
        if (!toggle) return;
        updateLocaleToggleUi(getCurrentLocale());
        toggle.addEventListener('click', function () {
            var nextLocale = getCurrentLocale() === 'zh-CN' ? 'en' : 'zh-CN';
            try {
                localStorage.setItem(LANG_STORAGE_KEY, nextLocale);
            } catch (err) {
                // Ignore storage failures.
            }
            setLocaleCookie(nextLocale);
            persistLocalePreference(nextLocale).finally(function () {
                window.location.reload();
            });
        });
    }

    function persistLocalePreference(locale) {
        if (!csrfToken) {
            return Promise.resolve();
        }
        return fetch('/dashboard/settings/locale', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({locale: locale}),
        }).catch(function () {
            // Locale still persists via cookie/localStorage; server sync is best effort.
        });
    }

    var persistedLocale = getStoredLocale();
    if (persistedLocale && persistedLocale !== getCurrentLocale()) {
        setLocaleCookie(persistedLocale);
    }

    function getCoachMode() {
        var mode = 'balanced';
        try {
            mode = localStorage.getItem(COACH_MODE_STORAGE_KEY) || mode;
        } catch (err) {
            // ignore storage failures
        }
        if (coachModeSelect && coachModeSelect.value) {
            mode = coachModeSelect.value;
        }
        if (['balanced', 'aggressive', 'supportive'].indexOf(mode) === -1) {
            mode = 'balanced';
        }
        return mode;
    }

    function initializeCoachMode() {
        if (!coachModeSelect) return;
        var saved = 'balanced';
        try {
            saved = localStorage.getItem(COACH_MODE_STORAGE_KEY) || 'balanced';
        } catch (err) {
            saved = 'balanced';
        }
        if (['balanced', 'aggressive', 'supportive'].indexOf(saved) === -1) {
            saved = 'balanced';
        }
        coachModeSelect.value = saved;
        coachModeSelect.addEventListener('change', function () {
            var next = coachModeSelect.value || 'balanced';
            if (['balanced', 'aggressive', 'supportive'].indexOf(next) === -1) {
                next = 'balanced';
                coachModeSelect.value = next;
            }
            try {
                localStorage.setItem(COACH_MODE_STORAGE_KEY, next);
            } catch (err) {
                // ignore storage failures
            }
        });
    }

    initializeLocaleToggle();
    initializeThemeToggle();
    initializeCoachMode();

    var flashes = document.querySelectorAll('.flash');
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(function () { flash.remove(); }, 300);
        }, 5000);
    });

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfToken ? csrfToken.getAttribute('content') : '';

    var STREAM_STATUS_MESSAGES = Array.isArray(I18N.streamStatus) ? I18N.streamStatus : ['Reading lane pressure', 'Comparing team tempo', 'Writing focused coaching'];
    var matchList = document.getElementById('match-list');
    var loadMoreBtn = document.getElementById('load-more-btn');
    var loadMoreContainer = document.getElementById('load-more-container');
    var filterBar = document.getElementById('match-filter-bar');
    var filterSummary = document.getElementById('match-filter-summary');
    var initialMatches = Array.isArray(window.__initialMatches) ? window.__initialMatches : [];
    var currentOffset = 0;
    var currentQueue = '';
    var POSITION_MAP = I18N.laneShort || {TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP'};
    var VISUAL_METRICS = [
        {key: 'gold_per_min', label: metricTxt('gold_per_min', 'Gold/min')},
        {key: 'damage_per_min', label: metricTxt('damage_per_min', 'Damage/min')},
        {key: 'cs_per_min', label: metricTxt('cs_per_min', 'CS/min')},
        {key: 'vision_per_min', label: metricTxt('vision_per_min', 'Vision/min')},
        {key: 'kda', label: metricTxt('kda', 'KDA')},
    ];

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    function fmtNum(value) {
        if (value === null || value === undefined || value === '') return '0';
        if (typeof value === 'number') {
            return Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2).replace(/\.00$/, '');
        }
        return value;
    }

    function championIconHtml(participant, sizeClass) {
        var name = participant && (participant.champion_label || participant.champion) ? (participant.champion_label || participant.champion) : '?';
        var icon = participant && participant.champion_icon ? participant.champion_icon : '';
        if (icon) {
            return '<img class="champion-icon ' + (sizeClass || '') + '" src="' + escapeHtml(icon) + '" alt="' + escapeHtml(name) + '">';
        }
        var first = name ? name.charAt(0) : '?';
        return '<span class="champion-icon-fallback ' + (sizeClass || '') + '">' + escapeHtml(first) + '</span>';
    }

    function renderCompIcons(team, className) {
        if (!team || !team.length) return '';
        var html = '<div class="team-composition ' + className + '">';
        team.forEach(function (p) {
            var champLabel = p.champion_label || p.champion;
            var title = escapeHtml((p.summoner_name || champLabel) + ' | ' + champLabel + ' | ' + p.kills + '/' + p.deaths + '/' + p.assists);
            html += '<div class="team-comp-icon-wrap" title="' + title + '">' +
                championIconHtml(p, '') +
                '<span class="lane-mini">' + escapeHtml((p.lane_label || POSITION_MAP[p.position] || '')) + '</span>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderLaneRows(laneMatchups) {
        if (!laneMatchups || !laneMatchups.length) return '';
        var html = '<div class="lane-grid">';
        laneMatchups.forEach(function (lane) {
            var ally = lane.ally || null;
            var enemy = lane.enemy || null;
            html += '<div class="lane-row">' +
                '<div class="lane-row-label">' + escapeHtml(lane.lane_label || lane.lane || '') + '</div>' +
                '<div class="lane-player ally">';
            if (ally) {
                var allyChamp = ally.champion_label || ally.champion;
                html += championIconHtml(ally, 'champion-icon-sm') +
                    '<div><div class="lane-player-name">' + escapeHtml(ally.summoner_name || allyChamp) + '</div>' +
                    '<div class="lane-player-sub">' + escapeHtml(allyChamp) + ' | ' + ally.kills + '/' + ally.deaths + '/' + ally.assists + '</div></div>';
            }
            html += '</div><div class="lane-player enemy">';
            if (enemy) {
                var enemyChamp = enemy.champion_label || enemy.champion;
                html += championIconHtml(enemy, 'champion-icon-sm') +
                    '<div><div class="lane-player-name">' + escapeHtml(enemy.summoner_name || enemyChamp) + '</div>' +
                    '<div class="lane-player-sub">' + escapeHtml(enemyChamp) + ' | ' + enemy.kills + '/' + enemy.deaths + '/' + enemy.assists + '</div></div>';
            }
            html += '</div></div>';
        });
        html += '</div>';
        return html;
    }

    function renderCompareRows(m) {
        var visuals = m.visuals || {};
        var player = visuals.player || {};
        var team = visuals.team_avg || {};
        var lobby = visuals.lobby_avg || {};
        var html = '<div class="compact-visuals">';
        VISUAL_METRICS.forEach(function (metric) {
            var p = Number(player[metric.key] || 0);
            var t = Number(team[metric.key] || 0);
            var l = Number(lobby[metric.key] || 0);
            var maxv = Math.max(p, t, l, 1);
            var pW = Math.max((p / maxv) * 100, 4);
            var tW = Math.max((t / maxv) * 100, 4);
            var lW = Math.max((l / maxv) * 100, 4);
            html += '<div class="compact-visual-row">' +
                '<div class="compact-visual-label">' + metric.label + '</div>' +
                '<div class="compact-visual-bars">' +
                    '<div class="mini-track"><div class="mini-bar player" style="width:' + pW.toFixed(1) + '%"></div></div>' +
                    '<div class="mini-track"><div class="mini-bar team" style="width:' + tW.toFixed(1) + '%"></div></div>' +
                    '<div class="mini-track"><div class="mini-bar lobby" style="width:' + lW.toFixed(1) + '%"></div></div>' +
                '</div>' +
                '<div class="compact-visual-values">' + txt('you', 'You') + ' ' + fmtNum(p) + ' | ' + txt('team', 'Team Avg') + ' ' + fmtNum(t) + ' | ' + txt('lobby', 'Lobby Avg') + ' ' + fmtNum(l) + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderShareRings(m) {
        var shares = (m.visuals && m.visuals.shares) ? m.visuals.shares : {};
        var metrics = [
            {key: 'gold_share_pct', label: metricTxt('gold_share_pct', 'Gold Share')},
            {key: 'damage_share_pct', label: metricTxt('damage_share_pct', 'Damage Share')},
            {key: 'cs_share_pct', label: metricTxt('cs_share_pct', 'CS Share')},
            {key: 'vision_share_pct', label: metricTxt('vision_share_pct', 'Vision Share')},
            {key: 'kill_participation_pct', label: metricTxt('kill_participation_pct', 'Kill Part.')},
        ];
        var html = '<div class="share-grid">';
        metrics.forEach(function (metric) {
            var value = Number(shares[metric.key] || 0);
            html += '<div class="share-card">' +
                '<div class="share-ring" style="--pct:' + value + ';"><span>' + fmtNum(value) + '%</span></div>' +
                '<div class="share-label">' + metric.label + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderLaneCharts(m) {
        var lane = (m.visuals && m.visuals.lane) ? m.visuals.lane : {};
        var opponent = lane.opponent || null;
        if (!opponent) {
            return '<p class="card-muted">' + escapeHtml(txt('noLaneOpponent', 'No direct lane opponent data in this match.')) + '</p>';
        }

        var deltas = [
            {key: 'gpm_delta', label: metricTxt('gpm_delta', 'Gold/min Delta')},
            {key: 'dpm_delta', label: metricTxt('dpm_delta', 'Damage/min Delta')},
            {key: 'cspm_delta', label: metricTxt('cspm_delta', 'CS/min Delta')},
            {key: 'vpm_delta', label: metricTxt('vpm_delta', 'Vision/min Delta')},
            {key: 'kda_delta', label: metricTxt('kda_delta', 'KDA Delta')},
        ];
        var html = '<div class="lane-chart-head">' +
            championIconHtml(opponent, 'champion-icon-sm') +
            '<span>' + escapeHtml(txt('laneVs', 'Lane vs ')) + escapeHtml(opponent.champion_label || opponent.champion) + '</span>' +
        '</div><div class="lane-delta-grid">';
        deltas.forEach(function (metric) {
            var value = Number(lane[metric.key] || 0);
            var positive = value >= 0;
            var width = Math.min(Math.abs(value) * 12, 100);
            html += '<div class="lane-delta-row">' +
                '<div class="lane-delta-label">' + metric.label + '</div>' +
                '<div class="lane-delta-track">' +
                    '<div class="lane-delta-bar ' + (positive ? 'positive' : 'negative') + '" style="width:' + width.toFixed(1) + '%"></div>' +
                '</div>' +
                '<div class="lane-delta-value ' + (positive ? 'positive' : 'negative') + '">' + (positive ? '+' : '') + fmtNum(value) + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderVisualPanel(m, idPrefix) {
        var compareId = idPrefix + '-compare';
        var sharesId = idPrefix + '-shares';
        var laneId = idPrefix + '-lane';
        return '' +
            '<div class="visual-toggle-bar" role="tablist" aria-orientation="horizontal" aria-label="' + escapeHtml(txt('visuals', 'Visuals')) + '">' +
                '<button class="visual-toggle-btn active" id="' + compareId + '-tab" data-group="compare" role="tab" aria-selected="true" aria-controls="' + compareId + '">' + escapeHtml(txt('compare', 'Compare')) + '</button>' +
                '<button class="visual-toggle-btn" id="' + sharesId + '-tab" data-group="shares" role="tab" aria-selected="false" aria-controls="' + sharesId + '" tabindex="-1">' + escapeHtml(txt('shares', 'Shares')) + '</button>' +
                '<button class="visual-toggle-btn" id="' + laneId + '-tab" data-group="lane" role="tab" aria-selected="false" aria-controls="' + laneId + '" tabindex="-1">' + escapeHtml(txt('lane', 'Lane')) + '</button>' +
            '</div>' +
            '<div class="visual-group active" id="' + compareId + '" data-group="compare" role="tabpanel" aria-labelledby="' + compareId + '-tab">' + renderCompareRows(m) + '</div>' +
            '<div class="visual-group" id="' + sharesId + '" data-group="shares" role="tabpanel" aria-labelledby="' + sharesId + '-tab" hidden>' + renderShareRings(m) + '</div>' +
            '<div class="visual-group" id="' + laneId + '" data-group="lane" role="tabpanel" aria-labelledby="' + laneId + '-tab" hidden>' + renderLaneCharts(m) + '</div>';
    }

    function normalizeAiText(text) {
        var normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        normalized = normalized.replace(/\n{3,}/g, '\n\n');
        return normalized.trim();
    }

    function clearAiContainerState(container) {
        container.classList.remove('card-muted');
        container.classList.remove('ai-stream-host', 'is-loading', 'is-streaming', 'ai-stream-fallback', 'llm-analysis', 'llm-analysis--rich');
        container.setAttribute('aria-busy', 'false');
        container.setAttribute('aria-live', 'polite');
    }

    function appendAiNote(container, text, className) {
        var note = document.createElement('p');
        note.className = className || 'card-muted';
        note.textContent = text;
        container.appendChild(note);
    }

    function renderAiError(container, text) {
        clearAiContainerState(container);
        container.innerHTML = '<p class="card-muted">' + escapeHtml(text || txt('aiFailed', 'AI analysis failed.')) + '</p>';
    }

    function aiInlineHtml(raw) {
        var safe = escapeHtml(String(raw || ''));
        // Inline code
        safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Bold + italic (minimal)
        safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        safe = safe.replace(/__([^_]+)__/g, '<strong>$1</strong>');
        safe = safe.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        safe = safe.replace(/_([^_]+)_/g, '<em>$1</em>');
        return safe;
    }

    function renderAiMarkdownLite(text) {
        var lines = normalizeAiText(text).split('\n');
        var html = '';
        var inUl = false;
        var inOl = false;

        function closeLists() {
            if (inUl) { html += '</ul>'; inUl = false; }
            if (inOl) { html += '</ol>'; inOl = false; }
        }

        function openUl() {
            if (!inUl) { closeLists(); html += '<ul class="ai-list">'; inUl = true; }
        }

        function openOl() {
            if (!inOl) { closeLists(); html += '<ol class="ai-list ai-list-ol">'; inOl = true; }
        }

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var trimmed = line.trim();

            if (!trimmed) {
                closeLists();
                continue;
            }

            var heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
            if (heading) {
                closeLists();
                var level = Math.min(4, Math.max(2, heading[1].length));
                html += '<h' + level + ' class="ai-h">' + aiInlineHtml(heading[2]) + '</h' + level + '>';
                continue;
            }

            var bullet = trimmed.match(/^[-*+]\s+(.*)$/);
            if (bullet) {
                openUl();
                html += '<li>' + aiInlineHtml(bullet[1]) + '</li>';
                continue;
            }

            var numbered = trimmed.match(/^\d+[.)]\s+(.*)$/);
            if (numbered) {
                openOl();
                html += '<li>' + aiInlineHtml(numbered[1]) + '</li>';
                continue;
            }

            closeLists();
            html += '<p class="ai-p">' + aiInlineHtml(trimmed) + '</p>';
        }

        closeLists();
        return html || '<p class="card-muted">' + escapeHtml(txt('runAi', 'Run AI Analysis')) + '</p>';
    }

    function renderAiText(container, text) {
        clearAiContainerState(container);
        container.classList.add('llm-analysis', 'llm-analysis--rich');
        container.innerHTML = renderAiMarkdownLite(text);
    }

    function buildStatusMarkup() {
        var messages = STREAM_STATUS_MESSAGES.slice();
        if (!messages.length) {
            messages = ['Analyzing'];
        }
        if (messages.length > 1) {
            messages.push(messages[0]);
        }
        return '<div class="ai-stream-status-track">' + messages.map(function (message) {
            return '<span class="ai-stream-status-line">' + escapeHtml(message) + '</span>';
        }).join('') + '</div>';
    }

    function prepareStreamUi(container) {
        clearAiContainerState(container);
        container.classList.add('ai-stream-host', 'is-loading');
        container.setAttribute('aria-busy', 'true');
        container.innerHTML =
            '<div class="ai-stream-dock" aria-hidden="true">' +
                '<div class="ai-stream-core">' +
                    '<div class="ai-stream-orb"></div>' +
                    '<div class="ai-stream-rings"><span></span><span></span><span></span></div>' +
                '</div>' +
                '<div class="ai-stream-meta">' +
                    '<div class="ai-stream-status">' + buildStatusMarkup() + '</div>' +
                    '<div class="ai-stream-wave">' +
                        '<span></span><span></span><span></span><span></span><span></span>' +
                    '</div>' +
                    '<div class="ai-stream-skeleton"><span></span><span></span><span></span></div>' +
                '</div>' +
            '</div>' +
            '<div class="llm-analysis ai-stream-output"></div>';
        return container.querySelector('.ai-stream-output');
    }

    function updateStreamOutput(container, output, text) {
        if (!output) return;
        if (container.classList.contains('is-loading')) {
            container.classList.remove('is-loading');
            container.classList.add('is-streaming');
        }
        output.textContent = text;
        if (container.scrollHeight > container.clientHeight) {
            container.scrollTop = container.scrollHeight;
        }
    }

    function completeAiButton(button) {
        button.disabled = false;
        button.classList.add('has-analysis');
        button.textContent = txt('regenAi', 'Regenerate AI Analysis');
    }

    function resetAiButton(button) {
        button.disabled = false;
        button.textContent = txt('runAi', 'Run AI Analysis');
    }

    function setAiStatus(statusEl, message, tone) {
        if (!statusEl) return;
        statusEl.textContent = message || '';
        statusEl.classList.remove('is-loading', 'is-success', 'is-error');
        if (tone === 'loading' || tone === 'success' || tone === 'error') {
            statusEl.classList.add('is-' + tone);
        }
    }

    async function runAiAnalysisSync(options) {
        var matchId = options.matchId;
        var force = options.force;
        var focus = options.focus || 'general';
        var container = options.container;
        var button = options.button;
        var statusEl = options.statusEl || null;
        var fallbackNotice = options.fallbackNotice || '';

        if (fallbackNotice) {
            renderAiError(container, fallbackNotice);
            container.classList.add('ai-stream-fallback');
            setAiStatus(statusEl, fallbackNotice, 'loading');
        } else {
            setAiStatus(statusEl, txt('aiStatusLoading', 'Status: running AI analysis...'), 'loading');
        }

        try {
            var resp = await fetch('/dashboard/api/matches/' + matchId + '/ai-analysis', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({force: force, language: getCurrentLocale(), focus: focus, coach_mode: getCoachMode()}),
            });
            var data = await resp.json();
            if (data.error && !data.analysis) {
                var failMessage = data.error || txt('aiFailed', 'AI analysis failed.');
                renderAiError(container, failMessage);
                setAiStatus(statusEl, txt('aiStatusFailed', 'Status: analysis failed.') + ' ' + failMessage, 'error');
                resetAiButton(button);
                return;
            }
            renderAiText(container, data.analysis || '');
            if (data.stale && data.error) {
                appendAiNote(container, txt('cachedBecauseFailed', 'Using cached analysis because regeneration failed: ') + data.error, 'card-muted');
                setAiStatus(statusEl, txt('aiStatusCached', 'Status: fallback to cached analysis due to generation error.'), 'error');
            } else {
                setAiStatus(statusEl, txt('aiStatusSuccess', 'Status: analysis updated.'), 'success');
            }
            completeAiButton(button);
        } catch (err) {
            renderAiError(container, txt('aiFailed', 'AI analysis failed.'));
            setAiStatus(statusEl, txt('aiStatusFailed', 'Status: analysis failed.'), 'error');
            resetAiButton(button);
        }
    }

    function parseNdjsonLine(line) {
        var trimmed = (line || '').trim();
        if (!trimmed) return null;
        try {
            return JSON.parse(trimmed);
        } catch (err) {
            return null;
        }
    }

    async function runAiAnalysisWithStreaming(options) {
        var matchId = options.matchId;
        var force = options.force;
        var focus = options.focus || 'general';
        var container = options.container;
        var button = options.button;
        var statusEl = options.statusEl || null;
        var streamFallbackNotice = txt('streamFallback', 'Live stream interrupted. Falling back to standard analysis...');

        button.disabled = true;
        button.textContent = txt('analyzing', 'Analyzing...');
        setAiStatus(statusEl, txt('aiStatusStreaming', 'Status: streaming AI analysis...'), 'loading');

        var output = prepareStreamUi(container);
        var streamedText = '';
        var gotTerminalEvent = false;

        var canStream = !!(window.ReadableStream && typeof TextDecoder !== 'undefined');
        if (!canStream) {
            await runAiAnalysisSync({
                matchId: matchId,
                force: force,
                focus: focus,
                container: container,
                button: button,
                statusEl: statusEl,
                fallbackNotice: txt('streamUnavailable', 'Live stream is unavailable in this browser. Running standard analysis...'),
            });
            return;
        }

        try {
            var response = await fetch('/dashboard/api/matches/' + matchId + '/ai-analysis/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({force: force, language: getCurrentLocale(), focus: focus, coach_mode: getCoachMode()}),
            });

            if (!response.ok) {
                throw new Error('Stream endpoint returned ' + response.status);
            }
            if (!response.body || !response.body.getReader) {
                throw new Error('Stream reader not available');
            }

            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';

            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, {stream: true});
                var lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (var i = 0; i < lines.length; i += 1) {
                    var event = parseNdjsonLine(lines[i]);
                    if (!event || !event.type) continue;

                    if (event.type === 'chunk') {
                        streamedText += String(event.delta || '');
                        updateStreamOutput(container, output, streamedText);
                        continue;
                    }

                    if (event.type === 'done') {
                        gotTerminalEvent = true;
                        renderAiText(container, event.analysis || streamedText);
                        setAiStatus(statusEl, txt('aiStatusSuccess', 'Status: analysis updated.'), 'success');
                        completeAiButton(button);
                        try {
                            await reader.cancel();
                        } catch (err) {
                            // Ignore cancellation errors after terminal event.
                        }
                        break;
                    }

                    if (event.type === 'stale') {
                        streamFallbackNotice = txt('staleFallback', 'Live stream returned cached analysis. Retrying with standard analysis...');
                        if (event.error) {
                            streamFallbackNotice += ' (' + event.error + ')';
                        }
                        throw new Error('Stream returned stale cached response.');
                    }

                    if (event.type === 'error') {
                        throw new Error(event.error || 'AI analysis stream failed.');
                    }
                }

                if (gotTerminalEvent) break;
            }

            if (!gotTerminalEvent && buffer.trim()) {
                var tailEvent = parseNdjsonLine(buffer);
                if (tailEvent && tailEvent.type === 'done') {
                    gotTerminalEvent = true;
                    renderAiText(container, tailEvent.analysis || streamedText);
                    setAiStatus(statusEl, txt('aiStatusSuccess', 'Status: analysis updated.'), 'success');
                    completeAiButton(button);
                } else if (tailEvent && tailEvent.type === 'stale') {
                    streamFallbackNotice = txt('staleFallback', 'Live stream returned cached analysis. Retrying with standard analysis...');
                    if (tailEvent.error) {
                        streamFallbackNotice += ' (' + tailEvent.error + ')';
                    }
                    throw new Error('Stream returned stale cached response.');
                } else if (tailEvent && tailEvent.type === 'error') {
                    throw new Error(tailEvent.error || 'AI analysis stream failed.');
                }
            }

            if (!gotTerminalEvent) {
                throw new Error('AI analysis stream ended without a final event.');
            }
        } catch (err) {
            await runAiAnalysisSync({
                matchId: matchId,
                force: force,
                focus: focus,
                container: container,
                button: button,
                statusEl: statusEl,
                fallbackNotice: streamFallbackNotice,
            });
        }
    }

    function renderMatchBox(m) {
        var winClass = m.win ? 'match-win' : 'match-loss';
        var resultText = m.win ? txt('victory', 'Victory') : txt('defeat', 'Defeat');
        var queueHtml = m.queue_type ? '<span class="match-queue">' + escapeHtml(m.queue_type_label || m.queue_type) + '</span>' : '';
        var positionBadge = m.player_position && POSITION_MAP[m.player_position]
            ? '<span class="position-badge">' + POSITION_MAP[m.player_position] + '</span>'
            : '';
        var initialAiText = normalizeAiText(m.initial_ai_analysis || '');
        var hasInitialAi = !!initialAiText;
        var hasAiAnalysis = !!m.has_llm_analysis || hasInitialAi;
        var aiClass = hasAiAnalysis ? ' has-analysis' : '';
        var aiText = hasAiAnalysis ? txt('regenAi', 'Regenerate AI Analysis') : txt('runAi', 'Run AI Analysis');
        var dateHtml = m.analyzed_at ? '<span class="match-duration">' + escapeHtml(m.analyzed_at.slice(0, 10)) + '</span>' : '';
        var tabPrefix = 'match-' + m.id + '-tab';
        var visualPrefix = 'match-' + m.id + '-visual';

        var overviewHtml = '' +
            '<div class="match-box-stats">' +
                '<span class="match-kda">' + m.kills + '/' + m.deaths + '/' + m.assists +
                    '<span class="match-kda-ratio">' + m.kda + ' KDA</span></span>' +
                '<div class="match-stat-pills">' +
                    '<span class="stat-pill">' + fmtNum(m.gold_per_min) + ' ' + escapeHtml(metricTxt('gold_per_min', 'Gold/min')) + '</span>' +
                    '<span class="stat-pill">' + fmtNum(m.damage_per_min) + ' ' + escapeHtml(metricTxt('damage_per_min', 'Damage/min')) + '</span>' +
                    '<span class="stat-pill">' + fmtNum(m.vision_score) + ' ' + escapeHtml(txt('visionShort', 'VS')) + '</span>' +
                    '<span class="stat-pill">' + fmtNum(m.cs_total) + ' CS</span>' +
                '</div>' +
            '</div>' +
            '<div class="composition-split">' +
                '<div><div class="team-comp-title">' + escapeHtml(txt('allies', 'Allies')) + '</div>' + renderCompIcons(m.ally_comp, 'ally') + '</div>' +
                '<div><div class="team-comp-title">' + escapeHtml(txt('enemies', 'Enemies')) + '</div>' + renderCompIcons(m.enemy_comp, 'enemy') + '</div>' +
            '</div>' +
            renderLaneRows(m.lane_matchups);

        var aiContentHtml = hasInitialAi
            ? '<div class="match-ai-content llm-analysis llm-analysis--rich">' + renderAiMarkdownLite(initialAiText) + '</div>'
            : '<div class="match-ai-content card-muted">' + escapeHtml(txt('aiEmpty', 'Generate AI coaching for this match from in-game metrics, rank context, and composition.')) + '</div>';

        return '<div class="match-box ' + winClass + '" data-match-id="' + m.id + '">' +
            '<div class="match-box-indicator"></div>' +
            '<div class="match-box-main">' +
                '<div class="match-box-header">' +
                    championIconHtml({champion: m.champion, champion_label: m.champion_label, champion_icon: m.champion_icon}, '') +
                    '<span class="match-champion">' + escapeHtml(m.champion_label || m.champion) + '</span>' +
                    positionBadge +
                    '<span class="match-result-tag">' + resultText + '</span>' +
                    queueHtml +
                    '<span class="match-duration">' + fmtNum(m.game_duration) + 'm</span>' +
                    dateHtml +
                '</div>' +
                '<div class="match-tab-bar" role="tablist" aria-orientation="horizontal" aria-label="' + escapeHtml(txt('overview', 'Overview')) + '">' +
                    '<button class="match-tab-btn active" id="' + tabPrefix + '-overview" data-tab="overview" role="tab" aria-selected="true" aria-controls="' + tabPrefix + '-panel-overview">' + escapeHtml(txt('overview', 'Overview')) + '</button>' +
                    '<button class="match-tab-btn" id="' + tabPrefix + '-visuals" data-tab="visuals" role="tab" aria-selected="false" aria-controls="' + tabPrefix + '-panel-visuals" tabindex="-1">' + escapeHtml(txt('visuals', 'Visuals')) + '</button>' +
                    '<button class="match-tab-btn" id="' + tabPrefix + '-ai" data-tab="ai" role="tab" aria-selected="false" aria-controls="' + tabPrefix + '-panel-ai" tabindex="-1">' + escapeHtml(txt('aiAnalysis', 'AI Analysis')) + '</button>' +
                '</div>' +
                '<div class="match-tab-stage">' +
                    '<div class="match-tab-panel active" id="' + tabPrefix + '-panel-overview" data-panel="overview" role="tabpanel" aria-labelledby="' + tabPrefix + '-overview">' + overviewHtml + '</div>' +
                    '<div class="match-tab-panel" id="' + tabPrefix + '-panel-visuals" data-panel="visuals" role="tabpanel" aria-labelledby="' + tabPrefix + '-visuals" hidden>' + renderVisualPanel(m, visualPrefix) + '</div>' +
                    '<div class="match-tab-panel" id="' + tabPrefix + '-panel-ai" data-panel="ai" role="tabpanel" aria-labelledby="' + tabPrefix + '-ai" hidden>' +
                        '<div class="ai-analysis-head ai-analysis-head-inline">' +
                            '<div>' +
                                '<p class="ai-analysis-label">' + escapeHtml(txt('aiHeader', 'AI Match Analysis')) + '</p>' +
                                '<p class="ai-analysis-sub">' + escapeHtml(txt('aiSub', 'Live coaching generated from lane, comp, and team-tempo context.')) + '</p>' +
                            '</div>' +
                            '<span class="ai-analysis-chip">' + escapeHtml(txt('live', 'Live')) + '</span>' +
                        '</div>' +
                        aiContentHtml +
                        '<button class="ai-btn' + aiClass + '" data-match-id="' + m.id + '">' + aiText + '</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="match-box-actions">' +
                '<a href="/dashboard/matches/' + m.id + '" class="btn btn-ghost btn-sm">' + escapeHtml(txt('details', 'Details')) + '</a>' +
            '</div>' +
        '</div>';
    }

    function renderMatches(matches, append) {
        if (!append) {
            matchList.innerHTML = '';
        }
        if (!matches.length && !append) {
            matchList.innerHTML = '' +
                '<div class="empty-state">' +
                    '<p>' + escapeHtml(txt('noMatches', 'No matches found for this filter.')) + '</p>' +
                    '<p class="empty-state-hint">' + escapeHtml(txt('noMatchesHelp', 'Connect your Riot account in settings and sync recent matches to populate this queue.')) + '</p>' +
                    '<a href="/dashboard/settings" class="btn btn-secondary btn-sm empty-state-cta">' + escapeHtml(txt('goSettings', 'Go to Settings')) + '</a>' +
                '</div>';
            return;
        }
        matches.forEach(function (m) {
            matchList.insertAdjacentHTML('beforeend', renderMatchBox(m));
        });
    }

    function setMatchFilterSummary(displayed, total) {
        if (!filterSummary) return;
        var displayedCount = Number(displayed);
        var totalCount = Number(total);
        if (!Number.isFinite(displayedCount) || displayedCount < 0) {
            displayedCount = 0;
        }
        if (!Number.isFinite(totalCount) || totalCount < displayedCount) {
            totalCount = displayedCount;
        }
        var template = txt('showingMatches', 'Showing {displayed} of {total} matches');
        filterSummary.textContent = template
            .replace('{displayed}', String(displayedCount))
            .replace('{total}', String(totalCount));
    }

    function normalizeBadgeCount(total) {
        var count = Number(total);
        if (!Number.isFinite(count) || count < 0) {
            return 0;
        }
        return Math.floor(count);
    }

    function setFilterButtonAriaCount(button, count) {
        if (!button) return;
        var queueLabel = button.getAttribute('data-label-base') || button.textContent || '';
        queueLabel = queueLabel.trim();
        var template = txt('filterTabWithCount', '{queue}: {count} matches');
        button.setAttribute(
            'aria-label',
            template
                .replace('{queue}', queueLabel)
                .replace('{count}', String(count))
        );
    }

    function setFilterBadgeCount(button, total) {
        if (!button) return;
        var badge = button.querySelector('.filter-count-badge');
        if (!badge) return;
        var count = normalizeBadgeCount(total);
        badge.textContent = String(count);
        setFilterButtonAriaCount(button, count);
    }

    function updateActiveFilterBadge(total) {
        if (!filterBar) return;
        var active = filterBar.querySelector('.filter-btn[aria-selected="true"]') || filterBar.querySelector('.filter-btn.active');
        setFilterBadgeCount(active, total);
    }

    function initializeFilterBadgeState() {
        if (!filterBar) return;
        filterBar.querySelectorAll('.filter-btn').forEach(function (button) {
            setFilterBadgeCount(button, 0);
        });
    }

    function updateLoadMoreVisibility(total, hasMore) {
        if (!loadMoreContainer || !loadMoreBtn) return;
        if (typeof hasMore === 'boolean') {
            loadMoreContainer.style.display = hasMore ? '' : 'none';
            loadMoreBtn.disabled = !hasMore;
            loadMoreBtn.textContent = txt('loadMore', 'Load More');
            return;
        }
        loadMoreContainer.style.display = currentOffset < total ? '' : 'none';
    }

    function loadMore() {
        if (!loadMoreBtn) return;
        loadMoreBtn.disabled = true;
        loadMoreBtn.textContent = txt('loading', 'Loading...');

        var url = '/dashboard/api/matches?offset=' + currentOffset + '&limit=10';
        if (currentQueue) url += '&queue=' + encodeURIComponent(currentQueue);

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderMatches(data.matches, true);
                initializeAriaTabs(matchList);
                currentOffset += data.matches.length;
                updateLoadMoreVisibility(data.total, data.has_more);
                setMatchFilterSummary(currentOffset, data.total);
                updateActiveFilterBadge(data.total);
            })
            .catch(function () {
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = txt('loadMore', 'Load More');
            });
    }

    function filterByQueue(queue, sourceBtn) {
        currentQueue = queue;
        currentOffset = 0;
        if (loadMoreContainer) {
            loadMoreContainer.style.display = '';
            if (loadMoreBtn) {
                loadMoreBtn.disabled = true;
                loadMoreBtn.textContent = txt('loading', 'Loading...');
            }
        }

        var url = '/dashboard/api/matches?offset=0&limit=10';
        if (queue) url += '&queue=' + encodeURIComponent(queue);

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderMatches(data.matches, false);
                initializeAriaTabs(matchList);
                currentOffset = data.matches.length;
                updateLoadMoreVisibility(data.total, data.has_more);
                setMatchFilterSummary(currentOffset, data.total);
                setFilterBadgeCount(sourceBtn, data.total);
            })
            .catch(function () {
                if (loadMoreBtn) {
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.textContent = txt('loadMore', 'Load More');
                }
            });
    }

    function getAiFocusValue() {
        var select = document.getElementById('ai-focus-select');
        return select ? select.value : 'general';
    }

    function handleAiAnalysis(btn) {
        var matchId = btn.getAttribute('data-match-id');
        var aiPanel = btn.closest('.match-tab-panel');
        var content = aiPanel ? aiPanel.querySelector('.match-ai-content') : null;
        if (!content) return;

        runAiAnalysisWithStreaming({
            matchId: matchId,
            force: btn.classList.contains('has-analysis'),
            container: content,
            button: btn,
            focus: getAiFocusValue(),
        });
    }

    function syncTabState(buttons, panels, activeKey, buttonAttr, panelAttr) {
        buttons.forEach(function (button) {
            var isActive = button.getAttribute(buttonAttr) === activeKey;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', isActive ? 'true' : 'false');
            // Keep all tab buttons in the keyboard tab order.
            button.tabIndex = 0;
        });
        panels.forEach(function (panel) {
            var isActive = panel.getAttribute(panelAttr) === activeKey;
            panel.classList.toggle('active', isActive);
            panel.hidden = !isActive;
        });
    }

    function initializeAriaTabs(scope) {
        scope.querySelectorAll('.match-box').forEach(function (box) {
            var tabButtons = box.querySelectorAll('.match-tab-btn');
            var tabPanels = box.querySelectorAll('.match-tab-panel');
            if (tabButtons.length && tabPanels.length) {
                var activeTab = box.querySelector('.match-tab-btn.active');
                syncTabState(tabButtons, tabPanels, activeTab ? activeTab.getAttribute('data-tab') : 'overview', 'data-tab', 'data-panel');
            }

            box.querySelectorAll('.match-tab-panel[data-panel="visuals"]').forEach(function (visualPanel) {
                var visualButtons = visualPanel.querySelectorAll('.visual-toggle-btn');
                var visualGroups = visualPanel.querySelectorAll('.visual-group');
                if (visualButtons.length && visualGroups.length) {
                    var activeGroup = visualPanel.querySelector('.visual-toggle-btn.active');
                    syncTabState(visualButtons, visualGroups, activeGroup ? activeGroup.getAttribute('data-group') : 'compare', 'data-group', 'data-group');
                }
            });
        });
    }

    function initializeFromServer() {
        renderMatches(initialMatches, false);
        initializeAriaTabs(matchList);
        currentOffset = initialMatches.length;
        var initialTotal = Number(window.__totalGames || 0);
        updateLoadMoreVisibility(initialTotal, undefined);
        setMatchFilterSummary(currentOffset, initialTotal);
        setFilterBadgeCount(document.getElementById('queue-filter-all'), initialTotal);
    }

    if (matchList) {
        initializeFilterBadgeState();

        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', loadMore);
        }

        if (filterBar) {
            function setActiveQueueFilter(btn, focus) {
                if (!btn) return;
                filterBar.querySelectorAll('.filter-btn').forEach(function (b) {
                    var isActive = b === btn;
                    b.classList.toggle('active', isActive);
                    b.setAttribute('aria-selected', isActive ? 'true' : 'false');
                    b.tabIndex = isActive ? 0 : -1;
                });
                if (focus) {
                    btn.focus();
                }
            }

            filterBar.addEventListener('click', function (e) {
                var btn = e.target.closest('.filter-btn');
                if (!btn) return;
                setActiveQueueFilter(btn, false);
                filterByQueue(btn.getAttribute('data-queue'), btn);
            });

            filterBar.addEventListener('keydown', function (e) {
                var current = e.target.closest('.filter-btn');
                if (!current) return;
                var buttons = Array.prototype.slice.call(filterBar.querySelectorAll('.filter-btn'));
                var currentIndex = buttons.indexOf(current);
                if (currentIndex < 0) return;

                var nextIndex = currentIndex;
                if (e.key === 'ArrowRight') {
                    nextIndex = (currentIndex + 1) % buttons.length;
                } else if (e.key === 'ArrowLeft') {
                    nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
                } else if (e.key === 'Home') {
                    nextIndex = 0;
                } else if (e.key === 'End') {
                    nextIndex = buttons.length - 1;
                } else {
                    return;
                }

                e.preventDefault();
                var next = buttons[nextIndex];
                setActiveQueueFilter(next, true);
                filterByQueue(next.getAttribute('data-queue'), next);
            });
        }

        matchList.addEventListener('click', function (e) {
            var tabBtn = e.target.closest('.match-tab-btn');
            if (tabBtn) {
                var tab = tabBtn.getAttribute('data-tab');
                var box = tabBtn.closest('.match-box');
                if (!box) return;
                syncTabState(
                    box.querySelectorAll('.match-tab-btn'),
                    box.querySelectorAll('.match-tab-panel'),
                    tab,
                    'data-tab',
                    'data-panel'
                );
                return;
            }

            var visualToggle = e.target.closest('.visual-toggle-btn');
            if (visualToggle) {
                var visualPanel = visualToggle.closest('.match-tab-panel');
                if (!visualPanel) return;
                var group = visualToggle.getAttribute('data-group');
                syncTabState(
                    visualPanel.querySelectorAll('.visual-toggle-btn'),
                    visualPanel.querySelectorAll('.visual-group'),
                    group,
                    'data-group',
                    'data-group'
                );
                return;
            }

            var aiBtn = e.target.closest('.ai-btn');
            if (aiBtn) {
                handleAiAnalysis(aiBtn);
            }
        });

        initializeFromServer();
    }

    function bindTablistArrowKeys(container, buttonSelector, activateByKey) {
        if (!container) return;
        container.addEventListener('keydown', function (e) {
            var current = e.target.closest(buttonSelector);
            if (!current || !container.contains(current)) return;
            var buttons = Array.prototype.slice.call(container.querySelectorAll(buttonSelector));
            if (!buttons.length) return;

            var idx = buttons.indexOf(current);
            if (idx < 0) return;

            var nextIdx = idx;
            if (e.key === 'ArrowRight') {
                nextIdx = (idx + 1) % buttons.length;
            } else if (e.key === 'ArrowLeft') {
                nextIdx = (idx - 1 + buttons.length) % buttons.length;
            } else if (e.key === 'Home') {
                nextIdx = 0;
            } else if (e.key === 'End') {
                nextIdx = buttons.length - 1;
            } else {
                return;
            }

            e.preventDefault();
            var nextBtn = buttons[nextIdx];
            activateByKey(nextBtn);
            nextBtn.focus();
        });
    }

    var detailTabs = document.getElementById('detail-tabs');
    var detailPanels = document.querySelectorAll('.detail-tab-panel');
    var detailVisualToggle = document.getElementById('detail-visual-toggle');
    if (detailTabs && detailPanels.length) {
        function activateDetailTab(tab) {
            var buttons = detailTabs.querySelectorAll('.detail-tab-btn');
            syncTabState(buttons, detailPanels, tab, 'data-tab', 'data-panel');
        }

        function activateDetailVisual(group) {
            if (!detailVisualToggle) return;
            var toggleButtons = detailVisualToggle.querySelectorAll('.visual-toggle-btn');
            var visualPanel = detailVisualToggle.closest('.card');
            if (!visualPanel) return;
            var groups = visualPanel.querySelectorAll('.visual-group');
            syncTabState(toggleButtons, groups, group, 'data-group', 'data-group');
        }

        detailTabs.addEventListener('click', function (e) {
            var btn = e.target.closest('.detail-tab-btn');
            if (!btn) return;
            activateDetailTab(btn.getAttribute('data-tab'));
        });

        if (detailVisualToggle) {
            detailVisualToggle.addEventListener('click', function (e) {
                var btn = e.target.closest('.visual-toggle-btn');
                if (!btn) return;
                activateDetailVisual(btn.getAttribute('data-group'));
            });
        }

        bindTablistArrowKeys(detailTabs, '.detail-tab-btn', function (btn) {
            activateDetailTab(btn.getAttribute('data-tab'));
        });
        bindTablistArrowKeys(detailVisualToggle, '.visual-toggle-btn', function (btn) {
            activateDetailVisual(btn.getAttribute('data-group'));
        });

        activateDetailTab('overview');
        activateDetailVisual('compare');

        var detailAiBtn = document.getElementById('detail-ai-btn');
        var detailAiContent = document.getElementById('detail-ai-content');
        var detailAiInitial = document.getElementById('detail-ai-initial');
        var detailAiStatus = document.getElementById('detail-ai-status');
        if (detailAiBtn && detailAiContent && detailAiInitial) {
            var initialText = '';
            try {
                initialText = JSON.parse(detailAiInitial.textContent || '""');
            } catch (e) {
                initialText = '';
            }
            if (initialText) {
                renderAiText(detailAiContent, initialText);
                detailAiBtn.classList.add('has-analysis');
                detailAiBtn.textContent = txt('regenAi', 'Regenerate AI Analysis');
                setAiStatus(detailAiStatus, txt('aiStatusLoaded', 'Status: loaded last saved analysis.'), 'success');
            }

            detailAiBtn.addEventListener('click', function () {
                runAiAnalysisWithStreaming({
                    matchId: detailAiBtn.getAttribute('data-match-id'),
                    force: detailAiBtn.classList.contains('has-analysis'),
                    container: detailAiContent,
                    button: detailAiBtn,
                    statusEl: detailAiStatus,
                    focus: getAiFocusValue(),
                });
            });
        }
    }
});
