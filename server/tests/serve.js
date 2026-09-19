/**
 * 시험용 서버 — 관리자 화면을 진짜로 눌러 보기 위한 것.
 *
 * `web/` 의 파일을 내어 주고, `/exec` 로 오는 요청은 keyserver.gs 에 그대로
 * 넘긴다. 구글에 올리기 전에 화면과 서버가 서로 말이 통하는지 여기서 본다.
 *
 * 화면과 서버를 **같은 주소**에서 내어 준다. 진짜 앱스 스크립트는 다른
 * 주소에 있지만, 그쪽은 `Access-Control-Allow-Origin: *` 을 붙여 주고
 * 우리 요청은 Content-Type 이 text/plain 이라 브라우저가 미리 묻지 않는다
 * (preflight 가 안 생긴다). 그래서 여기서 한 주소로 시험해도 뜻이 같다.
 *
 *   node server/tests/serve.js 8790
 */

'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { makeServer } = require('./harness');

const WEB = path.join(__dirname, '..', '..', 'web');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

function start(port, props) {
  const srv = makeServer(props);

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);

    if (url.pathname === '/exec') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', () => {
        let params = {};
        for (const [k, v] of url.searchParams) { params[k] = v; }
        if (body) {
          try { Object.assign(params, JSON.parse(body)); } catch (_) { /* 폼 모양은 안 쓴다 */ }
        }
        const out = srv.call(params);
        res.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
          'Access-Control-Allow-Origin': '*',
        });
        res.end(JSON.stringify(out));
      });
      return;
    }

    // 정적 파일. 시험용이라 web/ 밖으로는 못 나가게만 막는다.
    const name = url.pathname === '/' ? '/admin.html' : url.pathname;
    const file = path.join(WEB, path.normalize(name).replace(/^(\.\.[/\\])+/, ''));
    if (!file.startsWith(WEB)) { res.writeHead(403); res.end('no'); return; }
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end('없습니다'); return; }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });

  server.listen(port);
  return { server, srv };
}

if (require.main === module) {
  const port = Number(process.argv[2] || 8790);
  const props = {
    ADMIN_PASSWORD: process.env.TEST_PW || '주인비밀번호7',
    SIGNING_SECRET: '시험용-서명값',
    DEFAULT_PROGRAM: 'exam',
  };
  start(port, props);
  console.log(`시험 서버: http://127.0.0.1:${port}/  (API: /exec)`);
}

module.exports = { start };
