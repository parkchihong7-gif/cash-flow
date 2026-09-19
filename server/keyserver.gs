/**
 * 통합 접속키 서버 — 구글 앱스 스크립트 판.
 *
 * 왜 이것인가
 *   화면(GitHub Pages)은 파일만 내어 주는 곳이라 키를 발급할 수 없다.
 *   키 발급은 "어딘가에 적어 두는" 일이라 서버가 있어야 한다. 그 서버를
 *   돈 내고 빌리지 않고 구글 앱스 스크립트로 둔다. 무료이고, 항상 켜져
 *   있고, 구글 시트가 그대로 장부가 되고, Gmail 로 발송까지 된다.
 *
 *   공인중개사 기출문제 프로그램이 이미 이 방식으로 돌고 있다. 그 규약을
 *   그대로 지키면서, 16종이 **한 서버를 같이 쓰도록** program 칸과
 *   이중 판매(관리자키/고객키)를 더한 것이 이 파일이다.
 *
 * 키 구조 (16종 공통 표준)
 *   1차키  사람 한 명당 하나. 동시 접속 수를 세지 않는다.
 *   2차키  1차키 아래 PC·노트북·휴대폰 셋. **기기당 한 세션**이라,
 *          같은 2차키로 다른 기기에서 들어오면 먼저 있던 기기가 잠긴다.
 *   레거시 1차/2차 구분 없이 단독으로 쓰는 옛 방식. 받아만 준다.
 *
 * 파는 구조
 *   role=admin   이 프로그램을 **산 사람**. 자기 고객에게 키를 줄 수 있다.
 *   role=client  그 관리자의 고객. 쓰는 화면만 열린다.
 *   관리자키는 **주인만** 만든다. 산 사람이 관리자를 찍어 내며 재판매하는
 *   길을 막아야 하기 때문이다.
 *
 * 설치
 *   server/README.md 를 보세요. 시트 만들기 → 이 파일 붙이기 → 배포.
 */

// ── 설정 ────────────────────────────────────────────────────────────
// 값은 코드가 아니라 **스크립트 속성**에 둔다. 코드는 저장소에 올라가고,
// 저장소는 공개라서 여기 적으면 비밀번호가 그대로 새어 나간다.
//   파일 → 프로젝트 설정 → 스크립트 속성에서 넣습니다.
//     ADMIN_PASSWORD   관리자 비밀번호 (필수)
//     SIGNING_SECRET   관리자 표를 서명할 값 (필수, 아무 긴 글자)
//     SHEET_ID         장부로 쓸 구글 시트 id (비우면 붙어 있는 시트)
//     DEFAULT_PROGRAM  program 을 안 보내는 옛 화면이 쓸 프로그램 이름
//     MAIL_FROM_NAME   보내는 사람 이름 (비우면 계정 이름)

var SHEET_KEYS = 'keys';
var SHEET_LOG = 'log';

/** 0·O·1·I·L 을 뺐다. 전화로 불러 줄 때 서로 다른 글자를 못 듣는다. */
var ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
var BLOCK = 4;
var BLOCKS = 3;

/** 2차키는 이 셋으로 함께 나간다. 순서가 바뀌면 옛 화면이 못 읽는다. */
var DEVICES = ['PC', '노트북', '휴대폰'];

var ROLE_ADMIN = 'admin';
var ROLE_CLIENT = 'client';

var KIND_PRIMARY = 'primary';
var KIND_SECONDARY = 'secondary';
var KIND_LEGACY = 'legacy';

/** 한 번에 만들 수 있는 최대 개수. 실수로 0 을 더 붙여도 시트가 안 터진다. */
var MAX_BULK = 500;

/** 관리자 표가 살아 있는 시간. */
var ADMIN_TOKEN_HOURS = 12;

/** 키를 틀리게 넣어 볼 수 있는 횟수와 그 창의 길이(초). */
var GUESS_LIMIT = 10;
var GUESS_WINDOW = 600;

/** 시트의 칸 순서. 이 순서가 곧 장부의 머리글이다. */
var COLUMNS = [
  'program',        // 어느 프로그램의 키인가
  'key',            // 키 그 자체
  'type',           // primary / secondary / legacy
  'role',           // admin(산 사람) / client(그 사람의 고객)
  'issuedBy',       // 준 사람의 1차키. 비면 주인이 직접 준 것
  'parentKey',      // 2차키가 딸린 1차키
  'deviceLabel',    // PC / 노트북 / 휴대폰
  'status',         // active / suspended
  'issuedDate',
  'expiryDate',     // 비우면 무제한
  'assignedName',
  'assignedEmail',
  'usedDate',       // 마지막으로 들어온 때
  'sessionToken',   // 지금 이 기기가 쥐고 있는 표
  'sessionAt',
  'note'
];

// ── 들어오는 문 ─────────────────────────────────────────────────────

function doGet(e) { return handle(e); }
function doPost(e) { return handle(e); }

/**
 * 모든 요청이 여기로 온다.
 *
 * GET 과 POST 를 둘 다 받는다. 옛 화면이 GET 으로 부르고 있어서다.
 * 새로 만드는 화면은 POST 를 쓰는 편이 낫다 — GET 은 주소에 값이 실려
 * 실행 기록에 비밀번호가 그대로 남는다.
 */
function handle(e) {
  var p = {};
  try {
    if (e && e.parameter) { for (var k in e.parameter) { p[k] = e.parameter[k]; } }
    if (e && e.postData && e.postData.contents) {
      var body = {};
      try { body = JSON.parse(e.postData.contents); } catch (_) { body = {}; }
      for (var k2 in body) { p[k2] = body[k2]; }
    }
  } catch (_) { /* 빈 요청 */ }

  var action = String(p.action || '');
  try {
    switch (action) {
      // 쓰는 사람 쪽
      case 'ping':             return json({ ok: true, at: nowIso() });
      case 'validateKeyPair':  return json(validateKeyPair(p));
      case 'checkSession':     return json(checkSession(p));
      // 주인·관리자 쪽
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
    // 속사정을 그대로 내보내면 시트 구조가 밖으로 샌다. 사람에게는 한 줄만.
    log('error', action, String((err && err.message) || err));
    return json({ ok: false, reason: 'server_error', message: '서버에서 문제가 났습니다. 잠시 뒤 다시 해 주세요.' });
  }
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── 쓰는 사람: 문 열기 ──────────────────────────────────────────────

/**
 * 1차키(+2차키)로 문을 연다.
 *
 * 2차키를 같이 냈으면 그 기기에 **새 표**를 준다. 같은 2차키를 쥔 다른
 * 기기는 다음 확인 때 `session_replaced` 를 받고 잠긴다. 키를 빌려줘도
 * 기기 수만큼만 쓸 수 있게 하려는 것이다.
 */
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

    // 레거시 단일키는 짝이 없다. 그대로 열어 준다.
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

/**
 * 이 기기가 아직 주인인지 묻는다. 화면이 1분마다 부른다.
 *
 * 1차키가 정지되면 그 아래 2차키도 함께 끊는다. 정지해 놓았는데 이미
 * 들어와 있던 기기가 계속 쓰고 있으면 정지한 뜻이 없다.
 */
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

// ── 주인·관리자 쪽 ──────────────────────────────────────────────────

/**
 * 비밀번호를 확인하고 12시간짜리 표를 준다.
 *
 * 옛 화면은 비밀번호 자체를 매번 보낸다. 그것도 받아 주되, 새 화면은
 * 이 표를 쓰는 편이 낫다 — 주소에 비밀번호가 실려 실행 기록에 남지 않는다.
 */
function adminLogin(p) {
  var given = String(p.password || p.token || '');
  if (!passwordOk(given)) {
    Utilities.sleep(700);   // 빠르게 되물으며 찍어 보는 것을 늦춘다
    return { ok: false, reason: 'bad_password', message: '비밀번호가 올바르지 않습니다.' };
  }
  return { ok: true, token: makeAdminToken(), hours: ADMIN_TOKEN_HOURS };
}

/**
 * 발급한 키 목록.
 *
 * `issuer` 를 내면 **그 사람이 준 것만** 보인다. 학원 A 가 학원 B 의
 * 고객 명단을 보면 안 되기 때문이다.
 */
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

/** 레거시 단일키를 여러 개 한 번에. 1차/2차 구분 없이 단독으로 쓴다. */
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

/**
 * 한 사람에게 1차키 1개 + 2차키 3개를 만들고, 그대로 이메일로 보낸다.
 *
 * role=admin 은 **파는 키**다. 산 사람이 자기 고객에게 줄 키를 만들 때는
 * issuedBy 가 그 사람의 1차키로 들어오는데, 그 경우 관리자키는 만들 수
 * 없다. 허용하면 산 사람이 관리자를 찍어 내며 재판매할 수 있다.
 */
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

    // 산 사람이 발급하는 경우, 그 사람의 1차키가 실제로 쓸 수 있는 것인지 본다.
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

/**
 * 키 하나를 정지하거나 되살린다.
 *
 * 1차키를 정지하면 그 아래 2차키도 함께 정지한다. 1차키만 막고 2차키를
 * 살려 두면, 이미 들어와 있던 기기가 그대로 쓰게 된다.
 */
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

/** 키를 지운다. 1차키를 지우면 딸린 2차키도 함께 사라진다. */
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

/**
 * 전부 지운다. 되돌릴 수 없다.
 *
 * 그래서 `confirm` 에 '초기화' 를 받아야 움직인다. 버튼 한 번 잘못
 * 눌렀다고 판 키가 통째로 사라지면 안 된다.
 */
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

// ── 관리자인지 확인 ─────────────────────────────────────────────────

/**
 * 표를 냈으면 표를, 비밀번호를 냈으면 비밀번호를 본다.
 *
 * 옛 화면이 비밀번호를 그대로 `token` 에 실어 보내고 있어 둘 다 받는다.
 */
function whoAmI(p) {
  var given = String(p.token || '');
  if (given && checkAdminToken(given)) { return { ok: true }; }
  if (given && passwordOk(given)) { return { ok: true }; }
  Utilities.sleep(700);
  return { ok: false, reason: 'unauthorized', message: '관리자 비밀번호가 필요합니다.' };
}

function passwordOk(given) {
  var real = prop('ADMIN_PASSWORD');
  if (!real) { return false; }   // 안 정했으면 아무도 못 들어온다
  return constantEquals(String(given), String(real));
}

/** 길이만 보고 빨리 돌아가면 그것만으로 글자 수가 새어 나간다. */
function constantEquals(a, b) {
  var diff = a.length ^ b.length;
  var n = Math.max(a.length, b.length);
  for (var i = 0; i < n; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

/** 서명한 표. 어디에도 저장하지 않고 다시 계산해서 맞춰 본다. */
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
  var secret = prop('SIGNING_SECRET');
  if (!secret) { return '(서명값을 정해 주세요)'; }
  var raw = Utilities.computeHmacSha256Signature(text, secret);
  return raw.map(function (b) {
    return ('0' + (b & 0xff).toString(16)).slice(-2);
  }).join('');
}

// ── 찍어 보기 막기 ──────────────────────────────────────────────────

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

// ── 장부 (구글 시트) ────────────────────────────────────────────────

function book() {
  var id = prop('SHEET_ID');
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
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

/** 시트를 통째로 읽어 온다. 한 요청 안에서는 이것 한 번만 한다. */
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

/** 통째로 다시 쓴다. 줄 수가 적어 이 편이 단순하고 틀릴 자리가 없다. */
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
  } catch (_) { /* 기록을 못 남겨도 본 일은 계속한다 */ }
}

// ── 잔일 ────────────────────────────────────────────────────────────

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

/** 넣는 사람이 소문자로 쓰든 사이에 공백을 넣든 같은 키로 본다. */
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

/** 같은 키가 두 번 나오면 둘 중 하나는 영영 안 열린다. */
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

/** 못 쓰는 키면 그 이유를, 쓸 수 있으면 null 을 준다. */
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

/** 1차키면 자기와 딸린 2차키 전부, 2차키면 자기만. */
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

/** 밖으로 내보낼 때는 **지금 쥔 표를 뺀다.** 그것이 곧 남의 세션이다. */
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

// ── 이메일 ──────────────────────────────────────────────────────────

/**
 * 키를 보낸다. 못 보내도 **키는 이미 만들어져 있다** — 화면이 그것을
 * 보여 주므로, 복사해서 직접 보내시면 된다.
 */
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

// 노드에서 시험할 때만 쓴다. 앱스 스크립트에는 module 이 없어 그냥 지나간다.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    handle: handle, doGet: doGet, doPost: doPost,
    newKey: newKey, normalizeKey: normalizeKey, constantEquals: constantEquals,
    COLUMNS: COLUMNS, DEVICES: DEVICES, ALPHABET: ALPHABET
  };
}
