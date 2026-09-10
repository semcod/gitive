/** Deterministic numerical probe for the cross-language comparison. */
import {readFileSync} from 'node:fs';
import {object,rank,informationGain,number} from './engine.ts';
const x=object(JSON.parse(readFileSync(0,'utf8')));
if(!Array.isArray(x.cases))throw new Error('Expected cases');
const gains=x.cases.map(v=>{
  if(!Array.isArray(v)||v.length!==3)throw new Error('Expected triple');
  return informationGain(number(v[0],'p'),number(v[1],'s'),number(v[2],'f'));
});
console.log(JSON.stringify({ranking:rank(x.state,x.tasks),gains}));
