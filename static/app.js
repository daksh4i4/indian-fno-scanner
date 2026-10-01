let allRows = [];

async function api(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function render() {
  const q = document.getElementById("search").value.trim().toUpperCase();
  const rows = allRows.filter(x => x.symbol.includes(q));
  let buy=0,sell=0,wait=0;
  allRows.forEach(x => x.signal==="BUY"?buy++:x.signal==="SELL"?sell++:wait++);
  document.getElementById("count").textContent = allRows.length;
  document.getElementById("buy").textContent = buy;
  document.getElementById("sell").textContent = sell;
  document.getElementById("wait").textContent = wait;
  document.getElementById("rows").innerHTML = rows.map(x => `
    <tr>
      <td><b>${esc(x.symbol)}</b></td>
      <td>${x.ltp ? Number(x.ltp).toFixed(2) : "—"}</td>
      <td>${x.change_pct ? Number(x.change_pct).toFixed(2)+"%" : "—"}</td>
      <td>${esc(x.wave)}</td>
      <td>${esc(x.tide)}</td>
      <td><b>${Number(x.score||0).toFixed(0)}</b></td>
      <td>1:${Number(x.rr||2).toFixed(1)}</td>
      <td><span class="signal ${String(x.signal).toLowerCase()}">${esc(x.signal)}</span></td>
    </tr>`).join("");
}

async function refresh() {
  try {
    const s = await api("/api/status");
    document.getElementById("status").textContent = String(s.status).toUpperCase();
    document.getElementById("dot").className = s.feed_connected ? "on" : "";
    const d = await api("/api/scanner");
    allRows = d.stocks || [];
    render();
  } catch(e) {
    document.getElementById("status").textContent = "ERROR";
  }
}

async function openSettings() {
  const s = await api("/api/settings");
  Object.keys(s).forEach(k => {
    const el = document.getElementById(k);
    if (el) el.value = s[k];
  });
  document.getElementById("modal").classList.add("show");
}
function closeSettings(){ document.getElementById("modal").classList.remove("show"); }

async function saveSettings() {
  const ids = ["wave_timeframe","tide_timeframe","entry_timeframe","ema_fast","ema_mid","ema_slow",
    "rsi_length","rsi_overbought","rsi_oversold","macd_fast","macd_slow","macd_signal",
    "stoch_k","stoch_d","stoch_smooth","volume_sma","sr_lookback","pivot",
    "buy_threshold","sell_threshold","min_confirmation","minimum_rr"];
  const payload = {};
  ids.forEach(k => {
    const el = document.getElementById(k);
    if (!el) return;
    payload[k] = el.type === "number" ? Number(el.value) : el.value;
  });
  try {
    await api("/api/settings", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    closeSettings();
    refresh();
  } catch(e) { alert("Could not save settings: "+e.message); }
}

async function resetSettings() {
  await api("/api/reset", {method:"POST"});
  openSettings();
}

document.getElementById("search").addEventListener("input", render);
refresh();
setInterval(refresh, 3000);
