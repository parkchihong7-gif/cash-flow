/**
 * 손질한 안내문을 그대로 보내는 길 (`adminSendText`).
 *
 * `sendInvite` 는 글을 서버가 만든다. 그러면 보내는 사람이 한 글자도 못
 * 고친다 — 고객마다 덧붙일 말이 다른데 그걸 할 수가 없다. 이 길은
 * 대시보드가 완성된 글을 넘기면 그대로 보낸다.
 *
 * **아무나 쓰게 하면 스팸 발송기가 된다.** 그래서 주인만이다.
 */
const test = require('node:test');
const assert = require('node:assert');
const { makeServer } = require('./harness');

const PW = 'TEST-PASS-1234';

function 주인으로(props = {}) {
  const s = makeServer({ ADMIN_PASSWORD: PW, ...props });
  return s;
}

test('주인은 손질한 글을 그대로 보낼 수 있다', () => {
  const s = 주인으로();
  const 답 = s.call({ action: 'adminSendText', token: PW,
                      email: 'a@b.example', subject: '안내', body: '본문입니다' });
  assert.equal(답.ok, true);
  assert.equal(답.sentTo, 'a@b.example');

  assert.equal(s.mails.length, 1);
  assert.equal(s.mails[0].to, 'a@b.example');
  assert.equal(s.mails[0].subject, '안내');
  assert.equal(s.mails[0].body, '본문입니다', '글을 고치지 말고 그대로 보내야 한다');
});

test('산 분은 못 보낸다 — 열어 주면 스팸 발송기가 된다', () => {
  const s = 주인으로();
  // 판매 키를 하나 만들고 그 사람으로 들어온다.
  const 발급 = s.call({ action: 'adminCreateInvite', token: PW,
                        name: '산분', email: 'buyer@b.example',
                        role: 'admin', program: 'p1' });
  assert.equal(발급.ok, true);
  // 산 분은 **1차키와 2차키를 함께** 넣어야 들어온다 (이중키).
  const 로그인 = s.call({ action: 'resellerLogin', program: 'p1',
                          key1: 발급.primaryKey, key2: 발급.secondaryKeys.PC });
  assert.equal(로그인.ok, true, JSON.stringify(로그인));

  const 답 = s.call({ action: 'adminSendText', token: 로그인.token,
                      email: 'victim@b.example', subject: 'x', body: 'y' });
  assert.equal(답.ok, false);
  assert.equal(답.reason, 'forbidden');
});

test('비밀번호 없이 못 보낸다', () => {
  const s = 주인으로();
  const 답 = s.call({ action: 'adminSendText', email: 'a@b.example',
                      subject: 'x', body: 'y' });
  assert.equal(답.ok, false);
  assert.equal(답.reason, 'unauthorized');
  assert.equal(s.mails.length, 0);
});

test('빈 값은 거절한다', () => {
  const s = 주인으로();
  for (const [바꿀것, 이유] of [[{ email: '' }, 'bad_email'],
                                 [{ email: '골뱅이없음' }, 'bad_email'],
                                 [{ subject: '' }, 'bad_subject'],
                                 [{ body: '   ' }, 'bad_body']]) {
    const 답 = s.call({ action: 'adminSendText', token: PW,
                        email: 'a@b.example', subject: '제목', body: '본문',
                        ...바꿀것 });
    assert.equal(답.ok, false);
    assert.equal(답.reason, 이유);
  }
  assert.equal(s.mails.length, 0);
});

test('하루 한도를 다 썼으면 무엇을 해야 하는지 알려 준다', () => {
  const s = 주인으로({ __QUOTA__: 0 });
  const 답 = s.call({ action: 'adminSendText', token: PW,
                      email: 'a@b.example', subject: 'x', body: 'y' });
  assert.equal(답.ok, false);
  assert.equal(답.reason, 'quota');
  assert.match(답.message, /워크스페이스/, '무엇을 하면 되는지 적혀 있어야 한다');
  assert.equal(s.mails.length, 0);
});

test('보내다 실패하면 속사정을 흘리지 않는다', () => {
  const s = 주인으로({ __MAIL_FAILS__: true });
  const 답 = s.call({ action: 'adminSendText', token: PW,
                      email: 'a@b.example', subject: 'x', body: 'y' });
  assert.equal(답.ok, false);
  assert.equal(답.reason, 'mail_failed');
  assert.ok(!/한도를 넘었습니다/.test(답.message), '예외 문구가 그대로 나가면 안 된다');
});
