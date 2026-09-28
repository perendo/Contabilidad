export interface ErrorImport {
  fila: number;
  grupo_asiento: string;
  cuenta: string | null;
  tipo_error: string;
  mensaje: string;
}

export interface ResultadoPrevisualizacion {
  total_asientos: number;
  asientos_validos: number;
  asientos_con_error: number;
  errores: ErrorImport[];
}

export default function ResultadoImport({
  resultado,
}: {
  resultado: ResultadoPrevisualizacion;
}) {
  return (
    <div className="mt-4">
      <p className="mb-2 text-sm">
        Total {resultado.total_asientos} · Válidos {resultado.asientos_validos} · Errores{" "}
        {resultado.asientos_con_error}
      </p>
      {resultado.errores.length > 0 && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-right p-2">Fila</th>
              <th className="text-left p-2">Asiento</th>
              <th className="text-left p-2">Cuenta</th>
              <th className="text-left p-2">Tipo</th>
              <th className="text-left p-2">Mensaje</th>
            </tr>
          </thead>
          <tbody>
            {resultado.errores.map((e, i) => (
              <tr key={i} className="border-b text-red-700">
                <td className="text-right p-2 font-mono">{e.fila}</td>
                <td className="p-2 font-mono">{e.grupo_asiento}</td>
                <td className="p-2 font-mono">{e.cuenta ?? "—"}</td>
                <td className="p-2">{e.tipo_error}</td>
                <td className="p-2">{e.mensaje}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
