(function () {
  'use strict';

  const COLORS = {
    up: '#4cc38a',
    down: '#e5534b',
    grid: 'rgba(255,255,255,0.06)',
    text: '#9aa0b5',
  };

  function getCookie(name) {
    const row = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
    return row ? decodeURIComponent(row.split('=')[1]) : null;
  }

  function showToast(text, isError) {
    const toast = document.getElementById('toast');
    toast.textContent = text;
    toast.style.background = isError ? 'var(--red)' : 'var(--green)';
    toast.classList.remove('hidden');
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.add('hidden'), 2500);
  }

  function formatCoins(value) {
    return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
  }

  // ---------- Свечной график ----------

  function drawCandles(canvas, candles) {
    const dpr = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth || canvas.parentElement.clientWidth || 840;
    const cssHeight = 240;

    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    canvas.style.width = cssWidth + 'px';
    canvas.style.height = cssHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    if (!candles.length) {
      ctx.fillStyle = COLORS.text;
      ctx.font = '14px sans-serif';
      ctx.fillText('Истории пока нет — обновись через минуту', 16, 24);
      return;
    }

    const padTop = 14, padBottom = 20;
    const plotH = cssHeight - padTop - padBottom;
    let min = Infinity, max = -Infinity;
    for (const c of candles) {
      if (c.l < min) min = c.l;
      if (c.h > max) max = c.h;
    }
    const spread = (max - min) || max * 0.02 || 1;
    min -= spread * 0.08;
    max += spread * 0.08;

    const y = (p) => padTop + (max - p) / (max - min) * plotH;

    // Сетка
    ctx.strokeStyle = COLORS.grid;
    ctx.fillStyle = COLORS.text;
    ctx.font = '11px sans-serif';
    for (let i = 0; i <= 4; i++) {
      const py = padTop + plotH * i / 4;
      ctx.beginPath();
      ctx.moveTo(0, py);
      ctx.lineTo(cssWidth, py);
      ctx.stroke();
      const label = (max - (max - min) * i / 4).toFixed(2);
      ctx.fillText(label, 6, py - 3);
    }

    const slot = cssWidth / candles.length;
    const bodyW = Math.max(3, Math.min(slot * 0.62, 18));

    candles.forEach((c, i) => {
      const cx = slot * i + slot / 2;
      const up = c.c >= c.o;
      ctx.strokeStyle = up ? COLORS.up : COLORS.down;
      ctx.fillStyle = up ? COLORS.up : COLORS.down;

      // Фитиль
      ctx.beginPath();
      ctx.moveTo(cx, y(c.h));
      ctx.lineTo(cx, y(c.l));
      ctx.stroke();

      // Тело
      const top = y(Math.max(c.o, c.c));
      const bottom = y(Math.min(c.o, c.c));
      ctx.fillRect(cx - bodyW / 2, top, bodyW, Math.max(1.5, bottom - top));
    });
  }

  // ---------- Загрузка данных ----------

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    return { ok: response.ok, data: await response.json().catch(() => ({})) };
  }

  async function refreshAsset(id) {
    try {
      const { ok, data } = await fetchJson(window.MARKET.urls.asset + id + '/');
      if (!ok) return;
      const $price = document.getElementById('price-' + id);
      const $change = document.getElementById('change-' + id);
      if ($price) $price.textContent = data.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 });
      if ($change) {
        $change.textContent = (data.change_pct > 0 ? '+' : '') + data.change_pct + '%';
        $change.className = 'change ' + (data.change_pct >= 0 ? 'pos' : 'neg');
        $change.style.color = data.change_pct >= 0 ? COLORS.up : COLORS.down;
      }
      drawCandles(document.getElementById('chart-' + id), data.candles);
    } catch (e) { /* сеть мигнула — не страшно */ }
  }

  async function refreshPortfolio() {
    try {
      const { ok, data } = await fetchJson(window.MARKET.urls.portfolio);
      if (!ok) return;

      document.getElementById('invested').textContent =
        '🪙 ' + formatCoins(data.invested_value);
      const pnlEl = document.getElementById('unrealized-pnl');
      pnlEl.textContent = (data.unrealized_pnl >= 0 ? '+' : '') +
        formatCoins(data.unrealized_pnl);
      pnlEl.style.color = data.unrealized_pnl >= 0 ? COLORS.up : COLORS.down;

      renderPortfolioTable(data.holdings);

      const state = await fetchJson(window.GAME_URLS.state);
      if (state.ok) {
        document.getElementById('coins').textContent =
          '🪙 ' + formatCoins(state.data.coins);
      }
    } catch (e) { /* игнорируем */ }
  }

  function renderPortfolioTable(holdings) {
    const tbody = document.querySelector('#portfolio-table tbody');
    tbody.innerHTML = '';

    if (!holdings.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Пока пусто — купи что-нибудь!</td></tr>';
      return;
    }

    for (const h of holdings) {
      const tr = document.createElement('tr');
      const pnlClass = h.unrealized_pnl >= 0 ? 'pos' : 'neg';
      const pnlText = (h.unrealized_pnl >= 0 ? '+' : '') + formatCoins(h.unrealized_pnl);
      tr.innerHTML = [
        '<td>' + h.ticker + '</td>',
        '<td>' + h.quantity + '</td>',
        '<td>' + h.avg_price + '</td>',
        '<td>' + h.current_price + '</td>',
        '<td>' + formatCoins(h.value) + '</td>',
        '<td class="' + pnlClass + '" style="color:' +
          (h.unrealized_pnl >= 0 ? COLORS.up : COLORS.down) + '">' + pnlText + '</td>',
      ].join('');
      tbody.appendChild(tr);
    }
  }

  // ---------- Сделки ----------

  function bindTradeForms() {
    document.querySelectorAll('.asset-card').forEach((card) => {
      const assetId = card.dataset.assetId;

      card.querySelectorAll('.trade-form').forEach((form) => {
        form.addEventListener('submit', async (event) => {
          event.preventDefault();
          const side = form.dataset.side;
          const qty = parseInt(form.querySelector('[data-qty]').value, 10);

          const url = window.MARKET.urls.trade + assetId + '/' + side + '/';
          const { ok, data } = await fetchJson(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ quantity: qty }),
          });

          if (ok && data.ok) {
            showToast(
              side === 'buy'
                ? 'Куплено ' + data.quantity + ' шт по ' + data.price + ' 🪙−' + data.spent
                : 'Продано ' + data.quantity + ' шт по ' + data.price +
                  ' 🪙+' + data.earned +
                  (data.realized_pnl >= 0 ? ' (профит +' : ' (убыток ') +
                  data.realized_pnl + ')',
              false,
            );
            await Promise.all([refreshPortfolio(), refreshAsset(assetId)]);
          } else {
            const messages = {
              not_enough_coins: 'Не хватает монет!',
              not_enough_assets: 'Нет столько бумаг!',
              no_position: 'У тебя нет этого актива',
              invalid_quantity: 'Некорректное количество',
            };
            showToast(messages[data.error] || 'Сделка не прошла', true);
          }
        });
      });
    });
  }

  // ---------- Старт и поллинг ----------

  bindTradeForms();
  window.MARKET.assets.forEach(refreshAsset);
  refreshPortfolio();

  setInterval(() => {
    window.MARKET.assets.forEach(refreshAsset);
    refreshPortfolio();
  }, 10000);
})();
