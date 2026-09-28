interface ItemBalance {
  code: string;
  name: string;
  debe: string;
  haber: string;
  saldo: string;
}

export default function TrialBalanceTable({ items }: { items: ItemBalance[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b">
          <th className="text-left p-2">Cuenta</th>
          <th className="text-left p-2">Nombre</th>
          <th className="text-right p-2">Debe</th>
          <th className="text-right p-2">Haber</th>
          <th className="text-right p-2">Saldo</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.code} className="border-b">
            <td className="p-2 font-mono">{item.code}</td>
            <td className="p-2">{item.name}</td>
            <td className="text-right p-2 font-mono">{item.debe}</td>
            <td className="text-right p-2 font-mono">{item.haber}</td>
            <td className="text-right p-2 font-mono">{item.saldo}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
