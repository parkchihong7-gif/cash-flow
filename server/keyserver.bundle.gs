// ═══════════════════════════════════════════════════════════════════
//  접속키 서버 — 구글 앱스 스크립트에 붙여 넣는 **한 장짜리** 판입니다.
//
//  ■ 붙여넣기 전에 꼭 보세요
//    이 파일은 1,257줄입니다. 맨 아래에 ⛳ 표가 있습니다.
//    붙여 넣은 뒤 **맨 아래에 그 ⛳ 표가 보이는지** 확인하세요.
//    안 보이면 잘린 것이고, 그대로 저장하면
//      구문 오류: SyntaxError: Unexpected end of input
//    이 납니다. 그때는 GitHub 화면에서 Ctrl+A 하지 마시고
//    파일 위쪽의 [Raw] 또는 복사 아이콘을 쓰세요.
//    (GitHub 은 긴 파일을 보이는 만큼만 그려서, Ctrl+A 가 잘립니다.)
//
//  이 파일은 만들어진 것입니다. 손으로 고치지 마세요.
//    읽기 좋은 원본: server/keyserver.gs + web/admin.html
//    다시 만들기   : python -m tools.build_keyserver
//
//  설치 (세 단계)
//    1. script.google.com → 새 프로젝트 → 이 파일을 통째로 붙여넣기
//    2. 함수 고르는 칸에서 `처음설정` 을 고르고 [실행]
//       → 장부 시트·서명값·관리자 비밀번호를 만들어 알려 줍니다
//    3. [배포] → [새 배포] → 웹 앱
//       실행: 나 / 권한: 모든 사용자
//       → 나온 주소를 열면 관리자 화면이 바로 뜹니다
// ═══════════════════════════════════════════════════════════════════

var ADMIN_HTML = `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>접속키 관리자</title>
<style>
  :root {
    --ground: #10141a; --chrome: #171d26; --hairline: #2a3442;
    --ink: #e8eef6; --muted: #93a1b3; --amber: #e0a44a; --on-amber: #1a1206;
    --good: #5fbf8f; --bad: #ff8f7a; --chip: #1e2733;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0 16px 60px; background: var(--ground); color: var(--ink);
    font: 15px/1.6 "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
  }
  .wrap { max-width: 1100px; margin: 0 auto; }
  header { padding: 22px 0 16px; border-bottom: 1px solid var(--hairline); }
  h1 { margin: 0 0 4px; font-size: 21px; }
  .sub { margin: 0; color: var(--muted); font-size: 13px; }
  section { margin: 22px 0; padding: 18px; background: var(--chrome);
            border: 1px solid var(--hairline); border-radius: 10px; }
  h2 { margin: 0 0 14px; font-size: 16px; }
  label { display: block; margin: 0 0 5px; font-size: 13px; color: var(--muted); }
  input, select, button, textarea {
    font: inherit; color: var(--ink); background: var(--chip);
    border: 1px solid var(--hairline); border-radius: 7px; padding: 9px 11px;
  }
  input, select { width: 100%; }
  button { cursor: pointer; background: var(--amber); color: var(--on-amber);
           border: 0; font-weight: 600; white-space: nowrap; }
  button.quiet { background: var(--chip); color: var(--ink); border: 1px solid var(--hairline);
                 font-weight: 400; padding: 5px 9px; font-size: 13px; }
  button.danger { background: var(--chip); color: var(--bad); border: 1px solid var(--hairline); }
  button:disabled { opacity: .5; cursor: wait; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
  .row > div { flex: 1; min-width: 150px; }
  .row > div.narrow { flex: 0 0 130px; }
  .note { margin: 10px 0 0; font-size: 13px; min-height: 20px; }
  .note.bad { color: var(--bad); }
  .note.good { color: var(--good); }
  .note.busy { color: var(--muted); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--hairline);
           vertical-align: top; }
  th { color: var(--muted); font-weight: 500; }
  td.key { font-family: ui-monospace, Menlo, Consolas, monospace; letter-spacing: .02em; }
  .tag { display: inline-block; padding: 1px 7px; border-radius: 99px; font-size: 11px;
         background: var(--chip); border: 1px solid var(--hairline); }
  .tag.admin { color: var(--amber); }
  .tag.live { color: var(--good); }
  .tag.off { color: var(--bad); }
  .keys { margin: 12px 0 0; padding: 12px; background: var(--ground);
          border: 1px solid var(--hairline); border-radius: 8px;
          font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px;
          white-space: pre-wrap; word-break: break-all; }
  .stats { display: flex; gap: 14px; flex-wrap: wrap; margin: 0 0 14px; }
  .stat { padding: 8px 14px; background: var(--ground); border: 1px solid var(--hairline);
          border-radius: 8px; }
  .stat b { display: block; font-size: 19px; }
  .stat span { font-size: 12px; color: var(--muted); }
  .hide { display: none; }
  .warn { margin: 0 0 14px; padding: 10px 12px; border-radius: 8px;
          background: #3a2a12; border: 1px solid #6b4e1f; color: #f0d9a8; font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>접속키 관리자</h1>
  <p class="sub">16종 + 공인중개사 + maim 이 한 서버를 같이 씁니다. 여기서 발급하면 그 자리에서 이메일이 나갑니다.</p>
</header>
<section id="setup">
  <h2>키 서버 주소</h2>
  <p class="sub" style="margin-bottom:12px">
    구글 앱스 스크립트를 배포하면 나오는 주소입니다. 한 번 넣으면 이 브라우저가 기억합니다.
    처음이시면 <code>server/README.md</code> 를 보세요.
  </p>
  <div class="row">
    <div><input type="url" id="serverUrl" placeholder="https://script.google.com/macros/s/.../exec"></div>
    <div class="narrow"><button id="saveUrl">저장</button></div>
  </div>
  <p class="note" id="setupNote"></p>
</section>
<section id="login" class="hide">
  <h2>관리자 비밀번호</h2>
  <div class="row">
    <div><input type="password" id="pw" placeholder="비밀번호" autocomplete="current-password"></div>
    <div class="narrow"><button id="loginBtn">들어가기</button></div>
  </div>
  <p class="note" id="loginNote"></p>
</section>
<div id="main" class="hide">
  <section>
    <h2>프로그램 고르기</h2>
    <div class="row">
      <div><select id="program"></select></div>
      <div class="narrow"><button class="quiet" id="refreshBtn">새로 읽기</button></div>
      <div class="narrow"><button class="quiet" id="logoutBtn">나가기</button></div>
    </div>
  </section>
  <section>
    <h2>키 주기 — 1차키 1개 + 2차키 3개(PC·노트북·휴대폰)</h2>
    <div class="row">
      <div>
        <label for="role">무슨 키</label>
        <select id="role">
          <option value="admin">판매 — 이 프로그램을 산 분 (관리자)</option>
          <option value="client">고객용 — 쓰는 화면만</option>
        </select>
      </div>
      <div><label for="name">이름</label><input id="name" placeholder="홍길동"></div>
      <div><label for="email">이메일</label><input type="email" id="email" placeholder="hong@example.com"></div>
      <div class="narrow"><label for="days">유효기간</label><input id="days" placeholder="비우면 무제한"></div>
      <div class="narrow"><button id="issueBtn">발급하고 보내기</button></div>
    </div>
    <p class="note" id="issueNote"></p>
    <div class="keys hide" id="issued"></div>
  </section>
  <section>
    <h2>발급한 키</h2>
    <div class="stats" id="stats"></div>
    <div id="list"><p class="sub">읽는 중...</p></div>
  </section>
  <section>
    <h2>이 프로그램의 키 전부 지우기</h2>
    <p class="warn">되돌릴 수 없습니다. 이미 파신 키가 있으면 고객이 그 자리에서 못 들어오게 됩니다.</p>
    <div class="row">
      <div><input id="confirm" placeholder='지우시려면 여기에 "초기화" 라고 적으세요'></div>
      <div class="narrow"><button class="danger" id="resetBtn">전부 지우기</button></div>
    </div>
    <p class="note" id="resetNote"></p>
  </section>
</div>
</div>
<script>
window.PROGRAMS = [
  {
    "id": "funnel-builder",
    "name": "퍼널 빌더"
  },
  {
    "id": "hook-script",
    "name": "후킹 대본 생성기"
  },
  {
    "id": "ebook-gen",
    "name": "전자책 원고 생성기"
  },
  {
    "id": "lecture-deck",
    "name": "강의 슬라이드 생성기"
  },
  {
    "id": "kmong-copy",
    "name": "크몽 상세페이지 카피 생성기"
  },
  {
    "id": "n8n-gen",
    "name": "n8n 워크플로 JSON 생성기"
  },
  {
    "id": "groupbuy-ledger",
    "name": "공구 정산 엑셀 자동 생성기"
  },
  {
    "id": "income-sim",
    "name": "수익 시뮬레이터"
  },
  {
    "id": "notion-template-kit",
    "name": "노션 템플릿 기획·설명서 생성기"
  },
  {
    "id": "affiliate-matcher",
    "name": "제휴 상품 매칭 로직"
  },
  {
    "id": "agency-kit",
    "name": "자동화 대행 납품 키트"
  },
  {
    "id": "niche-research",
    "name": "니치 리서치"
  },
  {
    "id": "exam-drill",
    "name": "공인중개사 기출 풀이 분석기"
  },
  {
    "id": "senior-video",
    "name": "시니어 영상 비용 견적·절감기"
  },
  {
    "id": "naver-blog",
    "name": "네이버 블로그 초안 생성기"
  },
  {
    "id": "speaker-desk",
    "name": "해외 연사 초청 관리"
  },
  {
    "id": "exam",
    "name": "공인중개사 기출문제 (바깥 프로그램)"
  },
  {
    "id": "maim",
    "name": "maim 블로그 (바깥 프로그램)"
  }
];
</script>
<script>
(function () {
  "use strict";
  // 주소는 이 브라우저에만 둔다. 비밀은 아니지만 저장소에 박아 두면
  // 서버를 옮길 때마다 코드를 고쳐야 한다.
  var URL_KEY = "keyserver.url";
  // 표는 sessionStorage 에 둔다. 창을 닫으면 사라진다 — 공용 PC 에서
  // localStorage 에 두면 다음 사람이 그대로 들어온다.
  var TOKEN_KEY = "keyserver.token";
  var $ = function (id) { return document.getElementById(id); };
  function say(el, text, kind) {
    el.className = "note" + (kind ? " " + kind : "");
    el.textContent = text;
  }
  /**
   * 구글이 이 화면을 직접 내어 주고 있나?
   *
   * 그렇다면 주소를 물어볼 것이 없다 — \`google.script.run\` 이 같은
   * 스크립트를 바로 부른다. CORS 도, 주소를 어디 적어 둘 일도 없다.
   */
  var 구글안 = !!(window.google && window.google.script && window.google.script.run);
  function serverUrl() { return localStorage.getItem(URL_KEY) || ""; }
  function token() { return sessionStorage.getItem(TOKEN_KEY) || ""; }
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
    localStorage.setItem(URL_KEY, value);
    say($("setupNote"), "확인하는 중...", "busy");
    api("ping").then(function (data) {
      if (data.ok) { say($("setupNote"), "서버가 살아 있습니다.", "good"); showStage(); }
      else { say($("setupNote"), "서버가 답을 이상하게 합니다.", "bad"); }
    }).catch(function (err) {
      say($("setupNote"), "연결하지 못했습니다: " + err.message, "bad");
    });
  };
  // ── 로그인 ────────────────────────────────────────────────────
  $("loginBtn").onclick = function () {
    var pw = $("pw").value;
    if (!pw) { say($("loginNote"), "비밀번호를 넣어 주세요.", "bad"); return; }
    $("loginBtn").disabled = true;
    say($("loginNote"), "확인하는 중...", "busy");
    api("adminLogin", { password: pw }).then(function (data) {
      $("loginBtn").disabled = false;
      if (!data.ok) { say($("loginNote"), data.message || "들어가지 못했습니다.", "bad"); return; }
      sessionStorage.setItem(TOKEN_KEY, data.token);
      $("pw").value = "";
      say($("loginNote"), "", "");
      showStage();
      refresh();
    }).catch(function (err) {
      $("loginBtn").disabled = false;
      say($("loginNote"), err.message, "bad");
    });
  };
  $("pw").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { $("loginBtn").click(); }
  });
  $("logoutBtn").onclick = function () {
    sessionStorage.removeItem(TOKEN_KEY);
    showStage();
  };
  function showStage() {
    var hasUrl = 구글안 || !!serverUrl();
    var hasToken = !!token();
    // 구글이 내어 주는 판에서는 주소 칸 자체가 필요 없다.
    $("setup").classList.toggle("hide", 구글안 || (hasUrl && hasToken));
    $("login").classList.toggle("hide", !hasUrl || hasToken);
    $("main").classList.toggle("hide", !(hasUrl && hasToken));
  }
  // ── 프로그램 고르기 ───────────────────────────────────────────
  var select = $("program");
  (window.PROGRAMS || []).forEach(function (p) {
    var option = document.createElement("option");
    option.value = p.id;
    option.textContent = p.name + "  (" + p.id + ")";
    select.appendChild(option);
  });
  select.onchange = refresh;
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
      // 고객에게 보낼 주소. 구글이 내어 주는 판에서는 이 화면의 주소가
      // 곧 서버 주소라, 고객용 문 주소는 사장님이 따로 적어 주셔야 한다.
      baseUrl: 구글안 ? "" : location.origin + location.pathname.replace(/admin\\.html$/, "")
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
      copy.textContent = "전부 복사";
      copy.onclick = function () {
        navigator.clipboard.writeText(lines.join("\\n")).then(function () {
          copy.textContent = "복사했습니다";
        }).catch(function () { copy.textContent = "복사하지 못했습니다"; });
      };
      box.appendChild(document.createElement("br"));
      box.appendChild(copy);
      box.classList.remove("hide");
      $("name").value = ""; $("email").value = "";
      refresh();
    }).catch(function (err) {
      $("issueBtn").disabled = false;
      say($("issueNote"), err.message, "bad");
    });
  };
  // ── 목록 ──────────────────────────────────────────────────────
  function refresh() {
    if (!token()) { return; }
    $("list").innerHTML = '<p class="sub">읽는 중...</p>';
    authed("adminList", { program: select.value }).then(function (data) {
      if (!data.ok) {
        // 표가 만료됐으면 다시 로그인시킨다. 빈 목록을 보여 주면
        // 판 키가 사라진 줄 아시게 된다.
        if (data.reason === "unauthorized") {
          sessionStorage.removeItem(TOKEN_KEY);
          showStage();
          say($("loginNote"), "시간이 지나 다시 들어가셔야 합니다.", "busy");
          return;
        }
        $("list").innerHTML = '<p class="note bad">' + (data.message || "읽지 못했습니다.") + "</p>";
        return;
      }
      drawStats(data.counts);
      drawRows(data.rows);
    }).catch(function (err) {
      $("list").innerHTML = '<p class="note bad">' + err.message + "</p>";
    });
  }
  function drawStats(counts) {
    var pairs = [
      ["판 것 (관리자키)", counts.admins],
      ["고객키", counts.clients],
      ["2차키", counts.secondary],
      ["들어와 있음", counts.live],
      ["정지", counts.suspended]
    ];
    $("stats").innerHTML = pairs.map(function (p) {
      return '<div class="stat"><b>' + p[1] + "</b><span>" + p[0] + "</span></div>";
    }).join("");
  }
  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function drawRows(rows) {
    if (!rows.length) {
      $("list").innerHTML = '<p class="sub">아직 발급한 키가 없습니다.</p>';
      return;
    }
    // 1차키를 먼저, 그 아래 딸린 2차키를 붙여 보여 준다.
    var primaries = rows.filter(function (r) { return r.type !== "secondary"; });
    var byParent = {};
    rows.forEach(function (r) {
      if (r.type !== "secondary") { return; }
      (byParent[r.parentKey] = byParent[r.parentKey] || []).push(r);
    });
    var html = ['<table><thead><tr><th>키</th><th>누구</th><th>무슨 키</th>',
                '<th>상태</th><th>발급일</th><th>만료</th><th></th></tr></thead><tbody>'];
    primaries.forEach(function (r) {
      html.push(line(r, false));
      (byParent[r.key] || []).forEach(function (s) { html.push(line(s, true)); });
    });
    html.push("</tbody></table>");
    $("list").innerHTML = html.join("");
    $("list").querySelectorAll("button[data-do]").forEach(function (btn) {
      btn.onclick = function () {
        var what = btn.dataset.do, key = btn.dataset.key;
        if (what === "adminDeleteKey" &&
            !confirm("이 키를 지웁니다. 1차키면 딸린 2차키도 함께 사라집니다.\\n\\n" + key)) { return; }
        btn.disabled = true;
        authed(what, { program: select.value, key: key }).then(function (data) {
          if (!data.ok) { alert(data.message || "하지 못했습니다."); btn.disabled = false; return; }
          refresh();
        }).catch(function (err) { alert(err.message); btn.disabled = false; });
      };
    });
  }
  function line(r, indented) {
    var 상태 = r.status === "suspended"
      ? '<span class="tag off">정지</span>'
      : (r.live ? '<span class="tag live">들어와 있음</span>' : '<span class="tag">사용 가능</span>');
    var 종류 = r.type === "secondary"
      ? '<span class="tag">2차 · ' + esc(r.deviceLabel) + "</span>"
      : (r.type === "legacy"
          ? '<span class="tag">레거시</span>'
          : (r.role === "admin"
              ? '<span class="tag admin">1차 · 판매</span>'
              : '<span class="tag">1차 · 고객</span>'));
    var 되돌리기 = r.status === "suspended" ? "adminResumeKey" : "adminSuspendKey";
    return '<tr><td class="key" style="padding-left:' + (indented ? 26 : 8) + 'px">'
      + esc(r.key) + "</td>"
      + "<td>" + esc(r.assignedName) + "<br><span class='sub'>" + esc(r.assignedEmail) + "</span></td>"
      + "<td>" + 종류 + "</td>"
      + "<td>" + 상태 + "</td>"
      + "<td>" + esc(r.issuedDate) + "</td>"
      + "<td>" + (esc(r.expiryDate) || "무제한") + "</td>"
      + '<td><button class="quiet" data-do="' + 되돌리기 + '" data-key="' + esc(r.key) + '">'
      + (r.status === "suspended" ? "풀기" : "정지") + "</button> "
      + '<button class="quiet" data-do="adminDeleteKey" data-key="' + esc(r.key) + '">지우기</button></td>'
      + "</tr>";
  }
  // ── 초기화 ────────────────────────────────────────────────────
  $("resetBtn").onclick = function () {
    var word = $("confirm").value.trim();
    if (word !== "초기화") {
      say($("resetNote"), '"초기화" 라고 정확히 적어 주셔야 움직입니다.', "bad");
      return;
    }
    if (!confirm(select.options[select.selectedIndex].textContent
                 + "\\n\\n이 프로그램의 키를 전부 지웁니다. 되돌릴 수 없습니다.")) { return; }
    $("resetBtn").disabled = true;
    authed("adminResetAll", { program: select.value, confirm: "초기화" }).then(function (data) {
      $("resetBtn").disabled = false;
      $("confirm").value = "";
      say($("resetNote"), data.ok ? (data.deleted + "개를 지웠습니다.") : (data.message || "지우지 못했습니다."),
          data.ok ? "good" : "bad");
      refresh();
    }).catch(function (err) {
      $("resetBtn").disabled = false;
      say($("resetNote"), err.message, "bad");
    });
  };
  // ── 시작 ──────────────────────────────────────────────────────
  showStage();
  if ((구글안 || serverUrl()) && token()) { refresh(); }
})();
</script>
</body>
</html>`;

var SHEET_KEYS = 'keys';
var SHEET_TITLE = '접속키 장부 (지우지 마세요)';
var BOOK_CACHE = null;
var SHEET_LOG = 'log';
var ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
var BLOCK = 4;
var BLOCKS = 3;
var DEVICES = ['PC', '노트북', '휴대폰'];
var ROLE_ADMIN = 'admin';
var ROLE_CLIENT = 'client';
var KIND_PRIMARY = 'primary';
var KIND_SECONDARY = 'secondary';
var KIND_LEGACY = 'legacy';
var MAX_BULK = 500;
var ADMIN_TOKEN_HOURS = 12;
var GUESS_LIMIT = 10;
var GUESS_WINDOW = 600;
var COLUMNS = [
  'program',
  'key',
  'type',
  'role',
  'issuedBy',
  'parentKey',
  'deviceLabel',
  'status',
  'issuedDate',
  'expiryDate',
  'assignedName',
  'assignedEmail',
  'usedDate',
  'sessionToken',
  'sessionAt',
  'note'
];
function 처음설정() {
  var 직접정한비밀번호 = '';
  var 시트 = book();
  sheetOf(SHEET_KEYS, COLUMNS);
  sheetOf(SHEET_LOG, ['때', '무엇', '프로그램', '내용']);
  signingSecret();
  var 비밀번호 = prop('ADMIN_PASSWORD');
  var 새로만듦 = false;
  if (직접정한비밀번호) {
    비밀번호 = String(직접정한비밀번호);
    setProp('ADMIN_PASSWORD', 비밀번호);
    새로만듦 = true;
  } else if (!비밀번호) {
    비밀번호 = 읽기쉬운비밀번호();
    setProp('ADMIN_PASSWORD', 비밀번호);
    새로만듦 = true;
  }
  var 줄 = [
    '',
    '════════════════════════════════════════════════',
    '  설치가 끝났습니다.',
    '',
    '  관리자 비밀번호 :  ' + 비밀번호,
    (새로만듦 ? '' : '  (이미 정해 두신 것을 그대로 씁니다)'),
    '',
    '  장부 시트 : ' + 시트.getUrl(),
    '',
    '  다음 할 일',
    '   1. 오른쪽 위 [배포] → [새 배포] → 유형 **웹 앱**',
    '   2. 다음 사용자로 실행: **나**',
    '      액세스 권한이 있는 사용자: **모든 사용자**',
    '   3. 나오는 주소를 열면 **관리자 화면**이 바로 뜹니다.',
    '      위 비밀번호를 넣으시면 키를 발급하실 수 있습니다.',
    '════════════════════════════════════════════════',
    ''
  ];
  var 글 = 줄.filter(function (x) { return x !== ''; }).join('\n');
  Logger.log(글);
  return 글;
}
function 읽기쉬운비밀번호() {
  var 덩이 = [];
  for (var b = 0; b < 4; b++) {
    var one = '';
    for (var i = 0; i < 4; i++) {
      one += ALPHABET.charAt(Math.floor(Math.random() * ALPHABET.length));
    }
    덩이.push(one);
  }
  return 덩이.join('-');
}
function doGet(e) {
  if (!e || !e.parameter || !e.parameter.action) { return servePage(); }
  return handle(e);
}
function doPost(e) { return handle(e); }
function servePage() {
  if (typeof ADMIN_HTML === 'undefined' || !ADMIN_HTML) {
    return HtmlService.createHtmlOutput(
      '<meta charset="utf-8"><p style="font:15px sans-serif;padding:24px">' +
      '관리자 화면이 안 들어 있는 판입니다. ' +
      '<code>server/keyserver.bundle.gs</code> 를 붙여 넣으세요.</p>');
  }
  return HtmlService.createHtmlOutput(ADMIN_HTML)
    .setTitle('접속키 관리자')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
function apiCall(payloadJson) {
  var params = {};
  try { params = JSON.parse(payloadJson || '{}'); } catch (_) { params = {}; }
  return handle({ parameter: params }).getContent();
}
function handle(e) {
  var p = {};
  try {
    if (e && e.parameter) { for (var k in e.parameter) { p[k] = e.parameter[k]; } }
    if (e && e.postData && e.postData.contents) {
      var body = {};
      try { body = JSON.parse(e.postData.contents); } catch (_) { body = {}; }
      for (var k2 in body) { p[k2] = body[k2]; }
    }
  } catch (_) {  }
  var action = String(p.action || '');
  try {
    switch (action) {
      case 'ping':             return json({ ok: true, at: nowIso() });
      case 'validateKeyPair':  return json(validateKeyPair(p));
      case 'checkSession':     return json(checkSession(p));
      case 'adminLogin':       return json(adminLogin(p));
      case 'adminList':        return json(adminList(p));
      case 'adminCreateKeys':  return json(adminCreateKeys(p));
      case 'adminCreateInvite':return json(adminCreateInvite(p));
      case 'adminSuspendKey':  return json(adminSetStatus(p, 'suspended'));
      case 'adminResumeKey':   return json(adminSetStatus(p, 'active'));
      case 'adminDeleteKey':   return json(adminDeleteKey(p));
      case 'adminResetAll':    return json(adminResetAll(p));
      default:
        return json({ ok: false, reason: 'unknown_action', message: '모르는 요청입니다: ' + action });
    }
  } catch (err) {
    log('error', action, String((err && err.message) || err));
    return json({ ok: false, reason: 'server_error', message: '서버에서 문제가 났습니다. 잠시 뒤 다시 해 주세요.' });
  }
}
function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
function validateKeyPair(p) {
  var program = programOf(p);
  var key1 = normalizeKey(p.key1 || p.key || '');
  var key2 = normalizeKey(p.key2 || '');
  if (!key1) { return { ok: false, reason: 'no_primary', message: '1차 인증키를 입력해주세요.' }; }
  if (tooManyGuesses(key1)) {
    return { ok: false, reason: 'too_many_attempts',
             message: '너무 여러 번 틀렸습니다. 10분 뒤에 다시 해 주세요.' };
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    var row1 = findKey(table, program, key1);
    if (!row1) {
      countGuess(key1);
      return { ok: false, reason: 'not_found', message: '등록되지 않은 키입니다.' };
    }
    var bad = unusable(row1);
    if (bad) { return bad; }
    if (row1.type === KIND_LEGACY) {
      touch(table, row1, '');
      writeTable(table);
      log('open', program, key1 + ' (레거시)');
      return { ok: true, legacy: true, role: row1.role || ROLE_CLIENT,
               name: row1.assignedName || '', program: program };
    }
    if (!key2) {
      return { ok: false, reason: 'no_secondary',
               message: '2차 인증키도 함께 입력해주세요.' };
    }
    var row2 = findKey(table, program, key2);
    if (!row2 || row2.type !== KIND_SECONDARY) {
      countGuess(key1);
      return { ok: false, reason: 'secondary_not_found', message: '2차 인증키를 찾을 수 없습니다.' };
    }
    if (normalizeKey(row2.parentKey) !== key1) {
      countGuess(key1);
      return { ok: false, reason: 'pair_mismatch',
               message: '1차 인증키와 2차 인증키가 서로 맞지 않습니다.' };
    }
    var bad2 = unusable(row2);
    if (bad2) { return bad2; }
    var token = Utilities.getUuid();
    row2.sessionToken = token;
    row2.sessionAt = nowIso();
    touch(table, row1, '');
    touch(table, row2, '');
    writeTable(table);
    log('open', program, key1 + ' / ' + key2 + ' (' + (row2.deviceLabel || '') + ')');
    return {
      ok: true,
      sessionToken: token,
      role: row1.role || ROLE_CLIENT,
      name: row1.assignedName || '',
      deviceLabel: row2.deviceLabel || '',
      program: program
    };
  } finally {
    lock.releaseLock();
  }
}
function checkSession(p) {
  var program = programOf(p);
  var key = normalizeKey(p.key || p.key2 || '');
  var token = String(p.sessionToken || '');
  if (!key || !token) { return { ok: false, reason: 'missing' }; }
  var table = readTable();
  var row = findKey(table, program, key);
  if (!row) { return { ok: false, reason: 'not_found' }; }
  if (row.status === 'suspended') { return { ok: false, reason: 'suspended' }; }
  if (expired(row)) { return { ok: false, reason: 'expired' }; }
  var parent = row.parentKey ? findKey(table, program, row.parentKey) : null;
  if (parent) {
    if (parent.status === 'suspended') { return { ok: false, reason: 'suspended' }; }
    if (expired(parent)) { return { ok: false, reason: 'expired' }; }
  }
  if (String(row.sessionToken || '') !== token) {
    return { ok: false, reason: 'session_replaced' };
  }
  return { ok: true };
}
function adminLogin(p) {
  var given = String(p.password || p.token || '');
  if (!passwordOk(given)) {
    Utilities.sleep(700);
    return { ok: false, reason: 'bad_password', message: '비밀번호가 올바르지 않습니다.' };
  }
  return { ok: true, token: makeAdminToken(), hours: ADMIN_TOKEN_HOURS };
}
function adminList(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = String(p.program || '').trim();
  var issuer = normalizeKey(p.issuer || '');
  var rows = readTable().rows.filter(function (r) {
    if (program && r.program !== program) { return false; }
    if (issuer && normalizeKey(r.issuedBy) !== issuer) { return false; }
    return true;
  }).map(publicRow);
  return { ok: true, rows: rows, counts: countRows(rows) };
}
function adminCreateKeys(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = programOf(p);
  var count = Math.floor(Number(p.count || 0));
  if (!(count > 0)) { return { ok: false, reason: 'bad_count', message: '몇 개를 만들지 적어 주세요.' }; }
  if (count > MAX_BULK) {
    return { ok: false, reason: 'too_many',
             message: '한 번에 ' + MAX_BULK + '개까지 만드실 수 있습니다.' };
  }
  var expiry = expiryFrom(p.expiryDays);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    var made = [];
    for (var i = 0; i < count; i++) {
      var row = blankRow(program, KIND_LEGACY);
      row.key = uniqueKey(table);
      row.role = ROLE_CLIENT;
      row.expiryDate = expiry;
      table.rows.push(row);
      made.push(row.key);
    }
    writeTable(table);
    log('create', program, made.length + '개');
    return { ok: true, keys: made };
  } finally {
    lock.releaseLock();
  }
}
function adminCreateInvite(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = programOf(p);
  var name = String(p.name || '').trim();
  var email = String(p.email || '').trim();
  var role = String(p.role || ROLE_ADMIN);
  var issuedBy = normalizeKey(p.issuedBy || '');
  var baseUrl = String(p.baseUrl || '').trim();
  if (!name) { return { ok: false, reason: 'no_name', message: '이름을 적어 주세요. 누구에게 준 키인지 남아야 합니다.' }; }
  if (email.indexOf('@') < 0) { return { ok: false, reason: 'bad_email', message: '이메일 주소를 확인해 주세요.' }; }
  if (role !== ROLE_ADMIN && role !== ROLE_CLIENT) {
    return { ok: false, reason: 'bad_role', message: '모르는 역할입니다: ' + role };
  }
  if (role === ROLE_ADMIN && issuedBy) {
    return { ok: false, reason: 'not_allowed',
             message: '관리자키는 발급하실 수 없습니다. 고객용 키만 만드실 수 있습니다.' };
  }
  var expiry = expiryFrom(p.expiryDays);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    if (issuedBy) {
      var issuerRow = findKey(table, program, issuedBy);
      if (!issuerRow || issuerRow.role !== ROLE_ADMIN) {
        return { ok: false, reason: 'bad_issuer', message: '발급하실 수 있는 키가 아닙니다.' };
      }
      if (unusable(issuerRow)) {
        return { ok: false, reason: 'issuer_unusable', message: '발급하신 분의 키가 정지되었거나 만료되었습니다.' };
      }
    }
    var primary = blankRow(program, KIND_PRIMARY);
    primary.key = uniqueKey(table);
    primary.role = role;
    primary.issuedBy = issuedBy;
    primary.expiryDate = expiry;
    primary.assignedName = name;
    primary.assignedEmail = email;
    table.rows.push(primary);
    var secondaries = {};
    for (var i = 0; i < DEVICES.length; i++) {
      var s = blankRow(program, KIND_SECONDARY);
      s.key = uniqueKey(table);
      s.role = role;
      s.issuedBy = issuedBy;
      s.parentKey = primary.key;
      s.deviceLabel = DEVICES[i];
      s.expiryDate = expiry;
      s.assignedName = name;
      s.assignedEmail = email;
      table.rows.push(s);
      secondaries[DEVICES[i]] = s.key;
    }
    writeTable(table);
    var url = baseUrl || '';
    var sent = sendInvite(email, name, program, primary.key, secondaries, url, role, expiry);
    log('invite', program, name + ' <' + email + '> ' + (sent ? '보냄' : '못 보냄'));
    return {
      ok: true,
      primaryKey: primary.key,
      secondaryKeys: secondaries,
      url: url,
      mailed: sent,
      message: sent ? '발송했습니다.'
                    : '키는 만들었지만 메일이 나가지 않았습니다. 아래 키를 복사해 직접 보내 주세요.'
    };
  } finally {
    lock.releaseLock();
  }
}
function adminSetStatus(p, status) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = programOf(p);
  var key = normalizeKey(p.key || '');
  var issuer = normalizeKey(p.issuer || '');
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    var row = findKey(table, program, key);
    if (!row) { return { ok: false, reason: 'not_found', message: '그런 키가 없습니다.' }; }
    if (issuer && normalizeKey(row.issuedBy) !== issuer) {
      return { ok: false, reason: 'not_yours', message: '직접 발급하신 키만 다루실 수 있습니다.' };
    }
    var touched = 0;
    var family = familyOf(table, program, row);
    for (var i = 0; i < family.length; i++) { family[i].status = status; touched++; }
    writeTable(table);
    log(status, program, key + ' (' + touched + '개)');
    return { ok: true, changed: touched };
  } finally {
    lock.releaseLock();
  }
}
function adminDeleteKey(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = programOf(p);
  var key = normalizeKey(p.key || '');
  var issuer = normalizeKey(p.issuer || '');
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    var row = findKey(table, program, key);
    if (!row) { return { ok: false, reason: 'not_found', message: '그런 키가 없습니다.' }; }
    if (issuer && normalizeKey(row.issuedBy) !== issuer) {
      return { ok: false, reason: 'not_yours', message: '직접 발급하신 키만 다루실 수 있습니다.' };
    }
    var doomed = {};
    var family = familyOf(table, program, row);
    for (var i = 0; i < family.length; i++) { doomed[family[i].key] = true; }
    table.rows = table.rows.filter(function (r) {
      return !(r.program === program && doomed[r.key]);
    });
    writeTable(table);
    log('delete', program, key + ' (' + Object.keys(doomed).length + '개)');
    return { ok: true, deleted: Object.keys(doomed).length };
  } finally {
    lock.releaseLock();
  }
}
function adminResetAll(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var confirm = String(p.confirm || '').trim();
  if (confirm !== '초기화') {
    return { ok: false, reason: 'need_confirm',
             message: '정말 지우시려면 confirm 에 "초기화" 라고 적어 보내 주세요.' };
  }
  var program = String(p.program || '').trim();
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var table = readTable();
    var before = table.rows.length;
    table.rows = program ? table.rows.filter(function (r) { return r.program !== program; }) : [];
    writeTable(table);
    var gone = before - table.rows.length;
    log('reset', program || '(전부)', gone + '개');
    return { ok: true, deleted: gone };
  } finally {
    lock.releaseLock();
  }
}
function whoAmI(p) {
  var given = String(p.token || '');
  if (given && checkAdminToken(given)) { return { ok: true }; }
  if (given && passwordOk(given)) { return { ok: true }; }
  Utilities.sleep(700);
  return { ok: false, reason: 'unauthorized', message: '관리자 비밀번호가 필요합니다.' };
}
function passwordOk(given) {
  var real = prop('ADMIN_PASSWORD');
  if (!real) { return false; }
  return constantEquals(String(given), String(real));
}
function constantEquals(a, b) {
  var diff = a.length ^ b.length;
  var n = Math.max(a.length, b.length);
  for (var i = 0; i < n; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
function makeAdminToken() {
  var until = Date.now() + ADMIN_TOKEN_HOURS * 3600 * 1000;
  return until + '.' + signature(String(until));
}
function checkAdminToken(token) {
  var at = String(token).indexOf('.');
  if (at < 0) { return false; }
  var until = String(token).slice(0, at);
  var sig = String(token).slice(at + 1);
  if (!/^\d+$/.test(until)) { return false; }
  if (Number(until) < Date.now()) { return false; }
  return constantEquals(sig, signature(until));
}
function signature(text) {
  var secret = signingSecret();
  var raw = Utilities.computeHmacSha256Signature(text, secret);
  return raw.map(function (b) {
    return ('0' + (b & 0xff).toString(16)).slice(-2);
  }).join('');
}
function tooManyGuesses(key) {
  var cache = CacheService.getScriptCache();
  var n = Number(cache.get('guess:' + key) || 0);
  return n >= GUESS_LIMIT;
}
function countGuess(key) {
  var cache = CacheService.getScriptCache();
  var n = Number(cache.get('guess:' + key) || 0) + 1;
  cache.put('guess:' + key, String(n), GUESS_WINDOW);
}
function book() {
  if (BOOK_CACHE) { return BOOK_CACHE; }
  var id = prop('SHEET_ID');
  if (id) {
    try { return (BOOK_CACHE = SpreadsheetApp.openById(id)); }
    catch (_) {  }
  }
  try {
    var active = SpreadsheetApp.getActiveSpreadsheet();
    if (active) {
      setProp('SHEET_ID', active.getId());
      return (BOOK_CACHE = active);
    }
  } catch (_) {  }
  var made = SpreadsheetApp.create(SHEET_TITLE);
  setProp('SHEET_ID', made.getId());
  return (BOOK_CACHE = made);
}
function sheetOf(name, headers) {
  var ss = book();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(headers);
  } else if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
  }
  return sh;
}
function readTable() {
  var sh = sheetOf(SHEET_KEYS, COLUMNS);
  var values = sh.getDataRange().getValues();
  var head = values.length ? values[0].map(String) : COLUMNS.slice();
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var raw = values[i];
    if (!String(raw[head.indexOf('key')] || '').trim()) { continue; }
    var row = {};
    for (var c = 0; c < COLUMNS.length; c++) {
      var name = COLUMNS[c];
      var at = head.indexOf(name);
      row[name] = at < 0 ? '' : String(raw[at] == null ? '' : raw[at]);
    }
    rows.push(row);
  }
  return { sheet: sh, rows: rows };
}
function writeTable(table) {
  var sh = table.sheet;
  var out = [COLUMNS.slice()];
  for (var i = 0; i < table.rows.length; i++) {
    var row = table.rows[i];
    var line = [];
    for (var c = 0; c < COLUMNS.length; c++) { line.push(row[COLUMNS[c]] || ''); }
    out.push(line);
  }
  sh.clear();
  sh.getRange(1, 1, out.length, COLUMNS.length).setValues(out);
}
function log(what, program, detail) {
  try {
    var sh = sheetOf(SHEET_LOG, ['때', '무엇', '프로그램', '내용']);
    sh.appendRow([nowIso(), what, program || '', detail || '']);
  } catch (_) {  }
}
function signingSecret() {
  var secret = prop('SIGNING_SECRET');
  if (secret) { return secret; }
  secret = Utilities.getUuid() + Utilities.getUuid();
  setProp('SIGNING_SECRET', secret);
  return secret;
}
function setProp(name, value) {
  try { PropertiesService.getScriptProperties().setProperty(name, String(value)); }
  catch (_) {  }
}
function prop(name) {
  try { return PropertiesService.getScriptProperties().getProperty(name) || ''; }
  catch (_) { return ''; }
}
function programOf(p) {
  var given = String(p.program || '').trim();
  return given || prop('DEFAULT_PROGRAM') || 'default';
}
function nowIso() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', "yyyy-MM-dd'T'HH:mm:ss");
}
function today() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
}
function normalizeKey(text) {
  return String(text || '').trim().toUpperCase().replace(/\s+/g, '');
}
function newKey() {
  var blocks = [];
  for (var b = 0; b < BLOCKS; b++) {
    var one = '';
    for (var i = 0; i < BLOCK; i++) {
      one += ALPHABET.charAt(Math.floor(Math.random() * ALPHABET.length));
    }
    blocks.push(one);
  }
  return blocks.join('-');
}
function uniqueKey(table) {
  for (var tries = 0; tries < 50; tries++) {
    var candidate = newKey();
    var taken = false;
    for (var i = 0; i < table.rows.length; i++) {
      if (table.rows[i].key === candidate) { taken = true; break; }
    }
    if (!taken) { return candidate; }
  }
  throw new Error('키를 못 만들었습니다');
}
function blankRow(program, type) {
  var row = {};
  for (var i = 0; i < COLUMNS.length; i++) { row[COLUMNS[i]] = ''; }
  row.program = program;
  row.type = type;
  row.status = 'active';
  row.issuedDate = today();
  return row;
}
function findKey(table, program, key) {
  var want = normalizeKey(key);
  if (!want) { return null; }
  for (var i = 0; i < table.rows.length; i++) {
    var r = table.rows[i];
    if (r.program === program && normalizeKey(r.key) === want) { return r; }
  }
  return null;
}
function expiryFrom(days) {
  var n = Number(days || 0);
  if (!(n > 0)) { return ''; }
  var when = new Date(Date.now() + n * 86400000);
  return Utilities.formatDate(when, 'Asia/Seoul', 'yyyy-MM-dd');
}
function expired(row) {
  var until = String(row.expiryDate || '').trim();
  if (!until) { return false; }
  return until < today();
}
function unusable(row) {
  if (row.status === 'suspended') {
    return { ok: false, reason: 'suspended', message: '정지된 키입니다. 발급하신 분께 문의해 주세요.' };
  }
  if (expired(row)) {
    return { ok: false, reason: 'expired', message: '유효기간이 지난 키입니다.' };
  }
  return null;
}
function touch(table, row, _unused) {
  row.usedDate = nowIso();
}
function familyOf(table, program, row) {
  if (row.type !== KIND_PRIMARY) { return [row]; }
  var out = [row];
  for (var i = 0; i < table.rows.length; i++) {
    var r = table.rows[i];
    if (r.program === program && normalizeKey(r.parentKey) === normalizeKey(row.key)) {
      out.push(r);
    }
  }
  return out;
}
function publicRow(row) {
  return {
    program: row.program,
    key: row.key,
    type: row.type,
    role: row.role,
    issuedBy: row.issuedBy,
    parentKey: row.parentKey,
    deviceLabel: row.deviceLabel,
    status: row.status,
    issuedDate: row.issuedDate,
    expiryDate: row.expiryDate,
    assignedName: row.assignedName,
    assignedEmail: row.assignedEmail,
    usedDate: row.usedDate,
    live: !!String(row.sessionToken || '')
  };
}
function countRows(rows) {
  var out = { total: rows.length, primary: 0, secondary: 0, legacy: 0,
              admins: 0, clients: 0, suspended: 0, live: 0 };
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    if (r.type === KIND_PRIMARY) { out.primary++; }
    else if (r.type === KIND_SECONDARY) { out.secondary++; }
    else { out.legacy++; }
    if (r.type === KIND_PRIMARY && r.role === ROLE_ADMIN) { out.admins++; }
    if (r.type === KIND_PRIMARY && r.role !== ROLE_ADMIN) { out.clients++; }
    if (r.status === 'suspended') { out.suspended++; }
    if (r.live) { out.live++; }
  }
  return out;
}
function sendInvite(email, name, program, primaryKey, secondaries, url, role, expiry) {
  var lines = [];
  lines.push(name + '님, 안녕하세요.');
  lines.push('');
  lines.push('요청하신 접속키를 보내 드립니다.');
  lines.push('');
  lines.push('  1차키 (사람 한 명당 하나)');
  lines.push('    ' + primaryKey);
  lines.push('');
  lines.push('  2차키 (기기마다 하나씩)');
  for (var i = 0; i < DEVICES.length; i++) {
    lines.push('    ' + DEVICES[i] + ' : ' + secondaries[DEVICES[i]]);
  }
  lines.push('');
  if (url) {
    lines.push('  들어가는 곳');
    lines.push('    ' + url);
    lines.push('');
  }
  lines.push('쓰시는 법');
  lines.push('  1차키는 그대로 두시고, 기기에 맞는 2차키를 함께 넣으세요.');
  lines.push('  PC 에서는 PC 키, 휴대폰에서는 휴대폰 키입니다.');
  lines.push('  같은 2차키를 다른 기기에서 쓰시면 먼저 쓰던 기기가 잠깁니다.');
  if (expiry) {
    lines.push('');
    lines.push('유효기간: ' + expiry + ' 까지');
  }
  if (role === ROLE_ADMIN) {
    lines.push('');
    lines.push('관리자 화면이 함께 열립니다. 그 안에서 고객에게 줄 키를');
    lines.push('직접 발급하실 수 있습니다.');
  }
  lines.push('');
  lines.push('키는 다른 분께 알려 주지 마세요.');
  try {
    var options = { name: prop('MAIL_FROM_NAME') || undefined };
    MailApp.sendEmail(email, '[' + program + '] 접속키를 보내 드립니다', lines.join('\n'), options);
    return true;
  } catch (err) {
    log('mail-fail', program, email + ' — ' + String((err && err.message) || err));
    return false;
  }
}

// ⛳ 여기가 마지막 줄입니다. 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
