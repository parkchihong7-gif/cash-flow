/**
 * 키 서버 규약 시험.
 *
 * 여기서 도는 것은 사본이 아니라 **올릴 파일 그대로**(../keyserver.gs)다.
 * 구글에 붙이기 전에 여기서 틀린 것을 잡는 것이 목적이다.
 *
 *   node --test server/tests/
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { makeServer } = require('./harness');

const PW = '주인비밀번호7';
const PROPS = {
  ADMIN_PASSWORD: PW,
  SIGNING_SECRET: '서명값-아무거나-길게',
  DEFAULT_PROGRAM: 'exam',
};

/** 주인이 한 사람에게 키 한 벌을 준다. */
function invite(srv, extra = {}) {
  return srv.call(Object.assign({
    action: 'adminCreateInvite', token: PW,
    name: '홍길동', email: 'hong@example.com',
  }, extra));
}

// ── 들어오는 문 ─────────────────────────────────────────────────────

test('모르는 요청은 이름을 되돌려 준다', () => {
  const srv = makeServer(PROPS);
  const out = srv.call({ action: '없는것' });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'unknown_action');
});

test('ping 은 아무나 부를 수 있다', () => {
  const srv = makeServer(PROPS);
  assert.strictEqual(srv.call({ action: 'ping' }).ok, true);
});

test('POST 로 불러도 GET 과 같다', () => {
  const srv = makeServer(PROPS);
  const a = srv.post({ action: 'adminCreateInvite', token: PW, name: '김', email: 'k@example.com' });
  assert.strictEqual(a.ok, true);
  assert.ok(a.primaryKey);
});

// ── 관리자 확인 ─────────────────────────────────────────────────────

test('비밀번호 없이는 목록을 못 본다', () => {
  const srv = makeServer(PROPS);
  const out = srv.call({ action: 'adminList' });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'unauthorized');
  assert.ok(!out.rows, '막혔는데 목록이 딸려 나왔습니다');
});

test('틀린 비밀번호로는 못 들어온다', () => {
  const srv = makeServer(PROPS);
  assert.strictEqual(srv.call({ action: 'adminList', token: '틀린것' }).ok, false);
});

test('ADMIN_PASSWORD 를 안 정해 두면 아무도 못 들어온다', () => {
  // 빈 값을 비밀번호로 삼으면 주소만 아는 사람이 전부 가져간다.
  const srv = makeServer({ SIGNING_SECRET: 'x' });
  assert.strictEqual(srv.call({ action: 'adminList', token: '' }).ok, false);
  assert.strictEqual(srv.call({ action: 'adminList' }).ok, false);
});

test('로그인하면 표를 주고, 그 표로 일을 볼 수 있다', () => {
  const srv = makeServer(PROPS);
  const login = srv.call({ action: 'adminLogin', password: PW });
  assert.strictEqual(login.ok, true);
  assert.ok(login.token.includes('.'), '표가 서명 모양이 아닙니다');
  assert.strictEqual(srv.call({ action: 'adminList', token: login.token }).ok, true);
});

test('표를 손대면 안 먹는다', () => {
  const srv = makeServer(PROPS);
  const token = srv.call({ action: 'adminLogin', password: PW }).token;
  const [until, sig] = token.split('.');
  const 위조 = `${Number(until) + 86400000}.${sig}`;   // 기한만 늘려 본다
  assert.strictEqual(srv.call({ action: 'adminList', token: 위조 }).ok, false);
});

test('기한이 지난 표는 안 먹는다', () => {
  const srv = makeServer(PROPS);
  const 과거 = String(Date.now() - 1000);
  // 서명은 맞지만 기한이 지난 표. 서명만 보고 통과시키면 안 된다.
  const sig = srv.sandbox.signature(과거);
  assert.strictEqual(srv.call({ action: 'adminList', token: `${과거}.${sig}` }).ok, false);
});

// ── 키 한 벌 주기 ───────────────────────────────────────────────────

test('한 벌은 1차키 1개 + 2차키 3개(PC·노트북·휴대폰)', () => {
  const srv = makeServer(PROPS);
  const out = invite(srv);
  assert.strictEqual(out.ok, true);
  assert.match(out.primaryKey, /^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  assert.deepStrictEqual(Object.keys(out.secondaryKeys), ['PC', '노트북', '휴대폰']);
  for (const k of Object.values(out.secondaryKeys)) {
    assert.match(k, /^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  }
});

test('키에는 헷갈리는 글자가 없다', () => {
  const srv = makeServer(PROPS);
  const 전부 = [];
  for (let i = 0; i < 30; i++) {
    const out = invite(srv, { email: `x${i}@example.com` });
    전부.push(out.primaryKey, ...Object.values(out.secondaryKeys));
  }
  for (const key of 전부) {
    assert.ok(!/[0O1IL]/.test(key), `전화로 못 불러 주는 글자가 들었습니다: ${key}`);
  }
});

test('이름이나 이메일이 없으면 만들지 않는다', () => {
  const srv = makeServer(PROPS);
  assert.strictEqual(invite(srv, { name: '' }).reason, 'no_name');
  assert.strictEqual(invite(srv, { email: '주소아님' }).reason, 'bad_email');
});

test('이메일로 키를 보낸다', () => {
  const srv = makeServer(PROPS);
  const out = invite(srv, { baseUrl: 'https://example.com/exam/' });
  assert.strictEqual(out.mailed, true);
  assert.strictEqual(srv.mails.length, 1);
  const mail = srv.mails[0];
  assert.strictEqual(mail.to, 'hong@example.com');
  assert.ok(mail.body.includes(out.primaryKey), '메일에 1차키가 없습니다');
  for (const k of Object.values(out.secondaryKeys)) {
    assert.ok(mail.body.includes(k), '메일에 2차키가 빠졌습니다');
  }
  assert.ok(mail.body.includes('https://example.com/exam/'), '들어가는 곳이 없습니다');
});

test('메일이 안 나가도 키는 남고, 화면이 그것을 받는다', () => {
  // 하루 발송 한도를 넘으면 여기서 막힌다. 그때 키까지 사라지면
  // 사장님은 고객에게 줄 것이 없어진다.
  const srv = makeServer(Object.assign({}, PROPS, { __MAIL_FAILS__: true }));
  const out = invite(srv);
  assert.strictEqual(out.ok, true);
  assert.strictEqual(out.mailed, false);
  assert.ok(out.primaryKey, '메일이 막히자 키까지 안 나왔습니다');
  assert.ok(out.message.includes('직접 보내'), '어떻게 하라는 말이 없습니다');
});

// ── 문 열기 ─────────────────────────────────────────────────────────

test('1차키와 2차키를 함께 내면 열린다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const out = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey,
                         key2: 한벌.secondaryKeys.PC });
  assert.strictEqual(out.ok, true);
  assert.ok(out.sessionToken);
  assert.strictEqual(out.deviceLabel, 'PC');
  assert.strictEqual(out.name, '홍길동');
});

test('소문자로 넣어도 열린다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const out = srv.call({ action: 'validateKeyPair',
                         key1: 한벌.primaryKey.toLowerCase(),
                         key2: ' ' + 한벌.secondaryKeys.PC.toLowerCase() + ' ' });
  assert.strictEqual(out.ok, true);
});

test('1차키만 내면 2차키를 달라고 한다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const out = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'no_secondary');
});

test('짝이 안 맞는 2차키는 막는다', () => {
  const srv = makeServer(PROPS);
  const 갑 = invite(srv, { email: 'a@example.com' });
  const 을 = invite(srv, { email: 'b@example.com' });
  const out = srv.call({ action: 'validateKeyPair', key1: 갑.primaryKey,
                         key2: 을.secondaryKeys.PC });
  assert.strictEqual(out.reason, 'pair_mismatch');
});

test('없는 2차키', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const out = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey,
                         key2: 'ZZZZ-ZZZZ-ZZZZ' });
  assert.strictEqual(out.reason, 'secondary_not_found');
});

// ── 기기당 한 세션 ──────────────────────────────────────────────────

test('같은 2차키를 다른 기기에서 쓰면 먼저 기기가 잠긴다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const 먼저 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey,
                          key2: 한벌.secondaryKeys.PC });
  assert.strictEqual(
    srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC,
               sessionToken: 먼저.sessionToken }).ok, true);

  const 나중 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey,
                          key2: 한벌.secondaryKeys.PC });
  assert.notStrictEqual(나중.sessionToken, 먼저.sessionToken);

  const 확인 = srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC,
                          sessionToken: 먼저.sessionToken });
  assert.strictEqual(확인.ok, false);
  assert.strictEqual(확인.reason, 'session_replaced');
});

test('기기가 다르면(2차키가 다르면) 둘 다 살아 있다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const pc = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });
  const 폰 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys['휴대폰'] });
  assert.strictEqual(srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC, sessionToken: pc.sessionToken }).ok, true);
  assert.strictEqual(srv.call({ action: 'checkSession', key: 한벌.secondaryKeys['휴대폰'], sessionToken: 폰.sessionToken }).ok, true);
});

// ── 정지·삭제 ───────────────────────────────────────────────────────

test('1차키를 정지하면 이미 들어와 있던 기기도 끊긴다', () => {
  // 1차키만 막고 2차키를 살려 두면, 정지해 놓았는데 그대로 쓰게 된다.
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const 세션 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });

  assert.strictEqual(srv.call({ action: 'adminSuspendKey', token: PW, key: 한벌.primaryKey }).ok, true);

  const 확인 = srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC, sessionToken: 세션.sessionToken });
  assert.strictEqual(확인.ok, false);
  assert.strictEqual(확인.reason, 'suspended');
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC }).reason,
    'suspended');
});

test('정지를 풀면 다시 들어갈 수 있다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  srv.call({ action: 'adminSuspendKey', token: PW, key: 한벌.primaryKey });
  srv.call({ action: 'adminResumeKey', token: PW, key: 한벌.primaryKey });
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC }).ok, true);
});

test('1차키를 지우면 딸린 2차키도 함께 사라진다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const out = srv.call({ action: 'adminDeleteKey', token: PW, key: 한벌.primaryKey });
  assert.strictEqual(out.deleted, 4, '1차 1 + 2차 3 이 아닙니다');
  assert.strictEqual(srv.call({ action: 'adminList', token: PW }).rows.length, 0);
});

test('초기화는 "초기화" 라고 적어야 움직인다', () => {
  const srv = makeServer(PROPS);
  invite(srv);
  const 그냥 = srv.call({ action: 'adminResetAll', token: PW });
  assert.strictEqual(그냥.ok, false);
  assert.strictEqual(그냥.reason, 'need_confirm');
  assert.strictEqual(srv.call({ action: 'adminList', token: PW }).rows.length, 4, '안 지운다더니 지웠습니다');

  const 진짜 = srv.call({ action: 'adminResetAll', token: PW, confirm: '초기화' });
  assert.strictEqual(진짜.deleted, 4);
  assert.strictEqual(srv.call({ action: 'adminList', token: PW }).rows.length, 0);
});

// ── 16종이 한 서버를 같이 쓴다 ──────────────────────────────────────

test('프로그램이 다르면 키가 섞이지 않는다', () => {
  const srv = makeServer(PROPS);
  const 갑 = invite(srv, { program: 'exam', email: 'a@example.com' });
  const 을 = invite(srv, { program: 'agency-kit', email: 'b@example.com' });

  // 갑의 키로 을의 프로그램 문을 열면 안 된다.
  const 넘본다 = srv.call({ action: 'validateKeyPair', program: 'agency-kit',
                            key1: 갑.primaryKey, key2: 갑.secondaryKeys.PC });
  assert.strictEqual(넘본다.ok, false);
  assert.strictEqual(넘본다.reason, 'not_found');

  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', program: 'exam', key1: 갑.primaryKey, key2: 갑.secondaryKeys.PC }).ok, true);
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', program: 'agency-kit', key1: 을.primaryKey, key2: 을.secondaryKeys.PC }).ok, true);
});

test('한 프로그램만 초기화할 수 있다', () => {
  const srv = makeServer(PROPS);
  invite(srv, { program: 'exam', email: 'a@example.com' });
  invite(srv, { program: 'agency-kit', email: 'b@example.com' });
  srv.call({ action: 'adminResetAll', token: PW, program: 'exam', confirm: '초기화' });
  const 남은것 = srv.call({ action: 'adminList', token: PW }).rows;
  assert.strictEqual(남은것.length, 4);
  assert.ok(남은것.every((r) => r.program === 'agency-kit'));
});

test('program 을 안 보내는 옛 화면은 기본 프로그램으로 본다', () => {
  const srv = makeServer(PROPS);   // DEFAULT_PROGRAM = exam
  const 한벌 = invite(srv);        // program 없이
  const rows = srv.call({ action: 'adminList', token: PW }).rows;
  assert.ok(rows.every((r) => r.program === 'exam'));
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC }).ok, true);
});

// ── 이중 판매 (산 사람이 자기 고객에게) ─────────────────────────────

test('산 사람은 고객키를 만들 수 있다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = invite(srv, { role: 'admin', name: '김학원장', email: 'kim@example.com' });
  const 수강생 = srv.call({ action: 'adminCreateInvite', token: PW,
                            name: '이수강생', email: 'lee@example.com',
                            role: 'client', issuedBy: 학원장.primaryKey });
  assert.strictEqual(수강생.ok, true);
  assert.ok(수강생.primaryKey);
});

test('산 사람이 관리자키를 찍어 내지는 못한다', () => {
  // 허용하면 한 번 판 것이 끝없이 재판매된다.
  const srv = makeServer(PROPS);
  const 학원장 = invite(srv, { role: 'admin', name: '김학원장', email: 'kim@example.com' });
  const out = srv.call({ action: 'adminCreateInvite', token: PW,
                         name: '다른학원', email: 'x@example.com',
                         role: 'admin', issuedBy: 학원장.primaryKey });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'not_allowed');
});

test('정지된 관리자는 새 고객키를 못 만든다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = invite(srv, { role: 'admin', name: '김', email: 'kim@example.com' });
  srv.call({ action: 'adminSuspendKey', token: PW, key: 학원장.primaryKey });
  const out = srv.call({ action: 'adminCreateInvite', token: PW, name: '이', email: 'lee@example.com',
                         role: 'client', issuedBy: 학원장.primaryKey });
  assert.strictEqual(out.reason, 'issuer_unusable');
});

test('학원 A 는 학원 B 의 고객 명단을 못 본다', () => {
  const srv = makeServer(PROPS);
  const A = invite(srv, { role: 'admin', name: 'A학원', email: 'a@example.com' });
  const B = invite(srv, { role: 'admin', name: 'B학원', email: 'b@example.com' });
  srv.call({ action: 'adminCreateInvite', token: PW, name: 'A의학생', email: 'a1@example.com',
             role: 'client', issuedBy: A.primaryKey });
  srv.call({ action: 'adminCreateInvite', token: PW, name: 'B의학생', email: 'b1@example.com',
             role: 'client', issuedBy: B.primaryKey });

  const A가본다 = srv.call({ action: 'adminList', token: PW, issuer: A.primaryKey }).rows;
  assert.strictEqual(A가본다.length, 4);
  assert.ok(A가본다.every((r) => r.assignedName === 'A의학생'),
            'A 의 화면에 남의 고객이 보입니다');
});

test('학원 A 는 학원 B 의 키를 정지·삭제하지 못한다', () => {
  const srv = makeServer(PROPS);
  const A = invite(srv, { role: 'admin', name: 'A학원', email: 'a@example.com' });
  const B = invite(srv, { role: 'admin', name: 'B학원', email: 'b@example.com' });
  const B의학생 = srv.call({ action: 'adminCreateInvite', token: PW, name: 'B의학생',
                             email: 'b1@example.com', role: 'client', issuedBy: B.primaryKey });

  const 정지 = srv.call({ action: 'adminSuspendKey', token: PW, key: B의학생.primaryKey, issuer: A.primaryKey });
  assert.strictEqual(정지.reason, 'not_yours');
  const 삭제 = srv.call({ action: 'adminDeleteKey', token: PW, key: B의학생.primaryKey, issuer: A.primaryKey });
  assert.strictEqual(삭제.reason, 'not_yours');

  // B 의 학생은 그대로 들어갈 수 있어야 한다.
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: B의학생.primaryKey, key2: B의학생.secondaryKeys.PC }).ok, true);
});

// ── 레거시 단일키 ───────────────────────────────────────────────────

test('레거시 키는 혼자서 열린다', () => {
  const srv = makeServer(PROPS);
  const out = srv.call({ action: 'adminCreateKeys', token: PW, count: 3 });
  assert.strictEqual(out.keys.length, 3);
  const 열림 = srv.call({ action: 'validateKeyPair', key1: out.keys[0] });
  assert.strictEqual(열림.ok, true);
  assert.strictEqual(열림.legacy, true);
});

test('한 번에 만들 수 있는 수에 상한이 있다', () => {
  const srv = makeServer(PROPS);
  const out = srv.call({ action: 'adminCreateKeys', token: PW, count: 5000 });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'too_many');
});

// ── 유효기간 ────────────────────────────────────────────────────────

test('기간이 지난 키는 안 열린다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  // 장부에서 만료일만 어제로 돌린다.
  const sheet = srv.sheet('keys');
  const head = sheet.values[0];
  const at = head.indexOf('expiryDate');
  const 어제 = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  for (let i = 1; i < sheet.values.length; i++) { sheet.values[i][at] = 어제; }

  const out = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'expired');
});

// ── 새어 나갈 자리 ──────────────────────────────────────────────────

test('목록에 남의 세션 표가 딸려 나오지 않는다', () => {
  // 이게 새면 그 표로 남의 자리에 그대로 앉을 수 있다.
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });
  const rows = srv.call({ action: 'adminList', token: PW }).rows;
  const 글 = JSON.stringify(rows);
  assert.ok(!글.includes('sessionToken'), '세션 표 칸이 그대로 나갔습니다');
  assert.ok(!글.includes('uuid-'), '세션 표 값이 그대로 나갔습니다');
  assert.ok(rows.some((r) => r.live === true), '누가 들어와 있는지는 보여야 합니다');
});

test('여러 번 찍어 보면 막는다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  let 마지막;
  for (let i = 0; i < 12; i++) {
    마지막 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 'AAAA-BBBB-CCCC' });
  }
  assert.strictEqual(마지막.reason, 'too_many_attempts');
});

test('서버가 터져도 속사정을 밖으로 내지 않는다', () => {
  const srv = makeServer(PROPS);
  // 장부를 못 읽게 만든다.
  srv.sandbox.SpreadsheetApp.getActiveSpreadsheet = () => { throw new Error('시트 abc123 를 못 엽니다'); };
  const out = srv.call({ action: 'validateKeyPair', key1: 'AAAA-BBBB-CCCC', key2: 'DDDD-EEEE-FFFF' });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'server_error');
  assert.ok(!JSON.stringify(out).includes('abc123'), '시트 id 가 밖으로 샜습니다');
});

// ── 뒷정리 ──────────────────────────────────────────────────────────

test('자물쇠를 쥔 채로 끝나지 않는다', () => {
  // 놓지 않으면 다음 요청이 20초를 기다렸다 실패한다.
  const srv = makeServer(PROPS);
  invite(srv);
  srv.call({ action: 'adminCreateInvite', token: PW, name: '', email: 'x@example.com' });  // 도중에 튕기는 길
  srv.call({ action: 'adminDeleteKey', token: PW, key: '없는키' });
  assert.strictEqual(srv.lockLeaked(), false, '자물쇠를 안 놓고 끝났습니다');
});

test('장부에 머리글이 한 번만 들어간다', () => {
  const srv = makeServer(PROPS);
  invite(srv, { email: 'a@example.com' });
  invite(srv, { email: 'b@example.com' });
  const sheet = srv.sheet('keys');
  const 머리글수 = sheet.values.filter((r) => r[0] === 'program').length;
  assert.strictEqual(머리글수, 1);
  assert.strictEqual(sheet.values.length, 1 + 8);
});

// ── 시트를 손으로 고쳤을 때 ─────────────────────────────────────────
//
// 장부가 구글 시트라는 것은, 사장님이 거기서 직접 고치실 수 있다는 뜻이다.
// 1차키 줄만 골라 status 를 suspended 로 바꾸시는 일이 실제로 생긴다.
// 그때 2차키가 그대로 열리면, 막은 뜻이 없다.

/** 시트에서 한 줄의 한 칸만 손으로 고친다. */
function 손으로고침(srv, key, column, value) {
  const sheet = srv.sheet('keys');
  const head = sheet.values[0];
  const keyAt = head.indexOf('key');
  const at = head.indexOf(column);
  for (let i = 1; i < sheet.values.length; i++) {
    if (sheet.values[i][keyAt] === key) { sheet.values[i][at] = value; return true; }
  }
  throw new Error('그런 키가 장부에 없습니다: ' + key);
}

test('시트에서 1차키만 손으로 정지시켜도 2차키가 막힌다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const 세션 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });

  손으로고침(srv, 한벌.primaryKey, 'status', 'suspended');   // 2차키 줄은 그대로 둔다

  const 확인 = srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC, sessionToken: 세션.sessionToken });
  assert.strictEqual(확인.ok, false, '1차키를 막았는데 이미 들어와 있던 기기가 그대로 씁니다');
  assert.strictEqual(확인.reason, 'suspended');
});

test('시트에서 1차키 기간만 손으로 줄여도 2차키가 막힌다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = invite(srv);
  const 세션 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys.PC });

  const 어제 = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  손으로고침(srv, 한벌.primaryKey, 'expiryDate', 어제);

  const 확인 = srv.call({ action: 'checkSession', key: 한벌.secondaryKeys.PC, sessionToken: 세션.sessionToken });
  assert.strictEqual(확인.ok, false, '1차키 기간이 끝났는데 2차키가 그대로 열려 있습니다');
  assert.strictEqual(확인.reason, 'expired');
});
