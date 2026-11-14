const test=require('node:test');
const assert=require('node:assert/strict');
const {fixtures,scenario}=require('../scenario.js');
test('regression fixture reproduces Python arithmetic',()=>{const r=scenario(fixtures[0],10);assert.equal(r.activity,600);assert.equal(r.extra,60);assert.equal(r.points.find(p=>p.horizon===3).backlog,5620);assert.ok(Math.abs(r.required-16.6666666667)<1e-8);});
test('zero uplift exactly preserves all baselines',()=>{for(const f of fixtures)for(const p of scenario(f,0).points)assert.equal(p.backlog,p.baseline);});
test('monotonic in activity and non-negative across all permitted uplifts',()=>{for(const f of fixtures){let previous=scenario(f,0);for(let u=1;u<=100;u++){const current=scenario(f,u);current.points.forEach((p,i)=>{assert.ok(p.backlog>=0);assert.ok(p.backlog<=previous.points[i].backlog);});previous=current;}}});
test('unknown recent data cannot produce a scenario',()=>{assert.equal(scenario(fixtures[0],10,true).status,'no_activity_data');for(const activity of [[100,100,null],[100,NaN,100],[100,-1,100],[100,100],[0,0,0]])assert.equal(scenario({...fixtures[0],activity},10).status,'no_activity_data');});
test('nonfinite uplift is rejected and finite extremes are clamped',()=>{for(const u of [NaN,Infinity,-Infinity])assert.throws(()=>scenario(fixtures[0],u),/finite/);assert.equal(scenario(fixtures[0],-5).uplift,0);assert.equal(scenario(fixtures[0],105).uplift,100);});
test('improving and constrained fixtures preserve distinct interpretation',()=>{assert.equal(scenario(fixtures[1],10).required,0);assert.equal(scenario(fixtures[2],10).withinLimit,false);});

