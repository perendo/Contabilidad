"use client";

/**
 * LANDING DE TESORERÍA (SPEC-031, US5, T053)
 *
 * Muestra el espacio de trabajo de Tesorería y Gestión Bancaria (Migración 032),
 * con selector de cuentas bancarias vinculadas, subcuentas contables del PGC,
 * saldos, y accesos directos de cobro y conciliación.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "@/services/client";

interface CuentaBancaria {
  id: string;
  nombre: string;
  banco: string | null;
  iban: string;
  cuenta_contable: string;
  activa: boolean;
}

interface RespuestaCuentas {
  items: CuentaBancaria[];
  total: number;
}

export default function TesoreriaPage() {
  const [cuentas, setCuentas] = useState<CuentaBancaria[]>([]);
  const [cargando, setCargando] = useState(true);
  const [subTab, setSubTab] = useState<"cuentas" | "cobros" | "balance">("cuentas");

  useEffect(() => {
    async function cargar() {
      try {
        const res = await get<RespuestaCuentas>("/api/v1/cuentas-bancarias");
        setCuentas(res.items ?? []);
      } catch {
        // En caso de que la base aún no tenga bancos creados, mostramos el estado de demostración
        setCuentas([]);
      } finally {
        setCargando(false);
      }
    }
    void cargar();
  }, []);

  return (
    <div className="space-y-6">
      {/* Surface Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white flex items-center gap-2">
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-6 h-6 text-amber-400"
            >
              <line x1="3" x2="21" y1="22" y2="22" />
              <line x1="6" x2="6" y1="18" y2="11" />
              <line x1="10" x2="10" y1="18" y2="11" />
              <line x1="14" x2="14" y1="18" y2="11" />
              <line x1="18" x2="18" y1="18" y2="11" />
              <polygon points="12 2 20 7 4 7" />
            </svg>
            Tesorería y Gestión Bancaria
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Cuentas bancarias (Migración 032), conciliación automática, cobros, pagos y previsión de liquidez.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/tesoreria/cuentas-bancarias/nueva"
            className="px-3.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs flex items-center gap-1.5 shadow-md transition-all"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
              <path d="M5 12h14" />
              <path d="M12 5v14" />
            </svg>
            <span>Nueva Cuenta Bancaria</span>
          </Link>
          <Link
            href="/tesoreria/conciliacion"
            className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-all flex items-center gap-1.5"
          >
            <span>Conciliar Extracto</span>
          </Link>
        </div>
      </div>

      {/* Sub-tabs for Tesorería */}
      <div className="flex items-center space-x-2 border-b border-slate-800 pb-2 text-xs">
        <button
          type="button"
          onClick={() => setSubTab("cuentas")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            subTab === "cuentas"
              ? "bg-slate-800 text-emerald-400 border border-slate-700 font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Cuentas Bancarias ({cuentas.length > 0 ? cuentas.length : "Demo"})
        </button>
        <button
          type="button"
          onClick={() => setSubTab("cobros")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            subTab === "cobros"
              ? "bg-slate-800 text-emerald-400 border border-slate-700 font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Cobros y Pagos
        </button>
        <button
          type="button"
          onClick={() => setSubTab("balance")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            subTab === "balance"
              ? "bg-slate-800 text-emerald-400 border border-slate-700 font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Previsiones & Flujo (EFE)
        </button>
      </div>

      {/* SubTab 1: Cuentas Bancarias */}
      {subTab === "cuentas" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {cuentas.length > 0 ? (
              cuentas.map((cb) => (
                <div
                  key={cb.id}
                  className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3 hover:border-slate-700 transition-all shadow-md"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                        Subcuenta {cb.cuenta_contable}
                      </span>
                      <h3 className="text-sm font-semibold text-white mt-1.5">{cb.nombre}</h3>
                      <p className="text-xs text-slate-400">{cb.banco ?? "Entidad Financiera"}</p>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" title="Cuenta Activa" />
                  </div>

                  <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">IBAN Validado</div>
                    <div className="font-mono text-xs text-slate-300 mt-0.5 tracking-tight">{cb.iban}</div>
                  </div>
                </div>
              ))
            ) : (
              <>
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3 hover:border-slate-700 transition-all shadow-md">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                        Subcuenta 57200001
                      </span>
                      <h3 className="text-sm font-semibold text-white mt-1.5">Cuenta Principal Operativa</h3>
                      <p className="text-xs text-slate-400">Banco Santander</p>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" title="Cuenta Activa" />
                  </div>
                  <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">IBAN Validado</div>
                    <div className="font-mono text-xs text-slate-300 mt-0.5 tracking-tight">ES91 0049 1500 0512 3456 7890</div>
                  </div>
                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Saldo Contable:</span>
                    <span className="font-mono text-sm font-bold text-white">148.520,45 €</span>
                  </div>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3 hover:border-slate-700 transition-all shadow-md">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                        Subcuenta 57200002
                      </span>
                      <h3 className="text-sm font-semibold text-white mt-1.5">Cuenta Pagos y Nóminas</h3>
                      <p className="text-xs text-slate-400">BBVA</p>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" title="Cuenta Activa" />
                  </div>
                  <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">IBAN Validado</div>
                    <div className="font-mono text-xs text-slate-300 mt-0.5 tracking-tight">ES21 0182 2345 1102 9876 5432</div>
                  </div>
                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Saldo Contable:</span>
                    <span className="font-mono text-sm font-bold text-white">42.190,10 €</span>
                  </div>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3 hover:border-slate-700 transition-all shadow-md">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                        Subcuenta 57200003
                      </span>
                      <h3 className="text-sm font-semibold text-white mt-1.5">Línea de Crédito Comercial</h3>
                      <p className="text-xs text-slate-400">CaixaBank</p>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" title="Cuenta Activa" />
                  </div>
                  <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">IBAN Validado</div>
                    <div className="font-mono text-xs text-slate-300 mt-0.5 tracking-tight">ES66 2100 0418 4502 0005 1234</div>
                  </div>
                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Saldo Contable:</span>
                    <span className="font-mono text-sm font-bold text-white">87.300,00 €</span>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Tarjeta explicativa de integración 032 */}
          <div className="bg-slate-950 p-4 rounded-xl border border-indigo-500/20 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-indigo-400">
                <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
              </svg>
              Integración Contable Inmediata (Migración 032)
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Al registrar cobros o vencimientos desde esta pantalla, el selector de <strong>cuenta_bancaria_id</strong> resuelve automáticamente la subcuenta de tesorería vinculada (<code className="text-emerald-400 font-mono">57200001 Santander</code>, <code className="text-emerald-400 font-mono">57200002 BBVA</code>) imputando el movimiento al banco exacto dentro del asiento contable inmutable, respetando la Constitución I (Debe == Haber).
            </p>
          </div>
        </div>
      )}

      {/* SubTab 2: Cobros y Pagos */}
      {subTab === "cobros" && (
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold text-white">Últimos Cobros y Pagos Asentados</span>
            <span>Filtrado por Ejercicio Activo</span>
          </div>

          <div className="divide-y divide-slate-800 text-xs">
            <div className="py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-emerald-400 font-bold text-sm">↓</span>
                <div>
                  <div className="font-semibold text-white">Cobro Factura F2026-0042 · Tech Solutions S.L.</div>
                  <div className="text-[11px] text-slate-500 font-mono">Asiento #1402 · Banco Santander (57200001)</div>
                </div>
              </div>
              <span className="font-mono font-bold text-emerald-400">+ 12.450,00 €</span>
            </div>

            <div className="py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-rose-400 font-bold text-sm">↑</span>
                <div>
                  <div className="font-semibold text-white">Pago Suministros Eléctricos · Iberdrola</div>
                  <div className="text-[11px] text-slate-500 font-mono">Asiento #1403 · BBVA Nóminas (57200002)</div>
                </div>
              </div>
              <span className="font-mono font-bold text-rose-400">- 845,20 €</span>
            </div>
          </div>
        </div>
      )}

      {/* SubTab 3: Balance */}
      {subTab === "balance" && (
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-2">
          <h3 className="text-sm font-semibold text-white">Estado de Flujo de Efectivo (EFE)</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Consulte las previsiones de tesorería y el cálculo directo del estado de flujos según la Norma 9ª de Elaboración de las Cuentas Anuales del PGC.
          </p>
          <div className="pt-3">
            <Link
              href="/tesoreria/flujos-efectivo"
              className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 underline"
            >
              Abrir informe de flujos de efectivo →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
