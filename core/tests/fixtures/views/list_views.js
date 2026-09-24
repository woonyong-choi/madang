// 렌더러 listViews()가 공유 사례에서 찾는 key를 JSON으로 출력한다.
// 사용: node list_views.js <document.js> <fences.json>
'use strict';

const fs = require('fs');
const path = require('path');

const renderer = require(path.resolve(process.argv[2]));
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const keys = cases.map((c) => renderer.listViews(c.markdown).map((v) => v.key));
process.stdout.write(JSON.stringify(keys));
