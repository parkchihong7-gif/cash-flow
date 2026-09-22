// ── 접속키 서버 · 나눠 붙이는 판 3번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `3` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 3/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

var ADMIN_HTML_3 = `      copy.onclick = function () {
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
          지우기("sessionStorage", TOKEN_KEY);
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
  var 다음 = 새로만듦 ? [
    '  다음 할 일',
    '   1. 오른쪽 위 [배포] → [새 배포] → 유형 **웹 앱**',
    '   2. 다음 사용자로 실행: **나**',
    '      액세스 권한이 있는 사용자: **모든 사용자**',
    '   3. 나오는 주소를 열면 **관리자 화면**이 바로 뜹니다.',
    '      위 비밀번호를 넣으시면 키를 발급하실 수 있습니다.'
  ] : [
    '  다음 할 일 — 코드만 새로 올리기',
    '',
    '   ⚠ [새 배포] 를 누르지 마세요. **주소가 바뀝니다.**',
    '     이미 알려 드린 주소가 죽어서, 판 키가 전부 안 먹는 것처럼 보입니다.',
    '',
    '   1. 오른쪽 위 [배포] → [배포 관리]',
    '   2. 그 창 **오른쪽 위**의 연필(✏️) — 점 세 개 옆에 작게 있습니다.',
    '      연필을 누르기 전에는 「버전」 칸이 회색이라 안 눌립니다.',
    '   3. 버전: **새 버전** → [배포]',
    '',
    '   아직 한 번도 배포한 적이 없으시면 그때는 [새 배포] → 웹 앱,',
    '   실행: 나 / 액세스: 모든 사용자 로 하시면 됩니다.'
  ];
  var 줄 = [
    '',
    '════════════════════════════════════════════════',
    (새로만듦 ? '  설치가 끝났습니다.' : '  다시 돌렸습니다. 바뀐 것은 없습니다.'),
    '',
    '  관리자 비밀번호 :  ' + 비밀번호,
    (새로만듦 ? '' : '  (이미 정해 두신 것을 그대로 씁니다)'),
    '',
    '  장부 시트 : ' + 시트.getUrl(),
    ''
  ].concat(다음).concat([
    '════════════════════════════════════════════════',
    ''
  ]);
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
function adminHtml() {
  return ADMIN_HTML_1 + ADMIN_HTML_2 + ADMIN_HTML_3;
}

function servePage() {
  var 화면 = adminHtml();
  if (!화면) {
    return HtmlService.createHtmlOutput(
      '<meta charset="utf-8"><p style="font:15px sans-serif;padding:24px">' +
      '관리자 화면이 안 들어 있는 판입니다. ' +
      '<code>server/keyserver.bundle.gs</code> 를 붙여 넣으세요.</p>');
  }
  return HtmlService.createHtmlOutput(화면)
    .setTitle('접속키 관리자')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function apiCall(payloadJson) {
  var params = {};
  try { params = JSON.parse(payloadJson || '{}'); } catch (_) { params = {}; }
  return handle({ parameter: params }).getContent();
}

// ⛳ 3/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
