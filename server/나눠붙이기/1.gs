// ── 접속키 서버 · 나눠 붙이는 판 1번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `1` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 1/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

var ADMIN_HTML_1 = `<!DOCTYPE html>
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
  <p class="sub" id="whoami">여기서 발급하면 그 자리에서 이메일이 나갑니다.</p>
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
  <h2>들어가기</h2>
  <div class="row" style="margin-bottom:14px">
    <div class="narrow"><button class="quiet" id="tabOwner">주인 — 비밀번호</button></div>
    <div class="narrow"><button class="quiet" id="tabReseller">산 분 — 접속키</button></div>
  </div>
  <div id="byPw">
    <div class="row">
      <div><input type="password" id="pw" placeholder="관리자 비밀번호" autocomplete="current-password"></div>
      <div class="narrow"><button id="loginBtn">들어가기</button></div>
    </div>
  </div>
  <div id="byKey" class="hide">
    <p class="sub" style="margin-bottom:12px">
      이 프로그램을 <strong>사신 분</strong>이 자기 고객에게 키를 주실 때 쓰는 자리입니다.
      받으신 <strong>1차키와 2차키</strong>를 넣으세요.
    </p>
    <div class="row">
      <div><label for="keyProgram">무슨 프로그램</label>
        <select id="keyProgram"></select></div>
      <div><label for="k1">1차키</label><input id="k1" placeholder="XXXX-XXXX-XXXX"></div>
      <div><label for="k2">2차키 (이 기기 것)</label><input id="k2" placeholder="XXXX-XXXX-XXXX"></div>
      <div class="narrow"><button id="keyLoginBtn">들어가기</button></div>
    </div>
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
  <section id="issueBox">
    <h2>키 주기 — 1차키 1개 + 2차키 3개(PC·노트북·휴대폰)</h2>
    <p class="warn hide" id="resellerNote">
      <strong>고객용 키만 만드실 수 있습니다.</strong>
      여기서 만든 키를 받은 분은 <strong>쓰는 화면만</strong> 열립니다 —
      그분이 또 키를 파실 수는 없습니다.
      목록에도 <strong>직접 발급하신 것만</strong> 보입니다.
    </p>
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
    </div>
    <div class="row" style="margin-top:10px">
      <div>
        <label for="door" id="doorLabel">들어가는 곳 (메일에 이 주소가 적힙니다)</label>
        <input type="url" id="door" placeholder="https://… (비우면 메일에 주소가 안 적힙니다)">
      </div>
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
  <section id="resetBox">
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
    "id": "exam-drill",
    "name": "공인중개사 기출문제",
    "url": "https://parkchihong7-gif.github.io/gongin-jungsagsa-exam/",
    "adminUrl": "https://parkchihong7-gif.github.io/gongin-jungsagsa-exam/?admin=1"
  },
  {
    "id": "senior-video",
    "name": "시니어 영상 비용 견적·절감기"
  },
  {
    "id": "naver-blog",
    "name": "네이버 블로그 초안 생성기",
    "url": "https://maim-1048530680370.us-central1.run.app/",
    "adminUrl": "https://maim-1048530680370.us-central1.run.app/"
  },
  {
    "id": "speaker-desk",
    "name": "해외 연사 초청 관리"
  },
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
  //: 지금 들어온 사람이 주인인지 산 분인지. 화면이 달라진다.
  var SCOPE_KEY = "keyserver.scope";
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
  /**
   * 브라우저 저장소는 막힐 수 있다.
   *
   * 구글이 이 화면을 **샌드박스 안**에서 내어 주는데, 브라우저 설정이나
   * 시크릿 창에서는 localStorage 를 읽는 것만으로 예외가 난다. 감싸지
   * 않으면 그 한 줄에서 전체가 죽고, 화면은 아무 말 없이 빈 채로 남는다.
   * 막혀 있으면 이번 창에서만 기억한다 — 쓰는 데는 지장이 없다.
   */
  // 쿠키를 막아 둔 브라우저에서는 \`window.localStorage\` **에 닿는 것만으로**
  // 예외가 난다. 그래서 창고 자체를 넘기면 안 된다 — 이름만 넘기고,
  // 닿는 일까지 try 안에서 한다.
  var 기억 = {};
  function 꺼내기(창고이름, 이름) {
    try {
      var 값 = window[창고이름].getItem(이름);
      if (값 !== null) { return 값; }
    } catch (_) { /* 막혀 있다 */ }
    return 기억[이름] || "";
  }
  function 넣기(창고이름, 이름, 값) {
    기억[이름] = 값;`;

// ⛳ 1/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
