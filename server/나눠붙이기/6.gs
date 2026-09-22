// ── 접속키 서버 · 나눠 붙이는 판 6번 / 전체 6장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `6` 로 지은 뒤 통째로 붙이세요.
//  6장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ 6/6 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

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

function adminSendText(p) {
  var who = whoAmI(p);
  if (!who.ok) { return who; }
  if (who.scope !== 'owner') {
    return { ok: false, reason: 'forbidden',
             message: '메일 보내기는 주인만 할 수 있습니다.' };
  }
  var email = String(p.email || '').trim();
  var subject = String(p.subject || '').trim();
  var body = String(p.body || '');
  var html = String(p.html || '');
  if (!email || email.indexOf('@') < 1) {
    return { ok: false, reason: 'bad_email', message: '받는 분 메일 주소를 확인해 주세요.' };
  }
  if (!subject) {
    return { ok: false, reason: 'bad_subject', message: '제목이 비었습니다.' };
  }
  if (!body.trim()) {
    return { ok: false, reason: 'bad_body', message: '본문이 비었습니다.' };
  }
  var 남음 = -1;
  try { 남음 = MailApp.getRemainingDailyQuota(); } catch (_) { }
  if (남음 === 0) {
    return { ok: false, reason: 'quota',
             message: '오늘 보낼 수 있는 메일을 다 썼습니다. 내일 다시 하시거나 ' +
                      '워크스페이스 계정을 쓰세요.' };
  }
  try {
    var 옵션 = { name: prop('MAIL_FROM_NAME') || undefined };
    if (html) { 옵션.htmlBody = html; }
    MailApp.sendEmail(email, subject, body, 옵션);
    log('mail-sent', String(p.program || ''), email);
    return { ok: true, sentTo: email, remaining: 남음 > 0 ? 남음 - 1 : 남음 };
  } catch (err) {
    log('mail-fail', String(p.program || ''), email + ' — ' + String((err && err.message) || err));
    return { ok: false, reason: 'mail_failed',
             message: '보내지 못했습니다. 주소를 확인해 주세요.' };
  }
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

// ⛳ 6/6 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.
