(function () {
  'use strict';

  const $coins = document.getElementById('coins');
  const $clicks = document.getElementById('total-clicks');
  const $clickPower = document.getElementById('click-power');
  const $energyFill = document.getElementById('energy-fill');
  const $energyText = document.getElementById('energy-text');
  const $coinBtn = document.getElementById('click-btn');
  const $toast = document.getElementById('toast');
  const $floatTemplate = document.getElementById('float-template');

  const state = {
    coins: parseInt($coins.textContent.replace(/\D/g, ''), 10) || 0,
    energy: parseInt($energyText.textContent.split('/')[0], 10) || 0,
    maxEnergy: parseInt($energyText.textContent.split('/')[1], 10) || 100,
    clickPower: parseInt($clickPower.textContent, 10) || 1,
    queue: 0,
    busy: false,
    toastTimer: null,
  };

  function getCookie(name) {
    const row = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
    return row ? decodeURIComponent(row.split('=')[1]) : null;
  }

  async function post(url) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: '{}',
    });
    return { ok: response.ok, data: await response.json().catch(() => ({})) };
  }

  function renderStats(d) {
    if (d.coins !== undefined) state.coins = d.coins;
    if (d.energy !== undefined) state.energy = d.energy;
    if (d.max_energy !== undefined) state.maxEnergy = d.max_energy;
    if (d.click_power !== undefined) state.clickPower = d.click_power;

    $coins.textContent = '🪙 ' + state.coins.toLocaleString('ru-RU');
    if ($clicks && d.total_clicks !== undefined) {
      $clicks.textContent = d.total_clicks.toLocaleString('ru-RU');
    }
    $clickPower.textContent = state.clickPower;
    $energyFill.style.width = Math.min(100, (state.energy / state.maxEnergy) * 100) + '%';
    $energyText.textContent = state.energy + '/' + state.maxEnergy;
    $coinBtn.disabled = state.energy < 1;
  }

  function showToast(text) {
    $toast.textContent = text;
    $toast.classList.remove('hidden');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => $toast.classList.add('hidden'), 2200);
  }

  function spawnFloat(crit) {
    const el = $floatTemplate.content.firstElementChild.cloneNode(true);
    el.textContent = '+' + (crit ? state.clickPower * 5 : state.clickPower) +
      (crit ? ' КРИТ!' : '');
    if (crit) el.classList.add('crit');
    el.style.left = 40 + Math.random() * 20 + '%';
    $coinBtn.appendChild(el);
    el.addEventListener('animationend', () => el.remove());
  }

  async function drainQueue() {
    if (state.busy) return;
    state.busy = true;
    while (state.queue > 0) {
      state.queue -= 1;
      try {
        const { ok, data } = await post(window.GAME_URLS.click);
        if (ok && data.ok) {
          renderStats(data);
          if (!data.suppressFloat) spawnFloat(data.crit);
        } else if (data.error === 'no_energy') {
          showToast('Энергия кончилась! Подожди немного ⚡');
          renderStats(data);
        }
      } catch (e) {
        showToast('Ошибка сети');
        break;
      }
    }
    state.busy = false;
  }

  $coinBtn.addEventListener('pointerdown', () => {
    if (state.energy < 1) return;
    state.energy -= 1;
    state.coins += state.clickPower;
    renderStats({ total_clicks: undefined });
    state.queue += 1;
    void drainQueue();
  });

  document.querySelectorAll('.buy-form').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const url = form.getAttribute('action');
      const { ok, data } = await post(url);
      if (ok && data.ok) {
        window.location.reload();
      } else if (data.error === 'not_enough_coins') {
        showToast('Не хватает монет!');
      } else if (data.error === 'max_level') {
        showToast('Максимальный уровень!');
      } else {
        showToast('Не удалось купить апгрейд');
      }
    });
  });

  setInterval(async () => {
    try {
      const response = await fetch(window.GAME_URLS.state);
      if (response.ok) renderStats(await response.json());
    } catch (e) { /* игнорируем сетевые сбои фонового синка */ }
  }, 5000);

  renderStats({});
})();
