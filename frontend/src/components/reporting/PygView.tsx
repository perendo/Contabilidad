"use client";

import { formatearImporte, type PygReport } from "./api";

export function PygView({ report }: { report: PygReport }) {
  return (
    <div>
      <p className="text-sm mb-3">
        Resultado:{" "}
        <strong
          className={
            Number(report.resultado_ejercicio) >= 0
              ? "text-emerald-700"
              : "text-red-600"
          }
        >
          {formatearImporte(report.resultado_ejercicio)}
        </strong>
        <span className="ml-3 text-gray-600">
          {report.coincide_cierre
            ? "coincide con el cierre"
            : "no coincide con el cierre (descuadre)"}
        </span>
      </p>
      <table className="w-full text-sm border mb-3">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Grupo</th>
            <th className="text-left p-2">Nombre</th>
            <th className="text-right p-2">Importe</th>
          </tr>
        </thead>
        <tbody>
          {report.partidas.map((p) => (
            <tr key={p.grupo} className="border-t">
              <td className="p-2 font-mono">{p.grupo}</td>
              <td className="p-2">{p.nombre}</td>
              <td className="p-2 text-right">{formatearImporte(p.importe)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <span>Total ingresos</span>
        <span className="text-right">{formatearImporte(report.total_ingresos)}</span>
        <span>Total gastos</span>
        <span className="text-right">{formatearImporte(report.total_gastos)}</span>
        <span>Resultado del cierre</span>
        <span className="text-right">
          {report.resultado_cierre ? formatearImporte(report.resultado_cierre) : "—"}
        </span>
      </div>
    </div>
  );
}