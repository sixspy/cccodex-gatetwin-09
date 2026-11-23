import React, { useEffect, useState } from "react";
import { 取 } from "../api.js";

export default function 开腿账() {
  const [行, 设] = useState([]);
  const 刷 = () => 取("/开腿账").then(设);
  useEffect(() => { 刷(); }, []);
  return (
    <div>
      <h1 className="题">开腿账</h1>
      <p className="述">
        进站尚未出站的在途开腿。开腿落地即按超时权威（线路超时表优先，缺省回落站规）
        <strong>钉死本腿超时界</strong>；超时扫描只读钉界，改权威不回改在途腿。
      </p>
      <div className="行"><button className="次" onClick={刷}>刷新</button></div>
      {!行.length ? <div className="空态">暂无开腿。</div> : (
        <table>
          <thead><tr>
            <th>开腿键</th><th>卡号</th><th>进站站</th><th>进站时</th>
            <th>线路</th><th>钉死秒</th><th>权威来源</th><th>超时界</th><th>状态</th>
          </tr></thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.开腿键}>
                <td>{r.开腿键}</td><td>{r.卡号}</td><td>{r.进站站点键}</td>
                <td>{r.进站事件时}</td><td>{r.线路键 || "—"}</td>
                <td>{r.超时秒 ?? "—"}</td>
                <td><span className={`徽章 ${r.超时权威 === "线路超时表" ? "通" : "次"}`}>{r.超时权威 || "—"}</span></td>
                <td>{r.超时界 || "—"}</td><td>{r.状态}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
