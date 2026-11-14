'use strict';
const $=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('en-GB',{maximumFractionDigits:1}).format(n);
let activeResult,activeFixture;
function render(){
 const fixture=ElectiveScenario.fixtures.find(f=>f.id===$('fixture').value);
 const uplift=Number($('uplift').value),focus=Number($('horizon').value);
 const result=ElectiveScenario.scenario(fixture,uplift,$('missing').checked);
 activeResult=result;activeFixture=fixture;
 $('upliftValue').textContent=uplift+'%';$('fixtureLabel').textContent=fixture.label+' · '+fixture.code;
 document.querySelectorAll('[data-uplift]').forEach(b=>{const selected=Number(b.dataset.uplift)===uplift;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});
 $('unavailable').hidden=result.status==='ok';$('resultBody').hidden=result.status!=='ok';
 if(result.status!=='ok') return;
 const point=result.points.find(p=>p.horizon===focus),difference=point.backlog-point.baseline;
 $('current').textContent=fmt(fixture.history.at(-1));$('baselineTitle').textContent=focus+'-month baseline';$('baseline').textContent=fmt(point.baseline);$('projected').textContent=fmt(point.backlog);$('difference').textContent=(difference===0?'No change':fmt(Math.abs(difference))+' fewer')+' vs baseline';
 $('summaryText').textContent=result.required===0?'Baseline already stable or improving; no uplift is needed for arithmetic stabilisation.':fmt(result.required)+'% uplift would hold the list at its current level at +3 months'+(result.withinLimit?' (within the model’s 0–100% limit).':' (beyond the model’s 100% limit).');
 $('dataRows').innerHTML=result.points.map(p=>'<tr class="'+(p.horizon===focus?'active':'')+'"><th scope="row">+'+p.horizon+' month'+(p.horizon===1?'':'s')+'</th><td>'+fmt(p.baseline)+'</td><td>'+fmt(p.backlog)+'</td><td>'+fmt(p.backlog-p.baseline)+'</td></tr>').join('');
 draw(fixture,result);
}
function draw(f,r){
 const w=800,h=300,left=55,right=22,top=20,bottom=36;
 const max=Math.max(...f.history,...r.points.map(p=>p.baseline))*1.12;
 const x=i=>left+(w-left-right)*i/11,y=v=>h-bottom-(h-top-bottom)*v/max;
 const hist=f.history.map((v,i)=>[i,v]),base=[[5,f.history.at(-1)],...r.points.map(p=>[5+p.horizon,p.baseline])],scenario=[[5,f.history.at(-1)],...r.points.map(p=>[5+p.horizon,p.backlog])];
 const path=points=>points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+','+y(p[1]).toFixed(2)).join(' ');
 let svg='<title id="chartTitle">Synthetic waiting list trajectory</title><desc id="chartDescription">Fixture history, fixed baseline forecast and activity-uplift scenario. Exact outputs appear in the table below.</desc>';
 for(let i=0;i<=4;i++){const v=max*i/4;svg+='<line x1="'+left+'" y1="'+y(v)+'" x2="'+(w-right)+'" y2="'+y(v)+'" stroke="#1c3048"/><text x="'+(left-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+Math.round(v).toLocaleString('en-GB')+'</text>';}
 svg+='<rect x="'+x(5)+'" y="'+top+'" width="'+(x(11)-x(5))+'" height="'+(h-top-bottom)+'" fill="#2268e7" opacity=".045"/><line x1="'+x(5)+'" y1="'+top+'" x2="'+x(5)+'" y2="'+(h-bottom)+'" stroke="#36587e" stroke-dasharray="4 5"/>';
 svg+='<path d="'+path(hist)+'" fill="none" stroke="#8aaccf" stroke-width="2.5"/><path d="'+path(base)+'" fill="none" stroke="#627991" stroke-width="2.5" stroke-dasharray="5 5"/><path d="'+path(scenario)+'" fill="none" stroke="#60a5ff" stroke-width="3"/>';
 r.points.forEach(p=>{svg+='<circle cx="'+x(5+p.horizon)+'" cy="'+y(p.backlog)+'" r="4" fill="#60a5ff"/><text x="'+x(5+p.horizon)+'" y="'+(h-10)+'" text-anchor="middle">+'+p.horizon+'m</text>';});
 svg+='<text x="'+left+'" y="'+(h-10)+'">History</text><text x="'+x(5)+'" y="'+(h-10)+'" text-anchor="middle">Current</text>';
 $('chart').innerHTML=svg;
}
['fixture','uplift','horizon','missing'].forEach(id=>$(id).addEventListener('input',render));
document.querySelectorAll('[data-uplift]').forEach(b=>b.addEventListener('click',()=>{$('uplift').value=b.dataset.uplift;render();}));
$('reset').addEventListener('click',()=>{$('fixture').value='rising';$('uplift').value=10;$('horizon').value=3;$('missing').checked=false;render();});
$('download').addEventListener('click',()=>{if(activeResult.status!=='ok')return;const lines=['data_source_type,fixture,horizon_months,uplift_pct,baseline_backlog,scenario_backlog,difference_from_baseline',...activeResult.points.map(p=>['DEMO_SYNTHETIC',activeFixture.id,p.horizon,activeResult.uplift,p.baseline,p.backlog,p.backlog-p.baseline].join(','))];const url=URL.createObjectURL(new Blob([lines.join('\n')+'\n'],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='elective-care-synthetic-scenario.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
render();
