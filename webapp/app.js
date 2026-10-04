/* Мини-приложение «Кабинет»: профиль, магазин и метрики для админов.
   Личность пользователя сервер берёт только из initData — здесь id никуда не шлём. */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp;
  var initData = (tg && tg.initData) || "";

  var state = { me: null, shop: null, metrics: null, tab: "profile", chartMetric: "generations" };
  var timer = null;

  /* ---------- helpers ---------- */

  function $(id) { return document.getElementById(id); }

  function esc(v) {
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function num(n) {
    return String(n === null || n === undefined ? 0 : n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function haptic(kind) {
    try { tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* не везде есть */ }
  }

  var toastTimer = null;
  function toast(text) {
    var box = $("toast");
    box.textContent = text;
    box.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.classList.add("hidden"); }, 2600);
  }

  function closeApp() { if (tg) tg.close(); }

  function gate(emoji, text, btnText, onClick) {
    $("splash").classList.add("hidden");
    $("app").classList.add("hidden");
    $("tabbar").classList.add("hidden");
    $("gate-emoji").textContent = emoji;
    $("gate-text").textContent = text;
    $("gate-btn").textContent = btnText;
    $("gate-btn").onclick = onClick;
    $("gate").classList.remove("hidden");
  }

  function api(path, method, body) {
    var headers = { "Authorization": "tma " + initData };
    if (body) headers["Content-Type"] = "application/json";
    return fetch(path, {
      method: method || "GET",
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store"
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || "server");
          err.code = data.error || "server";
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function plural(n, one, few, many) {
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }

  function waitText(seconds) {
    if (seconds <= 0) return "готов";
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return "через " + h + " ч " + m + " мин";
    if (m > 0) return "через " + m + " " + plural(m, "минуту", "минуты", "минут");
    return "меньше минуты";
  }

  /* ---------- профиль ---------- */

  function renderProfile() {
    var me = state.me;
    var sub = me.sub.active
      ? "активна до " + esc(me.sub.until)
      : "нет — премиум-качество и ежедневные бонусы закрыты";
    var bonusLine = me.bonus.ready
      ? "Бонус готов: +" + me.bonus.amount + " 💎"
      : "Следующий бонус " + waitText(me.bonus.wait_seconds);

    var html = "" +
      '<div class="card balance">' +
        '<div class="balance-value">💎 ' + num(me.crystals) + "</div>" +
        '<div class="balance-label">' + plural(me.crystals, "кристаллик", "кристаллика", "кристалликов") +
        " · 1 фото = " + me.costs.base + " 💎</div>" +
      "</div>" +

      (me.public_name
        ? '<div class="card"><div class="card-title">🎭 В канале</div><div>' + esc(me.public_name) +
          (me.level ? " · " + esc(me.level) : "") + "</div></div>"
        : "") +

      '<div class="card">' +
        '<div class="card-title">⭐ Подписка</div>' +
        "<div>" + sub + "</div>" +
      "</div>" +

      '<div class="card">' +
        '<div class="card-title">🎁 Ежедневный бонус</div>' +
        '<div id="bonus-line" style="margin-bottom:12px">' + esc(bonusLine) + "</div>" +
        '<button class="btn btn-primary" id="bonus-btn"' + (me.bonus.ready ? "" : " disabled") + ">" +
          (me.bonus.ready ? "Забрать +" + me.bonus.amount + " 💎" : "Бонус ещё зреет 🌱") +
        "</button>" +
      "</div>" +

      '<div class="card">' +
        '<div class="card-title">🖼 Качество фото</div>' +
        '<div class="seg" id="quality-seg">' +
          '<button data-tier="base"' + (me.quality.tier === "base" ? ' class="is-active"' : "") + ">Обычное " + me.costs.base + " 💎</button>" +
          '<button data-tier="premium"' + (me.quality.tier === "premium" ? ' class="is-active"' : "") +
            (me.quality.can_premium ? "" : " disabled") + ">Премиум " + me.costs.premium + " 💎</button>" +
        "</div>" +
        (me.quality.can_premium ? "" : '<div class="muted" style="margin-top:10px">Премиум открывается с подпиской — она в «Магазине».</div>') +
      "</div>" +

      '<button class="btn btn-primary" id="create-btn">📸 Начни создание фото</button>';

    $("tab-profile").innerHTML = html;

    $("bonus-btn").onclick = claimBonus;
    $("create-btn").onclick = goCreate;
    Array.prototype.forEach.call($("quality-seg").querySelectorAll("button"), function (b) {
      b.onclick = function () { setQuality(b.getAttribute("data-tier")); };
    });

    startCountdown();
  }

  function startCountdown() {
    clearInterval(timer);
    if (state.me.bonus.ready) return;
    timer = setInterval(function () {
      var me = state.me;
      me.bonus.wait_seconds -= 1;
      if (me.bonus.wait_seconds <= 0) {
        clearInterval(timer);
        me.bonus.ready = true;
        me.bonus.wait_seconds = 0;
        if (state.tab === "profile") renderProfile();
        return;
      }
      var line = $("bonus-line");
      if (line) line.textContent = "Следующий бонус " + waitText(me.bonus.wait_seconds);
    }, 1000);
  }

  function claimBonus() {
    var btn = $("bonus-btn");
    btn.disabled = true;
    api("/api/bonus/claim", "POST").then(function (res) {
      if (res.ready === false) {
        state.me.bonus.ready = false;
        state.me.bonus.wait_seconds = res.wait_seconds;
        renderProfile();
        return;
      }
      haptic("success");
      toast("+" + res.claimed + " 💎 Баланс: " + res.balance);
      return refreshMe();
    }).catch(function () {
      btn.disabled = false;
      toast("Не получилось забрать бонус");
    });
  }

  function setQuality(tier) {
    if (tier === state.me.quality.tier) return;
    api("/api/quality", "POST", { tier: tier }).then(function () {
      state.me.quality.tier = tier;
      haptic("success");
      renderProfile();
    }).catch(function (e) {
      toast(e.code === "premium_locked" ? "Премиум-качество — по подписке ⭐" : "Не получилось переключить");
    });
  }

  function goCreate() {
    if (state.me.bot_username && tg && tg.openTelegramLink) {
      tg.openTelegramLink("https://t.me/" + state.me.bot_username + "?start=create");
      return;
    }
    toast("Нажми «📸 Создать фото» в боте");
    setTimeout(closeApp, 1200);
  }

  function refreshMe() {
    return api("/api/me").then(function (me) {
      state.me = me;
      if (state.tab === "profile") renderProfile();
    });
  }

  /* ---------- магазин ---------- */

  function priceRow(item) {
    var html = "";
    if (item.tribute_url) {
      html += '<button class="btn btn-outline" data-link="' + esc(item.tribute_url) + '">💳 СБП / карта' +
        (item.rub > 0 ? " — " + num(item.rub) + " ₽" : "") + "</button>";
    }
    if (item.stars > 0) {
      html += '<button class="btn btn-primary" data-buy="' + esc(item.code) + '">⭐ Купить за ' + num(item.stars) + " ⭐</button>";
    }
    if (!html) html = '<div class="muted">Способ оплаты пока не настроен.</div>';
    return html;
  }

  function renderShop() {
    var shop = state.shop;
    var html = "<h2>💎 Кристаллики</h2>" +
      '<div class="card"><div class="muted">1 кристаллик = 1 фото со звездой. Премиум-качество — ' +
      shop.cost_premium + " 💎 за фото. Кристаллики не сгорают.</div></div>";

    shop.packs.forEach(function (p) {
      html += '<div class="product">' +
        '<div class="product-head"><span class="product-title">' + num(p.crystals) + " 💎</span></div>" +
        '<div class="product-sub">' + num(p.crystals) + " " +
          plural(p.crystals, "фото", "фото", "фото") + " со звёздами</div>" +
        priceRow(p) +
      "</div>";
    });

    html += "<h2>⭐ Звёздная подписка</h2>" +
      '<div class="card"><ul class="benefits">' +
        "<li><span>🎁</span><span>" + shop.daily_bonus + " кристалликов каждый день</span></li>" +
        "<li><span>🖼</span><span>Премиум-качество: лица как живые</span></li>" +
        "<li><span>🎬</span><span>Все сцены и звёзды без ограничений</span></li>" +
        "<li><span>⚡</span><span>Это до " + shop.daily_bonus + " фото в день и до " + (shop.daily_bonus * 30) + " в месяц</span></li>" +
        "<li><span>🎉</span><span>И подарок сразу при покупке</span></li>" +
      "</ul></div>";

    shop.subs.forEach(function (p) {
      html += '<div class="product">' +
        '<div class="product-head"><span class="product-title">' + esc(p.title) + "</span></div>" +
        '<div class="product-sub">🎉 Сразу в подарок: +' + num(p.gift) + " 💎</div>" +
        priceRow(p) +
      "</div>";
    });

    if (shop.buy_stars_url) {
      html += '<button class="btn btn-outline" data-link="' + esc(shop.buy_stars_url) + '">🇷🇺 Купить звёзды по РУ-карте</button>';
    }

    var root = $("tab-shop");
    root.innerHTML = html;
    Array.prototype.forEach.call(root.querySelectorAll("[data-link]"), function (b) {
      b.onclick = function () { if (tg) tg.openLink(b.getAttribute("data-link")); };
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-buy]"), function (b) {
      b.onclick = function () { buyStars(b.getAttribute("data-buy"), b); };
    });
  }

  function buyStars(code, btn) {
    btn.disabled = true;
    api("/api/buy/stars", "POST", { code: code }).then(function (res) {
      btn.disabled = false;
      if (!tg || !tg.openInvoice) { toast("Оплата звёздами доступна только в Telegram"); return; }
      tg.openInvoice(res.invoice_link, function (status) {
        if (status === "paid") {
          haptic("success");
          toast("Оплата прошла! Обновляю баланс…");
          refreshMe();
        } else if (status === "failed") {
          toast("Оплата не прошла");
        }
      });
    }).catch(function () {
      btn.disabled = false;
      toast("Не получилось открыть оплату");
    });
  }

  /* ---------- метрики ---------- */

  var CHART_METRICS = [
    { key: "new_users", label: "👤 Юзеры" },
    { key: "generations", label: "🖼 Фото" },
    { key: "stars", label: "⭐ Stars" },
    { key: "tribute_rub", label: "₽ Tribute" }
  ];

  function kpi(value, label) {
    return '<div class="kpi"><div class="kpi-value">' + value + '</div><div class="kpi-label">' + label + "</div></div>";
  }

  function revenueRow(title, s) {
    return '<div class="card"><div class="row"><span>' + title + "</span><span><b>" +
      num(s.stars) + " ⭐</b> · <b>" + num(s.tribute_rub) + " ₽</b></span></div>" +
      '<div class="row muted" style="margin-top:6px"><span>Новые / фото</span><span>' +
      num(s.new_users) + " / " + num(gensTotal(s)) + "</span></div>" +
      '<div class="row muted" style="margin-top:4px"><span>Расход Runware</span><span>$' +
      s.cost_usd.toFixed(2) + "</span></div></div>";
  }

  function gensTotal(s) {
    var total = 0;
    for (var k in s.generations) { if (Object.prototype.hasOwnProperty.call(s.generations, k)) total += s.generations[k]; }
    return total;
  }

  function chartHtml(daily, metricKey) {
    var values = daily.map(function (d) { return d[metricKey] || 0; });
    var max = Math.max.apply(null, values.concat([1]));
    var bars = daily.map(function (d, i) {
      var pct = Math.round((values[i] / max) * 100);
      return '<div class="chart-col" title="' + esc(d.date) + ": " + values[i] + '">' +
        '<div class="chart-bar" style="height:' + Math.max(pct, values[i] > 0 ? 3 : 0) + '%"></div></div>';
    }).join("");
    var first = daily.length ? daily[0].date.slice(5) : "";
    var last = daily.length ? daily[daily.length - 1].date.slice(5) : "";
    return '<div class="chart">' + bars + "</div>" +
      '<div class="chart-axis"><span>' + esc(first) + "</span><span>максимум " + num(max) +
      "</span><span>" + esc(last) + "</span></div>";
  }

  function refsTable(refs) {
    if (!refs.length) return '<div class="card muted">Реф-ссылок пока нет.</div>';
    var rows = refs.map(function (r) {
      return "<tr>" +
        "<td><b>" + esc(r.code) + "</b><br><span class=\"muted\">" + esc(r.title) + "</span></td>" +
        "<td>" + num(r.users) + "</td>" +
        "<td>" + num(r.accepted) + "</td>" +
        "<td>" + num(r.paying_users) + "</td>" +
        "<td>" + num(r.stars) + "</td>" +
        "<td>" + num(r.tribute_rub) + "</td>" +
        "<td>" + num(r.generations_done) + "</td>" +
        "<td>" + (r.link ? '<button class="btn btn-outline btn-small" data-copy="' + esc(r.link) + '">Копировать</button>' : "—") + "</td>" +
      "</tr>";
    }).join("");
    return '<div class="table-wrap"><table><thead><tr>' +
      "<th>Код</th><th>👥</th><th>✅</th><th>💳</th><th>⭐</th><th>₽</th><th>🖼</th><th>Ссылка</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function renderMetrics() {
    var m = state.metrics;
    var t = m.totals;
    var html = "<h2>Всего</h2>" +
      '<div class="kpis">' +
        kpi(num(t.users), "Пользователей") +
        kpi(num(t.accepted), "Приняли правила") +
        kpi(num(t.active_subs), "Активных подписок") +
        kpi(num(t.generations_done), "Генераций") +
        kpi(num(t.crystals_in_wallets) + " 💎", "Кристалликов на руках") +
        kpi(num(t.ref_users), "Пришли по реф-ссылкам") +
      "</div>" +

      "<h2>Приход</h2>" +
      revenueRow("Сегодня", m.today) +
      revenueRow("7 дней", m.week) +
      revenueRow("30 дней", m.month) +

      "<h2>По дням</h2>" +
      '<div class="card">' +
        '<div class="seg" id="chart-seg">' +
          CHART_METRICS.map(function (c) {
            return "<button data-metric=\"" + c.key + "\"" +
              (state.chartMetric === c.key ? ' class="is-active"' : "") + ">" + c.label + "</button>";
          }).join("") +
        "</div>" +
        '<div id="chart-box">' + chartHtml(m.daily, state.chartMetric) + "</div>" +
      "</div>" +

      "<h2>Реф-ссылки</h2>" + refsTable(m.referrals);

    var root = $("tab-metrics");
    root.innerHTML = html;

    Array.prototype.forEach.call(root.querySelectorAll("[data-metric]"), function (b) {
      b.onclick = function () {
        state.chartMetric = b.getAttribute("data-metric");
        renderMetrics();
      };
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-copy]"), function (b) {
      b.onclick = function () { copy(b.getAttribute("data-copy")); };
    });
  }

  function copy(text) {
    var done = function () { haptic("success"); toast("Ссылка скопирована"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { legacyCopy(text, done); });
    } else {
      legacyCopy(text, done);
    }
  }

  function legacyCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("Скопируй вручную: " + text); }
    document.body.removeChild(ta);
  }

  /* ---------- вкладки ---------- */

  function showTab(name) {
    state.tab = name;
    ["profile", "shop", "metrics"].forEach(function (n) {
      $("tab-" + n).classList.toggle("hidden", n !== name);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".tabbtn"), function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-tab") === name);
    });
    window.scrollTo(0, 0);

    if (name === "shop" && !state.shop) {
      $("tab-shop").innerHTML = '<div class="card muted">Загружаю…</div>';
      api("/api/shop").then(function (data) { state.shop = data; renderShop(); })
        .catch(function () { $("tab-shop").innerHTML = '<div class="card muted">Магазин не загрузился. Попробуй позже.</div>'; });
    }
    if (name === "metrics" && !state.metrics) {
      $("tab-metrics").innerHTML = '<div class="card muted">Загружаю…</div>';
      api("/api/admin/metrics").then(function (data) { state.metrics = data; renderMetrics(); })
        .catch(function () { $("tab-metrics").innerHTML = '<div class="card muted">Метрики не загрузились.</div>'; });
    }
  }

  /* ---------- старт ---------- */

  function boot() {
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.setHeaderColor("secondary_bg_color"); } catch (e) { /* старые клиенты */ }
    }
    if (!initData) {
      gate("👋", "Открой кабинет из бота — кнопка «Кабинет» рядом с полем ввода.", "Закрыть", closeApp);
      return;
    }
    api("/api/me").then(function (me) {
      state.me = me;
      $("splash").classList.add("hidden");
      $("app").classList.remove("hidden");
      $("tabbar").classList.remove("hidden");
      $("tabbtn-metrics").classList.toggle("hidden", !me.is_admin);
      renderProfile();
      showTab("profile");
    }).catch(function (e) {
      if (e.code === "rules") {
        gate("📋", "Сначала прими правила в боте.", "Вернуться в бота", closeApp);
      } else if (e.code === "blocked") {
        gate("🚫", "Доступ к боту закрыт.", "Закрыть", closeApp);
      } else if (e.status === 401) {
        gate("🔒", "Не удалось подтвердить вход. Открой кабинет заново из бота.", "Закрыть", closeApp);
      } else {
        gate("😔", "Кабинет не загрузился. Попробуй ещё раз.", "Повторить", function () {
          $("gate").classList.add("hidden");
          $("splash").classList.remove("hidden");
          boot();
        });
      }
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".tabbtn"), function (b) {
    b.onclick = function () { showTab(b.getAttribute("data-tab")); };
  });

  boot();
})();
