"use client";

import { formatearImporte, type EfeReport } from "./api";

const ETIQUETA: Record<string, string> = {
  operativa: "Actividades operativas",
  inversion: "Actividades de inversión",
  financiacion: "Actividades de financiación",
};

export function EfeView({ report }: { report: EfeReport }) {
  return (
    <div>
      <p className="text-sm mb-3">
        Cuadre:{" "}
        <strong className={report.cuadre ? "text-emerald-700" : "text-red-600"}>
          {report.cuadre ? "correcto" : "descuadrado"}
        </strong>
      </p>
      <table className="w-full text-sm border mb-3">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Actividad</th>
            <th className="text-right p-2">Cobros</th>
            <th className="text-right p-2">Pagos</th>
            <th className="text-right p-2">Neto</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(report.actividades).map(([clave, valor]) => (
            <tr key={clave} className="border-t">
              <td className="p-2">{ETIQUETA[clave] ?? clave}</td>
              <td className="p-2 text-right">{formatearImporte(valor.cobros)}</td>
              <td className="p-2 text-right">{formatearImporte(valor.pagos)}</td>
              <td className="p-2 text-right">{formatearImporte(valor.neto)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <span>Saldo inicial de tesorería</span>
        <span className="text-right">
          {formatearImporte(report.saldo_inicial_tesoreria)}
        </span>
        <span>Variación neta</span>
        <span className="text-right">{formatearImporte(report.variacion_neta)}</span>
        <span className="font-semibold">Saldo final de tesorería</span>
        <span className="text-right font-semibold">
          {formatearImporte(report.saldo_final_tesoreria)}
        </span>
      </div>
    </div>
  );
}