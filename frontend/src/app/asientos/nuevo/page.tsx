"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import LineEditor, {
  type LineaMultilinea,
} from "../../../components/journal/line-editor";
import { ApiError } from "../../../components/treasury/api";
import { post } from "../../../services/client";

/**
 * Única pantalla de alta de asientos (SPEC-002 + SPEC-006, unificadas).
 *
 * Antes había dos: esta ruta creaba un borrador con `JournalEntryForm` y
 * `/contabilidad/asientos/nuevo` asentaba con `LineEditor`. La que estaba en el
 * mapa de superficies era la de borradores, de modo que un asiento creado desde
 * la navegación no aparecía en el libro diario, que solo lista POSTED/CANCELLED.
 *
 * Se conserva la vía borrador porque la baja lógica de documentos solo se admite
 * sobre un asiento en DRAFT (SPEC-030, FR-010).
 */
export default function NuevoAsientoPage() {
  const router = useRouter();
  const [fecha, setFecha] = useState("2026-05-01");
  const [concepto, setConcepto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  function lineasMotor(lineas: LineaMultilinea[]) {
    return lineas.map((l) => ({
      cuenta: l.cuentaCodigo,
      debe: l.debe || "0",
      haber: l.haber || "0",
      detalle: l.detalle,
      centro_coste_id: l.centroId || null,
    }));
  }

  function lineasBorrador(lineas: LineaMultilinea[]) {
    return lineas.map((l) => ({
      account_id: Number(l.cuentaId),
      debit: l.debe || "0",
      credit: l.haber || "0",
      detail: l.detalle || null,
    }));
  }

  async function lanzar(ruta: string, cuerpo: object) {
    setError(null);
    setGuardando(true);
    try {
      const creado = await post<{ id: string }>(ruta, cuerpo);
      router.push(`/asientos/${creado.id}`);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
      setGuardando(false);
    }
  }

  async function asentar(lineas: LineaMultilinea[]) {
    await lanzar("/api/v1/asientos", {
      fecha,
      concepto,
      lineas: lineasMotor(lineas),
    });
  }

  async function guardarBorrador(lineas: LineaMultilinea[]) {
    await lanzar("/api/v1/journal/entries", {
      fecha,
      concepto,
      lineas: lineasBorrador(lineas),
    });
  }

  return (
    <main className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Nuevo asiento multilínea</h1>
      <p className="text-sm text-gray-600 mb-4">
        Enter añade una fila, Tab navega, Ctrl+Supr elimina la fila activa. Las
        cuentas se eligen de la lista del PGC.
      </p>
      <div className="flex gap-3 mb-4">
        <label className="flex flex-col gap-1">
          Fecha
          <input
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
        <label className="flex flex-col gap-1 flex-1">
          Concepto
          <input
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {guardando && <p className="mb-4">Guardando…</p>}
      <LineEditor
        onGuardar={asentar}
        onGuardarBorrador={guardarBorrador}
        etiquetaGuardar="Asentar en el libro"
        guardando={guardando}
      />
    </main>
  );
}
