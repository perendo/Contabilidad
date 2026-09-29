"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { cabecerasEmpresa } from "../../../components/treasury/empresa";
import { getToken } from "../../../services/client";

/**
 * Los tres formatos de extracto que acepta la API. La lista esta escrita aqui y
 * en `services/reconciliation/layouts.py::LAYOUTS`: son las dos caras de un
 * mismo catalogo, y el backend valida contra el suyo (422 `layout_desconocido`).
 * El guard `backend/tests/unit/test_extracto_layouts.py` comprueba que las dos
 * listas digan lo mismo.
 */
const LAYOUTS: { valor: string; etiqueta: string; ayuda: string; acepta: string }[] = [
  {
    valor: "norma_43_1919",
    etiqueta: "Norma 43/19",
    ayuda: "Fichero de ancho fijo que da el banco (100 caracteres por linea, .txt).",
    acepta: ".txt",
  },
  {
    valor: "csv_normalizado",
    etiqueta: "CSV normalizado",
    ayuda: "CSV con las columnas numero, fecha_operacion, fecha_valor, concepto, importe y signo.",
    acepta: ".csv",
  },
  {
    valor: "xlsx_bancario",
    etiqueta: "XLSX de banco (Santander y similares)",
    ayuda:
      "Hoja de calculo del area de clientes del banco. La cuenta se indica a mano: el XLSX trae el IBAN, no el codigo del plan.",
    acepta: ".xlsx,.xlsm",
  },
];

/** Extension de un nombre de fichero, en minusculas y sin puntos. */
function extension(nombre: string): string {
  const punto = nombre.lastIndexOf(".");
  return punto < 0 ? "" : nombre.slice(punto + 1).toLowerCase();
}

/** El layout cuyo `acepta` menciona la extension del fichero elegido, si lo hay. */
function layoutPorExtension(nombre: string): string | null {
  const ext = extension(nombre);
  if (!ext) return null;
  const encontrado = LAYOUTS.find((l) =>
    l.acepta
      .split(",")
      .map((a) => a.replace(/^\./, ""))
      .includes(ext),
  );
  return encontrado?.valor ?? null;
}

export default function ImportarExtractoPage() {
  const router = useRouter();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cuenta, setCuenta] = useState("");
  const [layout, setLayout] = useState("norma_43_1919");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  const ayuda = LAYOUTS.find((l) => l.valor === layout)?.ayuda ?? "";
  // El XLSX del banco no trae codigo de cuenta, solo el IBAN: sin este campo la
  // importacion se para con "La cuenta es obligatoria". Se avisa antes de subir.
  const faltaCuenta = layout === "xlsx_bancario" && !cuenta.trim();

  const elegirArchivo = (fichero: File | null) => {
    setArchivo(fichero);
    setError(null);
    setPreview(null);
    // El layout sigue al fichero: un `.xlsx` solo se puede importar como XLSX de
    // banco, y equivocarse de formato daba un error de ancho de linea que no
    // explicaba nada. Si el usuario luego cambia el desplegable, manda el desplegable.
    if (fichero) {
      const deducido = layoutPorExtension(fichero.name);
      if (deducido) setLayout(deducido);
    }
  };

  async function subir(evento: React.FormEvent) {
    evento.preventDefault();
    if (!archivo) return;
    setError(null);
    setCargando(true);
    try {
      const datos = new FormData();
      datos.append("file", archivo);
      datos.append("layout", layout);
      if (cuenta) datos.append("cuenta", cuenta);
      const cabeceras: Record<string, string> = { ...cabecerasEmpresa() };
      const token = getToken();
      if (token) cabeceras["Authorization"] = `Bearer ${token}`;
      const respuesta = await fetch("/api/v1/extractos", { method: "POST", headers: cabeceras, body: datos });
      const cuerpo = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok) {
        const detalle = (cuerpo as { detail?: unknown })?.detail;
        const msg = typeof detalle === "string" ? detalle : (detalle as { detail?: string })?.detail;
        throw new ApiError(respuesta.status, msg ?? "Error al importar");
      }
      setPreview(
        `Importado: ${cuerpo.n_movimientos} movimientos, del ${cuerpo.fecha_inicio} al ${cuerpo.fecha_fin}, saldo final ${cuerpo.saldo_final}`
      );
      router.push("/conciliacion");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-lg mx-auto">
      <h1 className="text-xl font-semibold mb-4">Importar extracto bancario</h1>
      <form onSubmit={subir} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          Fichero
          <input
            type="file"
            accept=".txt,.csv,.xlsx,.xlsm"
            onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Formato
          <select value={layout} onChange={(e) => setLayout(e.target.value)} className="border rounded px-2 py-1">
            {LAYOUTS.map((l) => (
              <option key={l.valor} value={l.valor}>
                {l.etiqueta}
              </option>
            ))}
          </select>
        </label>
        {ayuda && <p className="text-xs text-slate-500">{ayuda}</p>}
        <label className="flex flex-col gap-1">
          Cuenta 572 (código)
          <input
            value={cuenta}
            onChange={(e) => setCuenta(e.target.value)}
            className="border rounded px-3 py-1"
            placeholder="5720"
          />
        </label>
        {faltaCuenta && (
          <p className="text-amber-700 text-sm">
            El XLSX del banco trae el IBAN, no el código del plan. Indica aquí la
            cuenta 572 a la que corresponde ese IBAN.
          </p>
        )}
        {error && <p className="text-red-600">{error}</p>}
        {preview && <p className="text-emerald-700">{preview}</p>}
        <button
          type="submit"
          disabled={cargando || !archivo || faltaCuenta}
          className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
        >
          {cargando ? "Importando…" : "Importar"}
        </button>
      </form>
    </main>
  );
}
