// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
    var flashes = document.querySelectorAll('.flash');
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(function () { flash.remove(); }, 300);
        }, 5000);
    });

    // ---- Dashboard match list logic ----
    var matchList = document.getElementById('match-list');
    if (!matchList) return;

    var loadMoreBtn = document.getElementById('load-more-btn');
    var loadMoreContainer = document.getElementById('load-more-container');
    var filterBar = document.getElementById('match-filter-bar');
    var initialMatches = Array.isArray(window.__initialMatches) ? window.__initialMatches : [];
    var currentOffset = 0;
    var currentQueue = '';
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfToken ? csrfToken.getAttribute('content') : '';

    var POSITION_MAP = {TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP'};
    var VISUAL_METRICS = [
        {key: 'gold_per_min', label: 'Gold/m'},
        {key: 'damage_per_min', label: 'Dmg/m'},
        {key: 'cs_per_min', label: 'CS/m'},
        {key: 'vision_per_min', label: 'Vision/m'},
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
            var title = escapeHtml((p.summoner_name || p.champion) + ' · ' + p.champion + ' · ' + p.kills + '/' + p.deaths + '/' + p.assists);
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
                    '<div class="lane-player-sub">' + escapeHtml(ally.champion) + ' · ' + ally.kills + '/' + ally.deaths + '/' + ally.assists + '</div></div>';
            }
            html += '</div><div class="lane-player enemy">';
            if (enemy) {
                html += championIconHtml(enemy, 'champion-icon-sm') +
                    '<div><div class="lane-player-name">' + escapeHtml(enemy.summoner_name || enemy.champion) + '</div>' +
                    '<div class="lane-player-sub">' + escapeHtml(enemy.champion) + ' · ' + enemy.kills + '/' + enemy.deaths + '/' + enemy.assists + '</div></div>';
            }
            html += '</div></div>';
        });
        html += '</div>';
        return html;
    }

    function renderVisualRows(m) {
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
                '<div class="compact-visual-values">Y ' + fmtNum(p) + ' · T ' + fmtNum(t) + ' · L ' + fmtNum(l) + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }

    function renderMatchBox(m) {
        var winClass = m.win ? 'match-win' : 'match-loss';
        var resultText = m.win ? 'Victory' : 'Defeat';
        var queueHtml = m.queue_type ? '<span class="match-queue">' + escapeHtml(m.queue_type) + '</span>' : '';
        var positionBadge = m.player_position && POSITION_MAP[m.player_position]
            ? '<span class="position-badge">' + POSITION_MAP[m.player_position] + '</span>'
            : '';
        var aiClass = m.has_llm_analysis ? ' has-analysis' : '';
        var aiText = m.has_llm_analysis ? 'Load AI Analysis' : 'Run AI Analysis';
        var dateHtml = m.analyzed_at ? '<span class="match-duration">' + escapeHtml(m.analyzed_at.slice(0, 10)) + '</span>' : '';

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
                '<div class="match-tab-bar">' +
                    '<button class="match-tab-btn active" data-tab="overview">Overview</button>' +
                    '<button class="match-tab-btn" data-tab="visuals">Visuals</button>' +
                    '<button class="match-tab-btn" data-tab="ai">AI Analysis</button>' +
                '</div>' +
                '<div class="match-tab-panel active" data-panel="overview">' + overviewHtml + '</div>' +
                '<div class="match-tab-panel" data-panel="visuals">' + renderVisualRows(m) + '</div>' +
                '<div class="match-tab-panel" data-panel="ai">' +
                    '<div class="match-ai-content card-muted">Generate AI coaching for this match from in-game metrics, rank context, and team composition.</div>' +
                    '<button class="ai-btn' + aiClass + '" data-match-id="' + m.id + '">' + aiText + '</button>' +
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

        btn.disabled = true;
        btn.textContent = 'Analyzing...';

        fetch('/dashboard/api/matches/' + matchId + '/ai-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    btn.textContent = 'Error';
                    btn.disabled = false;
                    setTimeout(function () { btn.textContent = 'Run AI Analysis'; }, 2000);
                    return;
                }
                content.className = 'match-ai-content llm-analysis';
                content.textContent = data.analysis || '';
                btn.textContent = 'Refresh AI Analysis';
                btn.classList.add('has-analysis');
                btn.disabled = false;
            })
            .catch(function () {
                btn.textContent = 'Error';
                btn.disabled = false;
                setTimeout(function () { btn.textContent = 'Run AI Analysis'; }, 2000);
            });
    }

    function initializeFromServer() {
        renderMatches(initialMatches, false);
        currentOffset = initialMatches.length;
        updateLoadMoreVisibility(window.__totalGames || 0, undefined);
    }

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
            box.querySelectorAll('.match-tab-btn').forEach(function (b) { b.classList.remove('active'); });
            tabBtn.classList.add('active');
            box.querySelectorAll('.match-tab-panel').forEach(function (panel) {
                panel.classList.toggle('active', panel.getAttribute('data-panel') === tab);
            });
            return;
        }

        var aiBtn = e.target.closest('.ai-btn');
        if (aiBtn) {
            handleAiAnalysis(aiBtn);
        }
    });

    initializeFromServer();
});
