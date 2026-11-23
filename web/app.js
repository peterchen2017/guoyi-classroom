/* 乐昌国艺书院机房课堂管理控制台
 * 写法兼容 Windows 7 上最后一版 Chrome（109）及同期 Edge，不使用可选链等过新语法。
 * 不支持 Internet Explorer。
 */
(function () {
  "use strict";

  var token = "";
  var state = null;
  var ws = null;
  var focusId = "";
  var focusTimer = null;
  var currentTab = "wall";

  function $(id) {
    return document.getElementById(id);
  }

  function on(el, ev, fn) {
    if (el) el.addEventListener(ev, fn);
  }

  function show(el, yes) {
    if (!el) return;
    if (yes) el.removeAttribute("hidden");
    else el.setAttribute("hidden", "hidden");
  }

  function api(path, opts) {
    opts = opts || {};
    var headers = opts.headers ? opts.headers : {};
    if (token) headers["Authorization"] = "Bearer " + token;
    if (opts.json) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
    }
    return fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body
    }).then(function (res) {
      if (res.status === 401) {
        logout();
        throw new Error("登录已过期，请重新登录");
      }
      var ctype = res.headers.get("content-type") || "";
      if (ctype.indexOf("application/json") >= 0) {
        return res.json().then(function (data) {
          if (!res.ok) {
            throw new Error((data && data.detail) ? String(data.detail) : "请求失败");
          }
          return data;
        });
      }
      if (!res.ok) throw new Error("请求失败");
      return res;
    });
  }

  function logout() {
    token = "";
    try { sessionStorage.removeItem("classroom_token"); } catch (e) {}
    if (ws) {
      try { ws.close(); } catch (e2) {}
      ws = null;
    }
    show($("login-page"), true);
    show($("app-page"), false);
  }

  function statusLabel(s) {
    if (!s.approved && s.online) return "待批准";
    if (s.online && s.locked) return "在线 · 已锁屏";
    if (s.online) return "在线";
    if (s.approved) return "离线";
    return "未加入";
  }

  function render() {
    if (!state) return;
    $("class-code").textContent = state.class_code || "------";
    var pill = $("class-pill");
    pill.textContent = state.class_active ? (state.broadcast_active ? "上课中 · 正在广播" : "上课中") : "未上课";
    if (state.class_active) pill.classList.add("on");
    else pill.classList.remove("on");

    var btn = $("btn-class");
    btn.textContent = state.class_active ? "下课" : "开始上课";
    if (state.class_active) {
      btn.classList.remove("primary");
      btn.classList.add("danger");
    } else {
      btn.classList.add("primary");
      btn.classList.remove("danger");
    }
    $("btn-broadcast").textContent = state.broadcast_active ? "停止广播" : "广播教师屏幕";
    var shrink = $("chk-shrink-screen");
    if (shrink) {
      shrink.checked = !!state.broadcast_shrink;
      if (state.broadcast_shrink) $("shrink-opt").classList.add("on");
      else $("shrink-opt").classList.remove("on");
    }
    var wr = state.web_restrict || {};
    var btnR = $("btn-restrict");
    if (btnR) {
      btnR.textContent = wr.enabled ? "关闭网页/下载限制" : "限制网页游戏和下载";
      if (wr.enabled) btnR.classList.add("restrict-on");
      else btnR.classList.remove("restrict-on");
    }
    var desk = state.desktop || {};
    var btnD = $("btn-desktop");
    if (btnD) {
      btnD.textContent = desk.locked ? "更换默认桌面（已锁定）" : "设置默认桌面";
      if (desk.locked) btnD.classList.add("desktop-on");
      else btnD.classList.remove("desktop-on");
    }
    var btnU = $("btn-desktop-unlock");
    if (btnU) {
      btnU.disabled = !desk.locked;
    }

    var students = state.students || [];
    var online = 0, pending = 0;
    var i;
    for (i = 0; i < students.length; i++) {
      if (students[i].online) online += 1;
      if (!students[i].approved && students[i].online) pending += 1;
    }
    $("student-summary").textContent = "在线 " + online + (pending ? " · 待批准 " + pending : "") + " · 共 " + students.length;

    var list = $("student-list");
    list.innerHTML = "";
    for (i = 0; i < students.length; i++) {
      list.appendChild(renderStudentItem(students[i]));
    }

    var wall = $("screen-wall");
    wall.innerHTML = "";
    var shown = 0;
    for (i = 0; i < students.length; i++) {
      var s = students[i];
      if (s.approved && s.online && state.class_active && s.thumb_at) {
        wall.appendChild(renderTile(s));
        shown += 1;
      }
    }
    show($("wall-empty"), shown === 0);
  }

  function renderStudentItem(s) {
    var li = document.createElement("li");
    if (!s.approved && s.online) li.className = "pending";
    else if (!s.online) li.className = "offline";

    var dot = document.createElement("span");
    dot.className = "dot " + (!s.approved && s.online ? "pending" : (s.locked ? "locked" : (s.online ? "on" : "off")));

    var name = document.createElement("div");
    name.className = "stu-name";
    name.appendChild(dot);
    name.appendChild(document.createTextNode(s.name || "学生"));

    var meta = document.createElement("div");
    meta.className = "stu-meta";
    meta.textContent = statusLabel(s) + (s.hostname ? " · " + s.hostname : "") + (s.ip ? " · " + s.ip : "");

    var actions = document.createElement("div");
    actions.className = "stu-actions";
    if (!s.approved) {
      actions.appendChild(btn("允许加入", "success", function () { approve(s.device_id); }));
      if (s.online) actions.appendChild(btn("拒绝", "", function () { revoke(s.device_id); }));
    } else {
      actions.appendChild(btn("查看", "", function () { openFocus(s.device_id); }));
      if (s.online) {
        if (s.locked) actions.appendChild(btn("解锁", "", function () { lockOne(s.device_id, false); }));
        else actions.appendChild(btn("锁屏", "danger", function () { lockOne(s.device_id, true); }));
      }
      actions.appendChild(btn("移出", "", function () { revoke(s.device_id); }));
    }

    li.appendChild(name);
    li.appendChild(meta);
    li.appendChild(actions);
    return li;
  }

  function btn(text, cls, handler) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn" + (cls ? " " + cls : "");
    b.textContent = text;
    on(b, "click", handler);
    return b;
  }

  function renderTile(s) {
    var div = document.createElement("div");
    div.className = "tile";
    div.setAttribute("data-id", s.device_id);
    var img = document.createElement("img");
    img.alt = s.name;
    img.src = "/api/thumbs/" + encodeURIComponent(s.device_id) + "?t=" + encodeURIComponent(s.thumb_at) + "&token_in_header=1";
    setImgAuth(img, "/api/thumbs/" + encodeURIComponent(s.device_id) + "?t=" + s.thumb_at);
    var cap = document.createElement("div");
    cap.className = "cap";
    cap.textContent = s.name + (s.locked ? " · 已锁屏" : "");
    div.appendChild(img);
    div.appendChild(cap);
    on(div, "click", function () { openFocus(s.device_id); });
    return div;
  }

  function setImgAuth(img, path) {
    // 用 fetch + blob，以便带上登录令牌（img.src 无法加 Authorization）。
    fetch(path, { headers: { "Authorization": "Bearer " + token } })
      .then(function (res) { return res.ok ? res.blob() : null; })
      .then(function (blob) {
        if (!blob) return;
        var url = URL.createObjectURL(blob);
        img.onload = function () { URL.revokeObjectURL(url); };
        img.src = url;
      })
      .catch(function () {});
  }

  function findStudent(id) {
    var students = (state && state.students) ? state.students : [];
    var i;
    for (i = 0; i < students.length; i++) {
      if (students[i].device_id === id) return students[i];
    }
    return null;
  }

  function openFocus(id) {
    focusId = id;
    api("/api/focus", { method: "POST", json: { student_id: id } }).catch(function () {});
    var s = findStudent(id) || { name: "学生", device_id: id, locked: false };
    var card = $("modal-card");
    card.innerHTML = "";
    var h = document.createElement("h3");
    h.textContent = s.name;
    var img = document.createElement("img");
    img.className = "focus-img";
    img.alt = s.name;
    var actions = document.createElement("div");
    actions.className = "modal-actions";
    actions.appendChild(btn(s.locked ? "解锁" : "锁屏", s.locked ? "" : "danger", function () {
      lockOne(id, !s.locked).then(function () {
        var ns = findStudent(id);
        closeModal();
        if (ns) openFocus(id);
      });
    }));
    var spacer = document.createElement("span");
    spacer.className = "spacer";
    actions.appendChild(spacer);
    actions.appendChild(btn("关闭", "", closeModal));
    card.appendChild(h);
    card.appendChild(img);
    card.appendChild(actions);
    show($("modal"), true);
    refreshFocus(img);
    if (focusTimer) clearInterval(focusTimer);
    focusTimer = setInterval(function () { refreshFocus(img); }, 400);
  }

  function refreshFocus(img) {
    if (!focusId) return;
    setImgAuth(img, "/api/focus/" + encodeURIComponent(focusId) + "?t=" + Date.now());
  }

  function closeModal() {
    show($("modal"), false);
    focusId = "";
    if (focusTimer) {
      clearInterval(focusTimer);
      focusTimer = null;
    }
    api("/api/focus", { method: "POST", json: { student_id: null } }).catch(function () {});
  }

  function approve(id) {
    return api("/api/students/" + encodeURIComponent(id) + "/approve", { method: "POST", json: {} });
  }
  function revoke(id) {
    return api("/api/students/" + encodeURIComponent(id) + "/revoke", { method: "POST", json: {} });
  }
  function lockOne(id, yes) {
    var path = yes ? "/api/lock" : "/api/unlock";
    return api(path, { method: "POST", json: { student_ids: [id] } });
  }

  function promptText(title, label, kind) {
    var card = $("modal-card");
    card.innerHTML = "<h3>" + title + "</h3>";
    var lab = document.createElement("label");
    lab.textContent = label;
    var ta = document.createElement("textarea");
    ta.rows = 5;
    lab.appendChild(ta);
    var actions = document.createElement("div");
    actions.className = "modal-actions";
    actions.appendChild(btn("发送", "primary", function () {
      var text = ta.value.replace(/^\s+|\s+$/g, "");
      if (!text) return;
      api("/api/announce", { method: "POST", json: { text: text, kind: kind } })
        .then(closeModal)
        .catch(function (err) { window.alert(err.message); });
    }));
    actions.appendChild(btn("取消", "", closeModal));
    card.appendChild(lab);
    card.appendChild(actions);
    show($("modal"), true);
    ta.focus();
  }

  function promptPassword() {
    var card = $("modal-card");
    card.innerHTML = "<h3>修改教师密码</h3>";
    function field(id, label, typ) {
      var lab = document.createElement("label");
      lab.textContent = label;
      var inp = document.createElement("input");
      inp.id = id;
      inp.type = typ;
      lab.appendChild(inp);
      return lab;
    }
    card.appendChild(field("pw-old", "原密码", "password"));
    card.appendChild(field("pw-new", "新密码（至少 8 位）", "password"));
    var actions = document.createElement("div");
    actions.className = "modal-actions";
    actions.appendChild(btn("保存", "primary", function () {
      api("/api/password", {
        method: "POST",
        json: { old_password: $("pw-old").value, new_password: $("pw-new").value }
      }).then(function () {
        window.alert("密码已更新");
        closeModal();
      }).catch(function (err) { window.alert(err.message); });
    }));
    actions.appendChild(btn("取消", "", closeModal));
    card.appendChild(actions);
    show($("modal"), true);
  }

  function openDesktopModal() {
    var desk = (state && state.desktop) ? state.desktop : {};
    var card = $("modal-card");
    card.innerHTML = "";
    var h = document.createElement("h3");
    h.textContent = "设置机房默认桌面";
    card.appendChild(h);
    var p = document.createElement("p");
    p.style.fontSize = "13px";
    p.style.color = "#5a6a80";
    p.textContent = "上传一张 jpg / png / bmp 壁纸，下发到已加入的学生机并设为桌面。锁定后学生不能通过系统个性化或桌面右键更改壁纸。下课或学生机重启后仍然保持，直到老师点「解除桌面锁定」。";
    card.appendChild(p);
    if (desk.has_wallpaper) {
      var prev = document.createElement("img");
      prev.alt = desk.filename || "当前默认桌面";
      prev.className = "desktop-preview";
      card.appendChild(prev);
      setImgAuth(prev, "/api/desktop/image");
      var cur = document.createElement("p");
      cur.style.fontSize = "13px";
      cur.textContent = "当前：" + (desk.filename || "已设置") + (desk.locked ? "（已锁定）" : "");
      card.appendChild(cur);
    }
    var lab = document.createElement("label");
    lab.textContent = "选择壁纸图片";
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".jpg,.jpeg,.png,.bmp,image/jpeg,image/png,image/bmp";
    lab.appendChild(inp);
    card.appendChild(lab);
    var lockLab = document.createElement("label");
    lockLab.className = "chk-row";
    var chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = true;
    var sp = document.createElement("span");
    sp.textContent = "锁定桌面（学生不能更改壁纸）";
    lockLab.appendChild(chk);
    lockLab.appendChild(sp);
    card.appendChild(lockLab);
    var actions = document.createElement("div");
    actions.className = "modal-actions";
    actions.appendChild(btn("下发并应用", "primary", function () {
      if (!inp.files || !inp.files[0]) {
        window.alert("请先选择一张壁纸图片（jpg / png / bmp）");
        return;
      }
      var fd = new FormData();
      fd.append("file", inp.files[0]);
      api("/api/desktop/wallpaper?lock=" + (chk.checked ? "1" : "0"), { method: "POST", body: fd })
        .then(function (st) {
          state = st;
          render();
          closeModal();
        })
        .catch(function (err) { window.alert(err.message); });
    }));
    if (desk.locked) {
      actions.appendChild(btn("解除锁定", "", function () {
        unlockDesktop().then(function () { closeModal(); });
      }));
    }
    actions.appendChild(btn("取消", "", closeModal));
    card.appendChild(actions);
    show($("modal"), true);
  }

  function unlockDesktop() {
    if (!window.confirm("解除后将恢复学生机锁定前保存的壁纸。确定解除？")) {
      return Promise.resolve();
    }
    return api("/api/desktop/unlock", { method: "POST", json: {} })
      .then(function (st) {
        state = st;
        render();
      })
      .catch(function (err) { window.alert(err.message); });
  }

  function openRestrictLists() {
    var wr = (state && state.web_restrict) ? state.web_restrict : {};
    var card = $("modal-card");
    card.innerHTML = "<h3>网页游戏 / 下载限制名单</h3><p style=\"font-size:13px;color:#5a6a80\">每行一个域名。按主机名拦截，不解密 HTTPS。教师机地址和课堂下发文件始终放行。可添加教学网站到白名单。</p>";
    function area(id, label, value) {
      var lab = document.createElement("label");
      lab.appendChild(document.createTextNode(label));
      var ta = document.createElement("textarea");
      ta.id = id;
      ta.value = (value || []).join("\n");
      lab.appendChild(ta);
      return lab;
    }
    var grid = document.createElement("div");
    grid.className = "list-grid";
    grid.appendChild(area("list-game", "网页游戏域名", wr.game_domains));
    grid.appendChild(area("list-down", "下载站 / 网盘域名", wr.download_domains));
    grid.appendChild(area("list-white", "白名单（教学网站）", wr.whitelist_domains));
    grid.appendChild(area("list-ext", "拦截的下载扩展名", wr.extensions));
    card.appendChild(grid);
    var actions = document.createElement("div");
    actions.className = "modal-actions";
    function splitLines(id) {
      return $(id).value.split(/\r?\n/).map(function (s) {
        return s.replace(/^\s+|\s+$/g, "");
      }).filter(function (s) { return s.length > 0; });
    }
    actions.appendChild(btn("保存名单", "primary", function () {
      api("/api/restrict/lists", {
        method: "POST",
        json: {
          game_domains: splitLines("list-game"),
          download_domains: splitLines("list-down"),
          whitelist_domains: splitLines("list-white"),
          extensions: splitLines("list-ext")
        }
      }).then(function (st) {
        state = st;
        render();
        closeModal();
      }).catch(function (err) { window.alert(err.message); });
    }));
    actions.appendChild(btn("恢复默认名单", "", function () {
      api("/api/restrict/lists", { method: "POST", json: { reset_defaults: true } })
        .then(function (st) { state = st; render(); closeModal(); openRestrictLists(); })
        .catch(function (err) { window.alert(err.message); });
    }));
    actions.appendChild(btn("关闭", "", closeModal));
    card.appendChild(actions);
    show($("modal"), true);
  }

  function connectWs() {
    if (ws) {
      try { ws.close(); } catch (e) {}
    }
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws/teacher?token=" + encodeURIComponent(token));
    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.type === "state" && msg.data) {
        state = msg.data;
        render();
      } else if (msg.type === "thumb" || msg.type === "focus" || msg.type === "broadcast") {
        if (msg.type === "thumb" && state && state.students) {
          var i, s;
          for (i = 0; i < state.students.length; i++) {
            s = state.students[i];
            if (s.device_id === msg.student_id) s.thumb_at = msg.at;
          }
          render();
        } else if (state) {
          render();
        }
      }
    };
    ws.onclose = function () {
      if (token) setTimeout(connectWs, 2000);
    };
  }

  function afterLogin(data) {
    token = data.token;
    state = data.state;
    try { sessionStorage.setItem("classroom_token", token); } catch (e) {}
    show($("login-page"), false);
    show($("app-page"), true);
    render();
    connectWs();
  }

  on($("login-form"), "submit", function (ev) {
    ev.preventDefault();
    show($("login-error"), false);
    fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("username").value,
        password: $("password").value
      })
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error((data && data.detail) ? String(data.detail) : "登录失败");
        afterLogin(data);
      });
    }).catch(function (err) {
      $("login-error").textContent = err.message || "登录失败";
      show($("login-error"), true);
    });
  });

  on($("btn-class"), "click", function () {
    var path = (state && state.class_active) ? "/api/class/end" : "/api/class/start";
    api(path, { method: "POST", json: {} }).then(function (st) {
      state = st;
      render();
    }).catch(function (err) { window.alert(err.message); });
  });

  on($("btn-refresh-code"), "click", function () {
    if (!window.confirm("更换加入码后，旧码将失效。确定吗？")) return;
    api("/api/class/code", { method: "POST", json: {} }).catch(function (err) { window.alert(err.message); });
  });

  on($("btn-lock-all"), "click", function () {
    api("/api/lock", { method: "POST", json: {} }).catch(function (err) { window.alert(err.message); });
  });
  on($("btn-unlock-all"), "click", function () {
    api("/api/unlock", { method: "POST", json: {} }).catch(function (err) { window.alert(err.message); });
  });
  on($("btn-announce"), "click", function () { promptText("发公告", "公告内容", "announce"); });
  on($("btn-question"), "click", function () { promptText("发题目", "题目内容", "question"); });
  on($("btn-password"), "click", promptPassword);

  on($("btn-file"), "click", function () { $("file-input").click(); });
  on($("file-input"), "change", function () {
    var f = $("file-input").files && $("file-input").files[0];
    $("file-input").value = "";
    if (!f) return;
    var fd = new FormData();
    fd.append("file", f, f.name);
    api("/api/files", { method: "POST", body: fd }).then(function () {
      window.alert("已发送：" + f.name);
    }).catch(function (err) { window.alert(err.message); });
  });

  on($("btn-restrict"), "click", function () {
    if (!state || !state.class_active) {
      window.alert("请先开始上课。开始上课后默认会开启「限制网页游戏和下载」，也可在下课前临时关闭。");
      return;
    }
    var wr = state.web_restrict || {};
    api("/api/restrict/web", { method: "POST", json: { enabled: !wr.enabled } })
      .then(function (st) { state = st; render(); })
      .catch(function (err) { window.alert(err.message); });
  });

  on($("btn-restrict-lists"), "click", function () { openRestrictLists(); });
  on($("btn-desktop"), "click", function () { openDesktopModal(); });
  on($("btn-desktop-unlock"), "click", function () { unlockDesktop(); });

  on($("chk-shrink-screen"), "change", function () {
    var on = $("chk-shrink-screen").checked;
    if (state && state.broadcast_active) {
      api("/api/broadcast/settings", { method: "POST", json: { shrink: on } })
        .then(function (data) {
          if (state) state.broadcast_shrink = !!(data && data.shrink);
          render();
        })
        .catch(function (err) { window.alert(err.message); });
    } else if (state) {
      state.broadcast_shrink = on;
      render();
    }
  });

  on($("btn-broadcast"), "click", function () {
    if (!state) return;
    if (state.broadcast_active) {
      api("/api/broadcast/end", { method: "POST", json: {} }).catch(function (err) { window.alert(err.message); });
      return;
    }
    var shrink = $("chk-shrink-screen") && $("chk-shrink-screen").checked;
    api("/api/broadcast/start", { method: "POST", json: { shrink: !!shrink } }).then(function () {
      if (location.hostname !== "127.0.0.1" && location.hostname !== "localhost") {
        window.alert("已开始广播。若本机采集不可用，请点「广播图片」上传一张画面。在教师机本机用 http://127.0.0.1:8765 打开时，服务端会尝试采集教师屏幕。可勾选「缩小屏幕」向学生发送较小画面。");
      }
    }).catch(function (err) { window.alert(err.message); });
  });

  on($("btn-broadcast-image"), "click", function () { $("broadcast-input").click(); });
  on($("broadcast-input"), "change", function () {
    var f = $("broadcast-input").files && $("broadcast-input").files[0];
    $("broadcast-input").value = "";
    if (!f) return;
    var start = (state && !state.broadcast_active)
      ? api("/api/broadcast/start", { method: "POST", json: {} })
      : Promise.resolve();
    start.then(function () {
      var fd = new FormData();
      fd.append("file", f, f.name);
      return api("/api/broadcast/frame", { method: "POST", body: fd });
    }).catch(function (err) { window.alert(err.message); });
  });

  on($("modal"), "click", function (ev) {
    if (ev.target === $("modal")) closeModal();
  });

  var tabBtns = document.querySelectorAll(".tab");
  var t;
  for (t = 0; t < tabBtns.length; t++) {
    (function (btn) {
      on(btn, "click", function () {
        currentTab = btn.getAttribute("data-tab");
        var k;
        for (k = 0; k < tabBtns.length; k++) tabBtns[k].classList.remove("active");
        btn.classList.add("active");
        document.body.className = document.body.className.replace(/tab-\w+/g, "");
        document.body.classList.add("tab-" + currentTab);
      });
    })(tabBtns[t]);
  }
  document.body.classList.add("tab-wall");

  try {
    var saved = sessionStorage.getItem("classroom_token");
    if (saved) {
      token = saved;
      api("/api/state").then(function (st) {
        state = st;
        show($("login-page"), false);
        show($("app-page"), true);
        render();
        connectWs();
      }).catch(function () { logout(); });
    }
  } catch (e) {}
})();
