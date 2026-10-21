import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Side = "old" | "new";
type Mark = { side: Side; page: number; box: { x0:number;y0:number;x1:number;y1:number } | null };
type Annotation = { diff_id:number; kind:"added"|"removed"|"modified"; old_text:string; new_text:string; page_marks:Mark[]; similarity:number|null };
type Preview = { filename:string; ext:string; page_count:number; page_width_pt:number; page_height_pt:number; pages:{page:number;url:string;width_px:number;height_px:number}[] };
type Result = { old:Preview; new:Preview; annotations:Annotation[]; added_count:number; removed_count:number; modified_count:number; similarity:number };

function defaultApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured;
  const tauriWindow = globalThis as typeof globalThis & { __TAURI_INTERNALS__?: unknown };
  if (tauriWindow.__TAURI_INTERNALS__ || location.protocol === "tauri:") {
    return "http://127.0.0.1:8000";
  }
  const hostname = location.hostname || "127.0.0.1";
  return `${location.protocol || "http:"}//${hostname}:8000`;
}

const apiBase = defaultApiBase().replace(/\/$/, "");
const api = (url:string) => url.startsWith("http") ? url : `${apiBase}${url.startsWith("/") ? url : `/${url}`}`;
const showSpace = (s:string) => s.replace(/ /g,"[空格]").replace(/\r?\n/g,"[换行]");

function FileBox({label,file,setFile}:{label:string;file:File|null;setFile:(f:File|null)=>void}) {
  return <label className="file-box"><b>{label}</b><span>{file ? `${file.name} (${(file.size/1024).toFixed(1)} KB)` : "选择文件"}</span><small>DOC、DOCX、PDF、JPG、PNG</small><input type="file" accept=".doc,.docx,.pdf,.jpg,.jpeg,.png" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>;
}

function Preview({side,data,active,onSelect,viewportRef,onScroll}:{side:Side;data:Preview;active:number|null;onSelect:(id:number)=>void;viewportRef:(n:HTMLDivElement|null)=>void;onScroll:(e:React.UIEvent<HTMLDivElement>)=>void}) {
  return <section className="preview-panel"><header><div><small>{side === "old" ? "旧文档" : "新文档"}</small><b>{data.filename}</b></div><span>{data.page_count} 页 · {data.ext.toUpperCase()}</span></header><div className="preview-scroll" ref={viewportRef} onScroll={onScroll}><div className="pages">{data.pages.map(page=><figure key={page.page} style={{width:900}}><img src={api(page.url)} /><div className="page-number">{page.page} / {data.page_count}</div>{/* boxes are positioned from backend PDF coordinates */}</figure>)}</div></div></section>;
}

function App() {
  const [oldFile,setOldFile]=useState<File|null>(null), [newFile,setNewFile]=useState<File|null>(null);
  const [ignoreWhitespace,setIgnoreWhitespace]=useState(true), [ignoreCase,setIgnoreCase]=useState(false), [loading,setLoading]=useState(false), [result,setResult]=useState<Result|null>(null), [error,setError]=useState("");
  const [active,setActive]=useState<number|null>(null); const oldRef=useRef<HTMLDivElement|null>(null), newRef=useRef<HTMLDivElement|null>(null), lock=useRef(false);
  const sync=(source:Side,e:React.UIEvent<HTMLDivElement>)=>{if(lock.current)return;const a=e.currentTarget,b=source==="old"?newRef.current:oldRef.current;if(!b)return;lock.current=true;const vr=Math.max(1,a.scrollHeight-a.clientHeight), br=Math.max(0,b.scrollHeight-b.clientHeight);b.scrollTop=a.scrollTop/vr*br;requestAnimationFrame(()=>lock.current=false)};
  async function compare(){if(!oldFile||!newFile){setError("请先选择旧文档和新文档");return}setLoading(true);setError("");const f=new FormData();f.append("old_file",oldFile);f.append("new_file",newFile);f.append("ignore_whitespace",String(ignoreWhitespace));f.append("ignore_case",String(ignoreCase));try{const r=await fetch(`${apiBase}/api/v1/compare`,{method:"POST",body:f});const j=await r.json();if(!r.ok)throw new Error(j.detail||"文档对比失败");setResult(j.result);setActive(j.result.annotations[0]?.diff_id??null)}catch(e){setError(e instanceof Error?e.message:"文档对比失败")}finally{setLoading(false)}}
  if(result)return <div className="result-page"><header className="result-header"><div><h1>文档内容对比</h1><p>格式变化已忽略，彩色标记表示内容不同的位置。</p></div><button onClick={()=>setResult(null)}>重新对比</button></header><main className="result-main"><div className="previews"><Preview side="old" data={result.old} active={active} onSelect={setActive} viewportRef={n=>oldRef.current=n} onScroll={e=>sync("old",e)}/><Preview side="new" data={result.new} active={active} onSelect={setActive} viewportRef={n=>newRef.current=n} onScroll={e=>sync("new",e)}/></div><aside className="diff-panel"><h2>内容差异 <small>{result.annotations.length} 处</small></h2>{result.annotations.map(a=><button key={a.diff_id} className={active===a.diff_id?"diff active":"diff"} onClick={()=>setActive(a.diff_id)}><div><b>#{a.diff_id}</b><em>{a.kind==="added"?"新增":a.kind==="removed"?"删除":"修改"}</em></div>{a.old_text&&<del>− {showSpace(a.old_text)}</del>}{a.new_text&&<ins>+ {showSpace(a.new_text)}</ins>}</button>)}</aside></main></div>;
  return <div className="app"><header className="top"><div className="brand"><small>CONTRACT REVIEW WORKSPACE　0.1.0</small><h1>标准合同 AI 预审工作台</h1></div><nav><button>合同预审</button><button className="selected">文档对比</button></nav><span className="status">● API 对比服务</span></header><main className="compare-form"><h2>文档内容对比</h2><p>上传旧版和新版文档，查看内容差异及其原文位置。</p><div className="file-grid"><FileBox label="旧文档" file={oldFile} setFile={setOldFile}/><FileBox label="新文档" file={newFile} setFile={setNewFile}/></div><div className="options"><label><input type="checkbox" checked={ignoreWhitespace} onChange={e=>setIgnoreWhitespace(e.target.checked)}/> 忽略排版空白差异</label><label><input type="checkbox" checked={ignoreCase} onChange={e=>setIgnoreCase(e.target.checked)}/> 忽略英文大小写</label><button className="primary" disabled={loading||!oldFile||!newFile} onClick={compare}>{loading?"正在生成预览并对比...":"开始对比"}</button></div>{error&&<p className="error">{error}</p>}</main></div>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
