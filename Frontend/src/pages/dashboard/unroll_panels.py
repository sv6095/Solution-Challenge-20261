import re

with open('NetworkView.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace ptCss
content = content.replace(
    'const ptCss: React.CSSProperties = { fontSize:12, fontWeight:700, textTransform:"uppercase", letterSpacing:1, color:"var(--text-muted)", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis", minWidth:100 };',
    'const ptCss: React.CSSProperties = { fontSize:12, fontWeight:700, textTransform:"uppercase", letterSpacing:1, color:"var(--text-muted)" };'
)

content = content.replace(
    'const phCss: React.CSSProperties = { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 14px", borderBottom:"1px solid var(--border-subtle)", background:"rgba(0,0,0,0.15)", flexWrap:"wrap", gap:8 };',
    'const phCss: React.CSSProperties = { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 14px", borderBottom:"1px solid var(--border-subtle)", background:"rgba(0,0,0,0.15)", gap:8 };'
)

# And tab states
content = re.sub(r'  const \[scTab, setScTab\].*?;\n', '', content)
content = re.sub(r'  const \[riskTab, setRiskTab\].*?;\n', '', content)
content = re.sub(r'  const \[intelTab, setIntelTab\].*?;\n', '', content)

grid_start_marker = "          {/* ① Supply Chain Panel (worldmonitor SupplyChainPanel) */}"
grid_end_marker = "          {/* ④ Supplier Risk Table */}"

idx_start = content.find(grid_start_marker)
idx_end = content.find(grid_end_marker)

if idx_start != -1 and idx_end != -1:
    new_panels = """
          {/* Chokepoints Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Chokepoints</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {chokepoints.length===0
                ? <div style={{ padding:16, color:"var(--text-muted)", fontSize:13 }}>Loading chokepoint data…</div>
                : [...chokepoints].sort((a,b)=>(b.risk_score??0)-(a.risk_score??0)).map(cp => <ChokepointCard key={cp.id} cp={cp} />)
              }
            </div>
          </div>

          {/* Shipping Corridors Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Shipping Corridors</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Corridor</th>
                  <th style={th}>Risk</th>
                  <th style={th}>Score</th>
                  <th style={th}>EONET</th>
                </tr></thead>
                <tbody>
                  {chokepoints.length===0 && <tr><td colSpan={4} style={{ ...td, textAlign:"center" as const }}>No data.</td></tr>}
                  {[...chokepoints].sort((a,b)=>(b.risk_score??0)-(a.risk_score??0)).map(cp => {
                    const rs = cp.risk_score??0;
                    const dot = rs>=70?"#e74c3c":rs>=40?"#f59e0b":"#27ae60";
                    return (
                      <tr key={cp.id}>
                        <td style={td}><span style={{ width:6,height:6,borderRadius:"50%",background:dot,display:"inline-block",marginRight:5 }}/>{cp.name}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:riskColor(rs) }}>{rs>=70?"HIGH":rs>=40?"MED":"LOW"}</td>
                        <td style={{ ...td, textAlign:"center" as const, fontWeight:700, color:riskColor(rs) }}>{rs}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:"#f59e0b" }}>{cp.eonet_nearby??0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {stress && <div style={{ marginTop:12 }}>
                <div style={{ fontWeight:600, fontSize:12, textTransform:"uppercase" as const, letterSpacing:1, color:"var(--text-muted)", marginBottom:6 }}>HIGH-RISK CORRIDORS</div>
                <div style={{ display:"flex", flexWrap:"wrap" as const, gap:4 }}>
                  {(stress.high_risk_chokepoints??[]).map((c,i)=>(
                    <span key={i} style={{ fontSize:11, padding:"2px 6px", background:"rgba(239,68,68,0.15)", border:"1px solid rgba(239,68,68,0.3)", borderRadius:3, color:"#f87171" }}>{c}</span>
                  ))}
                </div>
              </div>}
            </div>
          </div>

          {/* Critical Minerals Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Critical Minerals</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Mineral</th>
                  <th style={{ ...th, textAlign:"left" as const }}>Primary Producer</th>
                  <th style={th}>Market %</th>
                  <th style={th}>Risk</th>
                </tr></thead>
                <tbody>
                  {minerals.length===0 && <tr><td colSpan={4} style={{ ...td, textAlign:"center" as const }}>No mineral data.</td></tr>}
                  {[...minerals].sort((a,b)=>b.share_pct-a.share_pct).map(m => {
                    const rCls = m.share_pct>70?"critical":m.share_pct>40?"high":m.share_pct>20?"moderate":"low";
                    const rCol = rCls==="critical"?"var(--semantic-critical)":rCls==="high"?"var(--semantic-high)":rCls==="moderate"?"var(--semantic-elevated)":"var(--semantic-normal)";
                    return (
                      <tr key={m.id}>
                        <td style={{ ...td, color:"var(--text)", fontWeight:600 }}>{m.name}</td>
                        <td style={td}>{m.primary_producer}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:rCol, fontWeight:700 }}>{m.share_pct}%</td>
                        <td style={{ ...td, textAlign:"center" as const }}><span style={{ fontSize:11, fontWeight:700, textTransform:"uppercase" as const, color:rCol }}>{rCls}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Shipping Stress Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Shipping Stress</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {!stress && <div style={{ color:"var(--text-muted)", fontSize:13 }}>Shipping stress data unavailable.</div>}
              {stress && (
                <>
                  <StressGauge score={stress.stress_score} level={stress.stress_level} />
                  {stress.carriers?.map((c,i) => {
                    const typeLabel = "CARR";
                    return (
                      <div key={i} style={{ padding:"6px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                          <span style={{ fontSize:13, fontWeight:600, color:"var(--text)", flex:1 }}>{c.name}</span>
                          <span style={{ fontSize:11, padding:"1px 4px", background:"rgba(255,255,255,0.06)", borderRadius:2, color:"var(--text-dim)" }}>{typeLabel}</span>
                          <span style={{
                            fontSize:11, fontWeight:700, textTransform:"uppercase" as const, padding:"1px 6px", borderRadius:3,
                            background:c.risk==="high"?"rgba(239,68,68,0.15)":c.risk==="medium"?"rgba(245,158,11,0.15)":"rgba(34,197,94,0.15)",
                            color:c.risk==="high"?"#f87171":c.risk==="medium"?"#fcd34d":"#86efac",
                          }}>{c.risk}</span>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>

          {/* Strategic Risk Overview Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Strategic Risk Overview</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              <RiskRing score={srisk?.score??0} />
              <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:1, background:"var(--border)", marginBottom:12 }}>
                {[
                  { val:unifiedAlerts.filter(a=>a.priority==="critical"||a.priority==="high").length, label:"High Alerts" },
                  { val:conflicts.length, label:"Conflict Events" },
                  { val:impacted.size, label:"Impacted Nodes" },
                  { val:hazards.length, label:"Active Hazards" },
                ].map(({ val, label }) => (
                  <div key={label} style={{ background:"var(--surface)", padding:"6px 8px", textAlign:"center" as const }}>
                    <div style={{ fontSize:20, fontWeight:300, color:"var(--text)" }}>{val}</div>
                    <div style={{ fontSize:11, textTransform:"uppercase" as const, letterSpacing:1, color:"var(--text-muted)" }}>{label}</div>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontSize:11, fontWeight:700, textTransform:"uppercase" as const, letterSpacing:1, color:"var(--text-muted)", marginBottom:6 }}>TOP RISKS</div>
                {srisk?.components && Object.entries(srisk.components).map(([k,v],i) => (
                  <div key={k} style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                    <span style={{ fontSize:13, color:"var(--text-muted)", minWidth:16 }}>{i+1}.</span>
                    <span style={{ fontSize:13, color:"var(--text)", flex:1, textTransform:"capitalize" as const }}>{k.replace(/_/g," ")}</span>
                    <span style={{ fontSize:14, fontWeight:600, color:scoreColor(Number(v)) }}>{Number(v).toFixed(0)}</span>
                  </div>
                ))}
                {instability.slice(0,5).map((ci,i) => (
                  <div key={ci.country} style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                    <span style={{ fontSize:13, color:"var(--text-muted)", minWidth:16 }}>{(srisk?.components?Object.keys(srisk.components).length:0)+i+1}.</span>
                    <span style={{ fontSize:13, color:"var(--text)", flex:1 }}>{ci.country} instability</span>
                    <span style={{ fontSize:14, fontWeight:600, color:scoreColor(ci.instability_score) }}>{ci.instability_score.toFixed(0)}</span>
                  </div>
                ))}
              </div>
              {(mktImpl?.summary && mktImpl.summary.length > 0) && (
                <div style={{ marginTop:10 }}>
                  <div style={{ fontSize:11, fontWeight:700, textTransform:"uppercase" as const, letterSpacing:1, color:"var(--text-muted)", marginBottom:6 }}>MARKET IMPLICATIONS</div>
                  {mktImpl.summary.slice(0,3).map((line: string, i: number) => (
                    <div key={i} style={{ padding:"4px 6px", borderLeft:"2px solid var(--border)", color:"var(--text-secondary)", fontSize:13, marginBottom:3 }}>{line}</div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Predictive Intelligence Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Predictive Intelligence (T+48H)</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {(briefing?.critical_incidents as any[] ?? []).length === 0 && (
                <div style={{ padding:16, textAlign:"center" as const, color:"var(--text-dim)", fontSize:13 }}>
                  No projected disruptions in the 48h horizon.
                </div>
              )}
              {(briefing?.critical_incidents as any[] ?? []).map((inc, i) => (
                <div key={i} style={{ padding:10, background:"rgba(255,255,255,0.02)", border:"1px solid var(--border)", borderRadius:4, marginBottom:8, borderLeft:`3px solid ${ISSUE_COLORS[String(inc.category??"hazard").toLowerCase() as keyof typeof ISSUE_COLORS] || "var(--accent)"}` }}>
                  <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                    <span style={{ fontSize:13, fontWeight:700, color:"var(--text)" }}>{inc.event_title}</span>
                    <span style={{ fontSize:11, color:"var(--text-muted)", fontFamily:"var(--font-mono)" }}>PROJECTED T+48H</span>
                  </div>
                  <div style={{ fontSize:12, color:"var(--text-dim)", lineHeight:1.4, marginBottom:6 }}>{inc.reasoning}</div>
                  <div style={{ display:"flex", gap:10, fontSize:11, fontWeight:600 }}>
                    <span style={{ color:"var(--threat-critical)" }}>EXPOSURE: ${(inc.total_exposure_usd/1e6).toFixed(1)}M</span>
                    <span style={{ color:"var(--text-muted)" }}>AFFECTED NODES: {inc.affected_nodes?.length ?? 0}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Active Alerts Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Active Alerts</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {unifiedAlerts.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13, padding:8 }}>No active alerts.</div>}
              {unifiedAlerts.map(a => {
                const pCol = a.priority==="critical"?"var(--semantic-critical)":a.priority==="high"?"var(--semantic-high)":a.priority==="medium"?"var(--semantic-elevated)":"var(--semantic-normal)";
                const pEmoji = a.priority==="critical"?"🔴":a.priority==="high"?"🟠":a.priority==="medium"?"🟡":"🟢";
                const tEmoji = a.type==="earthquake"?"⚡":a.type==="hazard"?"🌪":a.type==="disaster"?"🌊":a.type==="composite"?"⚠️":"📍";
                return (
                  <div key={a.id} style={{ borderLeft:`3px solid ${pCol}`, padding:"6px 8px", marginBottom:4, background:"var(--overlay-subtle)", borderRadius:"0 3px 3px 0" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                      <span style={{ fontSize:14 }}>{tEmoji}</span>
                      <span style={{ fontSize:13, color:"var(--text)", flex:1, fontWeight:500 }}>{a.title}</span>
                      <span style={{ fontSize:14 }}>{pEmoji}</span>
                    </div>
                    <div style={{ fontSize:12, color:"var(--text-dim)", marginTop:2 }}>{a.summary}</div>
                    {a.time && <div style={{ fontSize:11, color:"var(--text-muted)", marginTop:2 }}>{a.time}</div>}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Intelligence Sources Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Intelligence Sources</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              <div style={{ display:"flex", gap:8, marginBottom:8, fontSize:12 }}>
                <span style={{ color:"var(--semantic-normal)" }}>● {liveSources} live</span>
                <span style={{ color:"var(--semantic-critical)" }}>● {deadSources} offline</span>
                <span style={{ color:"var(--text-muted)" }}>Overall: {overallStatus}</span>
              </div>
              {sources.map(s => (
                <div key={s.id} style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 0", borderBottom:"1px solid var(--border-subtle)", fontSize:13 }}>
                  <span style={{ width:6, height:6, borderRadius:"50%", background:s.fresh?"var(--status-live)":"var(--status-unavailable)", display:"inline-block", flexShrink:0 }} />
                  <span style={{ flex:1, color:"var(--text)" }}>{s.name}</span>
                  <span style={{ color:"var(--text-muted)", fontFamily:"var(--font-mono)", fontSize:12 }}>{s.records}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Live News Feed Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Live News Feed</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {news.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No news articles found.</div>}
              {news.map((n,i) => (
                <div key={n.id+i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <a href={n.url} target="_blank" rel="noreferrer" style={{ fontSize:13, color:"var(--text)", textDecoration:"none", fontWeight:600, display:"block", marginBottom:4 }}>{n.title}</a>
                  <div style={{ display:"flex", gap:8, fontSize:12, color:"var(--text-dim)" }}>
                    <span>{fmtDate(n.publishedAt)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Geological Hazards Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Geological Hazards</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {quakes.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No seismic activity reported.</div>}
              {quakes.slice(0,15).map((q,i) => (
                <div key={q.id+i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ display:"flex", justifyContent:"space-between" }}>
                    <span style={{ fontSize:13, fontWeight:600, color:"#f97316" }}>M{q.magnitude.toFixed(1)} {q.place}</span>
                    <span style={{ fontSize:11, color:"var(--text-dim)" }}>{fmtAgo(q.time)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Cyber Threats Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Cyber Threats</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {gdelt.filter(g => /cyber|hack|breach|malware|ransomware/i.test(g.title)).length === 0 && (
                <div style={{ padding:16, textAlign:"center" as const, color:"var(--text-dim)", fontSize:13 }}>No active cyber threats detected.</div>
              )}
              {gdelt.filter(g => /cyber|hack|breach|malware|ransomware/i.test(g.title)).map((g,i) => (
                <div key={i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ display:"flex", gap:8 }}>
                    <span style={{ color:ISSUE_COLORS.cyber, fontSize:14 }}>⚡</span>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:13, fontWeight:600, color:"var(--text)" }}>{g.title}</div>
                      <div style={{ fontSize:12, color:"var(--text-muted)", marginTop:2 }}>{g.source}</div>
                      <div style={{ fontSize:11, color:"var(--text-dim)", marginTop:4 }}>{fmtAgo(g.seendate)} · {g.country}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Conflict Events Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Conflict Events</span></div>
            <div style={{ ...pbCss, maxHeight: 310, overflowY: "auto" }}>
              {conflicts.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No active conflict events recorded.</div>}
              {conflicts.slice(0,15).map((c,i) => (
                <div key={i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ fontSize:13, fontWeight:600, color:"var(--threat-critical)" }}>{c.type}</div>
                  <div style={{ fontSize:12, color:"var(--text)", marginTop:2 }}>{c.notes}</div>
                  <div style={{ fontSize:11, color:"var(--text-dim)", marginTop:4 }}>{c.country} · {fmtDate(c.date)}</div>
                </div>
              ))}
            </div>
          </div>

"""
    new_content = content[:idx_start] + new_panels + content[idx_end:]

    # Remove the unneeded types
    new_content = re.sub(r'type SCTab.*?\n', '', new_content)
    new_content = re.sub(r'type RiskTab.*?\n', '', new_content)
    new_content = re.sub(r'type IntelTab.*?\n', '', new_content)

    new_content = new_content.replace(
        'gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))", gap:4, padding:4, overflowY:"auto", background:"var(--bg)", alignContent:"start"',
        'gridTemplateColumns:"repeat(auto-fill,minmax(340px,1fr))", gap:8, padding:8, overflowY:"auto", background:"var(--bg)", alignContent:"start"'
    )

    with open('NetworkView.tsx', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully unrolled panels")
else:
    print("Could not find markers.", idx_start, idx_end)
