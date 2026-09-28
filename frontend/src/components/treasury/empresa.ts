const CLAVE = "empresa_activa";

type Listener = (empresaId: string | null) => void;

const listeners = new Set<Listener>();

export function getEmpresaActiva(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(CLAVE);
}

export function setEmpresaActiva(empresaId: string | null): void {
  if (typeof window === "undefined") return;
  const limpio = empresaId?.trim();
  if (limpio) {
    window.localStorage.setItem(CLAVE, limpio);
  } else {
    window.localStorage.removeItem(CLAVE);
  }
  listeners.forEach((listener) => listener(getEmpresaActiva()));
}

export function suscribirEmpresa(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function cabecerasEmpresa(): Record<string, string> {
  const empresaId = getEmpresaActiva();
  return empresaId ? { "X-Empresa-Activa": empresaId } : {};
}
