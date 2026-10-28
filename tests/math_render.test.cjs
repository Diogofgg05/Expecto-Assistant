/* Native MathML renderer tests without jsdom or network access. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const test=require('node:test');
class Node {
  constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(key,value){this.attributes[key]=value;}
}
const document={
  createElementNS:(_ns,tag)=>new Node(tag),
  createElement:tag=>new Node(tag)
};
const window={};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/math.js'),'utf8'),
  {document,window}, {timeout:1000});
function all(node,tag){
  return (node.tagName===tag?[node]:[]).concat(...node.children.map(x=>all(x,tag)));
}
const det={calculation:{interpreted_task:{type:'determinant',matrix:[[2,1],[3,4]]},
  result:{actual:'5'},steps:['Operação exata']}};
const inverse={calculation:{interpreted_task:{type:'inverse',matrix:[[1,2],[3,4]]},
  result:{actual:[['-2','1'],['3/2','-1/2']]},steps:[]}};
const system={calculation:{interpreted_task:{type:'solve',matrix:[[2,1],[1,-1]]},
  result:{actual:{status:'unique'},solution_named:{x:'2',y:'1'}},steps:[]}};
test('renders matrix and determinant with selectable MathML, not images',()=>{
  const root=new Node('div');
  assert.equal(window.ExpectoMath.render(root,det),true);
  assert.ok(all(root,'math').length>=2);
  assert.ok(all(root,'mtable').length);
  assert.equal(all(root,'img').length,0);
  assert.ok(all(root,'mn').some(x=>x.textContent==='5'));
});
test('renders real vertical fractions and exponent in matrix inverse',()=>{
  const root=new Node('div');
  window.ExpectoMath.render(root,inverse);
  assert.equal(all(root,'mfrac').length,2);
  assert.equal(all(root,'msup').length,1);
});
test('renders named variables for a system',()=>{
  const root=new Node('div');
  window.ExpectoMath.render(root,system);
  assert.ok(all(root,'mi').some(x=>x.textContent==='x'));
  assert.ok(all(root,'mi').some(x=>x.textContent==='y'));
});
test('rejects unknown structured payload without HTML execution',()=>{
  const root=new Node('div');
  assert.equal(window.ExpectoMath.render(root,{}),false);
  assert.equal(all(root,'script').length,0);
});
