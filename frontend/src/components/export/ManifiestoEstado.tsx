"use client";

import { ETIQUETA_ESTADO, type Exportacion, type Verificacion } from "./api";

/**
 * T035 · Estado de integridad de la exportacion.
 *
 * Muestra la huella calculada frente a la del manifiesto y, si la verificacion
 * falla, el detalle de las diferencias por bloque. Los importes nunca se
 * interpretan como numero: viajan como cadenas de 4 decimales.
 */
export default function ManifiestoEstado({
  exportacion,
  verificacion,
}: {
  exportacion: Exportacion;
  verificacion: Verificacion | null;
}) {
  const huella = verificacion
    ? verificacion.sha256_calculado === verificacion.sha256_manifiesto
    : null;

  return (
    <section className="space-y-3">
      <div
        className={`rounded border p-4 text-sm ${
          verificacion === null
            ? "border-gray-200 bg-gray-50 text-gray-700"
            : verificacion.integro
              ? "border-green-300 bg-green-50 text-green-800"
              : "border-red-300 bg-red-50 text-red-800"
        }`}
      >
        <p className="font-semibold">
          {verificacion === null
            ? "Integridad sin verificar"
            : verificacion.integro
              ? "Integridad correcta"
              : "Integridad rota: el archivo no corresponde a su manifiesto"}
        </p>
        {verificacion && (
          <>
            <p className="mt-1 text-xs">
              Huella calculada: <span className="font-mono">{verificacion.sha256_calculado}</span>
            </p>
            <p className="text-xs">
              Huella del manifiesto:{" "}
              <span className="font-mono">
                {verificacion.sha256_manifiesto ?? "—"}
              </span>
              {huella === true && " · coinciden"}
            </p>
            <p className="text-xs">
              Estado del archivo: {ETIQUETA_ESTADO[exportacion.estado]}
              {exportacion.completado_at
                ? ` · completado ${exportacion.completado_at.slice(0, 19)}`
                : ""}
            </p>
          </>
        )}
      </div>

      {verificacion && !verificacion.integro && (
        <table className="w-full text-sm border-collapse">
          <caption className="sr-only">Diferencias detectadas</caption>
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Tipo</th>
              <th className="py-2 pr-3">Bloque</th>
              <th className="py-2">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {verificacion.diferencias.map((diferencia, indice) => (
              <tr key={`${diferencia.tipo}-${indice}`} className="border-b">
                <td className="py-1.5 pr-3 font-mono text-xs">{diferencia.tipo}</td>
                <td className="py-1.5 pr-3">{diferencia.bloque ?? "—"}</td>
                <td className="py-1.5">{diferencia.detalle}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
