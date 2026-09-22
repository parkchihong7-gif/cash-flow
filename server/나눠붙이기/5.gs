// ── 접속키 서버 · 나눠 붙이는 판 5번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `5` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 5/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

function adminSetStatus(p, status) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = programFor(who, p);
  var key = normalizeKey(p.key || '');
  var issuer = issuerOf(who, p);
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
  var program = programFor(who, p);
  var key = normalizeKey(p.key || '');
  var issuer = issuerOf(who, p);
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
  var 막힘 = ownerOnly(who);
  if (막힘) { return 막힘; }
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
  if (given) {
    var 표 = readToken(given);
    if (표) { return 표; }
    if (passwordOk(given)) { return OWNER; }
  }
  Utilities.sleep(700);
  return { ok: false, reason: 'unauthorized', message: '관리자 비밀번호가 필요합니다.' };
}

var OWNER = { ok: true, scope: 'owner', issuer: '' };
function issuerOf(who, p) {
  if (who.scope === 'reseller') { return who.issuer; }
  return normalizeKey(p.issuer || '');
}

function programFor(who, p) {
  if (who.scope === 'reseller') { return who.program; }
  return programOf(p);
}

function ownerOnly(who) {
  if (who.scope === 'owner') { return null; }
  return { ok: false, reason: 'owner_only',
           message: '이것은 프로그램을 만든 쪽에서만 할 수 있습니다.' };
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
  return signedToken(String(Date.now() + ADMIN_TOKEN_HOURS * 3600 * 1000));
}

function makeScopedToken(issuerKey, program) {
  var until = Date.now() + ADMIN_TOKEN_HOURS * 3600 * 1000;
  return signedToken(until + '~' + normalizeKey(issuerKey) + '~' + program);
}

function signedToken(payload) {
  return payload + '.' + signature(payload);
}

function readToken(token) {
  var text = String(token);
  var at = text.lastIndexOf('.');
  if (at < 0) { return null; }
  var payload = text.slice(0, at);
  var sig = text.slice(at + 1);
  if (!constantEquals(sig, signature(payload))) { return null; }
  var 칸 = payload.split('~');
  if (!/^\d+$/.test(칸[0])) { return null; }
  if (Number(칸[0]) < Date.now()) { return null; }
  if (칸.length === 1) { return OWNER; }
  if (칸.length !== 3) { return null; }
  return { ok: true, scope: 'reseller',
           issuer: normalizeKey(칸[1]), program: 칸[2] };
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

// ⛳ 5/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
