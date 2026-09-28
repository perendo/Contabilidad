"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { guardarSesion, type SesionIniciada } from "../../services/client";

interface EmpresaAccesible {
  company_id: number;
  nif: string;
  razon_social: string;
  role: string;
  is_default: boolean;
}

interface RespuestaLogin extends SesionIniciada {
  companies: EmpresaAccesible[];
}

/**
 * Pantalla de identificacion (SPEC-003, y SPEC-031 T021).
 *
 * `guardarSesion` escribe el token en los dos almacenes que hacen falta: en
 * `localStorage` para el encabezado `Authorization` del cliente, y en una cookie
 * `httpOnly` para que `src/middleware.ts` pueda hacer su redireccion optimista
 * (research D2).
 *
 * EL `Suspense` NO ES DECORATIVO: `useSearchParams` en una pagina que Next
 * prerenderiza hace fallar el build con "Error occurred prerendering page". Por
 * eso la parte que lee la query va en un hijo envuelto, y el padre la exporta.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-md p-6">Cargando…</main>}>
      <FormularioLogin />
    </Suspense>
  );
}

/** Destino de la redireccion posterior al login. */
function destinoDe(params: URLSearchParams): string {
  const bruto = params.get("next");
  // Solo rutas internas: un `?next=https://otro-sitio` seria una redireccion
  // abierta, y `//host` es una URL relativa al protocolo que tampoco vale.
  if (!bruto || !bruto.startsWith("/") || bruto.startsWith("//")) return "/";
  return bruto;
}

function FormularioLogin() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function entrar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const respuesta = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const cuerpo = (await respuesta.json().catch(() => ({}))) as
        | RespuestaLogin
        | { detail?: string };
      if (!respuesta.ok) {
        const detalle =
          typeof cuerpo === "object" && "detail" in cuerpo
            ? cuerpo.detail
            : null;
        throw new ApiError(
          respuesta.status,
          typeof detalle === "string" ? detalle : "Credenciales no válidas",
        );
      }
      guardarSesion(cuerpo as RespuestaLogin);
      router.push(destinoDe(params));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="mb-4 text-xl font-semibold">Iniciar sesión</h1>
      <form onSubmit={entrar} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          Correo electrónico
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border px-3 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          Contraseña
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border px-3 py-1"
          />
        </label>
        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={cargando}
          className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-blue-800"
        >
          {cargando ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </main>
  );
}
