import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 站规() {
  const [规, 设规] = useState(null);
  const [线, 设线] = useState([]);
  const [权威, 设权威] = useState(null);
  const [秒, 设秒] = useState("7200");
  const [线秒, 设线秒] = useState({});
  const [讯, 设讯] = useState("");
  const 刷 = () => {
    取("/站规").then((d) => { 设规(d); 设秒(d["最大行程秒"] ?? ""); });
    取("/线路超时").then(设线);
    取("/超时权威").then(设权威);
  };
  useEffect(() => { 刷(); }, []);
  const 存站规秒 = async () => {
    try {
      await 递("/站规", { 键: "最大行程秒", 值: 秒 });
      设讯("站规最大行程秒已改：只影响此后新钉的开腿，在途腿钉界不回改。");
      刷();
    } catch (e) { 设讯(String(e.message || e)); }
  };
  const 存线秒 = async (线路键, 值) => {
    try {
      await 递("/线路超时", { 线路键, 超时秒: 值 === "" ? null : Number(值) });
      设讯(`线路${线路键}超时已写闸。`);
      刷();
    } catch (e) { 设讯(String(e.message || e)); }
  };
  if (!规 || !权威) return <p className="讯">加载中…</p>;
  return (
    <div>
      <h1 className="题">站规</h1>
      <p className="述">配对与超时等口径。改权威只影响此后新钉的开腿；在途腿钉界不回改，贯验校验钉界有效与一腿不双判。</p>
      <table>
        <thead><tr><th>键</th><th>值</th></tr></thead>
        <tbody>
          {Object.entries(规).map(([k, v]) => (
            <tr key={k}><td>{k}</td><td>{v}</td></tr>
          ))}
        </tbody>
      </table>

      <div className="段">
        <div className="段题">超时权威（乙口径·全局唯一）</div>
        <p className="述">{权威.口径}。开腿落地钉死超时界，超时扫描只读钉界；改秒与扫描并发不半旁路。</p>
        <div className="行">
          <label>站规最大行程秒（缺省回落源）</label>
          <input className="入" style={{ width: "7rem" }} value={秒} onChange={(e) => 设秒(e.target.value)} />
          <button className="次 亮片" onClick={存站规秒}>改站规秒</button>
        </div>
        <table>
          <thead><tr><th>线路</th><th>名称</th><th>线路超时秒</th><th>权威来源</th><th>生效秒</th><th>写闸</th></tr></thead>
          <tbody>
            {线.map((ln) => (
              <tr key={ln.线路键}>
                <td>{ln.线路键}</td><td>{ln.名称}</td>
                <td>{ln.超时秒 ?? "—（回落站规）"}</td>
                <td><span className={`徽章 ${ln.权威来源 === "线路超时表" ? "通" : "次"}`}>{ln.权威来源}</span></td>
                <td>{ln.生效秒 ?? "—"}</td>
                <td>
                  <span className="行" style={{ margin: 0 }}>
                    <input
                      className="入" style={{ width: "5.5rem" }} placeholder="秒"
                      value={线秒[ln.线路键] ?? ""}
                      onChange={(e) => 设线秒({ ...线秒, [ln.线路键]: e.target.value })}
                    />
                    <button className="次" onClick={() => 存线秒(ln.线路键, 线秒[ln.线路键] ?? "")}>钉线秒</button>
                    <button className="次" onClick={() => 存线秒(ln.线路键, "")}>删行回落</button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="段">
        <div className="段题">已钉开腿超时界（只读）</div>
        {!权威.腿.length ? <div className="空态">暂无开腿。</div> : (
          <table>
            <thead><tr>
              <th>开腿键</th><th>卡号</th><th>线路</th><th>钉死秒</th>
              <th>权威来源</th><th>timeout_at</th><th>状态</th><th>valid</th>
            </tr></thead>
            <tbody>
              {权威.腿.map((r) => (
                <tr key={r.开腿键}>
                  <td>{r.开腿键}</td><td>{r.卡号}</td><td>{r.线路 || "—"}</td>
                  <td>{r.钉死秒 ?? "—"}</td><td>{r.权威来源 || "—"}</td>
                  <td>{r.timeout_at || "—"}</td><td>{r.状态}</td>
                  <td><span className={`徽章 ${r.valid ? "通" : "败"}`}>{r.valid ? "有效" : "撕裂"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {讯 && <p className="讯">{讯}</p>}
    </div>
  );
}
