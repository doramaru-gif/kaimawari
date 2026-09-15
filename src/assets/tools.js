(() => {
  const yen = (n) => '¥' + Math.round(n).toLocaleString('ja-JP');
  const pt = (n) => Math.round(n).toLocaleString('ja-JP') + 'pt';

  // 買いまわりプランの並べ方切り替え
  document.querySelectorAll('[data-strategy-root]').forEach((root) => {
    const tabs = [...root.querySelectorAll('[data-strategy]')];
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.forEach((t) => t.setAttribute('aria-selected', String(t === tab)));
        root.querySelectorAll('[data-plan]').forEach((panel) => {
          panel.hidden = panel.dataset.plan !== tab.dataset.strategy;
        });
        const active = root.querySelector(`[data-plan="${tab.dataset.strategy}"]`);
        const calc = document.querySelector('[data-marathon-calc]');
        if (active && calc) {
          calc.elements.total.value = active.dataset.total;
          calc.dispatchEvent(new Event('input'));
        }
      });
    });
  });

  // 買ったチェック（この端末にだけ保存）。チェックした商品の枠にスタンプを押す
  const BOUGHT_KEY = 'kaimawari:bought';
  const BOUGHT_KEEP_MS = 30 * 24 * 60 * 60 * 1000;
  const readBought = () => {
    try { return JSON.parse(localStorage.getItem(BOUGHT_KEY)) || {}; } catch { return {}; }
  };
  const writeBought = (data) => {
    try { localStorage.setItem(BOUGHT_KEY, JSON.stringify(data)); } catch { /* 保存できない環境では画面上だけ反映 */ }
  };
  const syncBought = (bought = readBought()) => {
    document.querySelectorAll('[data-plan]').forEach((panel) => {
      let done = 0;
      panel.querySelectorAll('[data-buy]').forEach((box) => {
        box.checked = Boolean(bought[box.dataset.buy]);
        box.closest('.line')?.classList.toggle('is-bought', box.checked);
        panel.querySelector(`[data-slot="${box.dataset.slot}"]`)?.classList.toggle('is-done', box.checked);
        if (box.checked) done += 1;
      });
      const progress = panel.querySelector('[data-progress]');
      if (progress) progress.textContent = `${done} / ${progress.dataset.target}`;
    });
  };
  let boughtState = readBought();
  document.addEventListener('change', (event) => {
    const box = event.target.closest('[data-buy]');
    if (!box) return;
    if (box.checked) boughtState[box.dataset.buy] = Date.now();
    else delete boughtState[box.dataset.buy];
    const cutoff = Date.now() - BOUGHT_KEEP_MS;
    Object.keys(boughtState).forEach((key) => { if (boughtState[key] < cutoff) delete boughtState[key]; });
    writeBought(boughtState);
    syncBought(boughtState);
  });
  document.querySelectorAll('[data-reset-bought]').forEach((button) => {
    button.addEventListener('click', () => { boughtState = {}; writeBought(boughtState); syncBought(boughtState); });
  });
  syncBought(boughtState);

  // 倍率と還元の計算（税抜は10%で割り戻して少なめに見積もる）
  const calc = document.querySelector('[data-marathon-calc]');
  const calcResult = document.querySelector('[data-marathon-result]');
  if (calc && calcResult) {
    const set = (key, text) => { calcResult.querySelector(`[data-k="${key}"]`).textContent = text; };
    const update = () => {
      const shops = Number(calc.elements.shops.value);
      const total = Math.max(0, Math.floor(Number(calc.elements.total.value) || 0));
      const cap = Math.max(0, Math.floor(Number(calc.elements.cap.value) || 0));
      calc.elements.shopsOut.value = shops;

      const exTax = Math.floor((total * 10) / 11);
      const normal = Math.floor(exTax / 100);
      const rawBonus = Math.floor((exTax * (shops - 1)) / 100);
      const bonus = Math.min(rawBonus, cap);
      set('normal', pt(normal));
      set('bonus', pt(bonus));
      set('points', pt(normal + bonus));
      set('rate', total ? (((normal + bonus) / total) * 100).toFixed(1) + '%' : '0.0%');

      if (shops <= 1) {
        set('cap', '2ショップ目から買いまわりボーナスが付きます。');
      } else if (rawBonus >= cap) {
        set('cap', `ボーナスは上限${pt(cap)}に到達。これ以上買ってもボーナスは増えません。`);
      } else {
        const exNeeded = Math.ceil((cap * 100) / (shops - 1));
        const totalNeeded = Math.ceil((exNeeded * 11) / 10);
        set('cap', `あと${yen(totalNeeded - total)}（税込）で上限${pt(cap)}に届きます。`);
      }
    };
    calc.addEventListener('input', update);
    update();
  }

  // ラクヨコ送料無料ライン計算機
  const rk = document.querySelector('[data-rakuyoko-calc]');
  if (rk) {
    const min = Number(rk.dataset.min);
    const max = Number(rk.dataset.max);
    const list = rk.querySelector('[data-rows]');
    const result = rk.querySelector('[data-result]');

    const meter = (total) => {
      const scaleMax = Math.max(max, total);
      const fill = Math.min(100, (total / scaleMax) * 100);
      const minAt = (min / scaleMax) * 100;
      const maxAt = (max / scaleMax) * 100;
      return `<div class="meter-wrap">
        <div class="meter" role="img" aria-label="合計${yen(total)}（注文できる範囲 ${yen(min)}〜${yen(max)}）">
          <span class="meter-fill${total > max ? ' is-over' : ''}" style="width:${fill}%"></span>
          <span class="meter-mark" style="left:${minAt}%"></span>
          <span class="meter-mark" style="left:calc(${maxAt}% - 2px)"></span>
        </div>
        <div class="meter-scale"><span>¥0</span><span>${yen(min)}</span><span>${yen(max)}</span></div>
      </div>`;
    };

    // 大きい順に、上限に収まる最初の注文へ入れる
    const splitOrders = (prices) => {
      const orders = [];
      [...prices].sort((a, b) => b - a).forEach((price) => {
        const order = orders.find((o) => o.sum + price <= max);
        if (order) { order.items.push(price); order.sum += price; }
        else orders.push({ items: [price], sum: price });
      });
      return orders;
    };

    const update = () => {
      const prices = [...list.querySelectorAll('input')]
        .map((input) => Math.floor(Number(input.value)))
        .filter((v) => v > 0);
      const total = prices.reduce((a, b) => a + b, 0);

      if (!prices.length) {
        result.innerHTML = '<p class="note">金額を入れると判定します。</p>';
        return;
      }
      const tooBig = prices.filter((p) => p > max);
      if (tooBig.length) {
        result.innerHTML = `<p class="verdict bad">${yen(tooBig[0])}の商品は1点で上限${yen(max)}を超えるため、ラクヨコでは注文できません。</p>`;
        return;
      }
      if (total < min) {
        result.innerHTML = `<p class="verdict warn">あと${yen(min - total)}で注文できます</p>${meter(total)}
          <p class="note">合計${yen(total)}。${yen(min)}（税込）以上から注文でき、送料は無料です。</p>`;
        return;
      }
      if (total <= max) {
        result.innerHTML = `<p class="verdict ok">1回で注文できます</p>${meter(total)}
          <p class="note">合計${yen(total)}。上限まではあと${yen(max - total)}入ります。</p>`;
        return;
      }

      const orders = splitOrders(prices);
      const short = orders.filter((o) => o.sum < min);
      const rows = orders.map((o, i) => `<li class="order">
          <span class="order-name">注文${i + 1}</span>
          <span class="order-items">${o.items.map(yen).join(' + ')}</span>
          <span class="order-sum">${yen(o.sum)}</span>
          ${o.sum < min
            ? `<span class="status warn">あと${yen(min - o.sum)}足りません</span>`
            : '<span class="status ok">注文できます</span>'}
        </li>`).join('');
      result.innerHTML = `<p class="verdict ${short.length ? 'warn' : 'ok'}">上限を超えるので${orders.length}回に分けます</p>${meter(total)}
        <ol class="orders">${rows}</ol>
        <p class="note">合計${yen(total)}。${short.length
          ? '足りない注文は、商品を足すか、ほかの注文と入れ替えて2,100円以上にしてください。'
          : 'どの注文も送料無料の範囲に収まっています。'}</p>`;
    };

    // スマホでは結果が入力欄の下に隠れるので、入力中も判定だけ見えるようにする
    const summary = rk.querySelector('[data-summary]');
    const syncSummary = () => {
      if (!summary) return;
      const verdict = result.querySelector('.verdict');
      summary.hidden = !verdict;
      if (!verdict) return;
      summary.textContent = verdict.textContent;
      summary.dataset.state = ['ok', 'bad'].find((s) => verdict.classList.contains(s)) || 'warn';
    };
    new MutationObserver(syncSummary).observe(result, { childList: true });

    const addRow = () => {
      const li = document.createElement('li');
      li.className = 'row';
      li.innerHTML = '<span class="row-tag"></span><label><span class="visually-hidden">商品の金額（円）</span>'
        + '<input type="number" min="1" step="1" inputmode="numeric" placeholder="例 1290"></label>'
        + '<button type="button" class="row-remove">削除</button>';
      list.append(li);
      li.querySelector('input').focus();
    };

    rk.querySelector('[data-add]').addEventListener('click', addRow);
    rk.querySelector('[data-clear]')?.addEventListener('click', () => {
      list.innerHTML = '';
      addRow();
      update();
    });
    list.addEventListener('click', (event) => {
      const remove = event.target.closest('.row-remove');
      if (remove) { remove.closest('li').remove(); update(); }
    });
    list.addEventListener('input', update);
    update();
  }
})();
