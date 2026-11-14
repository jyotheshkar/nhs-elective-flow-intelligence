(function(root){
  'use strict';
  const fixtures = [
    { id:'rising', name:'Rising list', label:'Scenario regression fixture', code:'P01 / C_110', history:[5000,5100,5200,5300,5400,5500], activity:[600,600,600], forecast:{1:5600,3:5800,6:6100}, origin:'backend/tests/test_scenarios.py' },
    { id:'improving', name:'Improving list', label:'Improving scenario fixture', code:'P01 / C_110', history:[5000,5100,5200,5300,5400,5500], activity:[600,600,600], forecast:{1:5400,3:5200,6:5000}, origin:'backend/tests/test_scenarios.py' },
    { id:'lowactivity', name:'Capacity constrained', label:'Illustrative synthetic fixture', code:'DEMO / CAPACITY', history:[4000,4300,4600,4900,5200,5500], activity:[100,100,100], forecast:{1:5800,3:6400,6:7300}, origin:'Additional synthetic browser example; not NHS statistics' }
  ];
  function scenario(fixture,uplift,missing=false){
    if(!Number.isFinite(uplift)) throw new TypeError('Uplift must be finite');
    const u=Math.max(0,Math.min(100,uplift));
    const values=fixture.activity.slice(-3);
    if(missing || values.length!==3 || values.some(x=>!Number.isFinite(x)||x<0)) return {status:'no_activity_data',points:[],uplift:u};
    const activity=values.reduce((a,b)=>a+b,0)/3;
    if(activity<=0) return {status:'no_activity_data',points:[],uplift:u};
    const extra=activity*u/100;
    const points=[1,3,6].map(h=>({horizon:h,baseline:fixture.forecast[h],backlog:Math.max(0,fixture.forecast[h]-h*extra),extra:h*extra}));
    const growth=fixture.forecast[3]-fixture.history.at(-1);
    const required=Math.max(0,growth/(3*activity)*100);
    return {status:'ok',uplift:u,activity,extra,points,required,withinLimit:required<=100};
  }
  const api={fixtures,scenario};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else root.ElectiveScenario=api;
})(typeof window!=='undefined'?window:globalThis);
