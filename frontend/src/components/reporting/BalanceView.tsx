"use client";

import { formatearImporte, type BalanceReport } from "./api";

function Bloque({ titulo, masas }: { titulo: string; masas: BalanceReport["activo"] }) {
  return (
    <div className="mb-4">
      <h3 className="font-medium mb-1">{titulo}</h3>
      <table className="w-full text-sm border">
        <tbody>
          {masas.map((masa) => (
            <tr key={masa.codigo} className="border-t">
              <td className="p-2">{masa.nombre}</td>
              <td className="p-2 text-right">{formatearImporte(masa.importe)}</td>
            </tr>
          ))}
          {masas.length === 0 && (
            <tr>
              <td className="p-2 text-gray-500" colSpan={2}>
                (sin movimientos)
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function BalanceView({ report }: { report: BalanceReport }) {
  return (
    <div>
      <p className="text-sm mb-3">
        Cuadre:{" "}
        <strong className={report.cuadre ? "text-emerald-700" : "text-red-600"}>
          {report.cuadre ? "correcto" : "descuadrado"}
        </strong>
        {report.hay_cuentas_sin_agrupar && (
          <span className="text-amber-700 ml-3">
            (hay cuentas sin agrupar en &quot;Otros&quot;)
          </span>
        )}
      </p>
      <Bloque titulo="ACTIVO" masas={report.activo} />
      <Bloque titulo="PASIVO" masas={report.pasivo} />
      <Bloque titulo="PATRIMONIO NETO" masas={report.patrimonio} />
      <div className="grid grid-cols-2 gap-2 text-sm font-semibold mt-2">
        <span>Total Activo</span>
        <span className="text-right">{formatearImporte(report.total_activo)}</span>
        <span>Total Pasivo + Patrimonio</span>
        <span className="text-right">
          {formatearImporte(
            String(Number(report.total_pasivo) + Number(report.total_patrimonio))
          )}
        </span>
      </div>
    </div>
  );
}