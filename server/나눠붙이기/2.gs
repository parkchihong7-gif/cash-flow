// ── 접속키 서버 · 나눠 붙이는 판 2번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `2` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 2/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

var ADMIN_HTML_2 = `    try { window[창고이름].setItem(이름, 값); } catch (_) { /* 막혀 있다 */ }
  }
  function 지우기(창고이름, 이름) {
    delete 기억[이름];
    try { window[창고이름].removeItem(이름); } catch (_) { /* 막혀 있다 */ }
  }
  function serverUrl() { return 꺼내기("localStorage", URL_KEY); }
  function token() { return 꺼내기("sessionStorage", TOKEN_KEY); }
  function scope() { return 꺼내기("sessionStorage", SCOPE_KEY) || "owner"; }
  function 산분() { return scope() === "reseller"; }
  /**
   * 서버를 부른다.
   *
   * POST 로 보낸다. GET 은 주소에 비밀번호가 실려 구글 실행 기록에 그대로
   * 남는다. 앱스 스크립트는 리다이렉트를 거치므로 형식은 text/plain 으로
   * 둔다 — 그래야 브라우저가 미리 묻는 요청(preflight)을 보내지 않는다.
   */
  function api(action, params) {
    var body = Object.assign({ action: action }, params || {});
    if (구글안) {
      // 구글이 감싸 준다. 주소도 CORS 도 없다.
      return new Promise(function (ok, fail) {
        google.script.run
          .withSuccessHandler(function (text) {
            try { ok(JSON.parse(text)); }
            catch (_) { fail(new Error("서버가 이상한 답을 보냈습니다.")); }
          })
          .withFailureHandler(function (err) {
            fail(new Error((err && err.message) || "서버에 닿지 못했습니다."));
          })
          .apiCall(JSON.stringify(body));
      });
    }
    var url = serverUrl();
    if (!url) { return Promise.reject(new Error("키 서버 주소를 먼저 넣어 주세요.")); }
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify(body)
    }).then(function (res) {
      if (!res.ok) { throw new Error("서버가 " + res.status + " 로 답했습니다."); }
      return res.json();
    });
  }
  function authed(action, params) {
    return api(action, Object.assign({ token: token() }, params || {}));
  }
  // ── 설정 ──────────────────────────────────────────────────────
  $("serverUrl").value = serverUrl();
  $("saveUrl").onclick = function () {
    var value = $("serverUrl").value.trim();
    if (!/^https:\\/\\/script\\.google\\.com\\/macros\\/s\\/.+\\/exec$/.test(value)) {
      say($("setupNote"), "앱스 스크립트 주소가 아닙니다. .../exec 으로 끝나야 합니다.", "bad");
      return;
    }
    넣기("localStorage", URL_KEY, value);
    say($("setupNote"), "확인하는 중...", "busy");
    api("ping").then(function (data) {
      if (data.ok) { say($("setupNote"), "서버가 살아 있습니다.", "good"); showStage(); }
      else { say($("setupNote"), "서버가 답을 이상하게 합니다.", "bad"); }
    }).catch(function (err) {
      say($("setupNote"), "연결하지 못했습니다: " + err.message, "bad");
    });
  };
  // ── 로그인 ────────────────────────────────────────────────────
  // 두 길 중 어느 쪽을 보여 줄지.
  function 로그인길(어느쪽) {
    $("byPw").classList.toggle("hide", 어느쪽 !== "owner");
    $("byKey").classList.toggle("hide", 어느쪽 === "owner");
    $("tabOwner").classList.toggle("on", 어느쪽 === "owner");
    $("tabReseller").classList.toggle("on", 어느쪽 !== "owner");
    say($("loginNote"), "", "");
  }
  $("tabOwner").onclick = function () { 로그인길("owner"); };
  $("tabReseller").onclick = function () { 로그인길("reseller"); };
  /** 들어온 뒤 공통으로 하는 일. */
  function 들어옴(표, 어느쪽) {
    넣기("sessionStorage", TOKEN_KEY, 표);
    넣기("sessionStorage", SCOPE_KEY, 어느쪽);
    say($("loginNote"), "", "");
    showStage();
    // 들어오면서 프로그램·역할이 정해진다. 주소를 그때 다시 채운다 —
    // 안 그러면 「들어가는 곳」 이 빈 채로 남아 메일에 주소가 안 실린다.
    $("door").dataset.auto = "1";
    주소채우기();
    refresh();
  }
  $("keyLoginBtn").onclick = function () {
    var k1 = $("k1").value.trim(), k2 = $("k2").value.trim();
    if (!k1 || !k2) { say($("loginNote"), "1차키와 2차키를 모두 넣어 주세요.", "bad"); return; }
    $("keyLoginBtn").disabled = true;
    say($("loginNote"), "확인하는 중...", "busy");
    var 고른것 = 키프로그램.value;
    api("resellerLogin", { program: 고른것, key1: k1, key2: k2 })
      .then(function (data) {
        $("keyLoginBtn").disabled = false;
        if (!data.ok) { say($("loginNote"), data.message || "들어가지 못했습니다.", "bad"); return; }
        $("k1").value = ""; $("k2").value = "";
        select.value = 고른것;          // 본 화면도 같은 프로그램으로
        들어옴(data.token, "reseller");
      })
      .catch(function (err) {
        $("keyLoginBtn").disabled = false;
        say($("loginNote"), err.message, "bad");
      });
  };
  $("k2").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { $("keyLoginBtn").click(); }
  });
  $("loginBtn").onclick = function () {
    var pw = $("pw").value;
    if (!pw) { say($("loginNote"), "비밀번호를 넣어 주세요.", "bad"); return; }
    $("loginBtn").disabled = true;
    say($("loginNote"), "확인하는 중...", "busy");
    api("adminLogin", { password: pw }).then(function (data) {
      $("loginBtn").disabled = false;
      if (!data.ok) { say($("loginNote"), data.message || "들어가지 못했습니다.", "bad"); return; }
      $("pw").value = "";
      들어옴(data.token, "owner");
    }).catch(function (err) {
      $("loginBtn").disabled = false;
      say($("loginNote"), err.message, "bad");
    });
  };
  $("pw").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { $("loginBtn").click(); }
  });
  $("logoutBtn").onclick = function () {
    지우기("sessionStorage", TOKEN_KEY);
    지우기("sessionStorage", SCOPE_KEY);
    showStage();
  };
  function showStage() {
    var hasUrl = 구글안 || !!serverUrl();
    var hasToken = !!token();
    // 산 분에게는 **못 하는 것을 아예 안 보여 준다.** 눌렀다가 거절당하면
    // 고장인 줄 아신다. 서버도 따로 막고 있으니 화면은 안내만 한다.
    if (hasToken) {
      var 좁힘 = 산분();
      $("resetBox").classList.toggle("hide", 좁힘);
      $("resellerNote").classList.toggle("hide", !좁힘);
      $("role").disabled = 좁힘;
      if (좁힘) { $("role").value = "client"; }
      $("program").disabled = 좁힘;   // 산 분은 산 프로그램 하나만 다룬다
      $("whoami").textContent = 좁힘
        ? "산 분으로 들어오셨습니다. 고객용 키만 만드실 수 있고, 직접 발급하신 것만 보입니다."
        : "주인으로 들어오셨습니다. 판매(관리자) 키와 고객용 키를 모두 만드실 수 있습니다.";
    }
    // 구글이 내어 주는 판에서는 주소 칸 자체가 필요 없다.
    $("setup").classList.toggle("hide", 구글안 || (hasUrl && hasToken));
    $("login").classList.toggle("hide", !hasUrl || hasToken);
    $("main").classList.toggle("hide", !(hasUrl && hasToken));
  }
  // ── 프로그램 고르기 ───────────────────────────────────────────
  var select = $("program");
  //: 프로그램 → { admin: 주소, client: 주소 }.
  //: 역할마다 다르다 — 관리자로 산 분에게 고객용 주소를 보내면 발급
  //: 화면이 안 열리고, 반대면 고객이 남의 관리자 화면을 보게 된다.
  var 주소표 = {};
  var 키프로그램 = $("keyProgram");
  (window.PROGRAMS || []).forEach(function (p) {
    [select, 키프로그램].forEach(function (칸) {
      var option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.name + "  (" + p.id + ")";
      칸.appendChild(option);
    });
    if (p.url || p.adminUrl) {
      주소표[p.id] = { client: p.url || "", admin: p.adminUrl || p.url || "" };
    }
  });
  /**
   * 고른 프로그램의 '들어가는 곳' 을 채워 준다.
   *
   * 이게 비어 있으면 메일에 주소가 안 적혀, 고객이 키만 받고 **어디로
   * 가야 하는지 모르게** 된다. 아는 프로그램은 미리 채우고, 모르는
   * 것은 사장님이 직접 적으실 수 있게 둔다.
   */
  function 주소채우기() {
    var 칸 = $("door");
    var 한벌 = 주소표[select.value] || {};
    var 역할 = 산분() ? "client" : $("role").value;
    var 알던주소 = (역할 === "admin" ? 한벌.admin : 한벌.client) || "";
    // 사장님이 손으로 고쳐 두셨으면 건드리지 않는다.
    if (!칸.value || 칸.dataset.auto === "1") {
      칸.value = 알던주소;
      칸.dataset.auto = "1";
    }
    칸.placeholder = 알던주소
      ? 알던주소
      : "https://… (이 프로그램은 아직 주소를 모릅니다. 직접 적어 주세요)";
    $("doorLabel").textContent = ((산분() ? "client" : $("role").value) === "admin"
      ? "산 분이 들어가는 곳 — 관리자 화면"
      : "고객이 들어가는 곳 — 쓰는 화면") + " (메일에 이 주소가 적힙니다)";
  }
  $("door").addEventListener("input", function () { this.dataset.auto = ""; });
  select.onchange = function () { 주소채우기(); refresh(); };
  // 역할을 바꾸면 주소도 따라 바뀌어야 한다. 안 그러면 관리자에게
  // 고객용 주소가, 고객에게 관리자 주소가 나간다.
  $("role").onchange = 주소채우기;
  주소채우기();
  $("refreshBtn").onclick = refresh;
  // ── 발급 ──────────────────────────────────────────────────────
  $("issueBtn").onclick = function () {
    var name = $("name").value.trim();
    var email = $("email").value.trim();
    if (!name) { say($("issueNote"), "이름을 적어 주세요. 누구에게 준 키인지 남아야 합니다.", "bad"); return; }
    if (email.indexOf("@") < 0) { say($("issueNote"), "이메일 주소를 확인해 주세요.", "bad"); return; }
    $("issueBtn").disabled = true;
    say($("issueNote"), "만들고 보내는 중...", "busy");
    $("issued").classList.add("hide");
    authed("adminCreateInvite", {
      program: select.value,
      name: name,
      email: email,
      role: $("role").value,
      expiryDays: $("days").value.trim(),
      // 고객에게 보낼 주소. 화면의 칸에 적힌 것을 그대로 쓴다.
      baseUrl: $("door").value.trim()
    }).then(function (data) {
      $("issueBtn").disabled = false;
      if (!data.ok) { say($("issueNote"), data.message || "발급하지 못했습니다.", "bad"); return; }
      // 메일이 막혀도 키는 이미 있다. 그것을 그대로 보여 줘야 직접 보내실 수 있다.
      say($("issueNote"), data.message || "발급했습니다.", data.mailed ? "good" : "bad");
      var lines = [
        "받는 분 : " + name + " <" + email + ">",
        "프로그램 : " + select.options[select.selectedIndex].textContent,
        "",
        "1차키   : " + data.primaryKey,
        "2차키 PC   : " + data.secondaryKeys["PC"],
        "2차키 노트북 : " + data.secondaryKeys["노트북"],
        "2차키 휴대폰 : " + data.secondaryKeys["휴대폰"]
      ];
      if (data.url) { lines.push("", "들어가는 곳 : " + data.url); }
      var box = $("issued");
      box.textContent = lines.join("\\n");
      var copy = document.createElement("button");
      copy.className = "quiet";
      copy.style.marginTop = "10px";
      copy.textContent = "전부 복사";`;

// ⛳ 2/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
