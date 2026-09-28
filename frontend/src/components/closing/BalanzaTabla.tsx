"use client";

import { formatearImporte, type LineaBalanza } from "./api";

interface Props {
  lineas: LineaBalanza[];
  totalDebe: string;
  totalHaber: string;
  resultadoProvisional?: string;
  cargando?: boolean;
}

/**
 * Tabla de balance de comprobacion del periodo (SPEC-028 T023).
 * Los importes viajan como cadenas de 4 decimales y solo se formatean al pintar.
 */
export default function BalanzaTabla({
  lineas,
  totalDebe,
  totalHaber,
  resultadoProvisional,
  cargando = false,
}: Props) {
  if (cargando) {
    return <p className="text-sm text-gray-500">Cargando balance…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-gray-50 text-xs uppercase text-gray-600">
            <tr>
              <th className="p-3">Codigo</th>
              <th className="p-3">Cuenta</th>
              <th className="p-3">Nivel</th>
              <th className="p-3 text-right">Debe</th>
              <th className="p-3 text-right">Haber</th>
              <th className="p-3 text-right">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {lineas.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-gray-400">
                  Sin movimientos en el periodo
                </td>
              </tr>
            ) : (
              lineas.map((linea) => (
                <tr key={linea.cuenta_id} className="border-b hover:bg-gray-50">
                  <td className="p-3 font-mono">{linea.codigo}</td>
                  <td className="p-3">{linea.nombre}</td>
                  <td className="p-3 text-gray-500">{linea.nivel}</td>
                  <td className="p-3 text-right font-mono">
                    {formatearImporte(linea.debe)}
                  </td>
                  <td className="p-3 text-right font-mono">
                    {formatearImporte(linea.haber)}
                  </td>
                  <td
                    className={`p-3 text-right font-mono ${
                      Number(linea.saldo) < 0 ? "text-red-700" : ""
                    }`}
                  >
                    {formatearImporte(linea.saldo)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
          <tfoot className="border-t bg-gray-50 font-semibold">
            <tr>
              <td className="p-3" colSpan={3}>
                Total
              </td>
              <td className="p-3 text-right font-mono">
                {formatearImporte(totalDebe)}
              </td>
              <td className="p-3 text-right font-mono">
                {formatearImporte(totalHaber)}
              </td>
              <td className="p-3 text-right font-mono">
                {totalDebe === totalHaber ? "Cuadra" : "DESCUADRE"}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {resultadoProvisional !== undefined && (
        <p className="text-sm text-gray-600">
          Resultado provisional del periodo (grupos 6/7):{" "}
          <span className="font-mono font-semibold">
            {formatearImporte(resultadoProvisional)}
          </span>
        </p>
      )}
    </div>
  );
}
