(() => {
  const HEADERS = { 'Content-Type': 'application/json', 'X-Kaimawari': '1' };
  const DONE = new Set(['approved', 'rejected', 'publishing', 'posted', 'failed', 'expired']);
  const UNDOABLE = new Set(['approved', 'rejected', 'failed', 'expired']);
  const PILL = { pending: '承認待ち', warn: '要確認', block: '要修正', approved: '予約済み', rejected: '却下', publishing: '投稿中', posted: '投稿済み', failed: '失敗', expired: '期限切れ' };
  const TICK = { pending: 'pending', warn: 'pending', block: 'block', approved: 'approved', publishing: 'approved', posted: 'posted', rejected: 'rejected', failed: 'block', expired: 'rejected' };
  const SEAL = { approved: ['承認<br>済', ''], posted: ['投稿<br>済', ' is-posted'], rejected: ['却下', ' is-muted'], expired: ['期限<br>切れ', ' is-muted'] };
  const MARK = { ok: '✓', warn: '!', block: '✕' };

  const state = { posts: [], events: [], threadsReady: false, demo: false, current: null };
  let saveTimer = null;
  let saveSeq = 0;
  let toastTimer = null;

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const dtf = new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const parts = (value) => Object.fromEntries(dtf.formatToParts(new Date(value)).map((p) => [p.type, p.value]));
  const fmt = (value) => { const p = parts(value); return `${p.month}/${p.day}（${p.weekday}）${p.hour}:${p.minute}`; };
  const hm = (value) => { const p = parts(value); return `${p.hour}:${p.minute}`; };
  const md = (value) => { const p = parts(value); return `${p.month}/${p.day}`; };
  const find = (id) => state.posts.find((p) => p.id === id);
  const currentPost = () => find(state.current);
  const statusOf = (p) => (DONE.has(p.state) ? p.state : p.blocking ? 'block' : p.checks.some((c) => c.status === 'warn') ? 'warn' : 'pending');
  const linkTitle = (url) => (url && url.includes('rakuyoko') ? 'ラクヨコ送料無料ライン計算機｜買いまわり帳' : '買いまわり帳｜今日の10ショッププラン');
  const hostOf = (url) => { try { const u = new URL(url); return u.host + u.pathname.replace(/\/$/, ''); } catch { return url; } };

  const toast = (message) => {
    const el = $('[data-toast]');
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2800);
  };

  async function api(path, body) {
    const init = body === undefined ? { headers: HEADERS } : { method: 'POST', headers: HEADERS, body: JSON.stringify(body) };
    const res = await fetch(path, init);
    let data = {};
    try { data = await res.json(); } catch { /* 本文なし */ }
    if (!res.ok) throw new Error(data.error || `サーバーエラー（${res.status}）`);
    return data;
  }

  async function load() {
    try {
      const data = await api('/api/posts');
      const dirty = currentPost()?.dirty ? currentPost() : null;
      state.posts = data.posts.map((p) => (dirty && p.id === dirty.id ? { ...p, text: dirty.text, dirty: true } : p));
      state.events = data.events;
      state.threadsReady = data.threads_ready;
      state.demo = data.demo;
      if (!find(state.current)) {
        const open = state.posts.find((p) => p.state === 'pending') || state.posts[state.posts.length - 1];
        state.current = open ? open.id : null;
      }
      renderAll();
    } catch (err) {
      toast(err.message);
    }
  }

  const renderHeader = () => {
    $('[data-demo]').hidden = !state.demo;
    $('[data-connection]').innerHTML = state.demo
      ? '<span class="conn warn">デモ</span>デモ用のキューです。承認しても投稿はされません。'
      : state.threadsReady
        ? '<span class="conn ok">Threads 接続済み</span>承認した投稿だけ、予約時刻に自動で公開します。'
        : '<span class="conn warn">Threads 未接続</span>承認はできますが、.env にトークンを入れるまで投稿はされません。';
    const n = { pending: 0, block: 0, approved: 0, posted: 0 };
    state.posts.forEach((p) => {
      const s = statusOf(p);
      if (s === 'pending' || s === 'warn') n.pending += 1;
      else if (s === 'block') n.block += 1;
      else if (s === 'approved' || s === 'publishing') n.approved += 1;
      else if (s === 'posted') n.posted += 1;
    });
    Object.entries(n).forEach(([key, value]) => { $(`[data-count="${key}"]`).textContent = value; });
  };

  const renderTimeline = () => {
    const wrap = $('[data-timeline]');
    if (!state.posts.length) { wrap.hidden = true; return; }
    wrap.hidden = false;
    const HOUR = 3600e3;
    const DAY = 24 * HOUR;
    const times = state.posts.map((p) => new Date(p.at).getTime());
    const start = Math.min(...times) - 6 * HOUR;
    const end = Math.max(...times) + 6 * HOUR;
    const pos = (t) => ((t - start) / (end - start)) * 100;
    const pieces = ['<span class="axis"></span>'];

    const ev = state.events.find((e) => new Date(e.end).getTime() > start && new Date(e.start).getTime() < end);
    $('[data-event-name]').textContent = ev ? ev.name : '投稿予定';
    if (ev) {
      const a = Math.max(start, new Date(ev.start).getTime());
      const b = Math.min(end, new Date(ev.end).getTime());
      pieces.push(`<span class="period" style="left:${pos(a)}%;width:${pos(b) - pos(a)}%"></span>`);
      pieces.push(`<span class="period-label" style="left:${pos(a)}%">マラソン期間 ${fmt(ev.start)} → ${fmt(ev.end)}</span>`);
    }
    // 日本時間の0時ごとに日付を置く
    const JST = 9 * HOUR;
    for (let t = Math.ceil((start + JST) / DAY) * DAY - JST; t < end; t += DAY) {
      pieces.push(`<span class="day" style="left:${pos(t)}%">${md(t)}</span>`);
    }
    state.posts.forEach((p) => {
      const s = statusOf(p);
      pieces.push(`<button type="button" class="tick" style="left:${pos(new Date(p.at).getTime())}%" data-id="${esc(p.id)}" data-state="${TICK[s]}" aria-current="${p.id === state.current}" aria-label="${esc(`${fmt(p.at)} ${p.kind} ${PILL[s]}`)}"><span class="tick-time">${hm(p.at)}</span><span class="tick-dot"></span></button>`);
    });
    $('[data-track]').innerHTML = pieces.join('');
  };

  const renderQueue = () => {
    $('[data-queue]').innerHTML = state.posts.map((p) => {
      const s = statusOf(p);
      return `<li><button type="button" class="q-item" data-id="${esc(p.id)}" aria-current="${p.id === state.current}">
        <span class="q-time">${fmt(p.at)}</span><span class="q-kind">${esc(p.kind)}</span>
        <span class="q-text">${esc(p.text.split('\n')[0])}</span><span class="pill ${s}">${PILL[s]}</span></button></li>`;
    }).join('');
  };

  const renderPreview = () => {
    const el = $('[data-preview]');
    const post = currentPost();
    if (!post) {
      el.innerHTML = `<div class="empty"><h2>承認待ちの投稿はありません</h2>
        <p>下書きは毎朝 run_daily.bat が、開催予定と今日のプランから作ります。今すぐ作るなら <code>python queue_cli.py draft</code> を実行してください。</p></div>`;
      return;
    }
    const editable = post.state === 'pending';
    const [sealText, sealClass] = SEAL[post.state] || [];
    const seal = sealText ? `<div class="seal${sealClass}" aria-label="${PILL[post.state]}">${sealText}<small>${hm(post.at)}</small></div>` : '';
    const alert = post.error ? `<p class="alert" role="alert">${esc(post.error)}</p>` : '';
    const link = post.link_url
      ? `<div class="linkcard"><span class="linkcard-host">${esc(hostOf(post.link_url))}</span><span class="linkcard-title">${esc(linkTitle(post.link_url))}</span></div>`
      : '';
    el.innerHTML = `${seal}
      <div class="preview-meta"><span>予約 <b class="mono">${fmt(post.at)}</b></span><span>生成元 <b>${esc(post.source)}</b></span></div>
      ${alert}
      <article class="post">
        <div class="avatar" aria-hidden="true">買</div>
        <div>
          <div class="post-head"><span class="post-name">買いまわり帳</span><span class="post-handle">Threads 投稿プレビュー</span></div>
          <label class="visually-hidden" for="post-text">投稿本文</label>
          <textarea id="post-text" class="post-text" data-text rows="${post.text.split('\n').length + 1}"${editable ? '' : ' readonly'}>${esc(post.text)}</textarea>
          ${link}
          <div class="post-foot"><span>${editable ? 'クリックして編集できます（自動保存）' : '確定済みの本文'}</span><span class="mono" data-len>${[...post.text].length} / 500</span></div>
        </div>
      </article>`;
  };

  const renderChecks = () => {
    const el = $('[data-checks]');
    const post = currentPost();
    if (!post) { el.innerHTML = '<h2>公開前チェック</h2><p class="hint">投稿を選ぶと表示されます。</p>'; return; }
    const editable = post.state === 'pending';
    const items = post.checks.map((c) => `<li class="check"><span class="mark ${c.status}" aria-hidden="true">${MARK[c.status]}</span>
      <div><div class="check-k">${esc(c.label)}</div><div class="check-msg">${esc(c.message)}</div>
      ${c.fix === 'pr' && editable ? '<button type="button" class="fix" data-fix="pr">末尾に #PR を追加</button>' : ''}</div></li>`).join('');

    let actions = '';
    if (editable) {
      const hint = post.blocking
        ? '✕ の項目を直すと承認できます。'
        : state.threadsReady ? '承認すると、予約時刻に Threads へ投稿します。' : 'Threads 未接続のため、承認しても投稿はされません。';
      actions = `<div class="actions">
        <button type="button" class="btn btn-primary" data-act="approve"${post.blocking ? ' disabled' : ''}>承認して ${fmt(post.at)} に予約</button>
        <button type="button" class="btn" data-act="reject">却下</button></div><p class="hint">${hint}</p>`;
    } else if (UNDOABLE.has(post.state)) {
      actions = '<div class="actions one"><button type="button" class="btn" data-act="undo">承認待ちに戻す</button></div>';
    } else if (post.state === 'posted') {
      actions = `<p class="hint">Threads 投稿ID <span class="mono">${esc(post.post_id)}</span></p>`;
    } else if (post.state === 'publishing') {
      actions = '<p class="hint">投稿処理中です。</p>';
    }
    el.innerHTML = `<h2>公開前チェック</h2><ul class="check-list">${items}</ul>${actions}`;
  };

  const renderSide = () => { renderHeader(); renderTimeline(); renderQueue(); renderChecks(); };
  const renderAll = () => { renderSide(); renderPreview(); };

  const scheduleSave = () => { clearTimeout(saveTimer); saveTimer = setTimeout(flushSave, 500); };

  async function flushSave() {
    clearTimeout(saveTimer);
    const post = currentPost();
    if (!post || post.state !== 'pending' || !post.dirty) return;
    const seq = ++saveSeq;
    post.dirty = false;
    try {
      const data = await api(`/api/posts/${encodeURIComponent(post.id)}/text`, { text: post.text });
      if (seq !== saveSeq) return;
      Object.assign(post, data.post, { text: post.text });
      renderSide();
    } catch (err) {
      post.dirty = true;
      toast(err.message);
    }
  }

  async function select(id) {
    if (id === state.current) return;
    await flushSave();
    state.current = id;
    renderAll();
  }

  const nextOpen = () => {
    const idx = state.posts.findIndex((p) => p.id === state.current);
    return [...state.posts.slice(idx + 1), ...state.posts.slice(0, idx)].find((p) => p.state === 'pending');
  };

  async function act(kind) {
    const post = currentPost();
    if (!post) return;
    await flushSave();
    const allowed = { approve: post.state === 'pending' && !post.blocking, reject: post.state === 'pending', undo: UNDOABLE.has(post.state) }[kind];
    if (!allowed) return;
    try {
      const data = await api(`/api/posts/${encodeURIComponent(post.id)}/${kind}`, {});
      Object.assign(post, data.post);
      const approved = state.threadsReady ? `承認しました。${fmt(post.at)} に投稿します` : '承認しました（Threads 未接続のため、まだ投稿はされません）';
      toast({ approve: approved, reject: '却下しました。この投稿は公開されません', undo: '承認待ちに戻しました' }[kind]);
      renderAll();
      if (kind !== 'undo') {
        const next = nextOpen();
        if (next) setTimeout(() => select(next.id), 700);
      }
    } catch (err) {
      toast(err.message);
      load();
    }
  }

  document.addEventListener('click', async (event) => {
    const pick = event.target.closest('[data-id]');
    if (pick) { select(pick.dataset.id); return; }
    const button = event.target.closest('[data-act]');
    if (button) { act(button.dataset.act); return; }
    if (event.target.closest('[data-fix="pr"]')) {
      const post = currentPost();
      post.text = `${post.text.replace(/\s+$/, '')}\n#PR`;
      post.dirty = true;
      renderPreview();
      await flushSave();
      toast('#PR を追加しました');
    }
  });

  document.addEventListener('input', (event) => {
    if (!event.target.matches('[data-text]')) return;
    const post = currentPost();
    if (!post || post.state !== 'pending') return;
    post.text = event.target.value;
    post.dirty = true;
    $('[data-len]').textContent = `${[...post.text].length} / 500`;
    scheduleSave();
  });

  document.addEventListener('keydown', (event) => {
    if (event.target.matches('textarea, input') || event.metaKey || event.ctrlKey || event.altKey) return;
    const idx = state.posts.findIndex((p) => p.id === state.current);
    if (idx < 0) return;
    const key = event.key.toLowerCase();
    if (key === 'j') select(state.posts[Math.min(state.posts.length - 1, idx + 1)].id);
    else if (key === 'k') select(state.posts[Math.max(0, idx - 1)].id);
    else if (key === 'a') act('approve');
    else if (key === 'r') act('reject');
  });

  // 予約投稿の結果を拾うため、編集中でなければ1分ごとに読み直す
  setInterval(() => {
    if (document.hidden || currentPost()?.dirty || document.activeElement?.matches('textarea')) return;
    load();
  }, 60000);

  load();
})();
