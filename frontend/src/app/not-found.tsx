import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center p-6 text-center space-y-3">
      <h2 className="text-xl font-bold text-slate-900">404 - Página no encontrada</h2>
      <p className="text-xs text-slate-500 max-w-sm">
        La ruta solicitada no existe o ha sido reubicada en una versión reciente.
      </p>
      <Link
        href="/"
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-colors"
      >
        Volver al inicio
      </Link>
    </div>
  );
}
