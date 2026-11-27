"use strict";

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const countryName = (() => {
  let dn = null;
  try { dn = new Intl.DisplayNames(["ru"], { type: "region" }); } catch (_) { /* old browser */ }
  return (code) => (dn && dn.of(code)) || code;
})();

async function api(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = resp.status === 204 ? null : await resp.json().catch(() => null);
  if (!resp.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg.replace(/^Value error, /, "")).join("\n");
    throw new Error(msg || `HTTP ${resp.status}`);
  }
  return data;
}

let toastTimer;
function toast(text, isError = false) {
  const el = $("#toast");
  el.textContent = text;
  el.className = "toast" + (isError ? " err" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), isError ? 6000 : 2500);
}

function mount(tplId) {
  const view = $("#view");
  view.replaceChildren($(tplId).content.cloneNode(true));
  return view;
}

/** Offer autocomplete. onPick(offer) is called with {id, name}. exclude() returns ids to hide. */
function offerPicker(root, onPick, exclude = () => []) {
  const input = $("input", root);
  const list = $(".picker-list", root);
  let timer, rows = [], hl = -1;

  const render = () => {
    list.hidden = false;
    if (!rows.length) { list.innerHTML = '<div class="empty">Ничего не найдено</div>'; return; }
    list.innerHTML = rows.map((o, i) =>
      `<div data-i="${i}" class="${i === hl ? "hl" : ""}"><span class="muted">#${o.id}</span> ${esc(o.name)}</div>`).join("");
  };
  const search = async () => {
    try {
      const skip = new Set(exclude());
      rows = (await api("GET", `/api/offers?limit=50&q=${encodeURIComponent(input.value)}`)).filter((o) => !skip.has(o.id));
      hl = rows.length ? 0 : -1;
      render();
    } catch (e) { toast(e.message, true); }
  };
  const pick = (o) => { list.hidden = true; input.value = ""; onPick(o); };

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 150); });
  input.addEventListener("focus", search);
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      hl = Math.max(0, Math.min(rows.length - 1, hl + (e.key === "ArrowDown" ? 1 : -1)));
      render();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (rows[hl]) pick(rows[hl]);
    } else if (e.key === "Escape") { list.hidden = true; }
  });
  list.addEventListener("mousedown", (e) => {
    const row = e.target.closest("[data-i]");
    if (row) { e.preventDefault(); pick(rows[+row.dataset.i]); }
  });
  input.addEventListener("blur", () => setTimeout(() => (list.hidden = true), 100));
}

// ---------------------------------------------------------- create campaign
async function viewNew() {
  const view = mount("#tpl-new");
  const form = $("#create-form", view);
  const geo = [];
  let offer = null;
  let countries = [];

  const renderGeo = () => {
    $("#geo-chips", view).innerHTML = geo.map((c) =>
      `<span class="chip" title="${esc(countryName(c))}">${c} <button type="button" data-c="${c}">×</button></span>`).join("");
  };
  const addGeo = (raw) => {
    const bad = [];
    raw.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean).forEach((c) => {
      if (countries.length && !countries.includes(c)) bad.push(c);
      else if (!geo.includes(c)) geo.push(c);
    });
    renderGeo();
    if (bad.length) toast(`Неизвестный код страны: ${bad.join(", ")}`, true);
  };

  const geoInput = $("#geo-input", view);
  geoInput.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === ",") && geoInput.value.trim()) {
      e.preventDefault(); addGeo(geoInput.value); geoInput.value = "";
    } else if (e.key === "Backspace" && !geoInput.value && geo.length) {
      geo.pop(); renderGeo();
    }
  });
  geoInput.addEventListener("change", () => { if (geoInput.value.trim()) { addGeo(geoInput.value); geoInput.value = ""; } });
  $("#geo-chips", view).addEventListener("click", (e) => {
    const c = e.target.dataset.c;
    if (c) { geo.splice(geo.indexOf(c), 1); renderGeo(); }
  });

  offerPicker($("#offer-picker", view), (o) => {
    offer = o;
    const el = $("#selected-offer", view);
    el.textContent = `#${o.id} ${o.name}`;
    el.classList.add("set");
  });

  api("GET", "/api/countries").then((list) => {
    countries = list;
    $("#countries", view).innerHTML = list.map((c) => `<option value="${c}">${esc(countryName(c))}</option>`).join("");
  });
  api("GET", "/api/settings").then((s) => {
    const part = (label, x) => `${label}: <b>${esc(x.name ?? "—")}</b> (id ${x.id})${x.found ? "" : ' <span class="total bad">не найден в Keitaro</span>'}`;
    $("#defaults", view).innerHTML = [part("Домен", s.domain), part("Группа", s.group), part("Источник", s.traffic_source)].join(" · ");
    $(".redirect-url", view).textContent = s.geo_redirect_url.replace(/^https?:\/\//, "");
  }).catch((e) => { $("#defaults", view).innerHTML = `<span class="total bad">${esc(e.message)}</span>`; });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (geoInput.value.trim()) { addGeo(geoInput.value); geoInput.value = ""; }
    const err = $("#create-error", view);
    err.hidden = true;
    const name = form.name.value.trim();
    const problems = [];
    if (!name) problems.push("Укажите название");
    if (!geo.length) problems.push("Добавьте хотя бы одну страну");
    if (!offer) problems.push("Выберите оффер из списка");
    if (problems.length) { err.textContent = problems.join("\n"); err.hidden = false; return; }

    form.classList.add("busy");
    try {
      const res = await api("POST", "/api/campaigns", { name, geo, offer_id: offer.id });
      const c = res.campaign;
      const box = $("#create-result", view);
      box.hidden = false;
      box.innerHTML = `
        <h2 class="ok">✓ Кампания создана</h2>
        <p><b>${esc(c.name)}</b> · ID ${c.id}${c.alias ? ` · alias <code>${esc(c.alias)}</code>` : ""}</p>
        <p>Поток 1: ${geo.map((g) => esc(countryName(g))).join(", ")} → google.com<br>
           Поток 2: все остальные → #${offer.id} ${esc(offer.name)} (100%)</p>
        <p><a class="btn primary" href="#/campaign/${c.id}">Открыть в редакторе</a>
           <a class="btn" href="${esc(res.admin_url)}" target="_blank" rel="noopener">Открыть в Keitaro</a></p>`;
      form.reset(); geo.length = 0; renderGeo(); offer = null;
      $("#selected-offer", view).textContent = "Оффер не выбран";
      $("#selected-offer", view).classList.remove("set");
      toast("Кампания создана");
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
    } finally {
      form.classList.remove("busy");
    }
  });
}

// ------------------------------------------------------------ campaign list
async function viewCampaigns() {
  const view = mount("#tpl-campaigns");
  const tbody = $("#campaign-rows", view);
  let rows = [];
  const render = () => {
    const q = $("#campaign-filter", view).value.trim().toLowerCase();
    const shown = rows.filter((c) => !q || `${c.id} ${c.name} ${c.alias}`.toLowerCase().includes(q));
    tbody.innerHTML = shown.length ? shown.map((c) => `
      <tr>
        <td class="num">${c.id}</td>
        <td><a href="#/campaign/${c.id}">${esc(c.name)}</a> ${c.created_here ? '<span class="badge green">создана здесь</span>' : ""}</td>
        <td class="muted">${esc(c.alias)}</td>
        <td><span class="badge ${c.state === "active" ? "green" : ""}">${esc(c.state)}</span></td>
        <td><a class="btn" href="#/campaign/${c.id}">Редактировать</a></td>
      </tr>`).join("") : `<tr><td colspan="5" class="muted">Кампаний нет. <a href="#/new">Создать</a></td></tr>`;
  };
  $("#campaign-filter", view).addEventListener("input", render);
  try {
    rows = await api("GET", "/api/campaigns");
    render();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="error">${esc(e.message)}</div></td></tr>`;
  }
}

// ---------------------------------------------------------- campaign editor
const ACTION_LABEL = {
  create_campaign: "Кампания создана",
  add_offer: "Добавлен оффер",
  remove_offer: "Удалён оффер",
  set_shares: "Изменены доли",
};

async function viewEditor(campaignId) {
  const view = mount("#tpl-editor");
  const streamsBox = $("#ed-streams", view);
  let keitaroUrl = "";
  try { keitaroUrl = (await api("GET", "/api/settings")).keitaro_url.replace(/\/$/, ""); } catch (_) { /* link only */ }

  const load = async () => {
    view.classList.add("busy");
    try {
      const data = await api("GET", `/api/campaigns/${campaignId}`);
      renderCampaign(data);
    } catch (e) {
      streamsBox.innerHTML = `<section class="card"><div class="error">${esc(e.message)}</div></section>`;
    } finally {
      view.classList.remove("busy");
    }
  };

  const renderCampaign = ({ campaign, streams, operations }) => {
    $("#ed-title", view).textContent = campaign.name;
    $("#ed-meta", view).innerHTML = `ID ${campaign.id}${campaign.alias ? ` · alias <code>${esc(campaign.alias)}</code>` : ""} · ротация: ${campaign.type === "weight" ? "по весу" : "по позиции"}`;
    $("#ed-admin", view).href = `${keitaroUrl}/admin/#!/campaign.editor/${campaign.id}`;

    streamsBox.replaceChildren();
    if (!streams.length) streamsBox.innerHTML = '<section class="card muted">В кампании нет потоков</section>';
    streams.forEach((s, i) => streamsBox.appendChild(renderStream(s, i + 1)));

    $("#ed-history", view).innerHTML = operations.length ? operations.map((op) => {
      const d = op.details || {};
      let text = ACTION_LABEL[op.action] || op.action;
      if (d.offer_id) text += ` #${d.offer_id}`;
      if (d.after) text += ` → ${d.after.filter((o) => o.state === "active").map((o) => `#${o.offer_id}: ${o.share}%`).join(", ") || "нет офферов"}`;
      return `<li><time>${new Date(op.created_at).toLocaleString("ru")}</time>${esc(text)}</li>`;
    }).join("") : '<li class="muted">Изменений через обёртку ещё не было</li>';
  };

  const streamTypeLabel = { regular: "обычный", forced: "перехватывающий", default: "замыкающий" };

  const renderStream = (s, n) => {
    const card = document.createElement("section");
    card.className = "card";
    const head = `<div class="stream-head"><h2>${esc(s.name || `Поток ${n}`)}</h2>
      <span class="badge">${esc(streamTypeLabel[s.type] || s.type)}</span>
      <span class="badge ${s.state === "active" ? "green" : ""}">${esc(s.state)}</span>
      <span class="muted">id ${s.id}</span></div>`;

    const filters = (s.filters || []).map((f) => {
      const vals = (f.payload || []).map((v) => (f.name === "country" ? `${esc(countryName(v))} (${esc(v)})` : esc(v))).join(", ");
      return `${f.name === "country" ? "Страны" : esc(f.name)} ${f.mode === "reject" ? "блокировать" : "принимать"}: <b>${vals}</b>`;
    });

    if (s.schema !== "landings") {
      card.innerHTML = head + `<div class="stream-desc">
        ${filters.length ? `<div>Фильтры: ${filters.join("; ")}</div>` : '<div class="muted">Без фильтров</div>'}
        <div>Редирект: <a href="${esc(s.action_payload)}" target="_blank" rel="noopener">${esc(s.action_payload || s.action_type)}</a></div></div>`;
      return card;
    }

    // ---- stream with offers: editable
    let offers = s.offers.map((o) => ({ ...o }));
    const base = `/api/campaigns/${campaignId}/streams/${s.id}/offers`;

    const total = () => offers.filter((o) => o.state === "active").reduce((a, o) => a + (+o.share || 0), 0);
    const dirty = () => JSON.stringify(offers.map((o) => [o.offer_id, +o.share, o.state])) !==
                        JSON.stringify(s.offers.map((o) => [o.offer_id, o.share, o.state]));

    // after every change re-read the whole campaign from Keitaro: the UI shows what is really stored
    const run = async (fn, okText) => {
      card.classList.add("busy");
      try { await fn(); toast(okText); await load(); }
      catch (e) { toast(e.message, true); card.classList.remove("busy"); }
    };

    const summary = () => {
      const t = total();
      const bad = offers.some((o) => o.state === "active") && t !== 100;
      const totalEl = $(".total", card);
      totalEl.textContent = `${t} %`;
      totalEl.classList.toggle("bad", bad);
      const warn = $(".warning", card);
      warn.hidden = !bad;
      warn.textContent = `Сумма долей включённых офферов — ${t}%, а не 100%.`;
      $("[data-save]", card).disabled = !dirty();
      $("[data-even]", card).disabled = !offers.some((o) => o.state === "active");
    };

    const draw = () => {
      card.innerHTML = head + `
        ${filters.length ? `<div class="stream-desc">Фильтры: ${filters.join("; ")}</div>` : ""}
        <table class="grid">
          <thead><tr><th class="num">ID</th><th>Оффер</th><th style="width:110px">Доля</th><th style="width:140px"></th><th style="width:70px">Вкл.</th><th style="width:40px"></th></tr></thead>
          <tbody>${offers.length ? offers.map((o, i) => `
            <tr class="${o.state === "active" ? "" : "disabled"}">
              <td class="num">${o.offer_id}</td>
              <td>${esc(o.name)}</td>
              <td><input class="share-input" type="number" min="0" max="100" step="1" value="${o.share}" data-i="${i}"> %</td>
              <td><div class="share-bar"><i style="width:${Math.min(100, +o.share || 0)}%"></i></div></td>
              <td><input type="checkbox" data-state="${i}" ${o.state === "active" ? "checked" : ""} style="width:auto"></td>
              <td><button class="icon-btn" title="Удалить оффер" data-del="${o.offer_id}">×</button></td>
            </tr>`).join("") : '<tr><td colspan="6" class="muted">В потоке нет офферов — добавьте первый</td></tr>'}
          </tbody>
          <tfoot><tr><td></td><td class="muted">Сумма долей включённых офферов</td>
            <td class="total"></td><td colspan="3"></td></tr></tfoot>
        </table>
        <div class="warning" hidden></div>
        <div class="stream-footer">
          <div class="picker"><input placeholder="Добавить оффер: начните вводить имя или ID"><div class="picker-list" hidden></div></div>
          <button class="btn" data-even>Поровну</button>
          <button class="btn primary" data-save>Сохранить доли</button>
        </div>`;

      offerPicker($(".picker", card), (o) => {
        if (dirty() && !confirm("Несохранённые изменения долей будут сброшены. Продолжить?")) return;
        run(() => api("POST", base, { offer_id: o.id }), `Оффер #${o.id} добавлен, доли пересчитаны`);
      }, () => offers.map((x) => x.offer_id));
      summary();
    };

    card.addEventListener("input", (e) => {
      if (e.target.dataset.i === undefined) return;
      const share = Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0));
      offers[+e.target.dataset.i].share = share;
      e.target.closest("tr").querySelector(".share-bar i").style.width = `${share}%`;
      summary();
    });
    card.addEventListener("change", (e) => {
      if (e.target.dataset.state === undefined) return;
      offers[+e.target.dataset.state].state = e.target.checked ? "active" : "disabled";
      e.target.closest("tr").classList.toggle("disabled", !e.target.checked);
      summary();
    });
    card.addEventListener("click", async (e) => {
      const del = e.target.closest("[data-del]");
      if (del) {
        const id = +del.dataset.del;
        const o = offers.find((x) => x.offer_id === id);
        if (!confirm(`Удалить оффер #${id} ${o ? o.name : ""} из потока? Доли остальных будут пересчитаны.`)) return;
        run(() => api("DELETE", `${base}/${id}`), `Оффер #${id} удалён, доли пересчитаны`);
      } else if (e.target.closest("[data-even]")) {
        const active = offers.filter((o) => o.state === "active");
        const baseShare = Math.floor(100 / active.length);
        let rest = 100 - baseShare * active.length;
        active.forEach((o) => { o.share = baseShare + (rest-- > 0 ? 1 : 0); });
        draw();
      } else if (e.target.closest("[data-save]")) {
        run(() => api("PUT", base, { offers: offers.map(({ offer_id, share, state }) => ({ offer_id, share: +share, state })) }), "Доли сохранены");
      }
    });

    draw();
    return card;
  };

  $("#ed-reload", view).addEventListener("click", load);
  await load();
}

// ------------------------------------------------------------------ router
function route() {
  const hash = location.hash.replace(/^#\/?/, "");
  const [page, id] = hash.split("/");
  document.querySelectorAll("[data-nav]").forEach((a) =>
    a.classList.toggle("active", a.dataset.nav === (page === "campaign" ? "campaigns" : page || "new")));
  if (page === "campaigns") return viewCampaigns();
  if (page === "campaign" && /^\d+$/.test(id)) return viewEditor(+id);
  return viewNew();
}
window.addEventListener("hashchange", route);
route();
