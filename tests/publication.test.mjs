import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {validate,escape} from '../scripts/build.mjs';
const sample=JSON.parse(fs.readFileSync(new URL('../content/articles.json',import.meta.url)))[0];
test('publication requires all review gates',()=>{for(const k of ['facts','value','rights','policy'])assert.throws(()=>validate({...sample,review:{...sample.review,[k]:false}}));assert.throws(()=>validate({...sample,review:{...sample.review,status:'candidate'}}));});
test('source, value and script injection checks',()=>{assert.throws(()=>validate({...sample,sources:[]}));assert.throws(()=>validate({...sample,sections:[{kind:'fact',html:'hello'}]}));assert.throws(()=>validate({...sample,sections:[{kind:'guide',html:'<img onerror="alert(1)">'}]}));});
test('metadata cannot inject HTML',()=>{assert.equal(escape('<&"'), '&lt;&amp;&quot;');});
test('copy share and storage failure paths are present',()=>{const js=fs.readFileSync(new URL('../src/app.js',import.meta.url),'utf8');assert.match(js,/catch\{storage=false/);assert.match(js,/location.href/);assert.match(js,/normalize\('NFKC'\)/);});
