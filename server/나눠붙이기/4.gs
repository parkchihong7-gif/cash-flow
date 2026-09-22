// ── 접속키 서버 · 나눠 붙이는 판 4번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `4` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 4/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

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
      case 'resellerLogin':    return json(resellerLogin(p));
      case 'adminList':        return json(adminList(p));
      case 'adminCreateKeys':  return json(adminCreateKeys(p));
      case 'adminCreateInvite':return json(adminCreateInvite(p));
      case 'adminSendText':    return json(adminSendText(p));
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

function resellerLogin(p) {
  var program = programOf(p);
  var key1 = normalizeKey(p.key1 || '');
  var key2 = normalizeKey(p.key2 || '');
  if (!key1 || !key2) {
    return { ok: false, reason: 'need_pair', message: '1차키와 2차키를 함께 넣어 주세요.' };
  }
  var 열림 = validateKeyPair({ program: program, key1: key1, key2: key2 });
  if (!열림.ok) { return 열림; }
  if (열림.role !== ROLE_ADMIN) {
    return { ok: false, reason: 'not_admin',
             message: '고객용 키로는 발급 화면이 열리지 않습니다.' };
  }
  return { ok: true, token: makeScopedToken(key1, program), name: 열림.name,
           program: program, hours: ADMIN_TOKEN_HOURS };
}

function adminList(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  var program = who.scope === 'reseller' ? who.program : String(p.program || '').trim();
  var issuer = issuerOf(who, p);
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
  var 막힘 = ownerOnly(who);
  if (막힘) { return 막힘; }
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
  var program = programFor(who, p);
  var name = String(p.name || '').trim();
  var email = String(p.email || '').trim();
  var role = String(p.role || ROLE_ADMIN);
  var issuedBy = normalizeKey(p.issuedBy || '');
  var baseUrl = String(p.baseUrl || '').trim();
  if (who.scope === 'reseller') {
    role = ROLE_CLIENT;
    issuedBy = who.issuer;
  }
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

// ⛳ 4/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
