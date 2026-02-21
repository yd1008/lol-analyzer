// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
    var THEME_STORAGE_KEY = 'lanescope-theme';

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

        toggle.dataset.theme = theme;
        toggle.setAttribute('aria-label', 'Switch to ' + nextTheme + ' theme');
        toggle.setAttribute('title', 'Switch to ' + nextTheme + ' theme');
        toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
        if (label) {
            label.textContent = theme === 'dark' ? 'Dark' : 'Light';
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

    initializeThemeToggle();

    var flashes = document.querySelectorAll('.flash');
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(function () { flash.remove(); }, 300);
        }, 5000);
    });

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfToken ? csrfToken.getAttribute('content') : '';

    var STREAM_STATUS_MESSAGES = ['Reading lane pressure', 'Comparing team tempo', 'Writing focused coaching'];
    var matchList = document.getElementById('match-list');
    var loadMoreBtn = document.getElementById('load-more-btn');
    var loadMoreContainer = document.getElementById('load-more-container');
    var filterBar = document.getElementById('match-filter-bar');
    var initialMatches = Array.isArray(window.__initialMatches) ? window.__initialMatches : [];
    var currentOffset = 0;
    var currentQueue = '';

    var POSITION_MAP = {TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP'};
    var VISUAL_METRICS = [
        {key: 'gold_per_min', label: 'Gold/min'},
        {key: 'damage_per_min', label: 'Damage/min'},
        {key: 'cs_per_min', label: 'CS/min'},
        {key: 'vision_per_min', label: 'Vision/min'},
        {key: 'kda', label: 'KDA'},
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
        var name = participant && participant.champion ? participant.champion : '?';
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
            var title = escapeHtml((p.summoner_name || p.champion) + ' | ' + p.champion + ' | ' + p.kills + '/' + p.deaths + '/' + p.assists);
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
                html += championIconHtml(ally, 'champion-icon-sm') +
                    '<div><div class="lane-player-name">' + escapeHtml(ally.summoner_name || ally.champion) + '</div>' +
                    '<div class="lane-player-sub">' + escapeHtml(ally.champion) + ' | ' + ally.kills + '/' + ally.deaths + '/' + ally.assists + '</div></div>';
            }
            html += '</div><div class="lane-player enemy">';
            if (enemy) {
                html += championIconHtml(enemy, 'champion-icon-sm') +
                    '<div><div class="lane-player-name">' + escapeHtml(enemy.summoner_name || enemy.champion) + '</div>' +
                    '<div class="lane-player-sub">' + escapeHtml(enemy.champion) + ' | ' + enemy.kills + '/' + enemy.deaths + '/' + enemy.assists + '</div></div>';
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
                '<div class="compact-visual-values">Y ' + fmtNum(p) + ' | T ' + fmtNum(t) + ' | L ' + fmtNum(l) + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderShareRings(m) {
        var shares = (m.visuals && m.visuals.shares) ? m.visuals.shares : {};
        var metrics = [
            {key: 'gold_share_pct', label: 'Gold Share'},
            {key: 'damage_share_pct', label: 'Damage Share'},
            {key: 'cs_share_pct', label: 'CS Share'},
            {key: 'vision_share_pct', label: 'Vision Share'},
            {key: 'kill_participation_pct', label: 'Kill Part.'},
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
            return '<p class="card-muted">No direct lane opponent data in this match.</p>';
        }

        var deltas = [
            {key: 'gpm_delta', label: 'Gold/min Delta'},
            {key: 'dpm_delta', label: 'Damage/min Delta'},
            {key: 'cspm_delta', label: 'CS/min Delta'},
            {key: 'vpm_delta', label: 'Vision/min Delta'},
            {key: 'kda_delta', label: 'KDA Delta'},
        ];
        var html = '<div class="lane-chart-head">' +
            championIconHtml(opponent, 'champion-icon-sm') +
            '<span>Lane vs ' + escapeHtml(opponent.champion) + '</span>' +
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
            '<div class="visual-toggle-bar" role="tablist" aria-label="Visualization groups">' +
                '<button class="visual-toggle-btn active" id="' + compareId + '-tab" data-group="compare" role="tab" aria-selected="true" aria-controls="' + compareId + '">Compare</button>' +
                '<button class="visual-toggle-btn" id="' + sharesId + '-tab" data-group="shares" role="tab" aria-selected="false" aria-controls="' + sharesId + '" tabindex="-1">Shares</button>' +
                '<button class="visual-toggle-btn" id="' + laneId + '-tab" data-group="lane" role="tab" aria-selected="false" aria-controls="' + laneId + '" tabindex="-1">Lane</button>' +
            '</div>' +
            '<div class="visual-group active" id="' + compareId + '" data-group="compare" role="tabpanel" aria-labelledby="' + compareId + '-tab">' + renderCompareRows(m) + '</div>' +
            '<div class="visual-group" id="' + sharesId + '" data-group="shares" role="tabpanel" aria-labelledby="' + sharesId + '-tab" hidden>' + renderShareRings(m) + '</div>' +
            '<div class="visual-group" id="' + laneId + '" data-group="lane" role="tabpanel" aria-labelledby="' + laneId + '-tab" hidden>' + renderLaneCharts(m) + '</div>';
    }

    function normalizeAiText(text) {
        var normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        normalized = normalized.replace(/^\s{0,3}#{1,6}\s*/gm, '');
        normalized = normalized.replace(/^\s*>\s?/gm, '');
        normalized = normalized.replace(/^\s*[-*+]\s+/gm, '');
        normalized = normalized.replace(/^\s*\d+[.)]\s+/gm, '');
        normalized = normalized.replace(/\*\*(.*?)\*\*/g, '$1');
        normalized = normalized.replace(/__(.*?)__/g, '$1');
        normalized = normalized.replace(/`([^`]+)`/g, '$1');
        normalized = normalized.replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1');
        normalized = normalized.replace(/\n{3,}/g, '\n\n');
        return normalized.trim();
    }

    function clearAiContainerState(container) {
        container.classList.remove('card-muted');
        container.classList.remove('ai-stream-host', 'is-loading', 'is-streaming', 'ai-stream-fallback', 'llm-analysis');
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
        container.innerHTML = '<p class="card-muted">' + escapeHtml(text || 'AI analysis failed.') + '</p>';
    }

    function renderAiText(container, text) {
        clearAiContainerState(container);
        container.classList.add('llm-analysis');
        container.textContent = normalizeAiText(text);
    }

    function buildStatusMarkup() {
        return STREAM_STATUS_MESSAGES.map(function (message) {
            return '<span>' + escapeHtml(message) + '</span>';
        }).join('');
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
        button.textContent = 'Regenerate AI Analysis';
    }

    function resetAiButton(button) {
        button.disabled = false;
        button.textContent = 'Run AI Analysis';
    }

    async function runAiAnalysisSync(options) {
        var matchId = options.matchId;
        var force = options.force;
        var container = options.container;
        var button = options.button;
        var fallbackNotice = options.fallbackNotice || '';

        if (fallbackNotice) {
            renderAiError(container, fallbackNotice);
            container.classList.add('ai-stream-fallback');
        }

        try {
            var resp = await fetch('/dashboard/api/matches/' + matchId + '/ai-analysis', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({force: force}),
            });
            var data = await resp.json();
            if (data.error && !data.analysis) {
                renderAiError(container, data.error || 'AI analysis failed.');
                resetAiButton(button);
                return;
            }
            renderAiText(container, data.analysis || '');
            if (data.stale && data.error) {
                appendAiNote(container, 'Using cached analysis because regeneration failed: ' + data.error, 'card-muted');
            }
            completeAiButton(button);
        } catch (err) {
            renderAiError(container, 'AI analysis failed.');
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
        var container = options.container;
        var button = options.button;
        var streamFallbackNotice = 'Live stream interrupted. Falling back to standard analysis...';

        button.disabled = true;
        button.textContent = 'Analyzing...';

        var output = prepareStreamUi(container);
        var streamedText = '';
        var gotTerminalEvent = false;

        var canStream = !!(window.ReadableStream && typeof TextDecoder !== 'undefined');
        if (!canStream) {
            await runAiAnalysisSync({
                matchId: matchId,
                force: force,
                container: container,
                button: button,
                fallbackNotice: 'Live stream is unavailable in this browser. Running standard analysis...',
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
                body: JSON.stringify({force: force}),
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
                        completeAiButton(button);
                        try {
                            await reader.cancel();
                        } catch (err) {
                            // Ignore cancellation errors after terminal event.
                        }
                        break;
                    }

                    if (event.type === 'stale') {
                        streamFallbackNotice = 'Live stream returned cached analysis. Retrying with standard analysis...';
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
                    completeAiButton(button);
                } else if (tailEvent && tailEvent.type === 'stale') {
                    streamFallbackNotice = 'Live stream returned cached analysis. Retrying with standard analysis...';
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
                container: container,
                button: button,
                fallbackNotice: streamFallbackNotice,
            });
        }
    }

    function renderMatchBox(m) {
        var winClass = m.win ? 'match-win' : 'match-loss';
        var resultText = m.win ? 'Victory' : 'Defeat';
        var queueHtml = m.queue_type ? '<span class="match-queue">' + escapeHtml(m.queue_type) + '</span>' : '';
        var positionBadge = m.player_position && POSITION_MAP[m.player_position]
            ? '<span class="position-badge">' + POSITION_MAP[m.player_position] + '</span>'
            : '';
        var aiClass = m.has_llm_analysis ? ' has-analysis' : '';
        var aiText = m.has_llm_analysis ? 'Regenerate AI Analysis' : 'Run AI Analysis';
        var dateHtml = m.analyzed_at ? '<span class="match-duration">' + escapeHtml(m.analyzed_at.slice(0, 10)) + '</span>' : '';
        var tabPrefix = 'match-' + m.id + '-tab';
        var visualPrefix = 'match-' + m.id + '-visual';

        var overviewHtml = '' +
            '<div class="match-box-stats">' +
                '<span class="match-kda">' + m.kills + '/' + m.deaths + '/' + m.assists +
                    '<span class="match-kda-ratio">' + m.kda + ' KDA</span></span>' +
                '<div class="match-stat-pills">' +
                    '<span class="stat-pill">' + fmtNum(m.gold_per_min) + ' G/m</span>' +
                    '<span class="stat-pill">' + fmtNum(m.damage_per_min) + ' D/m</span>' +
                    '<span class="stat-pill">' + fmtNum(m.vision_score) + ' VS</span>' +
                    '<span class="stat-pill">' + fmtNum(m.cs_total) + ' CS</span>' +
                '</div>' +
            '</div>' +
            '<div class="composition-split">' +
                '<div><div class="team-comp-title">Allies</div>' + renderCompIcons(m.ally_comp, 'ally') + '</div>' +
                '<div><div class="team-comp-title">Enemies</div>' + renderCompIcons(m.enemy_comp, 'enemy') + '</div>' +
            '</div>' +
            renderLaneRows(m.lane_matchups);

        return '<div class="match-box ' + winClass + '" data-match-id="' + m.id + '">' +
            '<div class="match-box-indicator"></div>' +
            '<div class="match-box-main">' +
                '<div class="match-box-header">' +
                    championIconHtml({champion: m.champion, champion_icon: m.champion_icon}, '') +
                    '<span class="match-champion">' + escapeHtml(m.champion) + '</span>' +
                    positionBadge +
                    '<span class="match-result-tag">' + resultText + '</span>' +
                    queueHtml +
                    '<span class="match-duration">' + fmtNum(m.game_duration) + 'm</span>' +
                    dateHtml +
                '</div>' +
                '<div class="match-tab-bar" role="tablist" aria-label="Match views">' +
                    '<button class="match-tab-btn active" id="' + tabPrefix + '-overview" data-tab="overview" role="tab" aria-selected="true" aria-controls="' + tabPrefix + '-panel-overview">Overview</button>' +
                    '<button class="match-tab-btn" id="' + tabPrefix + '-visuals" data-tab="visuals" role="tab" aria-selected="false" aria-controls="' + tabPrefix + '-panel-visuals" tabindex="-1">Visuals</button>' +
                    '<button class="match-tab-btn" id="' + tabPrefix + '-ai" data-tab="ai" role="tab" aria-selected="false" aria-controls="' + tabPrefix + '-panel-ai" tabindex="-1">AI Analysis</button>' +
                '</div>' +
                '<div class="match-tab-stage">' +
                    '<div class="match-tab-panel active" id="' + tabPrefix + '-panel-overview" data-panel="overview" role="tabpanel" aria-labelledby="' + tabPrefix + '-overview">' + overviewHtml + '</div>' +
                    '<div class="match-tab-panel" id="' + tabPrefix + '-panel-visuals" data-panel="visuals" role="tabpanel" aria-labelledby="' + tabPrefix + '-visuals" hidden>' + renderVisualPanel(m, visualPrefix) + '</div>' +
                    '<div class="match-tab-panel" id="' + tabPrefix + '-panel-ai" data-panel="ai" role="tabpanel" aria-labelledby="' + tabPrefix + '-ai" hidden>' +
                        '<div class="ai-analysis-head ai-analysis-head-inline">' +
                            '<div>' +
                                '<p class="ai-analysis-label">AI Match Analysis</p>' +
                                '<p class="ai-analysis-sub">Live coaching generated from lane, comp, and team-tempo context.</p>' +
                            '</div>' +
                            '<span class="ai-analysis-chip">Live</span>' +
                        '</div>' +
                        '<div class="match-ai-content card-muted">Generate AI coaching for this match from in-game metrics, rank context, and composition.</div>' +
                        '<button class="ai-btn' + aiClass + '" data-match-id="' + m.id + '">' + aiText + '</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="match-box-actions">' +
                '<a href="/dashboard/matches/' + m.id + '" class="btn btn-ghost btn-sm">Details</a>' +
            '</div>' +
        '</div>';
    }

    function renderMatches(matches, append) {
        if (!append) {
            matchList.innerHTML = '';
        }
        if (!matches.length && !append) {
            matchList.innerHTML = '<div class="empty-state"><p>No matches found for this filter.</p></div>';
            return;
        }
        matches.forEach(function (m) {
            matchList.insertAdjacentHTML('beforeend', renderMatchBox(m));
        });
    }

    function updateLoadMoreVisibility(total, hasMore) {
        if (!loadMoreContainer || !loadMoreBtn) return;
        if (typeof hasMore === 'boolean') {
            loadMoreContainer.style.display = hasMore ? '' : 'none';
            loadMoreBtn.disabled = !hasMore;
            loadMoreBtn.textContent = 'Load More';
            return;
        }
        loadMoreContainer.style.display = currentOffset < total ? '' : 'none';
    }

    function loadMore() {
        if (!loadMoreBtn) return;
        loadMoreBtn.disabled = true;
        loadMoreBtn.textContent = 'Loading...';

        var url = '/dashboard/api/matches?offset=' + currentOffset + '&limit=10';
        if (currentQueue) url += '&queue=' + encodeURIComponent(currentQueue);

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderMatches(data.matches, true);
                initializeAriaTabs(matchList);
                currentOffset += data.matches.length;
                updateLoadMoreVisibility(data.total, data.has_more);
            })
            .catch(function () {
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = 'Load More';
            });
    }

    function filterByQueue(queue) {
        currentQueue = queue;
        currentOffset = 0;
        if (loadMoreContainer) {
            loadMoreContainer.style.display = '';
            if (loadMoreBtn) {
                loadMoreBtn.disabled = true;
                loadMoreBtn.textContent = 'Loading...';
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
            })
            .catch(function () {
                if (loadMoreBtn) {
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.textContent = 'Load More';
                }
            });
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
        updateLoadMoreVisibility(window.__totalGames || 0, undefined);
    }

    if (matchList) {
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', loadMore);
        }

        if (filterBar) {
            filterBar.addEventListener('click', function (e) {
                var btn = e.target.closest('.filter-btn');
                if (!btn) return;
                filterBar.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                filterByQueue(btn.getAttribute('data-queue'));
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

        activateDetailTab('overview');
        activateDetailVisual('compare');

        var detailAiBtn = document.getElementById('detail-ai-btn');
        var detailAiContent = document.getElementById('detail-ai-content');
        var detailAiInitial = document.getElementById('detail-ai-initial');
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
                detailAiBtn.textContent = 'Regenerate AI Analysis';
            }

            detailAiBtn.addEventListener('click', function () {
                runAiAnalysisWithStreaming({
                    matchId: detailAiBtn.getAttribute('data-match-id'),
                    force: detailAiBtn.classList.contains('has-analysis'),
                    container: detailAiContent,
                    button: detailAiBtn,
                });
            });
        }
    }
});
