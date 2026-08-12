#!/usr/bin/env python3
import argparse
import urllib.request
from pathlib import Path

UPSTREAMS = [
    'https://a-share-top-monitor.netlify.app',
    'https://6a72ef4b5ab7ceed7c6b46fc--a-share-top-monitor.netlify.app',
]

CSS_ADD = r'''

/* Concentration enhancement */
.enhancement-panel{margin:16px 0 18px;padding:18px 20px;border:1px solid #d7e3ee;border-radius:18px;background:linear-gradient(135deg,#f8fbff 0%,#fff8f2 100%);box-shadow:0 10px 28px rgba(30,70,105,.07)}
.enhancement-grid{display:grid;grid-template-columns:1.1fr repeat(3,1fr);gap:12px;align-items:stretch}
.enhancement-main,.enhancement-card{background:#fff;border:1px solid #e1e8ef;border-radius:14px;padding:15px 16px;min-width:0}
.enhancement-main{background:linear-gradient(135deg,#123b63,#1d6a94);color:#fff;border:none}
.enhancement-main .panel-kicker{color:#8ed8ff}.enhancement-main h3{font-size:22px;margin:4px 0 8px}.enhancement-main p{margin:0;opacity:.86;font-size:13px;line-height:1.7}
.enhancement-card span{display:block;color:#72869a;font-size:12px;font-weight:700}.enhancement-card strong{display:block;margin:7px 0 4px;font-size:22px;color:#173f64}.enhancement-card small{display:block;color:#708293;line-height:1.55}
.enhancement-card.met{border-left:4px solid #2f855a}.enhancement-card.alert{border-left:4px solid #c73535}.enhancement-card.neutral{border-left:4px solid #d2a517}
.enhancement-heading{margin-top:28px}.enhancement-rule-panel{margin:18px 0;padding:18px 20px}.enhancement-rule-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.enhancement-rule-item{border:1px solid #e0e8ef;border-radius:13px;padding:14px;background:#fbfdff}.enhancement-rule-item strong{display:block;color:#153f65;margin-bottom:6px}.enhancement-rule-item span{display:block;color:#63788a;line-height:1.65;font-size:13px}
.enhancement-backtest-highlight{border-color:#b8d7c1!important;background:#f4fbf6!important}
@media(max-width:1000px){.enhancement-grid,.enhancement-rule-grid{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.enhancement-grid,.enhancement-rule-grid{grid-template-columns:1fr}.enhancement-panel{padding:14px}}
'''

JS_ADD = r'''

// --- Concentration enhancement: confirmation gate + 20-day overlay ---
function enhancementPp(value, digits = 2) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}个百分点` : "—";
}

function renderEnhancementCurrent(data) {
  const el = document.querySelector("#enhancement-current");
  const detail = document.querySelector("#enhancement-components");
  if (!el || !detail || !data.enhancement) { if (el) el.classList.add("hidden"); return; }
  const e = data.enhancement, c = e.current.concentration, g = e.current.gate, o = e.current.overlay;
  const gateText = g.status === "confirmed" ? "确认门已通过" : g.status === "waiting" ? "确认门等待中" : g.status === "filtered" ? "最近B/C预警未通过" : "确认门暂无状态";
  const gateNote = g.status === "confirmed" ? `${g.base_signal_date} ${g.path || ""}路径 → ${g.confirmation_date}确认` : g.base_signal_date ? `最近B/C预警 ${g.base_signal_date}` : "暂无B/C预警";
  const overlayNow = o.triggered_now ? "20日补充条件满足" : "20日补充未触发";
  el.innerHTML = `<div class="enhancement-grid">
    <div class="enhancement-main"><p class="panel-kicker">C50 ENHANCEMENT</p><h3>${escapeHtml(gateText)} · ${escapeHtml(overlayNow)}</h3><p>集中度数据截止 ${escapeHtml(e.concentration_data_asof)}；最近补充信号 ${escapeHtml(o.latest_signal_date || "暂无")}。本模块不改变B/C平滑分，只决定预警确认与独立补充。</p></div>
    <div class="enhancement-card neutral"><span>前50成交额占比</span><strong>${number(c.top50_share_pct,2)}%</strong><small>20日变化 ${enhancementPp(c.d20_change_pp)} · 40日变化 ${enhancementPp(c.d40_change_pp)}</small></div>
    <div class="enhancement-card ${Number(c.p40_252)>=.5?'met':'neutral'}"><span>40日确认门</span><strong>${pct(c.p40_252)}</strong><small>阈值50% · ${escapeHtml(gateNote)}</small></div>
    <div class="enhancement-card ${Number(c.p20_504)>=.9?'alert':'neutral'}"><span>20日加速补充</span><strong>${pct(c.p20_504)}</strong><small>阈值90% · 当前连续${escapeHtml(o.current_streak)}日</small></div>
  </div>`;

  const gateScore = Math.max(0, Math.min(100, Number(c.p40_252 || 0) * 100));
  const overlayScore = Math.max(0, Math.min(100, Number(c.p20_504 || 0) * 100));
  const gateInfo = {name:"40日集中度确认门",score:gateScore,components:[
    {name:"40日升幅252日分位",purpose:"B/C预警出现后检查成交拥挤是否同步增强",hard_rule:"达到50分位",hard_met:Number(c.p40_252)>=.5,reading:`40日${enhancementPp(c.d40_change_pp)}｜${pct(c.p40_252)}`,mapping:"历史分位直接映射为0—100"},
    {name:"最近B/C预警确认",purpose:"最多等待10个A股交易日，首次满足即确认",hard_rule:"10日内P40≥50%",hard_met:g.status==="confirmed",reading:gateNote,mapping:g.status==="confirmed"?"已通过":"等待或过滤"}
  ]};
  const overlayInfo = {name:"20日集中度极端加速补充",score:overlayScore,components:[
    {name:"20日升幅504日分位",purpose:"识别成交向少数热门股快速集中",hard_rule:"达到90分位",hard_met:Number(c.p20_504)>=.9,reading:`20日${enhancementPp(c.d20_change_pp)}｜${pct(c.p20_504)}`,mapping:"历史分位直接映射为0—100"},
    {name:"连续3日确认",purpose:"过滤单日主题或调仓造成的异常集中",hard_rule:"连续3日P20≥90%",hard_met:o.current_streak>=3,reading:`连续${o.current_streak}日`,mapping:"3日满足后产生补充信号；冷却45日"}
  ]};
  detail.innerHTML = componentPanel("G",gateInfo,"gold") + componentPanel("O",overlayInfo,"rose");
}

function renderEnhancementRules(data) {
  const el=document.querySelector("#enhancement-rule-panel");
  if (!el || !data.enhancement) return;
  const r=data.enhancement.rules;
  el.innerHTML=`<div class="panel-title-row"><div><p class="panel-kicker">C50 ENHANCEMENT RULES</p><h3>确认门 + 20日集中度补充</h3></div></div><div class="enhancement-rule-grid">
    <div class="enhancement-rule-item"><strong>① C50定义</strong><span>${escapeHtml(r.concentration)}</span></div>
    <div class="enhancement-rule-item"><strong>② 确认门</strong><span>${escapeHtml(r.gate)}</span></div>
    <div class="enhancement-rule-item"><strong>③ 补充信号</strong><span>${escapeHtml(r.overlay)}；最终信号=${escapeHtml(r.combination)}</span></div>
  </div>`;
}

function renderEnhancementBacktest(data) {
  const cards=document.querySelector("#enhancement-backtest-cards"), note=document.querySelector("#enhancement-backtest-note");
  if (!cards || !note || !data.enhancement) return;
  const bt=data.enhancement.backtest, s=bt.summary, g=bt.gate_only, o=bt.overlay_only;
  const metrics=[["增强信号",s.signals,"次"],["命中",s.hits,"次"],["精确率",pct(s.precision),`${s.hits}/${s.signals}`],["覆盖顶部",`${s.covered}/${s.tops}`,"个"],["召回率",pct(s.recall),`${s.covered}/${s.tops}`],["F1",pct(s.f1),"平衡指标"]];
  cards.innerHTML=metrics.map(([label,value,small],i)=>`<article class="metric-card ${i===2||i===4?'enhancement-backtest-highlight':''}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(small)}</small></article>`).join("");
  note.innerHTML=`<strong>当前网页版本重新回测</strong><span>原B/C：精确率${pct(data.backtest.summary.precision)}、召回率${pct(data.backtest.summary.recall)}；确认门单独：${pct(g.precision)}/${pct(g.recall)}；20日补充单独：${pct(o.precision)}/${pct(o.recall)}；组合后：${pct(s.precision)}/${pct(s.recall)}。${escapeHtml(bt.note)}</span>`;
}

const renderCurrentBase = renderCurrent;
renderCurrent = function(data) { renderCurrentBase(data); renderEnhancementCurrent(data); };
const renderRulesBase = renderRules;
renderRules = function(data) { renderRulesBase(data); renderEnhancementRules(data); };
const renderBacktestBase = renderBacktest;
renderBacktest = function(data) { renderBacktestBase(data); renderEnhancementBacktest(data); };
'''


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8-sig')


def load_assets(source_dir=None):
    if source_dir:
        p=Path(source_dir)
        index=(p/'index.html').read_text(encoding='utf-8')
        css=(p/'styles.css').read_text(encoding='utf-8')
        js=(p/'app.js').read_text(encoding='utf-8')
        return index,css,js,'local source'
    last=None
    for base in UPSTREAMS:
        try:
            return fetch_text(base+'/'), fetch_text(base+'/styles.css'), fetch_text(base+'/app.js'), base
        except Exception as e:
            last=e
    raise RuntimeError(f'failed to download upstream static assets: {last}')


def insert_once(text, needle, insertion, where='before'):
    if insertion.strip() in text:
        return text
    if needle not in text:
        raise RuntimeError(f'patch anchor missing: {needle[:80]}')
    return text.replace(needle, insertion+needle if where=='before' else needle+insertion, 1)


def patch_index(index):
    index=index.replace('0—100连续平滑分 · B/C双路径 · 80分红灯','0—100连续平滑分 · B/C双路径 · 前50成交集中度增强')
    index=insert_once(index,'<div id="lock-banner"', '      <div id="enhancement-current" class="enhancement-panel"></div>\n\n')
    current_block='''      <div class="section-subheading enhancement-heading">\n        <div><p class="section-kicker">CONCENTRATION ENHANCEMENT</p><h2>确认门 + 20日集中度补充</h2></div>\n        <p class="section-note">确认门负责过滤B/C预警；20日极端加速负责补充漏报。</p>\n      </div>\n      <div id="enhancement-components" class="component-panels"></div>\n'''
    index=insert_once(index,'    </section>\n\n    <section id="rules"',current_block)
    index=insert_once(index,'<div id="rule-methods"', '      <article id="enhancement-rule-panel" class="panel enhancement-rule-panel"></article>\n      ')
    bt='''      <div class="section-subheading enhancement-heading">\n        <div><p class="section-kicker">ENHANCED BACKTEST</p><h2>集中度增强策略回测</h2></div>\n        <p class="section-note">使用当前网页B/C版本重新计算，避免混用之前31次基线结果。</p>\n      </div>\n      <div id="enhancement-backtest-cards" class="metric-grid"></div>\n      <div id="enhancement-backtest-note" class="backtest-warning"></div>\n'''
    index=insert_once(index,'<div class="backtest-layout">',bt+'      ')
    return index


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--site-dir',default='site')
    ap.add_argument('--source-dir',help='Local directory containing index.html/styles.css/app.js for testing')
    args=ap.parse_args()
    site=Path(args.site_dir); site.mkdir(parents=True,exist_ok=True); (site/'data').mkdir(exist_ok=True)
    index,css,js,source=load_assets(args.source_dir)
    index=patch_index(index)
    if '/* Concentration enhancement */' not in css: css += CSS_ADD
    if '// --- Concentration enhancement:' not in js: js += JS_ADD
    (site/'index.html').write_text(index,encoding='utf-8')
    (site/'styles.css').write_text(css,encoding='utf-8')
    (site/'app.js').write_text(js,encoding='utf-8')
    print('static source:',source)
    print('patched:',site)

if __name__=='__main__': main()
