"""
WatchCrawler GUI - giao dien web cho crawler (Flask).
Chay:  python app.py   ->  mo http://127.0.0.1:5050
"""
import os
import threading
import time
import webbrowser

from flask import Flask, jsonify, request, send_file

import crawler

app = Flask(__name__)
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
os.makedirs(OUT_DIR, exist_ok=True)

STATE = {"running": False, "logs": [], "items": [], "file": None, "start": 0, "end": 0,
         "target": 0, "counts": {}}
LOCK = threading.Lock()


def log(msg):
    with LOCK:
        STATE["logs"].append(f"{time.strftime('%H:%M:%S')}  {msg}")
        STATE["logs"] = STATE["logs"][-500:]


def on_item(row, source):
    with LOCK:
        STATE["items"].append({
            "sku": row["SKU"], "name": row["Name"], "price": row["Sale price"] or row["Regular price"],
            "regular": row["Regular price"], "cat": row["Categories"], "src": source,
            "img": (row["Images"].split(",")[0] or "").strip()})
        STATE["counts"][source] = STATE["counts"].get(source, 0) + 1


crawler.LOG = log


def worker(cfg):
    try:
        opt = crawler.Options(
            limit=int(cfg.get("limit") or 50), min_price=int(cfg.get("min_price") or 0),
            max_price=int(cfg.get("max_price") or 0), keyword=cfg.get("keyword", ""),
            max_images=int(cfg.get("max_images") or 5), delay=float(cfg.get("delay") or 0.3),
            only_sale=bool(cfg.get("only_sale")))
        cats = [int(c) for c in cfg.get("categories", [])]
        rows = crawler.run(cfg.get("sites", []), cats, opt, on_item)
        name = (cfg.get("filename") or "woocommerce_watches").replace("/", "_")
        path = os.path.join(OUT_DIR, name if name.endswith(".csv") else name + ".csv")
        n = crawler.save_csv(rows, path)
        with LOCK:
            STATE["file"] = os.path.basename(path)
        log(f"HOÀN TẤT: {n} sản phẩm (đã loại trùng SKU)" + (" – đã dừng theo yêu cầu" if crawler.STOP.is_set() else ""))
    except Exception as e:
        log(f"LỖI: {e}")
    finally:
        with LOCK:
            STATE["running"] = False
            STATE["end"] = time.time()


@app.post("/api/start")
def start():
    if STATE["running"]:
        return jsonify(ok=False, msg="Crawler đang chạy")
    cfg = request.get_json(force=True)
    sources = len(cfg.get("categories", [])) * ("tiki" in cfg.get("sites", [])) + ("watchstore" in cfg.get("sites", []))
    crawler.STOP.clear()
    STATE.update(running=True, logs=[], items=[], file=None, start=time.time(), end=0,
                 target=sources * int(cfg.get("limit") or 50), counts={})
    threading.Thread(target=worker, args=(cfg,), daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/stop")
def stop():
    crawler.STOP.set()
    log("Đang dừng crawler...")
    return jsonify(ok=True)


@app.get("/api/status")
def status():
    since = int(request.args.get("since", 0))
    with LOCK:
        el = (STATE["end"] or time.time()) - STATE["start"] if STATE["start"] else 0
        return jsonify(running=STATE["running"], logs=STATE["logs"][-200:], total=len(STATE["items"]),
                       items=STATE["items"][since:], target=STATE["target"], file=STATE["file"],
                       counts=STATE["counts"], elapsed=int(el))


@app.get("/download/<name>")
def download(name):
    return send_file(os.path.join(OUT_DIR, os.path.basename(name)), as_attachment=True)


@app.get("/")
def index():
    return PAGE


PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>WatchCrawler – Tiki & WatchStore → WooCommerce</title>
<style>
:root{--bg:#0d0d16;--card:#161627;--line:#2a2a44;--gold:#c9a14a;--txt:#e6e6f0;--mut:#8d8da8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:18px 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px}
header h1{margin:0;font-size:20px;letter-spacing:2px}header h1 span{color:var(--gold)}header small{color:var(--mut)}
main{display:grid;grid-template-columns:330px 1fr;gap:18px;padding:18px 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px}
h3{margin:0 0 12px;font-size:13px;letter-spacing:1.5px;color:var(--gold);text-transform:uppercase}
label{display:block;margin:10px 0 4px;color:var(--mut);font-size:12.5px}
input[type=text],input[type=number]{width:100%;background:#0f0f1c;border:1px solid var(--line);color:var(--txt);padding:8px 10px;border-radius:5px}
.chk{display:flex;align-items:center;gap:8px;margin:6px 0;color:var(--txt);font-size:13.5px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btns{display:flex;gap:10px;margin-top:16px}
button{flex:1;padding:11px;border:0;border-radius:5px;font-weight:700;letter-spacing:1px;cursor:pointer}
#go{background:var(--gold);color:#111}#go:disabled{opacity:.4}#stop{background:#3a2030;color:#ff8fa3}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.stat b{display:block;font-size:24px;color:#fff}.stat span{color:var(--mut);font-size:12px}
.bar{height:6px;background:#22223a;border-radius:3px;overflow:hidden;margin-bottom:14px}.bar i{display:block;height:100%;background:var(--gold);width:0;transition:.4s}
#log{height:190px;overflow:auto;background:#08080f;border-radius:6px;padding:10px;font:12px Menlo,monospace;color:#9fe39f;white-space:pre-wrap;margin:0}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:var(--mut);font-weight:500;padding:6px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--card)}
td{padding:6px;border-bottom:1px solid #1e1e33;vertical-align:middle}td img{width:38px;height:38px;object-fit:cover;border-radius:4px;background:#fff}
.tbl{max-height:360px;overflow:auto;margin-top:14px}.src{font-size:11px;padding:2px 7px;border-radius:10px;background:#24243d}.src.Tiki{color:#5ab0ff}.src.WatchStore{color:var(--gold)}
.dl{display:none;margin-top:12px;background:#1d2a1d;border:1px solid #2f5a2f;padding:10px 14px;border-radius:6px}.dl a{color:var(--gold);font-weight:700}
s{color:var(--mut)}
</style></head><body>
<header><h1>WATCH<span>CRAWLER</span></h1><small>Thu thập đồng hồ từ Tiki & WatchStore qua API → CSV nhập WooCommerce · 24520176 – Nguyễn Văn Gia Bảo</small></header>
<main>
<div class="card">
 <h3>Nguồn dữ liệu</h3>
 <div class="chk"><input type="checkbox" id="s_tiki" checked> Tiki.vn (API listings + product detail)</div>
 <div style="margin-left:24px">
  <div class="chk"><input type="checkbox" class="cat" value="1778" checked> Đồng hồ nam (1778)</div>
  <div class="chk"><input type="checkbox" class="cat" value="977" checked> Đồng hồ nữ (977)</div>
  <div class="chk"><input type="checkbox" class="cat" value="11375"> Đồng hồ trẻ em (11375)</div>
 </div>
 <div class="chk"><input type="checkbox" id="s_ws" checked> WatchStore.vn (Shopify products.json)</div>
 <h3 style="margin-top:18px">Tuỳ chỉnh</h3>
 <label>Số sản phẩm tối đa mỗi nguồn / danh mục</label><input type="number" id="limit" value="200">
 <div class="row2"><div><label>Giá từ (đ)</label><input type="number" id="min_price" value="0"></div>
 <div><label>Đến (đ, 0 = không giới hạn)</label><input type="number" id="max_price" value="0"></div></div>
 <label>Từ khoá trong tên (vd: casio)</label><input type="text" id="keyword" placeholder="để trống = lấy tất cả">
 <div class="row2"><div><label>Số ảnh / sản phẩm</label><input type="number" id="max_images" value="5"></div>
 <div><label>Delay giữa request (s)</label><input type="number" id="delay" value="0.3" step="0.1"></div></div>
 <div class="chk" style="margin-top:10px"><input type="checkbox" id="only_sale"> Chỉ lấy sản phẩm đang giảm giá</div>
 <label>Tên file CSV</label><input type="text" id="filename" value="woocommerce_watches_500">
 <div class="btns"><button id="go">▶ BẮT ĐẦU</button><button id="stop">■ DỪNG</button></div>
</div>
<div>
 <div class="stats">
  <div class="stat"><b id="st_total">0</b><span>Sản phẩm đã lấy</span></div>
  <div class="stat"><b id="st_tiki">0</b><span>Từ Tiki</span></div>
  <div class="stat"><b id="st_ws">0</b><span>Từ WatchStore</span></div>
  <div class="stat"><b id="st_time">0s</b><span id="st_state">Sẵn sàng</span></div>
 </div>
 <div class="bar"><i id="bar"></i></div>
 <div class="card"><h3>Nhật ký</h3><pre id="log"></pre>
  <div class="dl" id="dl">✓ Đã xuất file: <a id="dla" href="#"></a> — import tại WooCommerce › Sản phẩm › Nhập</div></div>
 <div class="card" style="margin-top:14px"><h3>Xem trước dữ liệu</h3>
  <div class="tbl"><table><thead><tr><th></th><th>SKU</th><th>Tên sản phẩm</th><th>Giá</th><th>Danh mục</th><th>Nguồn</th></tr></thead><tbody id="tb"></tbody></table></div></div>
</div></main>
<script>
const $=id=>document.getElementById(id);let seen=0,timer=null;
const fmt=n=>n?Number(n).toLocaleString('vi-VN')+'đ':'';
$('go').onclick=async()=>{
 const sites=[];if($('s_tiki').checked)sites.push('tiki');if($('s_ws').checked)sites.push('watchstore');
 const cfg={sites,categories:[...document.querySelectorAll('.cat:checked')].map(c=>c.value),
  limit:$('limit').value,min_price:$('min_price').value,max_price:$('max_price').value,keyword:$('keyword').value,
  max_images:$('max_images').value,delay:$('delay').value,only_sale:$('only_sale').checked,filename:$('filename').value};
 const r=await(await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})).json();
 if(!r.ok)return alert(r.msg);seen=0;$('tb').innerHTML='';$('dl').style.display='none';poll();};
$('stop').onclick=()=>fetch('/api/stop',{method:'POST'});
async function poll(){
 const s=await(await fetch('/api/status?since='+seen)).json();
 $('log').textContent=s.logs.join('\n');$('log').scrollTop=1e9;
 $('st_total').textContent=s.total;$('st_tiki').textContent=s.counts.Tiki||0;$('st_ws').textContent=s.counts.WatchStore||0;
 $('st_time').textContent=s.elapsed+'s';$('st_state').textContent=s.running?'Đang chạy...':(s.file?'Hoàn tất':'Sẵn sàng');
 $('bar').style.width=(s.target?Math.min(100,s.total*100/s.target):0)+'%';$('go').disabled=s.running;
 const tb=$('tb');for(const it of s.items){const tr=document.createElement('tr');
  tr.innerHTML=`<td><img src="${it.img}" loading="lazy"></td><td>${it.sku}</td><td>${it.name}</td><td>${fmt(it.price)}${it.regular&&it.regular!=it.price?'<br><s>'+fmt(it.regular)+'</s>':''}</td><td>${it.cat}</td><td><span class="src ${it.src}">${it.src}</span></td>`;
  tb.prepend(tr);}seen=s.total;
 if(s.file){$('dl').style.display='block';$('dla').textContent=s.file;$('dla').href='/download/'+s.file;}
 clearTimeout(timer);if(s.running)timer=setTimeout(poll,1000);}
poll();
</script></body></html>"""

if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5050")).start() if os.environ.get("NO_BROWSER") is None else None
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
