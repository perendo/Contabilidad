interface Movimiento {
  fecha: string;
  numero: number | null;
  concepto: string;
  debe: string;
  haber: string;
  saldo_acumulado: string;
}

export default function LedgerTable({ movimientos }: { movimientos: Movimiento[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b">
          <th className="text-left p-2">Fecha</th>
          <th className="text-right p-2">Nº</th>
          <th className="text-left p-2">Concepto</th>
          <th className="text-right p-2">Debe</th>
          <th className="text-right p-2">Haber</th>
          <th className="text-right p-2">Saldo</th>
        </tr>
      </thead>
      <tbody>
        {movimientos.map((m, i) => (
          <tr key={i} className="border-b">
            <td className="p-2 font-mono">{m.fecha}</td>
            <td className="text-right p-2 font-mono">{m.numero ?? "—"}</td>
            <td className="p-2">{m.concepto}</td>
            <td className="text-right p-2 font-mono">{m.debe}</td>
            <td className="text-right p-2 font-mono">{m.haber}</td>
            <td className="text-right p-2 font-mono">{m.saldo_acumulado}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
