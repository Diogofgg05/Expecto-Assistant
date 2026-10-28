/* Accessible, dependency-free MathML presentation of server-verified algebra.
 * This never evaluates arbitrary LaTeX, JS or HTML supplied by a language model.
 */
(() => {
  'use strict';
  const NS='http://www.w3.org/1998/Math/MathML';
  function m(tag,text){
    const n=document.createElementNS(NS,tag);
    if(text!==undefined)n.textContent=String(text);
    return n;
  }
  function element(tag,cls,text){
    const n=document.createElement(tag);
    if(cls)n.className=cls;
    if(text!==undefined)n.textContent=String(text);
    return n;
  }
  function rational(value){
    const v=String(value);
    if(!/^-?\d+(?:\/\d+)?$/.test(v))return m('mtext',v.slice(0,70));
    const [numerator,denominator]=v.split('/');
    if(!denominator)return m('mn',numerator);
    const frac=m('mfrac');frac.append(m('mn',numerator),m('mn',denominator));
    return frac;
  }
  function math(child){
    const root=m('math');root.setAttribute('display','block');
    root.append(child);return root;
  }
  function matrix(rows,delimiters=true){
    if(!Array.isArray(rows)||!rows.length||rows.length>8||
       !rows.every(row=>Array.isArray(row)&&row.length>=1&&row.length<=8))return m('mtext','Matriz indisponível');
    const table=m('mtable');
    for(const values of rows){
      const tr=m('mtr');
      for(const val of values){
        const cell=m('mtd');cell.append(rational(val));tr.append(cell);
      }
      table.append(tr);
    }
    if(!delimiters)return table;
    const group=m('mrow');group.append(m('mo','['),table,m('mo',']'));
    return group;
  }
  function render(parent,info){
    parent.replaceChildren();
    const calc=info?.calculation;
    const task=calc?.interpreted_task;
    const result=calc?.result;
    if(!task||!result||!['determinant','inverse','solve'].includes(task.type)){
      parent.append(element('p','math-note','Não existem cálculos estruturados para apresentar.'));return false;
    }
    parent.append(element('h3','math-heading','PROBLEMA'));
    if(Array.isArray(task.matrix))parent.append(math(matrix(task.matrix)));
    parent.append(element('h3','math-heading','MÉTODO'));
    parent.append(element('p','math-note',task.type==='solve'?'Eliminação de Gauss-Jordan com números racionais exatos.':
      task.type==='inverse'?'Aplicação de Gauss-Jordan à matriz aumentada [A | I].':
      'Eliminação exata com operações elementares.'));
    const steps=Array.isArray(calc.steps)?calc.steps.slice(0,12):[];
    if(steps.length){
      parent.append(element('h3','math-heading','PASSOS E JUSTIFICAÇÃO'));
      const list=element('ol','math-steps');
      for(const step of steps)list.append(element('li','',String(step).slice(0,500)));
      parent.append(list);
    }
    parent.append(element('h3','math-heading','RESULTADO'));
    const actual=result.actual;
    if(task.type==='determinant'){
      const r=m('mrow');r.append(m('mi','det'),m('mo','('),m('mi','A'),m('mo',')'),m('mo','='),rational(actual));parent.append(math(r));
    }else if(task.type==='inverse'){
      if(actual===null)parent.append(element('p','math-note','A matriz é singular: não existe inversa.'));
      else{const r=m('mrow');const power=m('msup');power.append(m('mi','A'),m('mn','−1'));r.append(power,m('mo','='),matrix(actual));parent.append(math(r));}
    }else if(task.type==='solve'){
      if(actual.status==='unique'&&result.solution_named){
        const table=m('mtable');
        for(const [variable,value] of Object.entries(result.solution_named).slice(0,3)){
          const row=m('mtr'),cell=m('mtd'),expr=m('mrow');
          expr.append(m('mi',variable),m('mo','='),rational(value));
          cell.append(expr);row.append(cell);table.append(row);
        }
        parent.append(math(table));
      }else parent.append(element('p','math-note',actual.status==='none'?
        'Sistema impossível — não existem soluções.':'Sistema indeterminado — existem infinitas soluções.'));
    }
    parent.append(element('h3','math-heading','VERIFICAÇÃO'));
    parent.append(element('p','math-note','Resultado obtido com aritmética racional exata, sem aproximações do modelo. A interpretação do enunciado deve ser confirmada.'));
    return true;
  }
  window.ExpectoMath={render};
})();
