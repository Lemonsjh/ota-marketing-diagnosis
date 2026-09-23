from __future__ import annotations

import json
from typing import Any


STYLE = """
<style id='S14_MANUAL_SUPPLEMENT_STYLE'>
.manual-supplement-total{display:flex;min-width:190px;flex-direction:column;justify-content:center;padding:18px 22px;border:1px solid #d8e7e0;border-radius:14px;background:#f7fbf9;color:#26343d}
.manual-supplement-total small{color:#6c7a83;font-size:12px;font-weight:800}.manual-supplement-total strong{margin-top:7px;color:#16845b;font-size:30px}.manual-supplement-total span{margin-top:6px;color:#75828a;font-size:12px}
.manual-supplement-editor{margin-top:12px;padding:12px;border:1px dashed #b9d8ca;border-radius:10px;background:#f8fcfa}.config-item-name .manual-supplement-editor{min-width:240px}
.manual-supplement-editor summary{color:#16845b;font-size:12px;font-weight:850;cursor:pointer}.manual-supplement-fields{display:grid;grid-template-columns:minmax(170px,1fr) minmax(120px,.6fr);gap:9px;margin-top:10px}
.manual-supplement-criteria{margin-top:10px;padding:9px 10px;border-radius:7px;background:#eef7f3;color:#40534a;font-size:12px;line-height:1.55}.manual-supplement-criteria strong{color:#16845b}
.manual-supplement-fields label{display:grid;gap:5px;color:#68767f;font-size:11px;font-weight:750}.manual-supplement-fields select,.manual-supplement-fields input{height:36px;padding:0 9px;border:1px solid #ccd9d3;border-radius:7px;background:#fff;color:#26343d;font:inherit}
.manual-supplement-actions{display:flex;gap:8px;margin-top:9px}.manual-supplement-actions button{padding:7px 12px;border:1px solid #16845b;border-radius:7px;background:#16845b;color:#fff;font:inherit;font-size:12px;font-weight:800;cursor:pointer}.manual-supplement-actions button.secondary{border-color:#ccd8d3;background:#fff;color:#58666f}
.manual-supplement-result{margin-top:8px;color:#68767f;font-size:12px}.manual-supplement-result.saved{color:#16845b;font-weight:800}.manual-summary-score{margin-top:3px;color:#16845b;font-size:11px;font-weight:800}
@media(max-width:760px){.manual-supplement-fields{grid-template-columns:1fr}.manual-supplement-total{min-width:0}}
@media print{.manual-supplement-editor{display:none}.manual-supplement-total{box-shadow:none}}
</style>
"""


def _storage_prefix(result: dict[str, Any]) -> str:
    parts = (
        result.get("hotel_id") or result.get("hotel_name") or "hotel",
        result.get("period_start") or "start",
        result.get("period_end") or "end",
    )
    return "s14:manual-supplement:" + ":".join(str(value) for value in parts)


def _script(result: dict[str, Any]) -> str:
    prefix = json.dumps(_storage_prefix(result), ensure_ascii=False).replace("</", "<\\/")
    return rf"""
<script id='S14_MANUAL_SUPPLEMENT_SCRIPT'>
(function(){{
  const PREFIX={prefix};
  const SCOPES=[
    {{channel:'meituan',view:".page[data-channel-view='meituan']",ids:[15,16,17,18,19,20,21,23]}},
    {{channel:'ctrip',view:".page[data-channel-view='ctrip']",ids:[7,8,14,15,16,17,18,19,20,21]}}
  ];
  const PENDING=new Set(['missing','manual_pending','pending_rule','data_gap','unavailable','not_integrated']);
  const CRITERIA={{
    meituan:{{15:'已开通且报名/生效状态有效得满分；明确未开通或未参与得0分。',16:'已开通且报名/生效状态有效得满分；明确未开通得0分。',17:'已报名且生效得满分；明确未报名或未生效得0分。',18:'已配置普通可售钟点房得满分；明确未配置或不可售得0分。',19:'酒店亮点已配置且完整生效得满分；明确未配置得0分。',20:'预约开票已开启且生效得满分；明确未开启得0分。',21:'首页存在已上传并可展示的视频得满分；没有可展示视频得0分。',23:'自动接单已开启且生效得满分；明确未开启得0分。'}},
    ctrip:{{7:'近30天扫码订单少于60单得0分；60至120单得2.5分；超过120单得5分。',8:'信息完整度达到100得满分4分；低于100得0分。',14:'已报名且近30天有成交得3分；已报名但无成交得1.8分；未报名得0分。',15:'已参加且标签正常展示得3分；标签受限得1.8分；未参加得0分。',16:'已开通且有参与房型得2分；已开通但无有效房型得1分；未开通得0分。',17:'闪住已参与得2分；未参与得0分。数据未接入时可按后台实际状态补充。',18:'已配置钟点房得1分，近30天存在有效钟点房订单再得1分，合计最高2分。',19:'已上传且已认领得2分；已上传但未认领得1分；未上传得0分。',20:'详情页视频上传数量大于0得1分；等于0得0分。列表页和房型视频仅展示。'}}
  }};
  function number(value){{if(value===null||value===undefined||String(value).trim()==='')return null;const n=Number(value);return Number.isFinite(n)?n:null;}}
  function scoreText(value){{return Number(value.toFixed(2)).toString()+'分';}}
  function itemRoot(view,channel,id){{return channel==='ctrip'?(view.querySelector('#ctrip-rule-'+id)||view.querySelector('#rule-'+id)):view.querySelector('#rule-'+id);}}
  function isPending(root){{
    const state=(root.dataset.status||'').toLowerCase();
    if(state) return PENDING.has(state);
    return !!root.querySelector('.config-score-chip.pending,.config-status-chip.pending') || /待计算|待接入|未取到|未确定/.test(root.textContent||'');
  }}
  function fullScore(root){{
    const direct=root.querySelector('.config-full-score');
    const match=(direct?direct.textContent:root.textContent||'').match(/(?:满分\s*)?([0-9]+(?:\.[0-9]+)?)分/);
    return match?Number(match[1]):null;
  }}
  function storageKey(channel,id){{return PREFIX+':'+channel+':'+id;}}
  function criterion(channel,id,full){{return (CRITERIA[channel]||{{}})[id]||('满足本项页面所列全部条件得满分'+scoreText(full)+'；明确不满足得0分；部分满足请选择自定义得分。');}}
  function read(key){{try{{const value=JSON.parse(localStorage.getItem(key)||'null');return value&&number(value.score)!==null?value:null;}}catch(error){{return null;}}}}
  function summaryRow(view,id){{
    const link=view.querySelector("#summary a[href='#module-"+id+"'],#summary a[href='#rule-"+id+"'],#ctrip-summary a[href='#module-"+id+"']");
    return link?link.closest('tr'):null;
  }}
  function renderSummary(view,id,data){{
    const row=summaryRow(view,id);if(!row)return;
    const cells=row.querySelectorAll('td');if(cells.length<5)return;
    let score=cells[3].querySelector('.manual-summary-score');
    if(!score){{score=document.createElement('div');score.className='manual-summary-score';cells[3].appendChild(score);}}
    score.textContent=data?'人工补充 '+scoreText(Number(data.score)):'';
    let badge=cells[4].querySelector('.manual-supplement-badge');
    if(!badge){{badge=document.createElement('div');badge.className='manual-summary-score manual-supplement-badge';cells[4].appendChild(badge);}}
    badge.textContent=data?'人工补充（待复核）':'';
  }}
  function applyGeneric(target,data){{
    target.root.dataset.manualSupplementScore=data?String(data.score):'';
    target.result.textContent=data?'已保存：'+scoreText(Number(data.score)):'尚未补充';
    target.result.classList.toggle('saved',!!data);
    if(data){{target.mode.value=data.mode||'custom';target.score.value=data.score;}}
    renderSummary(target.view,target.id,data);recompute();
  }}
  function editor(target){{
    const full=fullScore(target.root);if(full===null)return;
    const host=target.root.matches('tr')?(target.root.querySelector('.config-item-name')||target.root.lastElementChild):(target.root.querySelector('.result-area')||target.root);
    if(!host||host.querySelector('.manual-supplement-editor')||host.querySelector('[data-ctrip-listing-select],#crown-type-input'))return;
    const box=document.createElement('details');box.className='manual-supplement-editor';
    box.innerHTML="<summary>手动补充（仅数据缺失时）</summary><div class='manual-supplement-criteria'><strong>评分条件：</strong>"+criterion(target.channel,target.id,full)+"</div><div class='manual-supplement-fields'><label>判定<select data-manual-mode><option value='full'>已满足（满分）</option><option value='zero'>未满足（0分）</option><option value='custom'>部分满足 / 自定义得分</option></select></label><label>人工得分<input data-manual-score type='number' min='0' max='"+full+"' step='0.5'></label></div><div class='manual-supplement-actions'><button type='button' data-manual-save>保存</button><button type='button' class='secondary' data-manual-clear>清除</button></div><div class='manual-supplement-result'>尚未补充</div>";
    host.appendChild(box);target.mode=box.querySelector('[data-manual-mode]');target.score=box.querySelector('[data-manual-score]');target.result=box.querySelector('.manual-supplement-result');
    target.mode.addEventListener('change',function(){{if(this.value==='full')target.score.value=full;if(this.value==='zero')target.score.value=0;target.score.disabled=this.value!=='custom';}});
    box.querySelector('[data-manual-save]').addEventListener('click',function(){{
      const score=target.mode.value==='full'?full:target.mode.value==='zero'?0:number(target.score.value);
      if(score===null||score<0||score>full){{target.result.textContent='请输入 0 至 '+full+' 分。';return;}}
      const data={{mode:target.mode.value,score:score,updatedAt:new Date().toISOString()}};
      try{{localStorage.setItem(storageKey(target.channel,target.id),JSON.stringify(data));}}catch(error){{}}
      applyGeneric(target,data);
    }});
    box.querySelector('[data-manual-clear]').addEventListener('click',function(){{try{{localStorage.removeItem(storageKey(target.channel,target.id));}}catch(error){{}}applyGeneric(target,null);}});
    target.mode.value='full';target.score.value=full;target.score.disabled=true;applyGeneric(target,read(storageKey(target.channel,target.id)));
  }}
  function overview(view,channel){{
    const score=view.querySelector(channel==='ctrip'?'.ctrip-overview-score strong':'.total-score-v17 strong');
    if(!score)return null;
    if(!score.dataset.systemScore)score.dataset.systemScore=String(number(score.textContent)||0);
    let box=view.querySelector('.manual-supplement-total');
    if(!box){{box=document.createElement('div');box.className='manual-supplement-total';box.innerHTML='<small>补充后得分</small><strong>—</strong><span>暂无人工补充</span>';score.closest('.ctrip-overview-score,.total-score-v17').insertAdjacentElement('afterend',box);}}
    return {{score:score,box:box}};
  }}
  function recompute(){{
    SCOPES.forEach(function(scope){{const view=document.querySelector(scope.view);if(!view)return;const output=overview(view,scope.channel);if(!output)return;let added=0,count=0;
      scope.ids.forEach(function(id){{const root=itemRoot(view,scope.channel,id);if(!root)return;const value=number(root.dataset.manualSupplementScore);if(value!==null){{added+=value;count+=1;}}}});
      output.box.querySelector('strong').textContent=count?scoreText((number(output.score.dataset.systemScore)||0)+added):'—';output.box.querySelector('span').textContent=count?'人工补充 '+count+' 项（待复核）':'暂无人工补充';
    }});
  }}
  function setup(){{SCOPES.forEach(function(scope){{const view=document.querySelector(scope.view);if(!view)return;overview(view,scope.channel);scope.ids.forEach(function(id){{const root=itemRoot(view,scope.channel,id);if(root&&isPending(root))editor({{view:view,root:root,channel:scope.channel,id:id}});}});}});recompute();document.addEventListener('s14:manual-supplement-changed',recompute);}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
}})();
</script>
"""


def patch_manual_supplements(document: str, result: dict[str, Any]) -> str:
    if "S14_MANUAL_SUPPLEMENT_SCRIPT" in document or "data-channel-view" not in document:
        return document
    document = document.replace("</head>", STYLE + "</head>", 1)
    return document.replace("</body>", _script(result) + "</body>", 1)


__all__ = ["patch_manual_supplements"]
