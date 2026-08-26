import { useState } from "react";
import { api } from "../api";

export default function SubnetOverlay({ onClose }: { onClose: () => void }) {
  const [cidr, setCidr] = useState("10.10.10.0/24");
  const [split, setSplit] = useState("");
  const [calc, setCalc] = useState<any>(null);
  const [err, setErr] = useState("");

  async function run() {
    setErr("");
    try {
      setCalc(await api("/api/calc/subnet", { method: "POST", body: JSON.stringify({ cidr, split: Number(split) || null }) }));
    } catch (e: any) {
      setErr(e.message);
      setCalc(null);
    }
  }

  return (
    <div className="overlay-card">
      <div className="row">
        <strong>Subnet</strong>
        <span className="spacer" />
        <button className="ghost" onClick={onClose}>Close</button>
      </div>
      <div className="row">
        <input value={cidr} onChange={(e) => setCidr(e.target.value)} placeholder="CIDR" />
        <input value={split} onChange={(e) => setSplit(e.target.value)} placeholder="split" style={{ width: 72 }} />
        <button className="primary" onClick={run}>Calc</button>
      </div>
      {err && <p className="dobar-err">{err}</p>}
      {calc && (
        <pre className="mono-out">{`network ${calc.network}/${calc.prefix}
mask ${calc.netmask}  wildcard ${calc.wildcard}
hosts ${calc.first_host} – ${calc.last_host} (${calc.usable_hosts})`}</pre>
      )}
    </div>
  );
}
